"""Bounded, quote-only AAPL option diagnostic; no execution eligibility claim."""
from datetime import date, datetime, time as daytime, timedelta, timezone
from decimal import Decimal
import re
import time
from zoneinfo import ZoneInfo

from gabfin.providers.futu.equity import number, ok

UNDERLYING = 'US.AAPL'
MIN_STRIKE = Decimal('350')
MAX_STRIKE = Decimal('360')
SOURCE_ZONE = 'America/New_York'
CODE = re.compile(r'US\.AAPL(\d{6})([CP])(\d{1,9})', re.ASCII)
ERRORS = {'expiry_unavailable', 'expiry_failed', 'window_empty', 'window_partial', 'chain_failed',
          'subscribe_failed', 'quote_incomplete', 'quote_failed', 'cleanup_wait_failed',
          'cleanup_verify_failed', 'unsubscribe_failed', 'close_failed', 'budget_exhausted'}
QUOTA_FIELDS = {'own_used': 'own_used', 'own_option_used': 'own_option_used_quota',
                'option_total_used': 'option_used_quota', 'option_remaining': 'option_remain_quota'}


def validate_smoke(result):
    """Revalidate the complete child allowlist, including cross-field identity."""
    fields = {'kind', 'underlying', 'checked_at', 'expiry', 'strike_window', 'chain_verified',
              'contracts', 'source_timezone', 'latency', 'cleanup', 'cleanup_quota',
              'subscription_attempted', 'errors'}
    if not isinstance(result, dict) or set(result) != fields:
        raise ValueError('result_fields')
    if (result['kind'] != 'options_smoke' or result['underlying'] != UNDERLYING
            or result['source_timezone'] != SOURCE_ZONE or result['latency'] != 'unverified'
            or result['strike_window'] != {'min': '350', 'max': '360'}
            or type(result['chain_verified']) is not bool
            or type(result['subscription_attempted']) is not bool):
        raise ValueError('result_scope')
    observed = datetime.fromisoformat(result['checked_at'])
    if observed.tzinfo is None:
        raise ValueError('naive_clock')
    today = observed.astimezone(ZoneInfo(SOURCE_ZONE)).date()
    expiry = result['expiry']
    if expiry is not None and not today <= date.fromisoformat(expiry) <= today + timedelta(days=30):
        raise ValueError('expiry_window')
    if result['cleanup'] not in ('not_subscribed', 'release_pending', 'unsubscribed'):
        raise ValueError('cleanup')
    errors = result['errors']
    if not isinstance(errors, list) or len(errors) > 16 or any(type(e) is not str or e not in ERRORS for e in errors):
        raise ValueError('errors')
    contracts = result['contracts']
    if not isinstance(contracts, list) or len(contracts) > 2:
        raise ValueError('contract_count')
    if result['chain_verified'] != bool(contracts):
        raise ValueError('chain_verification')
    before_chain = {'expiry_failed', 'expiry_unavailable', 'chain_failed', 'window_empty'}
    reasons = set(errors)
    if (contracts and before_chain.intersection(reasons)) or (
            not contracts and (len(before_chain.intersection(reasons)) != 1
                               or reasons - before_chain - {'close_failed'})):
        raise ValueError('error_phase')
    if {'expiry_failed', 'expiry_unavailable'}.intersection(errors) and expiry is not None:
        raise ValueError('expiry_failure_state')
    if {'chain_failed', 'window_empty'}.intersection(reasons) and expiry is None:
        raise ValueError('chain_without_expiry')
    if (len(contracts) == 1) != ('window_partial' in reasons):
        raise ValueError('partial_window_state')
    quota = result['cleanup_quota']
    if not isinstance(quota, dict) or set(quota) != set(QUOTA_FIELDS):
        raise ValueError('quota_fields')
    if any(v is not None and (type(v) is not int or not 0 <= v <= 9007199254740991) for v in quota.values()):
        raise ValueError('quota_counter')
    attempted = result['subscription_attempted']
    if attempted == (result['cleanup'] == 'not_subscribed') or (attempted and not contracts):
        raise ValueError('cleanup_phase')
    if contracts and ('budget_exhausted' in reasons) == attempted:
        raise ValueError('subscription_budget_state')
    if result['cleanup'] == 'not_subscribed' and any(v is not None for v in quota.values()):
        raise ValueError('unexpected_cleanup_quota')
    if result['cleanup'] == 'unsubscribed' and (
            quota['own_used'] != 0 or quota['own_option_used'] != 0
            or {'cleanup_wait_failed', 'cleanup_verify_failed', 'unsubscribe_failed'}.intersection(errors)):
        raise ValueError('cleanup_not_verified')
    cleanup_errors = {'cleanup_wait_failed', 'cleanup_verify_failed', 'unsubscribe_failed'}
    if result['cleanup'] == 'release_pending' and not cleanup_errors.intersection(reasons):
        raise ValueError('cleanup_pending_reason')
    if not attempted and reasons - before_chain - {'window_partial', 'budget_exhausted', 'close_failed'}:
        raise ValueError('error_before_subscription')
    quote_errors = {'quote_failed', 'quote_incomplete'}
    no_quote = not attempted or 'subscribe_failed' in reasons
    if no_quote and quote_errors.intersection(reasons):
        raise ValueError('quote_before_subscription')
    rights = set()
    for contract in contracts:
        if not isinstance(contract, dict) or set(contract) != {'code', 'expiry', 'right', 'strike',
                'shares_per_contract', 'last_price', 'data_date', 'data_time'}:
            raise ValueError('contract_fields')
        if (contract['expiry'] != expiry or expiry is None or contract['right'] not in ('CALL', 'PUT')
                or contract['right'] in rights or type(contract['strike']) is not str
                or number(contract['strike']) is None
                or not MIN_STRIKE <= Decimal(contract['strike']) <= MAX_STRIKE
                or contract['shares_per_contract'] != '100'
                or not _identity(contract['code'], expiry, contract['right'], contract['strike'])):
            raise ValueError('contract_identity')
        rights.add(contract['right'])
        price = contract['last_price']
        if price is not None and (type(price) is not str or number(price) is None):
            raise ValueError('price')
        if contract['data_date'] is not None:
            date.fromisoformat(contract['data_date'])
        if contract['data_time'] is not None:
            daytime.fromisoformat(contract['data_time'])
        dated = contract['data_date'] is not None
        timed = contract['data_time'] is not None
        if dated != timed or (price is not None and not (dated and timed)):
            raise ValueError('partial_quote_time')
        observations = [contract[k] for k in ('last_price', 'data_date', 'data_time')]
        if no_quote and any(v is not None for v in observations):
            raise ValueError('unexpected_quote')
        if not no_quote and not quote_errors.intersection(reasons) and any(v is None for v in observations):
            raise ValueError('incomplete_quote')
        if 'quote_incomplete' in reasons and 'quote_failed' not in reasons and any(
                contract[k] is None for k in ('data_date', 'data_time')):
            raise ValueError('missing_quote_time')
    if 'quote_incomplete' in reasons and not any(c['last_price'] is None for c in contracts):
        raise ValueError('incomplete_without_missing_price')
    if not errors and (not result['chain_verified'] or result['cleanup'] != 'unsubscribed'):
        raise ValueError('incomplete_success')
    return result


