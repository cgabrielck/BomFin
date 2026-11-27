"""Massive WebSocket quote adapter (Stocks, quote channel only).

Quote-only slice. Connects to the Massive WebSocket, subscribes to one
equity symbol, and converts `Q.<symbol>` messages into typed quote events.
The supervisor owns reconnects and the adapter is single-use.

Wire format (from the Massive WebSocket guide):
  subscribe:  {"action":"subscribe","params":"Q.AAPL"}
  ack/error:  {"status":"ok"|"error", ...}
  quote push: JSON object or array of objects with ev="Q", sym, bp, ap, t (ms).
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from gabfin.contracts.events import QuoteMarketEvent
from gabfin.contracts.feed import FeedCleanup, FeedHealth
from gabfin.contracts.market import (
    EntitlementStatus,
    MarketSession,
    QuoteEntitlements,
    QuotePoint,
    QuoteQuality,
    QuoteSnapshot,
)
from gabfin.contracts.subscriptions import FeedCapabilities, SubscriptionKey
from gabfin.market.stream import QuoteStream

logger = logging.getLogger(__name__)

SOURCE = 'massive'

def parse_quote_message(raw: str, *, symbol: str, instrument_id: UUID,
                        received_at: datetime) -> QuoteMarketEvent | None:
    """Convert one Massive text frame into a QuoteMarketEvent, or None.

    Non-quote frames (acks, other channels, other symbols) return None.
    Malformed quote frames also return None so one bad frame cannot kill the feed.
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        if not isinstance(item, dict) or item.get('ev') != 'Q' or item.get('sym') != symbol:
            continue
        try:
            return _quote_event(item, symbol=symbol, instrument_id=instrument_id, received_at=received_at)
        except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError):
            logger.debug('dropped malformed quote frame')
            return None
    return None


def _quote_event(item: dict, *, symbol: str, instrument_id: UUID,
                 received_at: datetime) -> QuoteMarketEvent:
    event_at = datetime.fromtimestamp(int(item['t']) / 1000, tz=timezone.utc)
    bid = _point(item.get('bp'), event_at, received_at)
    ask = _point(item.get('ap'), event_at, received_at)
    if bid is None and ask is None:
        raise ValueError('quote without prices')
    as_of = received_at
    quality = [] if event_at <= received_at else [QuoteQuality.CLOCK_SKEW]
    if bid is not None and ask is not None and bid.price > ask.price:
        quality.append(QuoteQuality.CROSSED)
    snapshot = QuoteSnapshot(
        schema_version='1.0',
        instrument_id=instrument_id,
        as_of=as_of,
        feed=SOURCE,
        session=MarketSession.UNKNOWN,
        bid=bid,
        ask=ask,
        last=None,
        quality=tuple(quality),
        entitlements=QuoteEntitlements(status=EntitlementStatus.UNKNOWN, checked_at=None),
    )
    return QuoteMarketEvent(
        schema_version='1.0',
        kind='quote',
        event_id=uuid4(),
        instrument_id=instrument_id,
        event_at=event_at,
        received_at=received_at,
        available_at=received_at,
        source=SOURCE,
        source_seq=str(item['t']),
        dedup_key=f'{SOURCE}:{symbol}:{item["t"]}:{item.get("bp")}:{item.get("ap")}',
        payload=snapshot,
    )


def _point(value, event_at: datetime, received_at: datetime) -> QuotePoint | None:
    if value is None:
        return None
    price = Decimal(str(value))
    if not price.is_finite() or price < 0:
        raise ValueError('invalid price')
    # Age is relative to snapshot as_of (= received_at). A future event time has no
    # valid age; QuoteSnapshot requires age_ms=None there and a CLOCK_SKEW quality flag.
    age_ms = None if event_at > received_at else int((received_at - event_at) / timedelta(milliseconds=1))
    return QuotePoint(price=price, event_at=event_at, received_at=received_at,
                      available_at=received_at, age_ms=age_ms)


