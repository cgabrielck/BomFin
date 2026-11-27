from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest

from gabfin.contracts.market import QuoteSnapshot
from gabfin.market.freshness import FeedHealth, FreshnessPolicy, entry_eligible
from gabfin.contracts.feed import CalendarSnapshot

NOW = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)
ID = uuid4()


def calendar():
    return CalendarSnapshot(schema_version='1.0', calendar_id='fixture-XNYS', version='2026',
        coverage_start=NOW.replace(hour=0), coverage_end=NOW + timedelta(days=1),
        windows=[dict(schema_version='1.0', session='regular', start=NOW.replace(hour=14, minute=30),
                      end=NOW.replace(hour=21, minute=0))])


def quote():
    point = dict(price='100', event_at=NOW - timedelta(seconds=2),
                 received_at=NOW, available_at=NOW, age_ms=2000)
    return QuoteSnapshot(schema_version='1.0', instrument_id=ID, as_of=NOW,
                         feed='futu', session='regular', bid=point, ask=point, last=point,
                         quality=(), entitlements=dict(status='realtime', checked_at=NOW,
                                                       capability_snapshot_id=uuid4()))


def policy():
    return FreshnessPolicy(schema_version='1.0', version='test-only', approved=True,
                           max_quote_age_ms=5000, max_heartbeat_age_ms=3000,
                           max_entitlement_age_ms=60000, allowed_sessions=('regular',))


def test_healthy_heartbeat_does_not_make_an_old_quote_fresh():
    health = FeedHealth(schema_version='1.0', source='futu', connected=True,
                        heartbeat_at=NOW + timedelta(seconds=10), gap_pending=False)
    decision = entry_eligible(quote(), policy(), now=NOW + timedelta(seconds=10), health=health, calendar=calendar())
    assert not decision.eligible
    assert 'quote_stale' in decision.reasons
    assert 'heartbeat_stale' not in decision.reasons
    assert decision.ages_ms == {'bid': 12000, 'ask': 12000, 'last': 12000}


def health(**kwargs):
    return FeedHealth(schema_version='1.0', source='futu', connected=True, heartbeat_at=NOW,
                      gap_pending=False).model_copy(update=kwargs)


def test_current_complete_quote_only_passes_data_checks():
    result = entry_eligible(quote(), policy(), now=NOW, health=health(), calendar=calendar())
    assert result.eligible and result.reasons == ('data_checks_passed',)


@pytest.mark.parametrize('change,reason', [
    ({'connected': False}, 'disconnected'), ({'gap_pending': True}, 'gap_pending'),
    ({'heartbeat_at': None}, 'heartbeat_stale'),
    ({'heartbeat_at': NOW - timedelta(seconds=4)}, 'heartbeat_stale'),
    ({'heartbeat_at': NOW + timedelta(seconds=1)}, 'heartbeat_clock_skew'),
    ({'source': 'other'}, 'health_source_mismatch'),
])
def test_health_problems_block_new_entries(change, reason):
    result = entry_eligible(quote(), policy(), now=NOW, health=health(**change), calendar=calendar())
    assert not result.eligible and reason in result.reasons


@pytest.mark.parametrize('status', ['unknown', 'delayed', 'indicative', 'denied'])
def test_non_realtime_rights_never_pass_even_with_recent_ticks(status):
    data = quote().model_dump()
    data['entitlements']['status'] = status
    if status == 'denied': data['quality'] = ('permission_denied',)
    result = entry_eligible(QuoteSnapshot.model_validate(data), policy(), now=NOW, health=health(), calendar=calendar())
    assert not result.eligible and 'realtime_unverified' in result.reasons


@pytest.mark.parametrize('session', ['closed', 'unknown', 'pre_market', 'post_market'])
def test_session_and_draft_policy_fail_closed(session):
    result = entry_eligible(quote().model_copy(update={'session': session}),
                            policy().model_copy(update={'approved': False}), now=NOW, health=health(), calendar=calendar())
    assert not result.eligible
    assert {'session_ineligible', 'policy_unapproved'} <= set(result.reasons)


def test_missing_bbo_and_old_entitlement_do_not_borrow_last_trade_freshness():
    value = quote().model_copy(update={'bid': None, 'ask': None})
    value = value.model_copy(update={'entitlements': value.entitlements.model_copy(
        update={'checked_at': NOW - timedelta(hours=1)})})
    result = entry_eligible(value, policy(), now=NOW, health=health(), calendar=calendar())
    assert not result.eligible
    assert {'quote_incomplete', 'entitlement_unverified'} <= set(result.reasons)


def test_no_new_market_event_is_not_reported_as_a_dead_connection():
    result = entry_eligible(quote(), policy(), now=NOW + timedelta(seconds=4),
                            health=health(heartbeat_at=NOW + timedelta(seconds=4)), calendar=calendar())
    assert result.reasons == ('quote_stale',)


def test_read_time_market_close_cannot_borrow_capture_session():
    captured = NOW.replace(hour=20, minute=59, second=59)
    data = quote().model_dump()
    point = dict(price='100', event_at=captured, received_at=captured,
                 available_at=captured, age_ms=0)
    data.update(as_of=captured, bid=point, ask=point, last=point)
    data['entitlements']['checked_at'] = captured
    value = QuoteSnapshot.model_validate(data)
    now = captured + timedelta(seconds=2)
    result = entry_eligible(value, policy(), now, health=health(heartbeat_at=now), calendar=calendar())
    assert not result.eligible and 'market_closed' in result.reasons


def test_source_time_ahead_of_its_receipt_is_rejected_even_when_now_is_later():
    data = quote().model_dump()
    for name in ('bid', 'ask', 'last'):
        data[name]['received_at'] = NOW - timedelta(seconds=3)
    result = entry_eligible(QuoteSnapshot.model_validate(data), policy(), NOW,
                            health=health(), calendar=calendar())
    assert not result.eligible and 'quote_clock_skew' in result.reasons


def test_original_three_argument_interface_fails_closed_without_context():
    result = entry_eligible(quote(), policy(), NOW)
    assert not result.eligible and 'health_unverified' in result.reasons
