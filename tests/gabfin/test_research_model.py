"""S4 provider-swappable model adapter: contract, budget, and secret hygiene.

Every test here runs without network access: a transport callable is injected
and the adapter never reads a dotenv file or a real credential store.
"""
import asyncio
import json
import logging

import pytest
from pydantic import ValidationError

from gabfin.research.model import (
    ModelConfig,
    ModelHttpRequest,
    ModelHttpResponse,
    ModelProviderError,
    OpenAICompatibleModel,
    load_model_config,
)
from gabfin.research.nodes import ModelReply, ModelRequest


KEY = 'synthetic-s4-secret-abcdef123456'
BASE = 'https://llm.example.test/v1'


def config(**kwargs):
    params = {'base_url': BASE, 'api_key': KEY, 'model': 'sim-model-1'}
    params.update(kwargs)
    return ModelConfig(**params)


def user_payload(obj):
    return ModelHttpResponse(200, json.dumps(obj).encode('utf-8'))


def completion(content, *, prompt_tokens=11, completion_tokens=7, model='sim-model-1',
               tool_calls=None):
    message = {'role': 'assistant', 'content': content}
    if tool_calls is not None:
        message['tool_calls'] = tool_calls
    return user_payload({
        'model': model,
        'choices': [{'index': 0, 'finish_reason': 'stop', 'message': message}],
        'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens},
    })


def tool_call(name, call_id='call_1'):
    return {'id': call_id, 'type': 'function',
            'function': {'name': name, 'arguments': '{}'}}


def run(model, request=None, dispatch=None):
    async def scenario():
        req = request or ModelRequest('technical', 'system text', 'user text', 100)
        return await model(req, dispatch or (lambda name, arguments: _noop(name, arguments)))
    return asyncio.run(scenario())


async def _noop(name, arguments):
    return {'evidence_id': 'e-1'}


def capture(calls):
    def transport(request: ModelHttpRequest) -> ModelHttpResponse:
        calls.append(request)
        return calls[-1].__class__ and user_payload({'unexpected': True})
    return transport


# ---------------------------------------------------------------- configuration


def test_load_model_config_reads_environment_explicitly(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', BASE)
    monkeypatch.setenv('LLM_API_KEY', KEY)
    monkeypatch.setenv('LLM_MODEL', 'sim-model-1')
    monkeypatch.setenv('LLM_TIMEOUT_SECONDS', '12')
    cfg = load_model_config()
    assert cfg.base_url == BASE
    assert cfg.api_key.get_secret_value() == KEY
    assert cfg.model == 'sim-model-1'
    assert cfg.timeout_seconds == 12


def test_load_model_config_does_not_auto_load_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('LLM_BASE_URL=https://leaked.example.test\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('LLM_BASE_URL', raising=False)
    monkeypatch.delenv('LLM_API_KEY', raising=False)
    with pytest.raises(ValidationError) as caught:
        load_model_config()
    assert 'LLM_BASE_URL' in str(caught.value)
    assert 'leaked.example.test' not in str(caught.value)


@pytest.mark.parametrize('missing', ['LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL'])
def test_missing_environment_fails_closed(monkeypatch, missing):
    monkeypatch.setenv('LLM_BASE_URL', BASE)
    monkeypatch.setenv('LLM_API_KEY', KEY)
    monkeypatch.setenv('LLM_MODEL', 'sim-model-1')
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(ValidationError) as caught:
        load_model_config()
    assert missing in str(caught.value)
    assert KEY not in str(caught.value)


def test_blank_environment_values_are_rejected(monkeypatch):
    monkeypatch.setenv('LLM_BASE_URL', BASE)
    monkeypatch.setenv('LLM_API_KEY', '   ')
    monkeypatch.setenv('LLM_MODEL', 'sim-model-1')
    with pytest.raises(ValidationError):
        load_model_config()


@pytest.mark.parametrize('url', [
    'http://llm.example.test/v1',
    'ftp://llm.example.test/v1',
    'https://user:password@llm.example.test/v1',
    f'https://llm.example.test/v1?key={KEY}',
    'https://llm.example.test/v1#frag',
    'not-a-url',
    'https://llm.example.test/v1/../../etc',
])
def test_unsafe_base_url_rejected_without_echoing(url):
    with pytest.raises(ValidationError) as caught:
        config(base_url=url)
    assert KEY not in str(caught.value)
    assert url not in str(caught.value)


def test_repr_and_dump_hide_key_and_endpoint(caplog):
    cfg = config()
    with caplog.at_level(logging.INFO):
        logging.getLogger('s4-model-test').info('%s %r', cfg, cfg)
    for output in (str(cfg), repr(cfg), cfg.model_dump_json(), repr(cfg.model_dump()),
                   caplog.text):
        assert KEY not in output
        assert BASE not in output


def test_config_rejects_invalid_timeout():
    with pytest.raises(ValidationError):
        config(timeout_seconds=0)
    with pytest.raises(ValidationError):
        config(timeout_seconds=100000)


def test_config_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ModelConfig(base_url=BASE, api_key=KEY, model='m', extra_option=True)


# ------------------------------------------------------------------- tool gates


def test_tool_definitions_only_for_whitelisted_role_tools():
    seen = []

    def transport(request):
        seen.append(json.loads(request.body))
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}))

    model = OpenAICompatibleModel(config(), transport=transport)
    run(model, ModelRequest('technical', 'sys', 'usr', 100))
    tools = seen[0]['tools']
    assert [t['function']['name'] for t in tools] == ['read_bars', 'compute_indicators',
                                                      'read_quote_snapshot']
    for tool in tools:
        assert tool['function']['parameters'] == {
            'type': 'object', 'properties': {}, 'additionalProperties': False}


