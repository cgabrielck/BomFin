from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest


NOW = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)


class SDK:
    QUOTE = 'QUOTE'
    ALL = 'ALL'
    RTH = 'RTH'


def contract(right='CALL', strike=355):
    return {
        'code': 'US.AAPL261127' + ('C' if right == 'CALL' else 'P') + str(strike * 1000),
        'stock_type': 'DRVT', 'stock_owner': 'US.AAPL', 'strike_time': '2026-11-27',
        'option_type': right, 'strike_price': strike, 'lot_size': 100,
        'option_standard_type': 'STANDARD', 'suspension': False,
    }


class QuoteContext:
    def __init__(self):
        self.closed = False
        self.subscriptions = []
        self.removals = []
        self.chain = [contract(), contract('PUT'), contract(strike=400)]

    def get_option_expiration_date(self, code):
        assert code == 'US.AAPL'
        return 0, [{'strike_time': '2026-11-27'}, {'strike_time': '2027-01-15'}]

    def get_option_chain(self, code, **kwargs):
        assert code == 'US.AAPL'
        assert kwargs == {'start': '2026-11-27', 'end': '2026-11-27', 'option_type': 'ALL'}
        return 0, self.chain

    def subscribe(self, codes, subtypes, **kwargs):
        assert subtypes == ['QUOTE']
        assert kwargs == dict(is_first_push=False, subscribe_push=False, extended_time=False, session='RTH')
        self.subscriptions.append(codes)
        return 0, None

    def get_stock_quote(self, codes):
        return 0, [dict(code=code, last_price=2.75, strike_price=355,
                        contract_size=100, data_date='2026-11-25', data_time='09:59:59',
                        private='PRIVATE') for code in codes]

    def unsubscribe(self, codes, subtypes):
        assert subtypes == ['QUOTE']
        self.removals.append(codes)
        return 0, None

    def query_subscription(self, **kwargs):
        assert kwargs == {'is_all_conn': False}
        return 0, {'own_used': 0, 'own_option_used_quota': 0,
                   'option_used_quota': 0, 'option_remain_quota': 60}

    def close(self):
        self.closed = True


def test_bounded_call_put_quote_and_own_subscription_release():
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    waits = []
    result = inspect_options(context, SDK, checked_at=NOW, sleep=waits.append)
    assert result['errors'] == []
    assert result['chain_verified'] is True
    assert [(r['right'], r['strike'], r['shares_per_contract'], r['last_price'])
            for r in result['contracts']] == [('CALL', '355', '100', '2.75'), ('PUT', '355', '100', '2.75')]
    assert result['cleanup'] == 'unsubscribed'
    assert waits == [61] and context.closed
    assert context.subscriptions == context.removals == [[contract()['code'], contract('PUT')['code']]]
    assert result['latency'] == 'unverified' and 'PRIVATE' not in str(result)


def run_child(tmp_path, payload):
    from gabfin.providers.futu.runner import run_probe

    worker = tmp_path / 'child.py'
    worker.write_text('import sys\nfrom pathlib import Path\n'
                      'Path(sys.argv[1]).write_text(' + repr(json.dumps(payload)) + ')\n', encoding='utf-8')
    return run_probe(Path(sys.executable), host='127.0.0.1', port=11111,
                     timeout=110, operation='options_smoke', _worker=worker)


def test_options_result_survives_real_parent_process_boundary(tmp_path):
    from gabfin.providers.futu.options import inspect_options

    result = inspect_options(QuoteContext(), SDK, checked_at=NOW, sleep=lambda n: None)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'ok', 'metadata': result}


@pytest.mark.parametrize('change', [
    {'stock_owner': 'US.MSFT'}, {'option_type': 'PUT'}, {'strike_time': '2026-12-04'},
    {'lot_size': 10}, {'lot_size': float('nan')}, {'code': 'PRIVATE'},
    {'stock_type': 'STOCK'}, {'strike_price': 356},
])
def test_chain_identity_errors_never_subscribe_and_always_close(change):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.chain[0].update(change)
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: pytest.fail('no subscription'))
    assert result['errors'] == ['chain_failed']
    assert not result['chain_verified'] and not context.subscriptions and context.closed
    assert 'PRIVATE' not in str(result)


def test_empty_window_does_not_fall_back_to_broad_subscription():
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.chain = [contract(strike=400)]
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: pytest.fail('no subscription'))
    assert result['errors'] == ['window_empty']
    assert context.closed and not context.subscriptions


def test_failed_subscription_may_be_partial_and_still_releases_only_own_codes():
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.subscribe = lambda *args, **kwargs: (1, 'PRIVATE')
    waits = []
    result = inspect_options(context, SDK, checked_at=NOW, sleep=waits.append)
    assert result['errors'] == ['subscribe_failed']
    assert waits == [61] and result['cleanup'] == 'unsubscribed' and context.closed
    assert context.removals == [[contract()['code'], contract('PUT')['code']]]


