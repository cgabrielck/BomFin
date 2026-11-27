from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest

NOW = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)


class SDK:
    RTH = 'RTH'
    ETH = 'ETH'
    K_1M = 'K_1M'
    NONE = 'NONE'
    FIELDS = ['time', 'open', 'high', 'low', 'close']


class QuoteContext:
    def __init__(self):
        self.closed = False
        self.history_calls = []
        self.quota_calls = 0

    def get_market_state(self, codes):
        assert codes == ['US.AAPL']
        return 0, [{'code': 'US.AAPL', 'market_state': 'PRE_MARKET_BEGIN', 'private': 'PRIVATE'}]

    def get_history_kl_quota(self, *, get_detail):
        assert get_detail is False
        self.quota_calls += 1
        return 0, (5 if self.quota_calls == 1 else 6, 295 if self.quota_calls == 1 else 294, [{'private': 'PRIVATE'}])

    def request_history_kline(self, code, **kwargs):
        assert code == 'US.AAPL'
        assert kwargs == dict(start='2026-11-24', end='2026-11-24', ktype='K_1M', autype='NONE',
                              fields=SDK.FIELDS, max_count=2, page_req_key=None,
                              session=kwargs['session'], extended_time=kwargs['session'] == 'ETH')
        self.history_calls.append(kwargs['session'])
        clock = '09:30:00' if kwargs['session'] == 'RTH' else '04:00:00'
        return 0, [dict(code=code, time_key='2026-11-24 ' + clock,
                        open=100, high=102, low=99, close=101, private='PRIVATE')], b'PRIVATE'

    def close(self):
        self.closed = True


def test_two_bounded_history_pages_without_subscription_or_pagination():
    from gabfin.providers.futu.history import inspect_history

    context = QuoteContext()
    result = inspect_history(context, SDK, checked_at=NOW)
    assert result['errors'] == [] and result['cleanup'] == 'closed' and context.closed
    assert result['requested_date'] == '2026-11-24'
    assert result['quota_before'] == {'used': 5, 'remaining': 295}
    assert result['quota_after'] == {'used': 6, 'remaining': 294}
    assert context.history_calls == ['RTH', 'ETH'] and context.quota_calls == 2
    assert [r['status'] for r in result['requests']] == ['available', 'available']
    assert [r['bars'][0]['clock_window'] for r in result['requests']] == ['RTH', 'PRE']
    assert all(r['has_more'] for r in result['requests'])
    assert result['live_rights'] == 'unverified' and 'PRIVATE' not in str(result)


def run_child(tmp_path, payload):
    from gabfin.providers.futu.runner import run_probe

    script = tmp_path / 'child.py'
    script.write_text('import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text('
                      + repr(json.dumps(payload)) + ')', encoding='utf-8')
    return run_probe(Path(sys.executable), host='127.0.0.1', port=11111,
                     timeout=90, operation='history_smoke', _worker=script)


def test_history_result_crosses_parent_process_boundary(tmp_path):
    from gabfin.providers.futu.history import inspect_history

    payload = {'status': 'ok', 'metadata': inspect_history(QuoteContext(), SDK, checked_at=NOW)}
    assert run_child(tmp_path, payload) == payload


@pytest.mark.parametrize('quota', [(0, 0), (True, 5), (-1, 5), (5, None)])
def test_unavailable_quota_stops_history_and_preserves_final_sample(quota):
    from gabfin.providers.futu.history import inspect_history, validate_smoke

    context = QuoteContext()
    context.get_history_kl_quota = lambda **kwargs: (0, (*quota, []))
    result = inspect_history(context, SDK, checked_at=NOW)
    assert not context.history_calls and context.closed
    assert all(r['status'] == 'not_attempted' for r in result['requests'])
    assert result['errors']
    assert validate_smoke(result) == result


def test_budget_exhaustion_between_reads_retains_first_page(tmp_path):
    from gabfin.providers.futu.history import inspect_history

    ticks = iter([0, 0, 0, 50, 50])
    context = QuoteContext()
    result = inspect_history(context, SDK, checked_at=NOW, deadline=90, monotonic=lambda: next(ticks))
    assert context.history_calls == ['RTH'] and context.closed
    assert [r['status'] for r in result['requests']] == ['available', 'not_attempted']
    assert result['errors'] == ['budget_exhausted']
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata'] == result


