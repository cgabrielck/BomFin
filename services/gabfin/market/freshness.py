"""Read-time freshness: a healthy connection cannot refresh an old market price."""
from datetime import timedelta
from pydantic import TypeAdapter

from gabfin.contracts.common import UtcTimestamp
from gabfin.contracts.feed import FeedHealth, FreshnessPolicy, FreshnessDecision, CalendarSnapshot, MarketSnapshot
from gabfin.contracts.market import QuoteSnapshot


def entry_eligible(snapshot: QuoteSnapshot | MarketSnapshot, policy: FreshnessPolicy, now,
                   *, health: FeedHealth | None = None, calendar: CalendarSnapshot | None = None) -> FreshnessDecision:
    """Evaluate data only, using explicit caller-verified policy and rights.

    Receipt clocks and heartbeat clocks never replace per-price source clocks.
    Returned ages are relative to now; the original snapshot is unchanged.
    """
    now = TypeAdapter(UtcTimestamp).validate_python(now)
    reasons = []
    if isinstance(snapshot, MarketSnapshot):
        health = snapshot.health
        if snapshot.gap is not None:
            reasons.append('gap_pending')
        if snapshot.as_of > now:
            reasons.append('snapshot_from_future')
        if len(snapshot.quotes) != 1:
            return FreshnessDecision(schema_version='1.0', eligible=False,
                reasons=('quote_selection_required',), ages_ms=dict(bid=None, ask=None, last=None),
                evaluated_at=now, policy_version=policy.version)
        event = snapshot.quotes[0]
        if event.event_at > event.received_at:
            reasons.append('quote_clock_skew')
        snapshot = event.payload
    if not policy.approved:
        reasons.append('policy_unapproved')
    if health is None:
        reasons.append('health_unverified')
    else:
        if snapshot.feed != health.source:
            reasons.append('health_source_mismatch')
        if not health.connected:
            reasons.append('disconnected')
        if health.gap_pending:
            reasons.append('gap_pending')
        heartbeat = health.heartbeat_at
        if heartbeat is None or now - heartbeat > timedelta(milliseconds=policy.max_heartbeat_age_ms):
            reasons.append('heartbeat_stale')
        elif heartbeat > now:
            reasons.append('heartbeat_clock_skew')
    if calendar is None:
        reasons.append('calendar_unverified')
    elif not calendar.coverage_start <= now < calendar.coverage_end:
        reasons.append('calendar_unavailable')
    else:
        current = next((window for window in calendar.windows if window.start <= now < window.end), None)
        if current is None:
            reasons.append('market_closed')
        elif current.session != snapshot.session:
            reasons.append('session_mismatch')
        elif current.session not in policy.allowed_sessions:
            reasons.append('session_ineligible')
    if snapshot.session not in policy.allowed_sessions:
        reasons.append('session_ineligible')
    if snapshot.as_of > now:
        reasons.append('snapshot_from_future')
    entitlement = snapshot.entitlements
    if entitlement.status != 'realtime':
        reasons.append('realtime_unverified')
    if (entitlement.checked_at is None or entitlement.checked_at > now
            or now - entitlement.checked_at > timedelta(milliseconds=policy.max_entitlement_age_ms)
            or entitlement.capability_snapshot_id is None):
        reasons.append('entitlement_unverified')
    if snapshot.quality:
        reasons.append('quote_quality_flagged')
    ages = {}
    for name in ('bid', 'ask', 'last'):
        point = getattr(snapshot, name)
        if point is None or point.event_at is None:
            ages[name] = None
            reasons.append('quote_incomplete')
        elif (point.event_at > now or point.event_at > point.received_at
              or point.available_at > now or point.received_at > now):
            ages[name] = None
            reasons.append('quote_clock_skew')
        else:
            age = (now - point.event_at) // timedelta(milliseconds=1)
            ages[name] = age
            if age > policy.max_quote_age_ms:
                reasons.append('quote_stale')
            if point.price <= 0:
                reasons.append('quote_nonpositive')
    unique = tuple(dict.fromkeys(reasons))
    return FreshnessDecision(schema_version='1.0', eligible=not unique,
                             reasons=unique or ('data_checks_passed',), ages_ms=ages,
                             evaluated_at=now, policy_version=policy.version)
