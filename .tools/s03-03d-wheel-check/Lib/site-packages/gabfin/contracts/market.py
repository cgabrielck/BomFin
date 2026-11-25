"""Market facts and provenance; no feed entitlement or trading authorization."""
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import BeforeValidator, Field, StrictInt, model_validator

from gabfin.contracts.common import (
    ContractModel,
    CurrencyCode,
    NonNegativeDecimal,
    OpaqueKey,
    PositiveDecimal,
    UtcTimestamp,
    VersionedContract,
)

NonNegativeCounter = Annotated[StrictInt, Field(ge=0, le=9007199254740991)]
PositiveCounter = Annotated[StrictInt, Field(ge=1, le=9007199254740991)]


class AssetClass(StrEnum):
    EQUITY = "equity"
    OPTION = "option"


class OptionRight(StrEnum):
    CALL = "call"
    PUT = "put"


def _expiry_date(value: object) -> date:
    if isinstance(value, datetime):
        raise ValueError("Option expiry is a date, not an instant")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError("Option expiry must be an ISO date")


class OptionTerms(ContractModel):
    underlying_id: UUID
    expiry: Annotated[date, BeforeValidator(_expiry_date)]
    right: OptionRight
    strike: PositiveDecimal
    multiplier: PositiveDecimal


class Instrument(VersionedContract):
    instrument_id: UUID
    asset_class: AssetClass
    vendor_symbols: dict[OpaqueKey, OpaqueKey] = Field(min_length=1)
    currency: CurrencyCode
    tick_size: PositiveDecimal
    lot_size: PositiveDecimal
    option: OptionTerms | None = None

    @model_validator(mode="after")
    def _option_identity(self) -> Self:
        if (self.asset_class == AssetClass.OPTION) != (self.option is not None):
            raise ValueError("Only options must carry complete option terms")
        if self.option is not None and self.option.underlying_id == self.instrument_id:
            raise ValueError("An option cannot be its own underlying")
        return self


class MarketSession(StrEnum):
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    POST_MARKET = "post_market"
    OVERNIGHT = "overnight"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class QuoteQuality(StrEnum):
    UNKNOWN = "unknown"
    DELAYED = "delayed"
    INDICATIVE = "indicative"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    CLOCK_SKEW = "clock_skew"
    CROSSED = "crossed"
    PERMISSION_DENIED = "permission_denied"
    UNAVAILABLE = "unavailable"


class EntitlementStatus(StrEnum):
    UNKNOWN = "unknown"
    REALTIME = "realtime"
    DELAYED = "delayed"
    INDICATIVE = "indicative"
    DENIED = "denied"


class QuoteEntitlements(ContractModel):
    """Reported metadata; actual capability verification is a service duty."""

    status: EntitlementStatus
    checked_at: UtcTimestamp | None
    capability_snapshot_id: UUID | None = None

    @model_validator(mode="after")
    def _known_status_has_check(self) -> Self:
        if self.status != EntitlementStatus.UNKNOWN and self.checked_at is None:
            raise ValueError("Known entitlement status requires a checked_at timestamp")
        return self


class QuotePoint(ContractModel):
    price: NonNegativeDecimal
    event_at: UtcTimestamp | None
    received_at: UtcTimestamp
    available_at: UtcTimestamp
    age_ms: NonNegativeCounter | None

    @model_validator(mode="after")
    def _local_capture_order(self) -> Self:
        if self.available_at < self.received_at:
            raise ValueError("Quote availability cannot precede local receipt")
        return self


class QuoteSnapshot(VersionedContract):
    """Per-price ages are relative to as_of, never a live wall clock."""

    instrument_id: UUID
    as_of: UtcTimestamp
    feed: OpaqueKey
    session: MarketSession
    bid: QuotePoint | None
    ask: QuotePoint | None
    last: QuotePoint | None
    quality: tuple[QuoteQuality, ...]
    entitlements: QuoteEntitlements

    @model_validator(mode="after")
    def _honest_observations(self) -> Self:
        points = tuple(point for point in (self.bid, self.ask, self.last) if point is not None)
        if not points and QuoteQuality.UNAVAILABLE not in self.quality:
            raise ValueError("An empty quote must be marked unavailable")
        for point in points:
            if point.available_at > self.as_of:
                raise ValueError("Snapshot cannot contain information unavailable at capture")
            if point.event_at is None:
                expected_age = None
                required_flag = QuoteQuality.INCOMPLETE
            elif point.event_at > self.as_of:
                expected_age = None
                required_flag = QuoteQuality.CLOCK_SKEW
            else:
                expected_age = (self.as_of - point.event_at) // timedelta(milliseconds=1)
                required_flag = None
            if point.age_ms != expected_age:
                raise ValueError("Quote age must match its own event time and snapshot as_of")
            if required_flag is not None and required_flag not in self.quality:
                raise ValueError("Unknown or future quote time requires an explicit quality flag")
        if self.bid is not None and self.ask is not None and self.bid.price > self.ask.price:
            if QuoteQuality.CROSSED not in self.quality:
                raise ValueError("Crossed prices require an explicit quality flag")
        if self.entitlements.checked_at is not None and self.entitlements.checked_at > self.as_of:
            raise ValueError("Entitlement check cannot be from after snapshot capture")
        if self.entitlements.status == EntitlementStatus.DENIED:
            if QuoteQuality.PERMISSION_DENIED not in self.quality:
                raise ValueError("Denied permissions must be visible in quote quality")
        return self


class TimeUnit(StrEnum):
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    TRADING_DAY = "trading_day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class Timeframe(ContractModel):
    count: PositiveCounter
    unit: TimeUnit


class BarStatus(StrEnum):
    FORMING = "forming"
    FINAL = "final"
    CORRECTED = "corrected"


class Bar(VersionedContract):
    instrument_id: UUID
    source: OpaqueKey
    timeframe: Timeframe
    session: MarketSession
    start: UtcTimestamp
    end: UtcTimestamp
    open: PositiveDecimal
    high: PositiveDecimal
    low: PositiveDecimal
    close: PositiveDecimal
    volume: NonNegativeDecimal | None
    status: BarStatus
    revision: NonNegativeCounter
    corporate_action_policy: OpaqueKey
    event_at: UtcTimestamp
    received_at: UtcTimestamp
    available_at: UtcTimestamp

    @model_validator(mode="after")
    def _consistent_bar(self) -> Self:
        if self.start >= self.end:
            raise ValueError("Bar interval must have positive length")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError("OHLC values must lie within the low/high range")
        if self.available_at < self.received_at:
            raise ValueError("Bar availability cannot precede local receipt")
        if self.status == BarStatus.CORRECTED and self.revision == 0:
            raise ValueError("A correction requires a positive revision")
        if self.status != BarStatus.FORMING and self.end > self.available_at:
            raise ValueError("A finalized bar cannot end after it became available")
        return self


class TradeTick(VersionedContract):
    """A market print, not an account fill or an instruction to trade."""

    instrument_id: UUID
    price: PositiveDecimal
    quantity: PositiveDecimal
    trade_id: OpaqueKey | None
