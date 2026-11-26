"""Alpaca feed entitlement guard; decides what a query may ask for.

This module never talks to Alpaca. It answers one question locally: given
a requested feed and a requested end time, what feed may actually be
queried, and why did it change.

The free tier can read SIP history only up to fifteen minutes in the past.
Asking for anything more recent returns HTTP 403 with a specific message.
That is an **entitlement** failure, not "no data", and the two must never
be confused: a caller that treats it as empty data will conclude the
symbol never traded.

OPRA is a different matter. It is not degraded, it is absent: the free
tier has no OPRA entitlement at all, so there is nothing to fall back to.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SIP = 'sip'
IEX = 'iex'
OPRA = 'opra'

#: How far back the free tier may safely query SIP data.
SIP_DELAY = timedelta(minutes=15)

#: The message Alpaca returns when the SIP window is exceeded.
SIP_FORBIDDEN_CODE = 'subscription does not permit querying recent SIP data'

#: The message Alpaca returns when the account has no OPRA entitlement.
OPRA_FORBIDDEN_CODE = 'subscription does not permit querying OPRA data'

#: The upgrade Alpaca's OPRA access requires.
OPRA_REQUIRED_PLAN = 'Algo Trader Plus'


class FeedUnavailable(ValueError):
    """A feed cannot be served and no fallback exists.

    Carries the reason so a caller can report it without inspecting the
    message text.
    """

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


class FeedDenied(FeedUnavailable):
    """The account lacks the entitlement for a feed it asked for."""


@dataclass(frozen=True)
class FeedDecision:
    """The feed to query, and what changed from the request."""

    feed: str
    requested: str
    degraded: bool
    reason: str | None = None

    def as_dict(self) -> dict:
        return {
            'feed': self.feed,
            'requested': self.requested,
            'degraded': self.degraded,
            'reason': self.reason,
        }


def sip_history_window(now: datetime) -> datetime:
    """The most recent instant the free tier may safely query SIP data.

    The result is floored to the minute, because Alpaca's SIP cutoff is
    observed at minute granularity and a request a few seconds newer would
    be rejected.
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError('An aware clock is required to bound the SIP window')
    safe = now - SIP_DELAY
    return safe.replace(second=0, microsecond=0)


def resolve_feed(
    requested: str,
    now: datetime,
    *,
    end: datetime | None = None,
) -> FeedDecision:
    """Decide which feed may be queried for a request ending at `end`.

    `end=None` means the request asks for the most recent data possible.
    A SIP request that reaches inside the delay window degrades to IEX and
    says so. A SIP request that stays outside the window is served as SIP.
    """
    if requested not in (SIP, IEX, OPRA):
        raise FeedUnavailable(
            'unknown_feed', f'Unknown feed: {requested}'
        )
    if requested == OPRA:
        raise FeedDenied(
            'opra_entitlement_missing',
            f'OPRA data requires the {OPRA_REQUIRED_PLAN} plan',
        )
    if requested == IEX:
        return FeedDecision(feed=IEX, requested=IEX, degraded=False)
    if end is None:
        return FeedDecision(
            feed=SIP,
            requested=SIP,
            degraded=True,
            reason='sip_end_unspecified_recent_data_unavailable',
        )
    if not isinstance(end, datetime) or end.tzinfo is None:
        raise ValueError('An aware end time is required to bound the SIP window')
    safe = sip_history_window(now)
    if end > safe:
        return FeedDecision(
            feed=IEX,
            requested=SIP,
            degraded=True,
            reason='sip_recent_data_requires_algo_trader_plus',
        )
    return FeedDecision(feed=SIP, requested=SIP, degraded=False)


def classify_status(status: int, message: str) -> str:
    """Classify a failed Alpaca response as an entitlement or data problem.

    Returns one of: `entitlement`, `no_data`, `rate_limited`, `unknown`.
    The distinction matters: `entitlement` means the plan must change,
    `no_data` means the query was fine and the range was empty.
    """
    if status == 429:
        return 'rate_limited'
    if status != 403:
        return 'unknown'
    text = (message or '').lower()
    if SIP_FORBIDDEN_CODE.lower() in text or OPRA_FORBIDDEN_CODE.lower() in text:
        return 'entitlement'
    if 'subscription does not permit' in text:
        return 'entitlement'
    return 'unknown'


def is_entitlement_message(message: str) -> bool:
    """Whether a message describes an entitlement failure rather than no data."""
    return classify_status(403, message) == 'entitlement'


def entitlement_note(status: int, message: str) -> str | None:
    """A human-readable note for a denied query, or None if it is not a denial."""
    if classify_status(status, message) != 'entitlement':
        return None
    if OPRA_FORBIDDEN_CODE.lower() in (message or '').lower():
        return f'OPRA data requires the {OPRA_REQUIRED_PLAN} plan'
    return 'The account plan does not cover the requested feed'


def utcnow() -> datetime:
    """The current instant, used only where a caller supplies no clock."""
    return datetime.now(timezone.utc)
