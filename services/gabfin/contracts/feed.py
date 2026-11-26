"""Market-state declarations; no trading authority or policy approval service."""
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from gabfin.contracts.common import ContractModel, OpaqueKey, UtcTimestamp, VersionedContract
from gabfin.contracts.market import NonNegativeCounter, PositiveCounter
from gabfin.contracts.events import MarketEvent, QuoteMarketEvent, BarMarketEvent
from gabfin.contracts.subscriptions import SubscriptionKey


class FeedCleanup(VersionedContract):
    source: OpaqueKey
    context_closed: StrictBool
    release_confirmed: StrictBool
    requested_keys: tuple[SubscriptionKey, ...]
    reason_codes: tuple[OpaqueKey, ...]


class SessionWindow(VersionedContract):
    session: Literal['pre_market', 'regular', 'post_market']
    start: UtcTimestamp
    end: UtcTimestamp

    @model_validator(mode='after')
    def positive_interval(self) -> Self:
        if self.start >= self.end:
            raise ValueError('Session must have positive duration')
        return self


class CalendarSnapshot(VersionedContract):
    """Exchange-sourced, finite coverage; absence inside coverage means closed.

    Ingestion supplies verified calendar identity/version. No weekday fallback.
    """
    calendar_id: OpaqueKey
    version: OpaqueKey
    coverage_start: UtcTimestamp
    coverage_end: UtcTimestamp
    windows: tuple[SessionWindow, ...] = Field(max_length=10000)

    @model_validator(mode='after')
    def disjoint_coverage(self) -> Self:
        if self.coverage_start >= self.coverage_end:
            raise ValueError('Invalid calendar coverage')
        previous = self.coverage_start
        for window in self.windows:
            if window.start < previous or window.end > self.coverage_end:
                raise ValueError('Calendar windows must be ordered, disjoint and covered')
            previous = window.end
        return self


class FeedHealth(VersionedContract):
    source: OpaqueKey
    connected: StrictBool
    heartbeat_at: UtcTimestamp | None
    gap_pending: StrictBool
    connection_started_at: UtcTimestamp | None = None


class FreshnessPolicy(VersionedContract):
    """Caller must supply a registry-verified policy; there are no defaults."""
    version: OpaqueKey
    approved: StrictBool
    max_quote_age_ms: PositiveCounter
    max_heartbeat_age_ms: PositiveCounter
    max_entitlement_age_ms: PositiveCounter
    allowed_sessions: tuple[Literal['pre_market', 'regular', 'post_market'], ...] = Field(min_length=1)

    @model_validator(mode='after')
    def distinct_sessions(self) -> Self:
        if len(set(self.allowed_sessions)) != len(self.allowed_sessions):
            raise ValueError('Duplicate session policy')
        return self


class FreshnessDecision(VersionedContract):
    """Data prerequisites only. Risk, account, strategy and execution remain separate."""
    eligible: StrictBool
    reasons: tuple[OpaqueKey, ...] = Field(min_length=1)
    ages_ms: dict[Literal['bid', 'ask', 'last'], NonNegativeCounter | None]
    evaluated_at: UtcTimestamp
    policy_version: OpaqueKey


class RecoveryGap(VersionedContract):
    gap_id: UUID
    source: OpaqueKey
    start: UtcTimestamp
    end: UtcTimestamp | None = None
    reason: OpaqueKey


class MarketCursor(ContractModel):
    epoch: UUID
    sequence: NonNegativeCounter


class MarketUpdate(VersionedContract):
    epoch: UUID
    sequence: PositiveCounter
    processed_at: UtcTimestamp
    event: MarketEvent | None
    health: FeedHealth
    gap: RecoveryGap | None

    @property
    def position(self) -> MarketCursor:
        return MarketCursor(epoch=self.epoch, sequence=self.sequence)


class RecoveryCoverage(ContractModel):
    """Trusted history adapter's pagination/coverage receipt, per subscription.

    This is evidence supplied by a verified adapter, not a claim accepted from
    consumers. Empty history needs an explicit provider/calendar explanation.
    """
    key: SubscriptionKey
    start: UtcTimestamp
    end: UtcTimestamp
    record_count: NonNegativeCounter
    complete: StrictBool
    has_more: StrictBool
    empty_reason: Literal['provider_verified_empty', 'market_closed'] | None = None

    @model_validator(mode='after')
    def valid_receipt(self) -> Self:
        if self.start > self.end:
            raise ValueError('Invalid coverage interval')
        if self.complete and (self.record_count == 0) != (self.empty_reason is not None):
            raise ValueError('Complete empty coverage needs an explicit explanation')
        return self


class RecoveryBatch(VersionedContract):
    gap_id: UUID
    source: OpaqueKey
    start: UtcTimestamp
    end: UtcTimestamp
    complete: StrictBool
    evidence: OpaqueKey
    mode: Literal['history', 'quote_snapshot'] = 'history'
    events: tuple[MarketEvent, ...] = Field(max_length=10000)
    coverage: tuple[RecoveryCoverage, ...] = Field(default=(), max_length=3000)


class MarketSnapshot(VersionedContract):
    epoch: UUID
    cursor: NonNegativeCounter
    as_of: UtcTimestamp
    quotes: tuple[QuoteMarketEvent, ...]
    bars: tuple[BarMarketEvent, ...]
    health: FeedHealth
    gap: RecoveryGap | None

    @property
    def position(self) -> MarketCursor:
        return MarketCursor(epoch=self.epoch, sequence=self.cursor)