@pytest.mark.parametrize('change', [
    {'code': 'US.MSFT'}, {'time_key': '2026-11-25 09:30:00'},
    {'time_key': '2026-11-24 02:00:00'}, {'time_key': 'PRIVATE'},
    {'open': float('nan')}, {'close': True}, {'low': -1}, {'high': 100},
])
def test_invalid_history_data_is_discarded_but_other_session_can_succeed(change):
    from gabfin.providers.futu.history import inspect_history

    context = QuoteContext()
    original = context.request_history_kline
    def request(code, **kwargs):
        ret, records, page = original(code, **kwargs)
        return ret, [r | change for r in records] if kwargs['session'] == 'RTH' else records, page
    context.request_history_kline = request
    result = inspect_history(context, SDK, checked_at=NOW)
    assert [r['status'] for r in result['requests']] == ['invalid_data', 'available']
    assert not result['requests'][0]['bars'] and result['requests'][0]['has_more'] is None
    assert context.closed and context.quota_calls == 2 and 'PRIVATE' not in str(result)


@pytest.mark.parametrize('mode', ['empty', 'failed', 'raised', 'oversize', 'duplicate', 'private_token'])
def test_empty_and_failed_pages_do_not_trigger_pagination_or_retry(tmp_path, mode):
    from gabfin.providers.futu.history import inspect_history

    context = QuoteContext()
    original = context.request_history_kline
    def request(code, **kwargs):
        ret, records, page = original(code, **kwargs)
        if mode == 'raised':
            raise RuntimeError('PRIVATE')
        if mode == 'failed':
            return 1, 'PRIVATE', None
        if mode == 'empty':
            return 0, [], None
        if mode == 'private_token':
            return ret, records, 'PRIVATE'
        return ret, records * (3 if mode == 'oversize' else 2), page
    context.request_history_kline = request
    result = inspect_history(context, SDK, checked_at=NOW)
    expected = 'empty' if mode == 'empty' else 'failed' if mode in ('failed', 'raised') else 'invalid_data'
    assert [r['status'] for r in result['requests']] == [expected, expected]
    assert len(context.history_calls) == 2 and context.closed
    assert 'PRIVATE' not in str(result)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata'] == result


@pytest.mark.parametrize('failure', ['market_state', 'quota_before', 'quota_after', 'close'])
def test_metadata_failures_are_explicit_and_close_is_attempted(tmp_path, failure):
    from gabfin.providers.futu.history import inspect_history

    context = QuoteContext()
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE')
    if failure == 'market_state':
        context.get_market_state = fail
    if failure.startswith('quota'):
        original = context.get_history_kl_quota
        def quota(**kwargs):
            response = original(**kwargs)
            if context.quota_calls == (1 if failure == 'quota_before' else 2):
                fail()
            return response
        context.get_history_kl_quota = quota
    if failure == 'close':
        def close():
            context.closed = True
            fail()
        context.close = close
    result = inspect_history(context, SDK, checked_at=NOW)
    assert context.closed and result['errors'] and 'PRIVATE' not in str(result)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata'] == result


@pytest.mark.parametrize('change', [
    {'account': 'PRIVATE'}, {'requested_date': '2026-11-25'}, {'market_state': 'PRIVATE'},
    {'quota_before': {'used': False, 'remaining': 5}}, {'quota_after': None},
    {'live_rights': 'verified'}, {'cleanup': 'close_failed'}, {'errors': ['PRIVATE']},
])
def test_parent_rejects_unsafe_or_contradictory_top_level_result(tmp_path, change):
    from gabfin.providers.futu.history import inspect_history

    result = inspect_history(QuoteContext(), SDK, checked_at=NOW) | change
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}


@pytest.mark.parametrize('change', [
    {'status': 'empty'}, {'status': 'not_attempted'}, {'has_more': 'PRIVATE'},
    {'session': 'ALL'}, {'bars': []}, {'account': 'PRIVATE'},
])
def test_parent_rejects_unsafe_or_contradictory_request(tmp_path, change):
    from gabfin.providers.futu.history import inspect_history

    result = inspect_history(QuoteContext(), SDK, checked_at=NOW)
    result['requests'][0].update(change)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}


@pytest.mark.parametrize('change', [
    {'time': '2026-11-25 09:30:00'}, {'clock_window': 'PRE'}, {'close': 'NaN'},
    {'low': '103'}, {'code': 'PRIVATE'}, {'open': 100},
])
def test_parent_rechecks_bar_semantics(tmp_path, change):
    from gabfin.providers.futu.history import inspect_history

    result = inspect_history(QuoteContext(), SDK, checked_at=NOW)
    result['requests'][0]['bars'][0].update(change)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}


