"""Two first-page historical samples, separate from realtime entitlement evidence."""
from datetime import datetime, timedelta, timezone, time as clock
from decimal import Decimal
import time
from zoneinfo import ZoneInfo

from gabfin.providers.futu.equity import number, ok

CODE = 'US.AAPL'
ZONE = 'America/New_York'
STATES = {'NONE', 'WAITING_OPEN', 'AUCTION', 'MORNING', 'REST', 'AFTERNOON', 'CLOSED',
          'PRE_MARKET_BEGIN', 'PRE_MARKET_END', 'AFTER_HOURS_BEGIN', 'AFTER_HOURS_END', 'OVERNIGHT'}
ERRORS = {'market_state_failed', 'quota_before_failed', 'quota_exhausted', 'budget_exhausted',
          'quota_after_failed', 'quota_after_skipped', 'close_failed', 'market_state_skipped', 'quota_before_skipped'}


def _evidence(requests):
    observed = {b['clock_window'] for sample in requests for b in sample['bars']}
    return {window: 'sampled' if window in observed else 'not_sampled' for window in ('PRE', 'RTH', 'POST')}


def validate_smoke(result):
    """Validate observations and request phases, not the provider's entitlement policy."""
    fields = {'kind', 'code', 'checked_at', 'requested_date', 'source_timezone', 'adjustment',
              'interval', 'live_rights', 'market_state', 'quota_before', 'quota_after',
              'requests', 'cleanup', 'errors', 'historical_evidence'}
    if not isinstance(result, dict) or set(result) != fields:
        raise ValueError('result_fields')
    if (result['kind'] != 'history_smoke' or result['code'] != CODE or result['source_timezone'] != ZONE
            or result['adjustment'] != 'NONE' or result['interval'] != 'K_1M' or result['live_rights'] != 'unverified'):
        raise ValueError('scope')
    observed = datetime.fromisoformat(result['checked_at'])
    if (observed.tzinfo is None or observed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') != result['checked_at']
            or result['requested_date'] != (
            observed.astimezone(ZoneInfo(ZONE)).date() - timedelta(days=1)).isoformat()):
        raise ValueError('date_scope')
    errors = result['errors']
    if not isinstance(errors, list) or any(type(e) is not str or e not in ERRORS for e in errors) or len(errors) != len(set(errors)):
        raise ValueError('errors')
    if ('market_state_skipped' in errors and 'quota_before_skipped' not in errors) or (
            'quota_before_skipped' in errors and 'quota_after_skipped' not in errors):
        raise ValueError('skip_phase')
    market_missing = set(errors) & {'market_state_failed', 'market_state_skipped'}
    if (result['market_state'] is not None and result['market_state'] not in STATES) or (
            (result['market_state'] is None) != bool(market_missing)) or len(market_missing) > 1:
        raise ValueError('market_state')
    for key, error in [('quota_before', 'quota_before_failed'), ('quota_after', 'quota_after_failed')]:
        quota = result[key]
        skipped = 'quota_after_skipped' if key == 'quota_after' else 'quota_before_skipped'
        missing = error in errors or skipped in errors
        if (quota is None) != missing or (error in errors and skipped in errors):
            raise ValueError('quota_phase')
        if quota is not None and (not isinstance(quota, dict) or set(quota) != {'used', 'remaining'}
                or any(type(v) is not int or not 0 <= v <= 9007199254740991 for v in quota.values())):
            raise ValueError('quota_counter')
    exhausted = result['quota_before'] is not None and result['quota_before']['remaining'] == 0
    if exhausted != ('quota_exhausted' in errors):
        raise ValueError('quota_gate')
    if result['cleanup'] not in ('closed', 'close_failed') or (
            (result['cleanup'] == 'close_failed') != ('close_failed' in errors)):
        raise ValueError('cleanup')
    requests = result['requests']
    if not isinstance(requests, list) or len(requests) != 2:
        raise ValueError('request_count')
    attempts = []
    for sample, session in zip(requests, ('RTH', 'ETH')):
        if not isinstance(sample, dict) or set(sample) != {'session', 'status', 'bars', 'has_more'} or sample['session'] != session:
            raise ValueError('request_fields')
        status, bars = sample['status'], sample['bars']
        if status not in ('not_attempted', 'available', 'empty', 'failed', 'invalid_data') or not isinstance(bars, list) or len(bars) > 2:
            raise ValueError('request_status')
        attempts.append(status != 'not_attempted')
        if status in ('available', 'empty'):
            if type(sample['has_more']) is not bool or (status == 'available') != bool(bars):
                raise ValueError('page_state')
        elif bars or sample['has_more'] is not None:
            raise ValueError('unexpected_page')
        for bar in bars:
            if not isinstance(bar, dict) or set(bar) != {'time', 'open', 'high', 'low', 'close', 'clock_window'}:
                raise ValueError('bar_fields')
            if any(type(bar[f]) is not str for f in ('time', 'open', 'high', 'low', 'close', 'clock_window')):
                raise ValueError('bar_types')
            raw = {'code': CODE, 'time_key': bar['time'], **{f: bar[f] for f in ('open', 'high', 'low', 'close')}}
            if _bar(raw, result['requested_date'], session) != bar:
                raise ValueError('bar_semantics')
        if any(a['time'] >= b['time'] for a, b in zip(bars, bars[1:])):
            raise ValueError('bar_order')
    pre_stop = result['quota_before'] is None or exhausted
    if attempts == [False, True] or (pre_stop and any(attempts)):
        raise ValueError('attempt_order')
    if ('budget_exhausted' in errors) != (not pre_stop and not all(attempts)):
        raise ValueError('budget_state')
    if result['historical_evidence'] != _evidence(requests):
        raise ValueError('historical_evidence')
    return result