def test_unknown_role_gets_no_tools_and_no_fabricated_capability():
    seen = []

    def transport(request):
        seen.append(json.loads(request.body))
        return completion(json.dumps({'role': 'other', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}))

    model = OpenAICompatibleModel(config(), transport=transport)
    run(model, ModelRequest('other', 'sys', 'usr', 100))
    assert 'tools' not in seen[0]


def test_tool_arguments_must_be_empty_object():
    seen = []

    def transport(request):
        seen.append(json.loads(request.body))
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}))

    model = OpenAICompatibleModel(config(), transport=transport)
    reply = run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert isinstance(reply, ModelReply)
    # The model reply is echoed back for the tool round trip.
    followup = seen[0]
    assert followup['messages'][0]['role'] == 'system'
    assert followup['messages'][1]['role'] == 'user'


def test_dispatch_receives_tool_name_and_arguments():
    calls = []

    def transport(request):
        payload = json.loads(request.body)
        if len(payload['messages']) == 2:
            return completion(None, tool_calls=[tool_call('read_bars')])
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}))

    async def dispatch(name, arguments):
        calls.append((name, arguments))
        return {'evidence_id': 'e-1'}

    model = OpenAICompatibleModel(config(), transport=transport)
    reply = run(model, ModelRequest('technical', 'sys', 'usr', 100), dispatch)
    assert calls == [('read_bars', {})]
    assert reply.output['role'] == 'technical'


def test_tool_not_in_whitelist_is_never_dispatched():
    calls = []

    def transport(request):
        payload = json.loads(request.body)
        if len(payload['messages']) == 2:
            return completion(None, tool_calls=[tool_call('submit_order')])
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}))

    async def dispatch(name, arguments):
        calls.append(name)
        return {}

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100), dispatch)
    assert calls == []
    # The provider-supplied tool name is not echoed; only the fixed reason is.
    assert caught.value.reason == 'tool_not_allowed'
    assert 'submit_order' not in str(caught.value)


def test_dispatch_failure_is_reported_without_leaking_payload():
    def transport(request):
        payload = json.loads(request.body)
        if len(payload['messages']) == 2:
            return completion(None, tool_calls=[tool_call('read_bars')])
        return completion('{}')

    async def dispatch(name, arguments):
        raise RuntimeError('internal detail with ' + KEY)

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100), dispatch)
    assert KEY not in str(caught.value)
    assert 'internal detail' not in str(caught.value)


# --------------------------------------------------------------------- budget


def test_tokens_accumulate_across_tool_rounds():
    def transport(request):
        payload = json.loads(request.body)
        if len(payload['messages']) == 2:
            return completion(None, prompt_tokens=10, completion_tokens=5,
                              tool_calls=[tool_call('read_bars')])
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}), prompt_tokens=20, completion_tokens=6)

    model = OpenAICompatibleModel(config(), transport=transport)
    reply = run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert reply.input_tokens == 30
    assert reply.output_tokens == 11
    assert reply.model_version == 'sim-model-1'


def test_max_tokens_never_exceeds_request_budget():
    seen = []

    def transport(request):
        payload = json.loads(request.body)
        seen.append(payload['max_tokens'])
        if len(payload['messages']) == 2:
            return completion(None, prompt_tokens=1, completion_tokens=1,
                              tool_calls=[tool_call('read_bars')])
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}), prompt_tokens=1, completion_tokens=1)

    model = OpenAICompatibleModel(config(), transport=transport)
    run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert seen == [100, 99]


def test_usage_missing_is_rejected():
    def transport(request):
        return user_payload({'model': 'sim-model-1',
                             'choices': [{'index': 0, 'finish_reason': 'stop',
                                          'message': {'role': 'assistant', 'content': '{}'}}]})

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert 'usage' in str(caught.value)