def test_target_date_is_previous_new_york_calendar_day_even_at_utc_midnight():
    from gabfin.providers.futu.history import inspect_history

    context = QuoteContext()
    context.get_history_kl_quota = lambda **kwargs: (0, (0, 0, []))
    result = inspect_history(context, SDK, checked_at=datetime(2026, 11, 25, 1, tzinfo=timezone.utc))
    assert result['requested_date'] == '2026-11-23' and context.closed


def test_initialization_failure_still_closes_context(monkeypatch):
    from gabfin.providers.futu import history

    def unavailable(zone):
        raise ValueError('PRIVATE')
    context = QuoteContext()
    monkeypatch.setattr(history, 'ZoneInfo', unavailable)
    with pytest.raises(ValueError):
        history.inspect_history(context, SDK, checked_at=NOW)
    assert context.closed


def test_final_quota_is_skipped_when_budget_cannot_cover_one_rpc(tmp_path):
    from gabfin.providers.futu.history import inspect_history

    context = QuoteContext()
    ticks = iter([0, 0, 0, 80, 80])
    result = inspect_history(context, SDK, checked_at=NOW, deadline=90, monotonic=lambda: next(ticks))
    assert context.history_calls == ['RTH'] and context.quota_calls == 1 and context.closed
    assert result['quota_after'] is None and 'quota_after_skipped' in result['errors']
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata'] == result


def test_parent_rejects_noncanonical_checked_at(tmp_path):
    from gabfin.providers.futu.history import inspect_history

    result = inspect_history(QuoteContext(), SDK, checked_at=NOW)
    result['checked_at'] = '2026-11-25私15:00:00+00:00'
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['status'] == 'invalid_result'


def test_history_clock_evidence_lists_unobserved_post_and_is_parent_checked(tmp_path):
    from gabfin.providers.futu.history import inspect_history

    result = inspect_history(QuoteContext(), SDK, checked_at=NOW)
    assert result['historical_evidence'] == {'PRE': 'sampled', 'RTH': 'sampled', 'POST': 'not_sampled'}
    result['historical_evidence']['POST'] = 'sampled'
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['status'] == 'invalid_result'


class Proto:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def HasField(self, name):
        return name in self.__dict__


@pytest.mark.parametrize('missing', [False, True])
def test_single_page_wire_does_not_inherit_prices_or_follow_token(missing):
    from gabfin.providers.futu.history import inspect_history
    from gabfin.providers.futu.history_wire import SinglePageHistoryContext

    raw = QuoteContext()
    wire_calls = []
    def query(pack, unpack, **kwargs):
        wire_calls.append(kwargs)
        row1 = Proto(time='2026-11-24 09:31:00', isBlank=False, openPrice=100, highPrice=102, lowPrice=99, closePrice=101)
        row2 = Proto(time='2026-11-24 09:32:00', isBlank=False, highPrice=102, lowPrice=99, closePrice=101)
        if not missing:
            row2.openPrice = 100
        response = Proto(retType=0, s2c=Proto(security=Proto(market=11, code='AAPL'), klList=[row1, row2], nextReqKey=b'PRIVATE'))
        return unpack(response)
    raw._query_sync = query
    raw.get_sync_conn_id = lambda: 1
    raw.get_security_firm = lambda: 'N/A'
    context = SinglePageHistoryContext(raw, pack_request=object(), us_market=11)
    result = inspect_history(context, SDK, checked_at=NOW)
    assert len(wire_calls) == 2
    assert all(c['max_num'] == 2 and c['next_req_key'] is None for c in wire_calls)
    assert all(c['start_date'] == '2026-11-24 00:00:00' and c['end_date'] == '2026-11-24 23:59:59' for c in wire_calls)
    assert [r['status'] for r in result['requests']] == (['invalid_data'] * 2 if missing else ['available'] * 2)
    assert raw.closed and 'PRIVATE' not in str(result)


def test_worker_startup_failure_after_context_creation_still_closes(tmp_path):
    from gabfin.providers.futu.runner import run_probe
    from gabfin.providers.futu import worker

    marker = tmp_path / 'closed'
    script = tmp_path / 'startup.py'
    script.write_text(
        'import sys,types,importlib.util\nfrom pathlib import Path\n'
        'f=types.ModuleType("futu")\n'
        'class C:\n def close(self): Path(' + repr(str(marker)) + ').write_text("closed")\n'
        'f.OpenQuoteContext=lambda **kw:C()\n'
        'f.SysConfig=types.SimpleNamespace(enable_console_log=lambda flag:None)\n'
        'sys.modules["futu"]=f\n'
        's=importlib.util.spec_from_file_location("quote_worker",' + repr(worker.__file__) + ')\n'
        'm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\nm.main()\n', encoding='utf-8')
    result = run_probe(Path(sys.executable), host='127.0.0.1', port=11111, timeout=90,
                       operation='history_smoke', _worker=script)
    assert result == {'status': 'worker_failed', 'metadata': None}
    assert marker.read_text() == 'closed'


