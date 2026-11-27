"""Typed source events; identity/provenance checks, not a deduplication store."""
from typing import Annotated, Generic, Literal, Self, TypeVar
from uuid import UUID

from pydantic import Field, model_validator

from gabfin.contracts.common import OpaqueKey, UtcTimestamp, VersionedContract
from gabfin.contracts.market import Bar, QuoteSnapshot, TradeTick

Payload = TypeVar("Payload", QuoteSnapshot, TradeTick, Bar)


class _MarketEnvelope(VersionedContract, Generic[Payload]):
    event_id: UUID
    instrument_id: UUID
    event_at: UtcTimestamp
    received_at: UtcTimestamp
    available_at: UtcTimestamp
    source: OpaqueKey
    source_seq: OpaqueKey | None
    dedup_key: OpaqueKey
    payload: Payload

    @model_validator(mode="after")
    def _capture_and_identity(self) -> Self:
        if self.available_at < self.received_at:
            raise ValueError("Event availability cannot precede local receipt")
        if self.instrument_id != self.payload.instrument_id:
            raise ValueError("Envelope instrument must match its typed payload")
        # Source clocks can be skewed and events can arrive late/out of order.
        # Do not compare event_at to the local receipt clock here.
        return self


class QuoteMarketEvent(_MarketEnvelope[QuoteSnapshot]):
    kind: Literal["quote"]

    @model_validator(mode="after")
    def _quote_provenance(self) -> Self:
        if self.source != self.payload.feed:
            raise ValueError("Envelope cannot relabel the quote feed")
        if self.payload.as_of > self.available_at:
            raise ValueError("Quote event cannot be available before snapshot capture")
        return self


class TradeMarketEvent(_MarketEnvelope[TradeTick]):
    kind: Literal["trade"]


class BarMarketEvent(_MarketEnvelope[Bar]):
    kind: Literal["bar"]

    @model_validator(mode="after")
    def _bar_provenance(self) -> Self:
        if self.source != self.payload.source:
            raise ValueError("Envelope cannot relabel the bar source")
        if any(
            getattr(self, field) != getattr(self.payload, field)
            for field in ("event_at", "received_at", "available_at")
        ):
            raise ValueError("Bar envelope must retain payload capture timestamps")
        return self


MarketEvent = Annotated[
    QuoteMarketEvent | TradeMarketEvent | BarMarketEvent,
    Field(discriminator="kind"),
]
