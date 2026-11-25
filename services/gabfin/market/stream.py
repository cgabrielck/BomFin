"""One-instrument, one-consumer latest quote stream, owned by one event loop.

Quotes are complete observations. Coalescing is deliberately unsuitable for
trades, fills or volume aggregation. No freshness/entry authorization lives here.
"""
import asyncio
from uuid import UUID
from gabfin.contracts.events import QuoteMarketEvent


class QuoteStream:
    def __init__(self, instrument_id: UUID):
        self._id = instrument_id
        self._latest: QuoteMarketEvent | None = None
        self._pending: QuoteMarketEvent | None = None
        self._changed = asyncio.Event()
        self._closed = False
        self._reading = False
        self.accepted = 0
        self.rejected = 0
        self.coalesced = 0

    def apply(self, event: QuoteMarketEvent) -> bool:
        """Apply typed observations; source clocks ahead cannot poison ordering.

        Equal source times with different provider dedup keys can be corrections.
        """
        try:
            if not isinstance(event, QuoteMarketEvent):
                raise ValueError('typed_quote_required')
            if self._closed or event.instrument_id != self._id:
                raise ValueError('inactive_or_foreign_quote')
            if event.event_at > event.received_at:
                raise ValueError('source_clock_ahead')
            if self._latest is not None and (event.event_at < self._latest.event_at
                                            or event.dedup_key == self._latest.dedup_key):
                raise ValueError('late_or_duplicate_quote')
        except (ValueError, TypeError, OverflowError):
            self.rejected += 1
            return False
        event = event.model_copy(deep=True)
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