@pytest.mark.parametrize('rows', [[], [Proto(time='2026-11-24 09:31:00', isBlank=True)]])
def test_short_or_blank_wire_page_is_not_refilled(rows):
    from gabfin.providers.futu.history import inspect_history
    from gabfin.providers.futu.history_wire import SinglePageHistoryContext

    raw = QuoteContext()
    calls = []
    def query(pack, unpack, **kwargs):
        calls.append(kwargs)
        return unpack(Proto(retType=0, s2c=Proto(security=Proto(market=11, code='AAPL'), klList=rows, nextReqKey=b'PRIVATE')))
    raw._query_sync = query
    raw.get_sync_conn_id = lambda: 1
    raw.get_security_firm = lambda: 'N/A'
    result = inspect_history(SinglePageHistoryContext(raw, pack_request=object(), us_market=11), SDK, checked_at=NOW)
    assert len(calls) == 2 and raw.closed
    assert [r['status'] for r in result['requests']] == (['empty'] * 2 if not rows else ['invalid_data'] * 2)


@pytest.mark.parametrize('mode', ['wrong_security', 'missing_security', 'missing_time', 'missing_blank', 'oversize'])
def test_malformed_successful_wire_payload_is_invalid_not_transport_failure(mode):
    from gabfin.providers.futu.history import inspect_history
    from gabfin.providers.futu.history_wire import SinglePageHistoryContext

    raw = QuoteContext()
    def query(pack, unpack, **kwargs):
        row = Proto(time='2026-11-24 09:31:00', isBlank=False, openPrice=100, highPrice=102, lowPrice=99, closePrice=101)
        page = Proto(security=Proto(market=11, code='MSFT' if mode == 'wrong_security' else 'AAPL'), klList=[row])
        if mode == 'missing_security':
            del page.security
        if mode == 'missing_time':
            del row.time
        if mode == 'missing_blank':
            del row.isBlank
        if mode == 'oversize':
            page.klList = [row] * 3
        try:
            return unpack(Proto(retType=0, s2c=page))
        except Exception:
            return -1, 'PRIVATE', None  # The pinned SDK catches decoder exceptions.
    raw._query_sync = query
    raw.get_sync_conn_id = lambda: 1
    raw.get_security_firm = lambda: 'N/A'
    result = inspect_history(SinglePageHistoryContext(raw, pack_request=object(), us_market=11), SDK, checked_at=NOW)
    assert [r['status'] for r in result['requests']] == ['invalid_data', 'invalid_data']
    assert raw.closed and 'PRIVATE' not in str(result)


@pytest.mark.parametrize('after_market', [False, True])
def test_metadata_queries_respect_remaining_budget(tmp_path, after_market):
    from gabfin.providers.futu.history import inspect_history

    context = QuoteContext()
    market_calls = []
    original = context.get_market_state
    def market(codes):
        market_calls.append(codes)
        return original(codes)
    context.get_market_state = market
    ticks = iter([0, 80, 80] if after_market else [99, 99])
    result = inspect_history(context, SDK, checked_at=NOW, deadline=100, monotonic=lambda: next(ticks))
    assert bool(market_calls) is after_market
    assert context.quota_calls == 0 and not context.history_calls and context.closed
    assert 'quota_before_skipped' in result['errors'] and 'quota_after_skipped' in result['errors']
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata'] == result


@pytest.mark.parametrize('case', ['market_skipped_but_read', 'before_skipped_but_after_read'])
def test_parent_rejects_impossible_skipped_query_phases(tmp_path, case):
    from gabfin.providers.futu.history import inspect_history

    if case == 'market_skipped_but_read':
        result = inspect_history(QuoteContext(), SDK, checked_at=NOW)
        result.update(market_state=None, errors=['market_state_skipped'])
    else:
        result = inspect_history(QuoteContext(), SDK, checked_at=NOW, deadline=100, monotonic=lambda: 99)
        result.update(market_state='PRE_MARKET_BEGIN', errors=['quota_before_skipped'],
                      quota_after={'used': 5, 'remaining': 295})
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}
