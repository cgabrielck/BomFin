"""One wire reader dispatches bounded market frames and serialized control ACKs."""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlencode

from gabfin.providers.massive.config import MassiveConfig

_PARAMETER = re.compile(r'(?:Q|T|A|AM)\.(?:[A-Z0-9]+(?:\.[A-Z0-9]+)*|O:[A-Z0-9]+[0-9]{6}[CP][0-9]{8})')


class MassiveWebSocketError(RuntimeError):
    """Sanitized transport or protocol failure."""


def _connect(url: str, key: str):
    import websockets
    return websockets.connect(url + '?' + urlencode({'key': key}),
                              open_timeout=10, close_timeout=5, max_size=2**22, compression=None)


class MassiveWebSocket:
    """A single-use session; its owner supervises reconnects after verified close."""

    def __init__(self, config: MassiveConfig, *, connect=None):
        self._config = config
        self._connect = connect or _connect
        self._connection = self._socket = self._reader = None
        self._used = False
        self._parameters = set()
        self._pending = asyncio.Queue(maxsize=1000)
        self._control = asyncio.Lock()
        self._ack = None
        self._awaited = set()
        self._terminal = None
        self._ended = asyncio.Event()
        self.closed = False

    @property
    def stats(self):
        return {'subscribed_parameters': len(self._parameters), 'pending_frames': self._pending.qsize()}

    async def __aenter__(self):
        if self._used:
            raise MassiveWebSocketError('session_single_use')
        self._used = True
        try:
            self._connection = self._connect(self._config.ws_url, self._config.api_key.get_secret_value())
            entering = asyncio.ensure_future(self._connection.__aenter__())
            try:
                self._socket = await asyncio.shield(entering)
            except asyncio.CancelledError:
                # Acquisition may finish after cancellation. Its owner must still
                # close an acquired context before the supervisor can release it.
                try:
                    self._socket = await entering
                except Exception:
                    self.closed = True
                else:
                    await self._connection.__aexit__(None, None, None)
                    self._socket = None
                    self.closed = True
                raise
        except Exception:
            raise MassiveWebSocketError('connect_failed') from None
        self._reader = asyncio.create_task(self._read())
        return self

    def _fail(self, reason):
        self._terminal = self._terminal or reason
        self._ended.set()
        if self._ack is not None and not self._ack.done():
            self._ack.set_result(reason)

    async def _read(self):
        try:
            while True:
                payload = json.loads(await self._socket.recv())
                items = payload if isinstance(payload, list) else [payload]
                events = [item for item in items if isinstance(item, dict) and item.get('ev') in ('Q', 'T', 'A', 'AM')]
                if events:
                    self._pending.put_nowait(json.dumps(events))
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    status, message = item.get('status'), str(item.get('message', '')).lower()
                    if status in ('error', 'auth_failed', 'not_authorized'):
                        if self._ack is not None and not self._ack.done():
                            self._ack.set_result('subscription_rejected')
                        else:
                            self._fail('provider_rejected')
                            return
                    elif (self._ack is not None and not self._ack.done()
                          and status in ('ok', 'success')
                          and (message == 'subscribed' or message.startswith('subscribed to:'))):
                        if message == 'subscribed':
                            self._ack.set_result(None)
                        else:
                            confirmed = {part.strip().upper() for part in message.split(':', 1)[1].split(',')}
                            self._awaited -= confirmed
                            if not self._awaited:
                                self._ack.set_result(None)
        except asyncio.CancelledError:
            raise
        except asyncio.QueueFull:
            self._fail('pending_overflow')
        except Exception:
            self._fail('receive_failed')

    async def __aexit__(self, exc_type, exc, tb):
        self._fail('session_closed')
        if self._reader is not None:
            self._reader.cancel()
            await asyncio.gather(self._reader, return_exceptions=True)
        self._socket = None
        if self._connection is not None:
            try:
                await self._connection.__aexit__(None, None, None)
            except Exception:
                raise MassiveWebSocketError('close_failed') from None
        self.closed = True
        return False

    async def subscribe(self, parameters: list[str]):
        if any(not isinstance(item, str) or not _PARAMETER.fullmatch(item) for item in parameters):
            raise ValueError('Invalid Massive subscription parameter')
        async with self._control:
            added = set(parameters) - self._parameters
            if len(self._parameters | added) > self._config.max_subscriptions:
                raise ValueError('Massive subscription capacity exceeded')
            if not added:
                return
            if self._socket is None or self._terminal:
                raise MassiveWebSocketError(self._terminal or 'not_connected')
            self._awaited = set(added)
            self._ack = asyncio.get_running_loop().create_future()
            try:
                await self._socket.send(json.dumps({'action': 'subscribe', 'params': ','.join(sorted(added))}))
                async with asyncio.timeout(10):
                    reason = await self._ack
                if reason:
                    raise MassiveWebSocketError(reason)
                self._parameters.update(added)
            except (asyncio.CancelledError, TimeoutError):
                # A late ACK must never be attributed to the next command.
                self._fail('subscription_uncertain')
                raise
            except MassiveWebSocketError:
                raise
            except Exception:
                self._fail('subscribe_failed')
                raise MassiveWebSocketError('subscribe_failed') from None
            finally:
                self._ack = None

    async def receive(self):
        if self._terminal:
            raise MassiveWebSocketError(self._terminal)
        if self._socket is None:
            raise MassiveWebSocketError('not_connected')
        frame = asyncio.create_task(self._pending.get())
        ended = asyncio.create_task(self._ended.wait())
        try:
            await asyncio.wait((frame, ended), return_when=asyncio.FIRST_COMPLETED)
            if self._terminal:
                raise MassiveWebSocketError(self._terminal)
            return frame.result()
        finally:
            frame.cancel()
            ended.cancel()
            await asyncio.gather(frame, ended, return_exceptions=True)