def successful(result):
    return not result['errors'] and all(r['status'] == 'available' for r in result['requests'])


def _quota(response):
    if not ok(response) or not isinstance(response[1], tuple) or len(response[1]) != 3:
        raise ValueError('quota_shape')
    used, remaining = response[1][:2]
    if any(type(v) is not int or not 0 <= v <= 9007199254740991 for v in (used, remaining)):
        raise ValueError('quota_counter')
    return {'used': used, 'remaining': remaining}


def _records(data, limit):
    if len(data) > limit:
        raise ValueError('row_limit')
    records = data if isinstance(data, list) else data.to_dict(orient='records')
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError('records_shape')
    return records


def _clock_window(stamp):
    """Conventional clock-label windows only, not an exchange calendar ruling."""
    value = stamp.time()
    if clock(4) <= value < clock(9, 30):
        return 'PRE'
    if clock(9, 30) <= value < clock(16):
        return 'RTH'
    if clock(16) <= value < clock(20):
        return 'POST'
    raise ValueError('outside_eth_clock')


def _bar(raw, requested_date, session):
    if raw.get('code') != CODE:
        raise ValueError('wrong_code')
    stamp = datetime.fromisoformat(raw['time_key'])
    if (stamp.tzinfo is not None or stamp.second or stamp.microsecond
            or stamp.strftime('%Y-%m-%d %H:%M:%S') != raw['time_key']
            or stamp.date().isoformat() != requested_date):
        raise ValueError('source_time')
    window = _clock_window(stamp)
    if session == 'RTH' and window != 'RTH':
        raise ValueError('wrong_session')
    prices = {field: number(raw.get(field)) for field in ('open', 'high', 'low', 'close')}
    if any(v is None for v in prices.values()):
        raise ValueError('missing_price')
    o, h, low, c = [Decimal(prices[k]) for k in ('open', 'high', 'low', 'close')]
    if not low <= min(o, c) <= max(o, c) <= h:
        raise ValueError('ohlc_order')
    return {'time': raw['time_key'], **prices, 'clock_window': window}


def inspect_history(context, sdk, *, checked_at=None, deadline=None, monotonic=time.monotonic):
    """Read two bounded pages without subscriptions; preserve samples and close."""
    result = None
    try:
        now = checked_at if checked_at is not None else datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError('naive_clock')
        requested = (now.astimezone(ZoneInfo(ZONE)).date() - timedelta(days=1)).isoformat()
        result = dict(kind='history_smoke', code=CODE,
                      checked_at=now.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'), requested_date=requested,
                      source_timezone=ZONE, adjustment='NONE', interval='K_1M', live_rights='unverified',
                      market_state=None, quota_before=None, quota_after=None,
                      requests=[dict(session=s, status='not_attempted', bars=[], has_more=None) for s in ('RTH', 'ETH')],
                      historical_evidence={}, cleanup='closed', errors=[])
        if deadline is not None and deadline - monotonic() < 28:
            result['errors'].extend(['market_state_skipped', 'quota_before_skipped'])
            return result
        try:
            response = context.get_market_state([CODE])
            if not ok(response):
                raise ValueError('market_state')
            rows = _records(response[1], 1)
            if len(rows) != 1 or rows[0].get('code') != CODE or rows[0].get('market_state') not in STATES:
                raise ValueError('market_state')
            result['market_state'] = rows[0]['market_state']
        except Exception:
            result['errors'].append('market_state_failed')
        if deadline is not None and deadline - monotonic() < 28:
            result['errors'].append('quota_before_skipped')
            return result
        try:
            result['quota_before'] = _quota(context.get_history_kl_quota(get_detail=False))
        except Exception:
            result['errors'].append('quota_before_failed')
            return result
        if result['quota_before']['remaining'] == 0:
            result['errors'].append('quota_exhausted')
            return result
        for sample in result['requests']:
            if deadline is not None and deadline - monotonic() < 60:
                result['errors'].append('budget_exhausted')
                break
            sample['status'] = 'failed'
            try:
                response = context.request_history_kline(
                    CODE, start=requested, end=requested, ktype=sdk.K_1M, autype=sdk.NONE,
                    fields=sdk.FIELDS, max_count=2, page_req_key=None,
                    session=getattr(sdk, sample['session']), extended_time=sample['session'] == 'ETH')
                if not isinstance(response, tuple) or len(response) != 3 or type(response[0]) is not int or response[0] != 0:
                    continue
                sample['status'] = 'invalid_data'
                if response[2] is not None and type(response[2]) is not bytes:
                    continue
                bars = [_bar(row, requested, sample['session']) for row in _records(response[1], 2)]
                if any(a['time'] >= b['time'] for a, b in zip(bars, bars[1:])):
                    continue
                sample.update(status='available' if bars else 'empty', bars=bars, has_more=response[2] is not None)
            except Exception:
                # A raised API error and invalid payload both stay sanitized.
                pass
    finally:
        try:
            if result is not None:
                result['historical_evidence'] = _evidence(result['requests'])
                if deadline is not None and deadline - monotonic() < 28:
                    result['errors'].append('quota_after_skipped')
                else:
                    result['quota_after'] = _quota(context.get_history_kl_quota(get_detail=False))
        except Exception:
            if result is not None:
                result['errors'].append('quota_after_failed')
        try:
            context.close()
        except Exception:
            if result is None:
                raise
            result['cleanup'] = 'close_failed'
            result['errors'].append('close_failed')
    return result
