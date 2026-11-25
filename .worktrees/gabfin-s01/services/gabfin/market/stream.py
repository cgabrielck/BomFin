"""One-instrument, one-consumer latest quote stream, owned by one event loop.

Quotes are complete observations. Coalescing is deliberately unsuitable for
trades, fills or volume aggregation. No freshness/entry authorization lives here.
"""
import asyncio
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import Field, StrictInt

from gabfin.contracts.common import ContractModel, NonNegativeDecimal, UtcTimestamp
from gabfin.contracts.events import QuoteMarketEvent
from gabfin.contracts.market import QuoteSnapshot, QuotePoint, QuoteEntitlements


class _QuoteWire(ContractModel):
    version: StrictInt = Field(ge=1, le=1)
    kind: Literal['quote']
    code: str = Field(max_length=100)
    price: NonNegativeDecimal
    event_at: UtcTimestamp
    received_at: UtcTimestamp


class QuoteStream:
    def __init__(self, instrument_id: UUID, symbol: str):
        self._id = instrument_id
        self._symbol = symbol
        self._latest: QuoteMarketEvent | None = None
        self._pending: QuoteMarketEvent | None = None
        self._changed = asyncio.Event()
        self._closed = False
        self._reading = False
        self.accepted = 0
        self.rejected = 0
        self.coalesced = 0

    def accept(self, message: dict, *, available_at: datetime) -> bool:
        """Accept a sanitized SDK callback. Invalid/late/duplicate input is counted.

        Source clock skew is rejected, rather than poisoning latest ordering.
        Equal source times with changed prices remain legitimate corrections.
        """
        try:
            quote = _QuoteWire.model_validate(message)
            if self._closed or quote.code != self._symbol:
                raise ValueError('inactive_or_foreign_quote')
            if quote.event_at > quote.received_at:
                raise ValueError('source_clock_ahead')
            point = QuotePoint(price=quote.price, event_at=quote.event_at,
                               received_at=quote.received_at, available_at=available_at,
                               age_ms=(available_at - quote.event_at) // timedelta(milliseconds=1))
            sign, digits, exponent = quote.price.as_tuple()
            digits = list(digits)
            while digits and digits[-1] == 0:
                digits.pop()
                exponent += 1
            price_key = f'{sign}:{digits}:{exponent}' if digits else 'zero'
            digest = sha256(f'{quote.code}|{quote.event_at.isoformat()}|{price_key}'.encode()).hexdigest()
            key = 'futu:quote:' + digest
            event = QuoteMarketEvent(
                schema_version='1.0', kind='quote', event_id=uuid5(NAMESPACE_URL, key),
                instrument_id=self._id, event_at=quote.event_at, received_at=quote.received_at,
                available_at=available_at, source='futu', source_seq=None, dedup_key=key,
                payload=QuoteSnapshot(schema_version='1.0', instrument_id=self._id,
                                      as_of=available_at, feed='futu', session='unknown',
                                      bid=None, ask=None, last=point, quality=('unknown', 'incomplete'),
                                      entitlements=QuoteEntitlements(status='unknown', checked_at=None)))
            if self._latest is not None and (event.event_at < self._latest.event_at
                                            or event.dedup_key == self._latest.dedup_key):
                raise ValueError('late_or_duplicate_quote')
        except (ValueError, TypeError, OverflowError):
            self.rejected += 1
            return False
        self._latest = event
        if self._pending is not None:
            self.coalesced += 1
        self._pending = event
        self.accepted += 1
        self._changed.set()
        return True

    def snapshot(self) -> QuoteMarketEvent | None:
        return self._latest.model_copy(deep=True) if self._latest is not None else None

    @property
    def pending_count(self) -> int:
        return int(self._pending is not None)

    def close(self) -> None:
        self._closed = True
        self._changed.set()

    async def events(self):
        if self._reading:
            raise RuntimeError('One event consumer is supported; use snapshot for reads')
        self._reading = True
        try:
            while True:
                if self._pending is not None:
                    value = self._pending
                    self._pending = None
                    yield value.model_copy(deep=True)
                elif self._closed:
                    return
                else:
                    self._changed.clear()
                    await self._changed.wait()
        finally:
            self._reading = False
