"""Bounded, single-use US equity FeedAdapter backed by a private SDK process.

This is a quote-only slice, not the live manifest/planner apply service. Only
explicit canonical instruments are accepted; no SDK is imported into this host.
"""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid5

from pydantic import Field, StrictBool, StrictInt, field_validator

from gabfin.contracts.common import ContractModel, NonNegativeDecimal, UtcTimestamp
from gabfin.contracts.events import QuoteMarketEvent
from gabfin.contracts.market import NonNegativeCounter, QuotePoint, QuoteSnapshot, QuoteEntitlements
from gabfin.contracts.subscriptions import FeedCapabilities, SubscriptionKey
from gabfin.market.stream import QuoteStream
from gabfin.providers.futu.quote_push import ERRORS
from gabfin.providers.futu.symbols import InstrumentCatalog
from gabfin.providers.futu.symbols_wire import us_equity_symbol


class _ClosedMessage(ContractModel):
    version: Literal[1]
    kind: Literal['closed']
    cleanup: Literal['not_subscribed', 'unsubscribed', 'release_pending']
    closed: StrictBool
    errors: list[str] = Field(max_length=10)
    callbacks: NonNegativeCounter
    coalesced: NonNegativeCounter
    rejected: NonNegativeCounter


class _QuoteWire(ContractModel):
    version: StrictInt = Field(ge=1, le=1)
    kind: Literal['quote']
    code: str = Field(max_length=100)
    price: NonNegativeDecimal
    event_at: UtcTimestamp
    received_at: UtcTimestamp

    @field_validator('price', mode='before')
    @classmethod
    def decimal_wire(cls, value):
        if not isinstance(value, str) or len(value) > 100:
            raise ValueError('IPC price must be a bounded decimal string')
        return value