def _records(response, limit):
    if not ok(response):
        raise ValueError('provider_response')
    data = response[1]
    if len(data) > limit:
        raise ValueError('response_limit')
    records = data if isinstance(data, list) else data.to_dict(orient='records')
    if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
        raise ValueError('provider_records')
    return records


def _identity(code, expiry, right, strike):
    match = CODE.fullmatch(code) if type(code) is str else None
    return bool(match and match[1] == date.fromisoformat(expiry).strftime('%y%m%d')
                and match[2] == {'CALL': 'C', 'PUT': 'P'}.get(right)
                and Decimal(match[3]) / 1000 == Decimal(strike))


def _select(records, expiry):
    candidates = []
    for row in records:
        strike = number(row.get('strike_price'))
        if strike is None:
            raise ValueError('invalid_strike')
        if not MIN_STRIKE <= Decimal(strike) <= MAX_STRIKE:
            continue
        if row.get('option_standard_type') != 'STANDARD' or row.get('suspension') is not False:
            continue
        right = row.get('option_type')
        if (row.get('stock_type') != 'DRVT' or row.get('stock_owner') != UNDERLYING
                or row.get('strike_time') != expiry or right not in ('CALL', 'PUT')
                or number(row.get('lot_size')) is None or Decimal(str(row['lot_size'])) != 100
                or not _identity(row.get('code'), expiry, right, strike)):
            raise ValueError('invalid_identity')
        candidates.append(dict(code=row['code'], expiry=expiry, right=right, strike=strike,
                               shares_per_contract='100', last_price=None,
                               data_date=None, data_time=None))
    selected = []
    for right in ('CALL', 'PUT'):
        matching = [r for r in candidates if r['right'] == right]
        if not matching:
            continue
        selected.append(min(matching, key=lambda r: (abs(Decimal(r['strike']) - 355), r['code'])))
    return selected