@pytest.mark.parametrize('change', [{'contract_size': 10}, {'strike_price': 350}, {'code': 'US.MSFT'}])
def test_quote_identity_mismatch_never_presents_success(change):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    original = context.get_stock_quote
    context.get_stock_quote = lambda codes: (0, [q | change for q in original(codes)[1]])
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert result['errors'] == ['quote_failed']
    assert result['cleanup'] == 'unsubscribed' and context.closed


@pytest.mark.parametrize('price', [None, float('nan'), float('inf'), True, -1])
def test_invalid_quote_price_remains_missing_and_report_is_incomplete(price):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    original = context.get_stock_quote
    context.get_stock_quote = lambda codes: (0, [q | {'last_price': price} for q in original(codes)[1]])
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert 'quote_incomplete' in result['errors']
    assert all(c['last_price'] is None for c in result['contracts'])
    assert result['cleanup'] == 'unsubscribed' and context.closed


@pytest.mark.parametrize('failure', ['unsubscribe', 'quota', 'close', 'wait', 'quote'])
def test_provider_failure_is_sanitized_and_context_close_is_attempted(failure):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    def fail(*args, **kwargs):
        raise RuntimeError('PRIVATE')
    if failure == 'unsubscribe':
        context.unsubscribe = fail
    elif failure == 'quota':
        context.query_subscription = lambda **kwargs: (0, {'own_used': 1})
    elif failure == 'close':
        def close():
            context.closed = True
            raise RuntimeError('PRIVATE')
        context.close = close
    elif failure == 'quote':
        context.get_stock_quote = fail
    result = inspect_options(context, SDK, checked_at=NOW, sleep=fail if failure == 'wait' else lambda n: None)
    assert result['errors'] and context.closed and 'PRIVATE' not in str(result)
    if failure in ('unsubscribe', 'quota', 'wait'):
        assert result['cleanup'] == 'release_pending'
    else:
        assert result['cleanup'] == 'unsubscribed'


def test_expiry_uses_new_york_date_and_bounded_future_window():
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.get_option_expiration_date = lambda code: (0, [{'strike_time': '2026-11-24'}, {'strike_time': '2027-01-15'}])
    context.get_option_chain = lambda code, **kwargs: (0, []) if kwargs['start'] == '2026-11-24' else pytest.fail('wrong expiry')
    result = inspect_options(context, SDK, checked_at=datetime(2026, 11, 25, 1, tzinfo=timezone.utc), sleep=lambda n: None)
    assert result['expiry'] == '2026-11-24' and context.closed


@pytest.mark.parametrize('kind', ['expired', 'future', 'oversize', 'denied'])
def test_unavailable_expiry_or_oversize_chain_stops_before_subscribe(kind):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    if kind in ('expired', 'future'):
        context.get_option_expiration_date = lambda code: (0, [{'strike_time': '2026-11-24' if kind == 'expired' else '2027-01-15'}])
    elif kind == 'oversize':
        context.chain = [contract()] * 2001
    else:
        context.get_option_expiration_date = lambda code: (1, 'PRIVATE')
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert result['errors'] and not context.subscriptions and context.closed
    assert 'PRIVATE' not in str(result)


@pytest.mark.parametrize('change', [
    {'account': 'PRIVATE'}, {'cleanup': 'PRIVATE'}, {'latency': 'realtime'},
    {'chain_verified': False}, {'errors': ['PRIVATE']}, {'expiry': '2027-01-15'},
    {'checked_at': '2026-11-25T15:00:00'}, {'strike_window': {'min': '0', 'max': '999'}},
])
def test_parent_rejects_unsafe_or_inconsistent_child_fields(tmp_path, change):
    from gabfin.providers.futu.options import inspect_options

    result = inspect_options(QuoteContext(), SDK, checked_at=NOW, sleep=lambda n: None)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result | change}) == {'status': 'invalid_result', 'metadata': None}


@pytest.mark.parametrize('change', [
    {'code': 'PRIVATE'}, {'shares_per_contract': '10'}, {'last_price': 'NaN'},
    {'data_time': 'PRIVATE'}, {'right': 'PUT'}, {'expiry': '2026-12-04'}, {'strike': '356'},
])
def test_parent_rejects_untrusted_contracts(tmp_path, change):
    from gabfin.providers.futu.options import inspect_options

    result = inspect_options(QuoteContext(), SDK, checked_at=NOW, sleep=lambda n: None)
    result['contracts'][0].update(change)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}


def test_options_cli_default_allows_subscription_release(monkeypatch, capsys):
    from gabfin.providers.futu import runner

    calls = []
    def run(python, **kwargs):
        calls.append(kwargs)
        return {'status': 'sdk_unavailable', 'metadata': None}
    monkeypatch.setattr(runner, 'run_probe', run)
    monkeypatch.setattr(sys, 'argv', ['runner', '--python', sys.executable, '--host', '127.0.0.1',
                                     '--port', '11111', '--operation', 'options_smoke'])
    assert runner.main() == 2
    assert calls[0]['timeout'] == 110
    assert 'sdk_unavailable' in capsys.readouterr().out