@pytest.mark.parametrize('usage', [
    {'prompt_tokens': 'many', 'completion_tokens': 5},
    {'prompt_tokens': 10, 'completion_tokens': -3},
    {'prompt_tokens': 10},
    {'completion_tokens': 5},
])
def test_invalid_usage_is_rejected(usage):
    def transport(request):
        return user_payload({'model': 'sim-model-1',
                             'choices': [{'index': 0, 'finish_reason': 'stop',
                                          'message': {'role': 'assistant', 'content': '{}'}}],
                             'usage': usage})

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError):
        run(model, ModelRequest('technical', 'sys', 'usr', 100))


def test_budget_exhaustion_reports_clear_error():
    """Output tokens are cumulative: the adapter stops once the budget is gone."""
    def transport(request):
        payload = json.loads(request.body)
        if len(payload['messages']) == 2:
            return completion(None, prompt_tokens=1, completion_tokens=1,
                              tool_calls=[tool_call('read_bars')])
        return completion(None, prompt_tokens=1, completion_tokens=1,
                          tool_calls=[tool_call('read_bars', 'c2')])

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 2))
    assert caught.value.reason == 'budget_exhausted'


def test_zero_budget_never_calls_the_provider():
    calls = []

    def transport(request):
        calls.append(request)
        return completion('{}')

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 0))
    assert caught.value.reason == 'budget_exhausted'
    assert calls == []


def test_tool_loop_is_bounded():
    rounds = []

    def transport(request):
        rounds.append(json.loads(request.body))
        return completion(None, prompt_tokens=1, completion_tokens=1,
                          tool_calls=[tool_call('read_bars', 'c1')])

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert caught.value.reason == 'tool_loop_exhausted'
    assert len(rounds) == 8


# ---------------------------------------------------------------- bad responses


@pytest.mark.parametrize('content', ['not json', '```json\n{"a":1}\n```', '[]', '"text"', '123',
                                     ''])
def test_non_object_content_rejected(content):
    def transport(request):
        return completion(content)

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError):
        run(model, ModelRequest('technical', 'sys', 'usr', 100))


def test_json_fence_is_not_accepted():
    def transport(request):
        return completion('```json\n{"role": "technical"}\n```')

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError):
        run(model, ModelRequest('technical', 'sys', 'usr', 100))


def test_empty_choices_rejected():
    def transport(request):
        return user_payload({'model': 'sim-model-1', 'choices': [],
                             'usage': {'prompt_tokens': 1, 'completion_tokens': 1}})

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError):
        run(model, ModelRequest('technical', 'sys', 'usr', 100))


def test_non_json_body_rejected():
    def transport(request):
        return ModelHttpResponse(200, b'<html>gateway</html>')

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert 'gateway' not in str(caught.value)


def test_http_error_status_is_reported_without_body():
    def transport(request):
        return ModelHttpResponse(401, json.dumps({'error': {'message': KEY}}).encode())

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert KEY not in str(caught.value)
    assert caught.value.status == 401
    assert '401' in str(caught.value)


def test_redirect_response_is_blocked():
    def transport(request):
        return ModelHttpResponse(302, b'')

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert 'redirect' in str(caught.value).lower()


def test_transport_exception_is_wrapped_without_details():
    def transport(request):
        raise OSError('connection failed to https://llm.example.test/v1 with ' + KEY)

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert KEY not in str(caught.value)
    assert 'llm.example.test' not in str(caught.value)


# -------------------------------------------------------------- secret hygiene


def test_request_headers_carry_key_but_errors_do_not():
    seen = []

    def transport(request):
        seen.append(request)
        return ModelHttpResponse(500, b'boom')

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert seen[0].headers['Authorization'] == f'Bearer {KEY}'
    assert KEY not in str(caught.value)


def test_request_body_never_contains_the_api_key():
    seen = []

    def transport(request):
        seen.append(request.body)
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}))

    model = OpenAICompatibleModel(config(), transport=transport)
    run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert KEY.encode() not in seen[0]


def test_error_message_never_leaks_url_or_payload():
    def transport(request):
        return ModelHttpResponse(400, json.dumps({'error': 'bad', 'url': BASE,
                                                  'key': KEY}).encode())

    model = OpenAICompatibleModel(config(), transport=transport)
    with pytest.raises(ModelProviderError) as caught:
        run(model, ModelRequest('technical', 'sys', 'usr', 100))
    message = str(caught.value)
    assert KEY not in message
    assert BASE not in message