def inspect_options(context, sdk, *, checked_at=None, sleep=time.sleep,
                    deadline=None, monotonic=time.monotonic):
    """Inspect one expiry and at most two standard contracts; always close context."""
    observed = checked_at if checked_at is not None else datetime.now(timezone.utc)
    result = dict(kind='options_smoke', underlying=UNDERLYING,
                  checked_at=observed.isoformat(), expiry=None,
                  strike_window={'min': '350', 'max': '360'}, chain_verified=False,
                  contracts=[], source_timezone=SOURCE_ZONE, latency='unverified',
                  cleanup='not_subscribed', cleanup_quota=dict.fromkeys(QUOTA_FIELDS),
                  subscription_attempted=False, errors=[])
    attempted = False
    codes = []
    try:
        try:
            if observed.tzinfo is None:
                raise ValueError('naive_clock')
            today = observed.astimezone(ZoneInfo(SOURCE_ZONE)).date()
            dates = [date.fromisoformat(r['strike_time']) for r in
                     _records(context.get_option_expiration_date(UNDERLYING), 256)]
            dates = [d for d in dates if today <= d <= today + timedelta(days=30)]
            if not dates:
                result['errors'].append('expiry_unavailable')
                return result
            result['expiry'] = min(dates).isoformat()
        except Exception:
            result['errors'].append('expiry_failed')
            return result
        try:
            records = _records(context.get_option_chain(
                UNDERLYING, start=result['expiry'], end=result['expiry'], option_type=sdk.ALL), 2000)
            result['contracts'] = _select(records, result['expiry'])
            if not result['contracts']:
                result['errors'].append('window_empty')
                return result
            result['chain_verified'] = True
            if len(result['contracts']) == 1:
                result['errors'].append('window_partial')
        except Exception:
            result['errors'].append('chain_failed')
            return result
        codes = [r['code'] for r in result['contracts']]
        if deadline is not None and deadline - monotonic() < 75:
            result['errors'].append('budget_exhausted')
            return result
        attempted = True
        result['subscription_attempted'] = True
        try:
            if not ok(context.subscribe(codes, [sdk.QUOTE], is_first_push=False,
                                        subscribe_push=False, extended_time=False, session=sdk.RTH)):
                raise ValueError('subscribe_failed')
        except Exception:
            result['errors'].append('subscribe_failed')
            return result
        try:
            quotes = _records(context.get_stock_quote(codes), 2)
            if len(quotes) != len(codes) or {q.get('code') for q in quotes} != set(codes):
                raise ValueError('quote_identity')
            for contract in result['contracts']:
                quote = next(q for q in quotes if q['code'] == contract['code'])
                if (number(quote.get('strike_price')) is None
                        or Decimal(str(quote['strike_price'])) != Decimal(contract['strike'])
                        or number(quote.get('contract_size')) is None
                        or Decimal(str(quote['contract_size'])) != Decimal(contract['shares_per_contract'])):
                    raise ValueError('quote_identity')
                price = number(quote.get('last_price'))
                quote_date, quote_time = quote.get('data_date'), quote.get('data_time')
                date.fromisoformat(quote_date)
                daytime.fromisoformat(quote_time)
                contract.update(last_price=price, data_date=quote_date, data_time=quote_time)
                if price is None:
                    result['errors'].append('quote_incomplete')
        except Exception:
            result['errors'].append('quote_failed')
    finally:
        if attempted:
            result['cleanup'] = 'release_pending'
            # A failed subscribe can have partial server-side effects too.
            waited = False
            removed = False
            try:
                sleep(61)
                waited = True
            except Exception:
                result['errors'].append('cleanup_wait_failed')
            if waited:
                try:
                    removed = ok(context.unsubscribe(codes, [sdk.QUOTE]))
                    if not removed:
                        result['errors'].append('unsubscribe_failed')
                except Exception:
                    result['errors'].append('unsubscribe_failed')
            # Check counters even if waiting or unsubscribe failed.
            try:
                response = context.query_subscription(is_all_conn=False)
                if not ok(response) or not isinstance(response[1], dict):
                    raise ValueError('quota_failed')
                for field, provider_field in QUOTA_FIELDS.items():
                    value = response[1].get(provider_field)
                    if type(value) is int and 0 <= value <= 9007199254740991:
                        result['cleanup_quota'][field] = value
                if result['cleanup_quota']['own_used'] != 0 or result['cleanup_quota']['own_option_used'] != 0:
                    raise ValueError('quota_remaining')
                if waited and removed:
                    result['cleanup'] = 'unsubscribed'
            except Exception:
                result['errors'].append('cleanup_verify_failed')
        try:
            context.close()
        except Exception:
            result['errors'].append('close_failed')
    return result
