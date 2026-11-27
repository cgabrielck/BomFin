"""The Alpaca feed guard: SIP boundary, degradation, and entitlement errors."""
from datetime import datetime, timedelta, timezone

import pytest

from gabfin.providers.alpaca import feed_guard

NOW = datetime(2026, 11, 27, 12, 0, 30, tzinfo=timezone.utc)


def test_sip_window_is_fifteen_minutes_back():
    safe = feed_guard.sip_history_window(NOW)
    assert safe == datetime(2026, 11, 27, 11, 45, tzinfo=timezone.utc)


def test_sip_window_is_floored_to_the_minute():
    stamp = datetime(2026, 11, 27, 12, 0, 59, 999, tzinfo=timezone.utc)
    safe = feed_guard.sip_history_window(stamp)
    assert safe.second == 0
    assert safe.microsecond == 0
    assert safe == datetime(2026, 11, 27, 11, 45, tzinfo=timezone.utc)


def test_sip_window_needs_an_aware_clock():
    with pytest.raises(ValueError):
        feed_guard.sip_history_window(datetime(2026, 11, 27, 12, 0))


def test_sip_beyond_the_window_degrades_to_iex_with_a_reason():
    decision = feed_guard.resolve_feed(
        'sip', NOW, end=NOW - timedelta(minutes=5)
    )
    assert decision.feed == 'iex'
    assert decision.degraded is True
    assert decision.requested == 'sip'
    assert decision.reason == 'sip_recent_data_requires_algo_trader_plus'


def test_sip_outside_the_window_is_served_as_sip():
    decision = feed_guard.resolve_feed(
        'sip', NOW, end=NOW - timedelta(minutes=20)
    )
    assert decision.feed == 'sip'
    assert decision.degraded is False
    assert decision.reason is None


def test_sip_at_the_exact_boundary_is_served_as_sip():
    safe = feed_guard.sip_history_window(NOW)
    decision = feed_guard.resolve_feed('sip', NOW, end=safe)
    assert decision.feed == 'sip'
    assert decision.degraded is False


def test_a_sip_request_without_an_end_is_degraded():
    decision = feed_guard.resolve_feed('sip', NOW)
    assert decision.feed == 'sip'
    assert decision.degraded is True
    assert decision.reason == 'sip_end_unspecified_recent_data_unavailable'


def test_iex_is_never_degraded():
    decision = feed_guard.resolve_feed('iex', NOW, end=NOW)
    assert decision.feed == 'iex'
    assert decision.degraded is False


def test_opra_is_refused_rather_than_degraded():
    with pytest.raises(feed_guard.FeedDenied) as error:
        feed_guard.resolve_feed('opra', NOW, end=NOW)
    assert error.value.reason == 'opra_entitlement_missing'
    assert 'Algo Trader Plus' in str(error.value)


def test_an_unknown_feed_is_refused():
    with pytest.raises(feed_guard.FeedUnavailable) as error:
        feed_guard.resolve_feed('nbbo', NOW, end=NOW)
    assert error.value.reason == 'unknown_feed'


def test_the_sip_forbidden_message_is_an_entitlement_not_no_data():
    message = feed_guard.SIP_FORBIDDEN_CODE
    assert feed_guard.classify_status(403, message) == 'entitlement'
    assert feed_guard.is_entitlement_message(message) is True


def test_the_opra_forbidden_message_is_an_entitlement():
    message = feed_guard.OPRA_FORBIDDEN_CODE
    assert feed_guard.classify_status(403, message) == 'entitlement'


def test_a_generic_forbidden_is_still_an_entitlement():
    assert feed_guard.classify_status(403, 'subscription does not permit') == (
        'entitlement'
    )


def test_an_empty_body_is_not_an_entitlement():
    assert feed_guard.classify_status(403, '') == 'unknown'
    assert feed_guard.classify_status(200, '') == 'unknown'


def test_rate_limiting_is_classified_separately():
    assert feed_guard.classify_status(429, 'too many requests') == 'rate_limited'


def test_an_entitlement_note_names_the_required_plan():
    note = feed_guard.entitlement_note(403, feed_guard.OPRA_FORBIDDEN_CODE)
    assert 'Algo Trader Plus' in note
    assert feed_guard.entitlement_note(403, '') is None


def test_a_decision_serializes_for_the_api():
    decision = feed_guard.resolve_feed('sip', NOW, end=NOW)
    payload = decision.as_dict()
    assert payload['feed'] == 'iex'
    assert payload['degraded'] is True
    assert payload['reason']