def test_model_version_tracks_the_served_response_model():
    """The reported version is the model the provider actually served."""
    def transport(request):
        return completion(json.dumps({'role': 'technical', 'snapshot_id': 's', 'findings': [],
                                      'missing_data': []}), model='served-model-2026-11-27')

    model = OpenAICompatibleModel(config(), transport=transport)
    reply = run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert reply.model_version == 'served-model-2026-11-27'


def test_model_version_falls_back_to_the_configured_model():
    def transport(request):
        return user_payload({
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant',
                                     'content': '{"role": "technical"}'}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1}})

    model = OpenAICompatibleModel(config(), transport=transport)
    reply = run(model, ModelRequest('technical', 'sys', 'usr', 100))
    assert reply.model_version == 'sim-model-1'


def test_model_error_reason_is_stable_allowlist():
    """Every provider failure maps to a fixed reason token."""
    from gabfin.research import model as model_module

    allowed = getattr(model_module, 'REASONS', None)
    if allowed is not None:
        assert all(isinstance(item, str) for item in allowed)


# ----------------------------------------------------------------- integration


def test_adapter_drives_the_unmodified_research_runtime():
    """The adapter satisfies the nodes.ModelRequest/ModelReply contract."""
    from pathlib import Path
    from uuid import UUID

    from gabfin.research.nodes import ResearchRuntime

    root = Path(__file__).resolve().parents[2]
    snapshot = UUID('77777777-7777-4777-8777-777777777777')
    evidence = '88888888-8888-4888-8888-888888888888'
    seen = []

    def transport(request):
        payload = json.loads(request.body)
        seen.append(payload)
        if len(payload['messages']) == 2:
            return completion(None, prompt_tokens=9, completion_tokens=3,
                              tool_calls=[tool_call('read_bars')])
        return completion(json.dumps({
            'role': 'technical', 'snapshot_id': str(snapshot),
            'findings': [{'text': 'Trend intact', 'evidence_id': evidence}],
            'missing_data': []}), prompt_tokens=12, completion_tokens=8)

    async def read_bars(arguments):
        return {'evidence_id': evidence, 'bars': []}

    model = OpenAICompatibleModel(config(), transport=transport)
    runtime = ResearchRuntime(root / 'config/agents', root / 'schemas/research',
                              model=model, tools={'read_bars': read_bars},
                              snapshot_evidence={snapshot: frozenset({evidence})})
    payload = {
        'snapshot_id': str(snapshot), 'as_of': '2026-11-27T00:00:00Z',
        'data_quality': ['delayed'],
        'context': {'bars': [], 'indicators': []},
    }
    result = asyncio.run(runtime.run('technical', payload))
    assert result['status'] == 'success'
    assert result['report']['snapshot_id'] == str(snapshot)
    # Only the role's whitelisted tools are offered to the provider.
    assert [tool['function']['name'] for tool in seen[0]['tools']] == [
        'read_bars', 'compute_indicators', 'read_quote_snapshot']
    # The tool round trip used the shrinking max_tokens budget.
    assert seen[0]['max_tokens'] == 4000
    assert seen[1]['max_tokens'] == 4000 - 3
    record = result['audit'][-1]
    assert record.execution_result.value == 'success'
    assert record.model_version == 'sim-model-1'


def test_runtime_tool_denial_is_not_masked_by_the_adapter():
    """A runtime permission denial must reach the runtime, not be swallowed."""
    from pathlib import Path
    from uuid import UUID

    from gabfin.research.nodes import ResearchRuntime

    root = Path(__file__).resolve().parents[2]
    snapshot = UUID('99999999-9999-4999-8999-999999999999')

    def transport(request):
        payload = json.loads(request.body)
        if len(payload['messages']) == 2:
            return completion(None, tool_calls=[tool_call('read_bars')])
        return completion(json.dumps({'role': 'technical', 'snapshot_id': str(snapshot),
                                      'findings': [], 'missing_data': []}))

    model = OpenAICompatibleModel(config(), transport=transport)
    runtime = ResearchRuntime(root / 'config/agents', root / 'schemas/research',
                              model=model, tools={},
                              snapshot_evidence={snapshot: frozenset()})
    payload = {
        'snapshot_id': str(snapshot), 'as_of': '2026-11-27T00:00:00Z',
        'data_quality': ['delayed'],
        'context': {'bars': [], 'indicators': []},
    }
    result = asyncio.run(runtime.run('technical', payload))
    # The runtime decided the denial; the adapter did not convert it into a
    # provider fault or invent a successful report.
    assert result['status'] == 'invalid'
    assert result['report'] is None
    assert len(result['audit']) == 1
    reasons = result['audit'][-1].reasons
    assert any('Tool unavailable' in reason for reason in reasons)
    assert KEY not in ' '.join(reasons)

