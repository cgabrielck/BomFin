"""Research production wiring: immutable local tools, snapshots and durable checks."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from gabfin.research.nodes import ModelReply

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)


def test_service_runs_three_roles_with_durable_frozen_tools(tmp_path):
    from gabfin.research.service import ResearchService
    from gabfin.research.store import ResearchStore
    evidence = str(uuid4())
    context = {'observations': [{'evidence_id': evidence, 'text': 'recorded observation'}],
               'bars': [], 'indicators': [],
               'account': {'equity': '1000', 'evidence_id': evidence, 'position_count': 0, 'max_weight': 0},
               'limits': {'per_trade_risk': '0.01', 'daily_loss': '0.02'},
               'symbols': ['AAPL'], 'quote': {}, 'massive_snapshot': {}}
    store = ResearchStore(tmp_path / 'research.sqlite')
    snapshot = store.get_snapshot(store.create_snapshot(as_of=NOW, context=context, data_quality=['fixture'],
                                     evidence_ids=frozenset({evidence})))
    calls = []
    async def model(request, dispatch):
        name = {'discovery': 'read_observations', 'technical': 'read_bars', 'portfolio': 'read_account'}[request.role]
        data = await dispatch(name, {})
        calls.append((request.role, data))
        return ModelReply({'role': request.role, 'snapshot_id': str(snapshot['snapshot_id']),
                           'findings': [{'text': 'fixture finding', 'evidence_id': evidence}], 'missing_data': []},
                          10, 10, 'fixture-v1')
    context['observations'].clear()
    service = ResearchService(store, model=model, roles_dir=ROOT/'config/agents', schema_dir=ROOT/'schemas/research')
    result = asyncio.run(service.run(UUID(str(snapshot['snapshot_id']))))
    assert result['status'] == 'success'
    assert len(result['reports']) == 3
    assert calls[0][1][0]['evidence_id'] == evidence
    checks = ResearchStore(tmp_path / 'research.sqlite').checks(UUID(str(snapshot['snapshot_id'])))
    assert len(checks) == 3
    assert all(check.model_version == 'fixture-v1' and check.prompt_version == 1 for check in checks)


def test_tool_arguments_cannot_switch_snapshot_or_symbol(tmp_path):
    from gabfin.research.tools import SnapshotTools
    context = {'bars': [{'close': '10'}]}
    tools = SnapshotTools(context).mapping()
    with pytest.raises(ValueError):
        asyncio.run(tools['read_bars']({'symbol': 'OTHER'}))
    first = asyncio.run(tools['read_bars']({}))
    first[0]['close'] = '99'
    assert asyncio.run(tools['read_bars']({}))[0]['close'] == '10'


def test_capture_roundtrip_can_render_real_snapshot_prompts(tmp_path):
    from gabfin.research.capture import SnapshotCapture
    from gabfin.research.service import ResearchService
    from gabfin.research.store import ResearchStore
    from gabfin.indicators.inputs import PriceBar
    from datetime import timedelta
    from decimal import Decimal
    class Bars:
        def coverage_of(self, timeframe):
            return 'sip'
        def bars(self, instrument_id, timeframe):
            return [PriceBar(event_at=NOW-timedelta(days=40-i), open=Decimal(100+i),
                             high=Decimal(102+i), low=Decimal(99+i), close=Decimal(101+i), volume=Decimal(1000))
                    for i in range(35)]
    from gabfin.contracts.market import Timeframe
    store = ResearchStore(tmp_path/'capture.sqlite')
    snapshot = SnapshotCapture(store, bars=Bars(),
        observations=lambda cutoff: [{'text': 'published observation', 'release_date': '2026-11-26'}],
        account=lambda: {'equity':'1000', 'position_count':0, 'max_weight':0},
        limits=lambda: {'per_trade_risk':'0.01', 'daily_loss':'0.02'}).capture(
            instrument_id=uuid4(), symbol='AAPL', timeframe=Timeframe(count=1, unit='trading_day'), as_of=NOW)
    identifier = UUID(str(snapshot['snapshot_id']))
    async def model(request, dispatch):
        assert 'AAPL' in request.user if request.role == 'technical' else True
        return ModelReply({'role': request.role, 'snapshot_id': str(identifier),
                           'findings': [], 'missing_data':['fixture model; no recommendation']}, 1, 1, 'fixture')
    result = asyncio.run(ResearchService(store, model=model, roles_dir=ROOT/'config/agents',
                                        schema_dir=ROOT/'schemas/research').run(identifier))
    assert result['status'] == 'success'
    assert len(store.checks(identifier)) == 3


def test_http_adapter_tool_roundtrip_reaches_durable_audit(tmp_path):
    import json
    from gabfin.research.model import ModelConfig, OpenAICompatibleModel, ModelHttpResponse
    from gabfin.research.service import ResearchService
    from gabfin.research.store import ResearchStore
    store = ResearchStore(tmp_path/'http.sqlite')
    snapshot = store.get_snapshot(store.create_snapshot(as_of=NOW, context={'observations': []},
                               data_quality=[], evidence_ids=frozenset()))
    outbound = []
    def transport(request):
        body = json.loads(request.body)
        outbound.append(body)
        if len(outbound) == 1:
            message = {'role':'assistant', 'content':None, 'tool_calls':[
                {'id':'call_1', 'type':'function', 'function':{'name':'read_observations','arguments':'{}'}}]}
        else:
            assert body['messages'][-1]['role'] == 'tool'
            message = {'role':'assistant', 'content':json.dumps({'role':'discovery',
                'snapshot_id':str(snapshot['snapshot_id']), 'findings':[], 'missing_data':['No observations']})}
        return ModelHttpResponse(200, json.dumps({'model':'fixture-http', 'choices':[{'message':message}],
            'usage':{'prompt_tokens':7,'completion_tokens':5}}).encode())
    model = OpenAICompatibleModel(ModelConfig(base_url='https://example.test/v1', api_key='fixture',
                                               model='fixture'), transport=transport)
    result = asyncio.run(ResearchService(store, model=model, roles_dir=ROOT/'config/agents',
        schema_dir=ROOT/'schemas/research').run(UUID(str(snapshot['snapshot_id'])), role='discovery'))
    assert result['status'] == 'success'
    assert len(outbound) == 2
    assert outbound[1]['max_tokens'] == outbound[0]['max_tokens'] - 5
    assert store.checks(UUID(str(snapshot['snapshot_id'])))[-1].model_version == 'fixture-http'


def test_capture_does_not_substitute_vintage_dates_for_release_date(tmp_path):
    from gabfin.research.capture import SnapshotCapture
    from gabfin.research.store import ResearchStore
    from gabfin.contracts.market import Timeframe
    class Bars:
        def bars(self, instrument_id, timeframe):
            return []
    capture = SnapshotCapture(ResearchStore(tmp_path/'date.sqlite'), bars=Bars(),
        observations=lambda cutoff: [{'text':'not an actual release date', 'realtime_start':'2026-11-01'}])
    with pytest.raises(ValueError, match='release'):
        capture.capture(instrument_id=uuid4(), symbol='AAPL',
                        timeframe=Timeframe(count=1, unit='trading_day'), as_of=NOW)


def test_capture_never_uses_live_indicator_plane_for_historical_snapshot(tmp_path):
    from gabfin.research.capture import SnapshotCapture
    from gabfin.research.store import ResearchStore
    from gabfin.contracts.market import Timeframe
    class Bars:
        def bars(self, instrument_id, timeframe):
            return []
        def coverage_of(self, timeframe):
            return 'sip'
    class LivePlane:
        def series(self, *args):
            pytest.fail('Live plane can include bars outside the frozen snapshot')
    snapshot = SnapshotCapture(ResearchStore(tmp_path/'frozen.sqlite'), bars=Bars(),
        indicators=LivePlane()).capture(instrument_id=uuid4(), symbol='AAPL',
        timeframe=Timeframe(count=1, unit='trading_day'), as_of=NOW)
    assert snapshot['context']['indicators'] == []


def test_multi_day_bar_does_not_finalize_after_one_day():
    from datetime import timedelta
    from gabfin.research.capture import bar_end
    from gabfin.contracts.market import Timeframe
    with pytest.raises(ValueError, match='calendar'):
        bar_end(NOW, Timeframe(count=5, unit='trading_day'))


def test_capture_rejects_invalid_release_date(tmp_path):
    from gabfin.research.capture import SnapshotCapture
    from gabfin.research.store import ResearchStore
    from gabfin.contracts.market import Timeframe
    class Bars:
        def bars(self, instrument_id, timeframe):
            return []
    capture = SnapshotCapture(ResearchStore(tmp_path/'invalid-date.sqlite'), bars=Bars(),
        observations=lambda cutoff: [{'text':'invalid date', 'release_date':'0000-00-00'}])
    with pytest.raises(ValueError):
        capture.capture(instrument_id=uuid4(), symbol='AAPL',
                        timeframe=Timeframe(count=1, unit='trading_day'), as_of=NOW)


def test_model_adapter_stops_before_second_round_when_input_budget_spent():
    import json
    from gabfin.research.model import ModelConfig, OpenAICompatibleModel, ModelHttpResponse
    from gabfin.research.nodes import ModelRequest
    calls = []
    def transport(request):
        calls.append(request)
        return ModelHttpResponse(200, json.dumps({'model':'fixture','choices':[{'message':{'content':None,
            'tool_calls':[{'id':'call1','type':'function','function':{'name':'read_bars','arguments':'{}'}}]}}],
            'usage':{'prompt_tokens':20000,'completion_tokens':1}}).encode())
    async def dispatch(name, arguments):
        return []
    model = OpenAICompatibleModel(ModelConfig(base_url='https://example.test/v1', api_key='fixture', model='fixture'), transport=transport)
    with pytest.raises(Exception):
        asyncio.run(model(ModelRequest('technical','system','user',100), dispatch))
    assert len(calls) == 1


def test_capture_refuses_future_quote_snapshot_as_of(tmp_path):
    from gabfin.research.capture import SnapshotCapture
    from gabfin.research.store import ResearchStore
    from gabfin.contracts.market import Timeframe
    class Bars:
        def bars(self, instrument_id, timeframe):
            return []
    capture = SnapshotCapture(ResearchStore(tmp_path/'future.sqlite'), bars=Bars(),
        quote=lambda: {'as_of':'2027-01-01T00:00:00Z', 'bid':'100'})
    with pytest.raises(ValueError):
        capture.capture(instrument_id=uuid4(), symbol='AAPL',
                        timeframe=Timeframe(count=1, unit='trading_day'), as_of=NOW)


def test_tool_missing_data_is_explicit():
    from gabfin.research.tools import SnapshotTools
    with pytest.raises(ValueError, match='unavailable'):
        asyncio.run(SnapshotTools({}).mapping()['read_account']({}))


def test_service_persists_broken_evidence_reference(tmp_path):
    from gabfin.research.service import ResearchService
    from gabfin.research.store import ResearchStore
    store = ResearchStore(tmp_path/'research.sqlite')
    snapshot = store.get_snapshot(store.create_snapshot(as_of=NOW, context={'observations': []},
                                     data_quality=[], evidence_ids=frozenset()))
    async def model(request, dispatch):
        return ModelReply({'role': 'discovery', 'snapshot_id': str(snapshot['snapshot_id']),
                           'findings': [{'text': 'invented', 'evidence_id': str(uuid4())}],
                           'missing_data': []}, 1, 1, 'fixture')
    service = ResearchService(store, model=model, roles_dir=ROOT/'config/agents', schema_dir=ROOT/'schemas/research')
    result = asyncio.run(service.run(UUID(str(snapshot['snapshot_id'])), role='discovery'))
    assert result['status'] == 'invalid'
    checks = store.checks(UUID(str(snapshot['snapshot_id'])))
    assert checks and all(check.execution_result.value == 'snapshot_reference_broken' for check in checks)


def test_service_persists_forbidden_attempt_and_never_executes(tmp_path):
    from gabfin.research.service import ResearchService
    from gabfin.research.store import ResearchStore
    store = ResearchStore(tmp_path/'research.sqlite')
    snapshot = store.get_snapshot(store.create_snapshot(as_of=NOW, context={'observations': []},
                                     data_quality=[], evidence_ids=frozenset()))
    async def model(request, dispatch):
        await dispatch('submit_order', {})
        pytest.fail('forbidden tool returned')
    service = ResearchService(store, model=model, roles_dir=ROOT/'config/agents', schema_dir=ROOT/'schemas/research')
    result = asyncio.run(service.run(UUID(str(snapshot['snapshot_id'])), role='discovery'))
    assert result['status'] == 'invalid'
    assert store.checks(UUID(str(snapshot['snapshot_id'])))[-1].execution_result.value == 'tool_forbidden'


def test_audit_write_failure_prevents_success(tmp_path):
    from gabfin.research.service import ResearchService
    from gabfin.research.store import ResearchStore
    evidence = str(uuid4())
    store = ResearchStore(tmp_path/'research.sqlite')
    snapshot = store.get_snapshot(store.create_snapshot(as_of=NOW, context={'observations': []}, data_quality=[],
                                     evidence_ids=frozenset({evidence})))
    async def model(request, dispatch):
        return ModelReply({'role': 'discovery', 'snapshot_id': str(snapshot['snapshot_id']),
                           'findings': [], 'missing_data': ['No observations']}, 1, 1, 'fixture')
    def fail(record):
        raise OSError('disk failure')
    store.append_check = fail
    service = ResearchService(store, model=model, roles_dir=ROOT/'config/agents', schema_dir=ROOT/'schemas/research')
    with pytest.raises(OSError):
        asyncio.run(service.run(UUID(str(snapshot['snapshot_id'])), role='discovery'))
