"""Exercise the compiled graph and its permission boundary without an LLM API."""
import asyncio
from pathlib import Path
from uuid import UUID

import pytest

from gabfin.research.nodes import ModelReply, ResearchRuntime, build_research_graph

ROOT = Path(__file__).resolve().parents[2]
SNAP = UUID('22222222-2222-4222-8222-222222222222')
EV = '33333333-3333-4333-8333-333333333333'


def payload():
    return {'snapshot_id': str(SNAP), 'as_of': '2026-11-27T00:00:00Z',
            'data_quality': ['delayed'], 'context': {
                'observations': [{'evidence_id': EV, 'text': 'AAPL volume observation'}],
                'bars': [], 'indicators': [],
                'account': {'equity': '100000', 'evidence_id': EV, 'position_count': 0, 'max_weight': 0},
                'limits': {'per_trade_risk': '0.01', 'daily_loss': '0.02'}}}


def output(role):
    return {'role': role, 'snapshot_id': str(SNAP),
            'findings': [{'text': 'Watch concentration', 'evidence_id': EV}], 'missing_data': []}


def runtime(model, tools=None):
    return ResearchRuntime(ROOT / 'config/agents', ROOT / 'schemas/research',
                           model=model, tools=tools or {}, snapshot_evidence={SNAP: frozenset({EV})})


def test_graph_runs_three_isolated_roles():
    calls = []
    async def model(request, tools):
        calls.append(request.role)
        assert 'output' not in request.user
        return ModelReply(output(request.role), 20, 30, 'fixture')
    rt = runtime(model)
    result = asyncio.run(build_research_graph(rt).ainvoke({'payload': payload()}))
    assert calls == ['discovery', 'technical', 'portfolio']
    assert set(result['reports']) == set(calls)
    assert all(r.execution_result.value == 'success' for r in result['audit'])


@pytest.mark.parametrize('role', ['discovery', 'technical', 'portfolio'])
def test_forbidden_tool_never_executes(role):
    executed = []
    async def dangerous(args):
        executed.append(args)
    async def model(request, tools):
        await tools('submit_order', {})
        return ModelReply(output(request.role), 1, 1, 'fixture')
    rt = runtime(model, {'submit_order': dangerous})
    result = asyncio.run(rt.run(role, payload()))
    assert result['status'] == 'invalid'
    assert executed == []
    assert result['audit'][-1].execution_result.value == 'tool_forbidden'


def test_invalid_schema_retries_then_stops_graph():
    calls = []
    async def model(request, tools):
        calls.append(request.role)
        return ModelReply({'order': 'BUY'}, 1, 1, 'fixture')
    rt = runtime(model)
    result = asyncio.run(build_research_graph(rt).ainvoke({'payload': payload()}))
    assert calls == ['discovery', 'discovery']
    assert result['status'] == 'invalid'
    assert not result['reports']


def test_broken_reference_rejected():
    async def model(request, tools):
        data = output(request.role)
        data['findings'][0]['evidence_id'] = '44444444-4444-4444-8444-444444444444'
        return ModelReply(data, 1, 1, 'fixture')
    result = asyncio.run(runtime(model).run('technical', payload()))
    assert result['status'] == 'invalid'
    assert result['audit'][-1].execution_result.value == 'snapshot_reference_broken'


def test_invalid_input_does_not_call_model():
    async def model(request, tools):
        pytest.fail('invalid input reached model')
    with pytest.raises(ValueError):
        asyncio.run(runtime(model).run('technical', {'snapshot_id': 'bad'}))


def test_success_has_stable_cache_key_and_strict_prompt():
    async def model(request, tools):
        return ModelReply(output(request.role), 1, 1, 'fixture')
    rt = runtime(model)
    a = asyncio.run(rt.run('technical', payload()))
    b = asyncio.run(rt.run('technical', payload()))
    assert a['cache_key'] == b['cache_key']
    bad = payload()
    bad['context'].pop('indicators')
    with pytest.raises(ValueError):
        asyncio.run(rt.run('technical', bad))


def test_token_budget_accumulates_across_retries():
    calls = []
    async def model(request, tools):
        calls.append(request)
        return ModelReply({'bad': True}, 11000, 10, 'fixture')
    result = asyncio.run(runtime(model).run('technical', payload()))
    assert len(calls) == 2
    assert result['audit'][-1].execution_result.value == 'output_schema_invalid'
    assert any('input tokens' in reason for reason in result['audit'][-1].reasons)


def test_allowed_tool_runs_through_guard():
    calls = []
    async def read_bars(args):
        calls.append(args)
        return {'evidence_id': EV}
    async def model(request, tools):
        assert (await tools('read_bars', {'symbol': 'AAPL'}))['evidence_id'] == EV
        return ModelReply(output(request.role), 1, 1, 'fixture')
    result = asyncio.run(runtime(model, {'read_bars': read_bars}).run('technical', payload()))
    assert result['status'] == 'success'
    assert calls == [{'symbol': 'AAPL'}]


def test_wrong_role_in_output_rejected():
    async def model(request, tools):
        return ModelReply(output('discovery'), 1, 1, 'fixture')
    result = asyncio.run(runtime(model).run('technical', payload()))
    assert result['status'] == 'invalid'


def test_wrong_snapshot_in_output_rejected():
    async def model(request, tools):
        data = output(request.role)
        data['snapshot_id'] = '55555555-5555-4555-8555-555555555555'
        return ModelReply(data, 1, 1, 'fixture')
    result = asyncio.run(runtime(model).run('technical', payload()))
    assert result['status'] == 'invalid'


def test_provider_failure_stops_without_retrying_unknown_usage():
    calls = []
    async def model(request, tools):
        calls.append(request)
        raise RuntimeError('usage unavailable after provider request')
    result = asyncio.run(runtime(model).run('technical', payload()))
    assert result['status'] == 'invalid'
    assert len(calls) == 1


def test_deadline_cancels_model():
    async def model(request, tools):
        await asyncio.sleep(2)
        return ModelReply(output(request.role), 1, 1, 'fixture')
    rt = runtime(model)
    card = rt.cards['technical']
    rt.cards['technical'] = card.model_copy(update={
        'budget': card.budget.model_copy(update={'deadline_seconds': 1})})
    result = asyncio.run(rt.run('technical', payload()))
    assert result['status'] == 'invalid'
    assert len(result['audit']) == 1
    assert 'Research deadline exceeded' in result['audit'][-1].reasons


def test_prompt_version_changes_cache_key():
    async def model(request, tools):
        return ModelReply(output(request.role), 1, 1, 'fixture')
    rt = runtime(model)
    a = asyncio.run(rt.run('technical', payload()))
    card = rt.cards['technical']
    rt.cards['technical'] = card.model_copy(update={
        'prompt': card.prompt.model_copy(update={'version': 2})})
    b = asyncio.run(rt.run('technical', payload()))
    assert a['cache_key'] != b['cache_key']


def test_unknown_snapshot_does_not_call_model():
    async def model(request, tools):
        pytest.fail('unknown snapshot reached model')
    data = payload()
    data['snapshot_id'] = '55555555-5555-4555-8555-555555555555'
    with pytest.raises(ValueError):
        asyncio.run(runtime(model).run('technical', data))