def test_options_rejects_explicit_deadline_too_short_for_release():
    from gabfin.providers.futu.runner import run_probe

    assert run_probe(Path(sys.executable), host='127.0.0.1', port=11111,
                     timeout=10, operation='options_smoke')['status'] == 'invalid_config'


def test_single_direction_is_reported_as_partial_without_broadening_window():
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.chain = [contract()]
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert result['errors'] == ['window_partial']
    assert result['contracts'][0]['right'] == 'CALL'
    assert result['contracts'][0]['last_price'] == '2.75'
    assert result['cleanup'] == 'unsubscribed' and context.closed


@pytest.mark.parametrize('chain_verified,contracts,cleanup', [
    (False, [], 'unsubscribed'),
    (True, None, 'not_subscribed'),
])
def test_parent_validates_cleanup_state_even_when_errors_exist(tmp_path, chain_verified, contracts, cleanup):
    from gabfin.providers.futu.options import inspect_options

    result = inspect_options(QuoteContext(), SDK, checked_at=NOW, sleep=lambda n: None)
    result.update(chain_verified=chain_verified, cleanup=cleanup, errors=['expiry_failed'])
    if contracts is not None:
        result['contracts'] = contracts
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}


def test_nonzero_option_quota_is_not_successful_cleanup():
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.query_subscription = lambda **kwargs: (0, {'own_used': 0, 'own_option_used_quota': 2})
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert result['cleanup'] == 'release_pending'
    assert 'cleanup_verify_failed' in result['errors']
    assert context.closed


def test_unsubscribe_failure_still_checks_quota():
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.unsubscribe = lambda *args: (1, 'PRIVATE')
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert result['cleanup_quota']['own_option_used'] == 0
    assert result['cleanup'] == 'release_pending' and context.closed


@pytest.mark.parametrize('option_quota', [2, False, None])
def test_parent_requires_observed_zero_option_quota_for_release(tmp_path, option_quota):
    from gabfin.providers.futu.options import inspect_options

    result = inspect_options(QuoteContext(), SDK, checked_at=NOW, sleep=lambda n: None)
    result['cleanup_quota']['own_option_used'] = option_quota
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}


def test_partial_and_unavailable_reports_cross_parent_boundary(tmp_path):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    context.chain = [contract()]
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata']['errors'] == ['window_partial']
    context = QuoteContext()
    context.get_option_expiration_date = lambda code: (0, [])
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata']['errors'] == ['expiry_unavailable']


@pytest.mark.parametrize('case', ['empty_partial', 'subscribe_with_quotes', 'partial_without_quote_error',
                                  'pending_without_error', 'window_without_expiry'])
def test_parent_rejects_contradictory_failure_phases(tmp_path, case):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    if case in ('partial_without_quote_error', 'pending_without_error'):
        context.chain = [contract()]
    if case in ('empty_partial', 'window_without_expiry'):
        context.chain = []
    result = inspect_options(context, SDK, checked_at=NOW, sleep=lambda n: None)
    if case == 'empty_partial':
        result['errors'].append('window_partial')
    elif case == 'subscribe_with_quotes':
        result['errors'].append('subscribe_failed')
    elif case == 'partial_without_quote_error':
        result['contracts'][0].update(last_price=None, data_date=None, data_time=None)
    elif case == 'pending_without_error':
        result['cleanup'] = 'release_pending'
    else:
        result['expiry'] = None
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}


def test_does_not_start_subscription_if_discovery_used_cleanup_budget(tmp_path):
    from gabfin.providers.futu.options import inspect_options

    context = QuoteContext()
    result = inspect_options(context, SDK, checked_at=NOW, deadline=100, monotonic=lambda: 30,
                             sleep=lambda n: pytest.fail('no subscription'))
    assert result['errors'] == ['budget_exhausted']
    assert result['chain_verified'] and not result['subscription_attempted']
    assert result['cleanup'] == 'not_subscribed' and not context.subscriptions and context.closed
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result})['metadata'] == result


@pytest.mark.parametrize('missing', [('data_time',), ('data_date', 'data_time')])
def test_parent_rejects_price_without_complete_source_time_even_on_quote_failure(tmp_path, missing):
    from gabfin.providers.futu.options import inspect_options

    result = inspect_options(QuoteContext(), SDK, checked_at=NOW, sleep=lambda n: None)
    result['errors'] = ['quote_failed']
    for field in missing:
        result['contracts'][0][field] = None
    assert run_child(tmp_path, {'status': 'ok', 'metadata': result}) == {'status': 'invalid_result', 'metadata': None}