class FutuQuoteAdapter:
    def __init__(self, catalog: InstrumentCatalog, instrument_id: UUID, *, python: Path,
                 port: int = 11111, lifetime: float = 110, _worker: Path | None = None):
        instrument = catalog.get(instrument_id)
        symbol = instrument.vendor_symbols.get('futu') if instrument else None
        if instrument is None or instrument.asset_class != 'equity' or not us_equity_symbol(symbol):
            raise ValueError('One registered Futu US equity is required')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid OpenD port')
        if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or not 90 <= lifetime <= 120:
            raise ValueError('Lifetime must reserve cleanup within 90–120 seconds')
        self._python = Path(python).resolve(strict=True)
        self._worker = Path(_worker).resolve(strict=True) if _worker else Path(__file__).with_name('quote_worker.py')
        self._key = SubscriptionKey(instrument_id=instrument_id, channel='quote', timeframe=None)
        self._symbol = symbol
        self._port = port
        self._lifetime = lifetime
        self._stream = QuoteStream(instrument_id)
        self._invalid_quotes = 0
        self._process = None
        self._reader = None
        self._ready = None
        self._close_task = None
        self._started = False
        self._consuming = False
        self._result = None
        self.failure: str | None = None

    async def capabilities(self) -> FeedCapabilities:
        return FeedCapabilities(schema_version='1.0', source='futu', asset_classes=('equity',),
                                sessions=(), latency_label='unknown', max_subscriptions=None,
                                history_limits=(), checked_at=datetime.now(timezone.utc),
                                permission_errors=('live_manifest_unverified',))

    def _validate_keys(self, keys):
        if any(key.identity != self._key.identity for key in keys):
            raise ValueError('Only the configured equity quote key is supported')

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    @property
    def result(self):
        return deepcopy(self._result)

    def snapshot(self):
        return self._stream.snapshot()

    @property
    def stats(self):
        return dict(accepted=self._stream.accepted, rejected=self._stream.rejected + self._invalid_quotes,
                    coalesced=self._stream.coalesced, pending=self._stream.pending_count)

    async def subscribe(self, keys: list[SubscriptionKey]) -> None:
        self._validate_keys(keys)
        if not keys:
            return
        if self._close_task is not None or self._result is not None:
            raise RuntimeError('Adapter is single-use')
        if self._started and self._reader.done():
            raise RuntimeError('Adapter is single-use')
        if not self._started:
            self._started = True
            self._ready = asyncio.get_running_loop().create_future()
            self._reader = asyncio.create_task(self._read_worker())
        try:
            async with asyncio.timeout(10):
                if not await asyncio.shield(self._ready):
                    raise RuntimeError('Quote worker could not subscribe')
        except BaseException:
            await self.close()
            raise

    async def unsubscribe(self, keys: list[SubscriptionKey]) -> None:
        self._validate_keys(keys)
        if keys:
            await self.close()

    async def events(self):
        if self._consuming:
            raise RuntimeError('One event consumer is supported; use snapshot for reads')
        self._consuming = True
        try:
            async for event in self._stream.events():
                yield event
        finally:
            try:
                await self.close()
            finally:
                self._consuming = False
        if self.failure:
            raise RuntimeError(self.failure)

    async def close(self) -> None:
        """Cancellation requests cleanup; the private reader keeps draining IPC."""
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._finish())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            await asyncio.shield(self._close_task)
            raise

    async def _finish(self):
        self._stream.close()
        # Startup may still be creating the process. The reader sees the close
        # request after spawn and signals stop before awaiting any output.
        if self.running:
            self._send_stop()
        if self._reader is not None:
            await self._reader

    def _send_stop(self):
        try:
            self._process.stdin.write(b'stop\n')
        except (AttributeError, BrokenPipeError, ConnectionResetError):
            pass

    def _apply_quote(self, message):
        """Normalize provider data before it reaches the typed market cache."""
        try:
            quote = _QuoteWire.model_validate(message)
            if quote.code != self._symbol or quote.event_at > quote.received_at:
                raise ValueError('foreign_or_clock_skewed_quote')
            available_at = datetime.now(timezone.utc)
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
                instrument_id=self._key.instrument_id, event_at=quote.event_at,
                received_at=quote.received_at, available_at=available_at,
                source='futu', source_seq=None, dedup_key=key,
                payload=QuoteSnapshot(schema_version='1.0', instrument_id=self._key.instrument_id,
                                      as_of=available_at, feed='futu', session='unknown',
                                      bid=None, ask=None, last=point, quality=('unknown', 'incomplete'),
                                      entitlements=QuoteEntitlements(status='unknown', checked_at=None)))
        except (ValueError, TypeError, OverflowError):
            self._invalid_quotes += 1
            return
        self._stream.apply(event)

    async def _read_worker(self):
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix='gabfin-push-') as folder:
                env = {key: value for key, value in os.environ.items()
                       if key.upper() in ('SYSTEMROOT', 'WINDIR', 'COMSPEC')}
                env.update(TEMP=folder, TMP=folder, APPDATA=folder, LOCALAPPDATA=folder,
                           PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
                deadline = time.monotonic() + self._lifetime
                async with asyncio.timeout(self._lifetime):
                    try:
                        process = await asyncio.create_subprocess_exec(
                            str(self._python), '-I', str(self._worker),
                            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.DEVNULL, limit=4096, env=env, cwd=folder,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        self._process = process
                        config = dict(version=1, code=self._symbol, host='127.0.0.1',
                                      port=self._port, deadline=deadline)
                        process.stdin.write(json.dumps(config).encode() + b'\n')
                        if self._close_task is not None:
                            self._send_stop()
                        await process.stdin.drain()
                        seen_ready = False
                        while line := await process.stdout.readline():
                            if len(line) > 4096:
                                raise ValueError('oversized_ipc')
                            message = json.loads(line)
                            if not isinstance(message, dict) or type(message.get('version')) is not int or message['version'] != 1:
                                raise ValueError('invalid_ipc_version')
                            if message.get('kind') == 'ready':
                                if set(message) != {'version', 'kind'} or seen_ready or self._result is not None:
                                    raise ValueError('invalid_ready')
                                seen_ready = True
                                if not self._ready.done():
                                    self._ready.set_result(True)
                            elif message.get('kind') == 'quote' and seen_ready and self._result is None:
                                self._apply_quote(message)
                            elif message.get('kind') == 'closed' and self._result is None:
                                result = _ClosedMessage.model_validate(message)
                                if any(error not in ERRORS for error in result.errors):
                                    raise ValueError('invalid_error_code')
                                if seen_ready and result.cleanup == 'not_subscribed':
                                    raise ValueError('inconsistent_terminal_state')
                                self._result = result.model_dump()
                                process.stdin.close()
                                if result.errors or not result.closed or result.cleanup == 'release_pending':
                                    self.failure = 'quote_cleanup_incomplete'
                            else:
                                raise ValueError('invalid_ipc_message')
                        await process.wait()
                        if process.returncode != 0 or self._result is None:
                            self.failure = 'quote_worker_failed'
                    finally:
                        if process is not None and process.returncode is None:
                            process.kill()
                            await process.wait()
                        if process is not None and process.stdin is not None:
                            process.stdin.close()
        except TimeoutError:
            self.failure = 'quote_worker_timeout'
        except Exception:
            self.failure = 'quote_worker_failed'
        finally:
            if self._ready is not None and not self._ready.done():
                self._ready.set_result(False)
            self._stream.close()