class MassiveQuoteAdapter:
    """Single-use, quote-only Massive adapter for one US equity symbol."""

    def __init__(self, *, instrument_id: UUID, symbol: str, config=None,
                 api_key: str | None = None, ws_url: str | None = None, _connect=None):
        from gabfin.providers.massive.config import load_config
        if config is not None or (api_key is None and ws_url is None):
            config = config or load_config()
            api_key = config.api_key.get_secret_value()
            ws_url = config.ws_url
        if config is None:
            from gabfin.providers.massive.config import MassiveConfig
            from urllib.parse import urlsplit
            parts = urlsplit(ws_url or '')
            config = MassiveConfig(base_url=('https' if parts.scheme == 'wss' else 'http') + '://' + parts.netloc,
                                   api_key=api_key or '', ws_path=parts.path or '/ws')
        self._config = config
        self._session_closed = True
        self._requested = ()
        self._cleanup = None
        self._max_subscriptions = config.max_subscriptions
        if not symbol or not symbol.isalpha() or len(symbol) > 10:
            raise ValueError('One plain US equity symbol is required')
        if not api_key:
            raise ValueError('Massive API key is required')
        if not ws_url or not ws_url.startswith('wss://'):
            raise ValueError('Massive WebSocket URL must use wss://')
        self._instrument_id = instrument_id
        self._symbol = symbol.upper()
        self._api_key = api_key
        self._ws_url = ws_url
        self._connect = _connect  # injection point for tests
        self._stream = QuoteStream(instrument_id)
        self._task: asyncio.Task | None = None
        self._ready: asyncio.Future | None = None
        self._closed = False
        self._started = False
        self._rejected_frames = 0
        self._reconnects = 0
        self.failure: str | None = None
        self._health = FeedHealth(schema_version='1.0', source=SOURCE, connected=False,
                                  heartbeat_at=None, gap_pending=True)

    @property
    def key(self) -> SubscriptionKey:
        return SubscriptionKey(instrument_id=self._instrument_id, channel='quote', timeframe=None)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def health(self) -> FeedHealth:
        return self._health.model_copy(deep=True)

    @property
    def stats(self) -> dict:
        return dict(accepted=self._stream.accepted, rejected=self._stream.rejected + self._rejected_frames,
                    coalesced=self._stream.coalesced, pending=self._stream.pending_count,
                    reconnects=self._reconnects)

    def snapshot(self):
        return self._stream.snapshot()

    async def capabilities(self) -> FeedCapabilities:
        return FeedCapabilities(schema_version='1.0', source=SOURCE, asset_classes=('equity',),
                                sessions=(), latency_label='unknown', max_subscriptions=self._max_subscriptions,
                                history_limits=(), checked_at=datetime.now(timezone.utc),
                                permission_errors=('entitlement_unverified',))

    async def subscribe(self, keys: list[SubscriptionKey]) -> None:
        if not keys:
            return
        if any(k.identity != self.key.identity for k in keys):
            raise ValueError('Only the configured equity quote key is supported')
        if self._closed or self._started:
            raise RuntimeError('Adapter is single-use')
        self._requested = tuple(keys)
        self._started = True
        loop = asyncio.get_running_loop()
        self._ready = loop.create_future()
        self._task = asyncio.create_task(self._run())
        try:
            async with asyncio.timeout(10):
                await asyncio.shield(self._ready)
        except BaseException:
            self._closed = True
            self.failure = self.failure or 'subscribe_failed'
            self._task.cancel()
            raise

    @property
    def cleanup(self):
        return self._cleanup.model_copy(deep=True) if self._cleanup else None

    async def unsubscribe(self, keys):
        if any(key.identity != self.key.identity for key in keys):
            raise ValueError('Unknown quote key')
        if keys:
            await self.close()

    async def events(self):
        try:
            async for event in self._stream.events():
                yield event
        finally:
            await self.close()
        if self.failure:
            raise RuntimeError(self.failure)

    async def close(self) -> None:
        self._closed = True
        self._stream.close()
        self._health = self._health.model_copy(update={'connected': False})
        if self._task is not None and not self._task.done():
            if not self._task.cancelling():
                self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._cleanup = FeedCleanup(schema_version='1.0', source=SOURCE,
            context_closed=self._session_closed, release_confirmed=self._session_closed,
            requested_keys=self._requested,
            reason_codes=('connection_closed',) if self._session_closed else ('cleanup_unverified',))

    async def _run(self) -> None:
        try:
            await self._session()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.failure = 'connection_failed'
            logger.warning('massive session error: %s', type(exc).__name__)
            if self._ready is not None and not self._ready.done():
                self._ready.set_exception(RuntimeError('subscribe_failed'))
        finally:
            self._health = self._health.model_copy(update={'connected': False})
            self._stream.close()

    async def _session(self) -> None:
        from gabfin.providers.massive.ws import MassiveWebSocket
        session = MassiveWebSocket(self._config, connect=self._connect)
        try:
            async with session:
                self._session_closed = False
                self._health = self._health.model_copy(update={'connection_started_at': datetime.now(timezone.utc)})
                await session.subscribe([f'Q.{self._symbol}'])
                self._health = self._health.model_copy(update={
                    'connected': True, 'heartbeat_at': datetime.now(timezone.utc)})
                if self._ready is not None and not self._ready.done():
                    self._ready.set_result(True)
                while True:
                    payload = json.loads(await session.receive())
                    for item in payload:
                        event = parse_quote_message(json.dumps(item), symbol=self._symbol,
                            instrument_id=self._instrument_id, received_at=datetime.now(timezone.utc))
                        if event is None:
                            self._rejected_frames += 1
                        elif self._stream.apply(event):
                            self._health = self._health.model_copy(update={'heartbeat_at': datetime.now(timezone.utc)})
        finally:
            self._session_closed = session.closed
            self._health = self._health.model_copy(update={'connected': False})
            self._stream.close()

