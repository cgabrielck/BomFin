"""Server-owned read-only connections to the single S03 market process."""
import asyncio
import ipaddress
from uuid import uuid4
from contextlib import asynccontextmanager

from pydantic import TypeAdapter
from pydantic import SecretStr

from gabfin.contracts.market import PositiveCounter
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.contracts.common import OpaqueKey
from gabfin.contracts.internal_stream import InternalFrame, SnapshotFrame, UpdateFrame, ErrorFrame


class MarketUnavailable(ValueError):
    pass


class MarketBusy(MarketUnavailable):
    pass


async def _store_call(function, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.shield(task)
        raise


class _LeasedConnection:
    def __init__(self, raw, store, token):
        self._raw, self._store, self._token = raw, store, SecretStr(token)

    async def receive(self, *, timeout):
        return await self._raw.receive(timeout=timeout)

    async def close(self):
        try:
            await self._raw.close()
        finally:
            await _store_call(self._store.revoke, self._token.get_secret_value())


class ScopedMarketConnection:
    def __init__(self, raw, keys, source):
        self._raw, self._keys, self._source = raw, keys, source
        self._ids = {key.instrument_id for key in keys}
        self._identities = {key.identity for key in keys}
        self._position = None

    def _event(self, event):
        if event.instrument_id not in self._ids or event.source != self._source:
            raise MarketUnavailable('Market provenance mismatch')
        timeframe = ((event.payload.timeframe.count, event.payload.timeframe.unit)
                     if event.kind == 'bar' else None)
        return event if (event.instrument_id, event.kind, timeframe) in self._identities else None

    async def receive(self, *, timeout):
        value = await self._raw.receive(timeout=timeout)
        frame = TypeAdapter(InternalFrame).validate_python(value.model_dump(mode='python'))
        if isinstance(frame, ErrorFrame):
            if frame.code in ('snapshot_required', 'slow_consumer'):
                return frame
            raise MarketUnavailable('Internal market connection denied')
        if not isinstance(frame, (SnapshotFrame, UpdateFrame)):
            raise MarketUnavailable('Unexpected market handshake')
        payload = frame.payload
        if payload.health.source != self._source or (payload.gap is not None and payload.gap.source != self._source):
            raise MarketUnavailable('Market health provenance mismatch')
        if isinstance(frame, SnapshotFrame):
            if self._position is not None:
                raise MarketUnavailable('Unexpected repeated snapshot')
            quotes = tuple(event for value in payload.quotes if (event := self._event(value)) is not None)
            bars = tuple(event for value in payload.bars if (event := self._event(value)) is not None)
            self._position = payload.position
            return frame.model_copy(update={'payload': payload.model_copy(update={'quotes': quotes, 'bars': bars})})
        if (self._position is None or payload.epoch != self._position.epoch
                or payload.sequence != self._position.sequence + 1):
            return ErrorFrame(version=1, kind='error', code='snapshot_required')
        event = self._event(payload.event) if payload.event is not None else None
        self._position = payload.position
        return frame.model_copy(update={'payload': payload.model_copy(update={'event': event})})


class MarketGateway:
    def __init__(self, connect, *, registered_keys, source, max_clients=8):
        keys = tuple(SubscriptionKey.model_validate(key.model_dump()) for key in registered_keys)
        if not keys or len(keys) > 64 or len({key.identity for key in keys}) != len(keys):
            raise ValueError('Finite unique registered market keys required')
        self.registered = {key.identity: key for key in keys}
        self._connect = connect
        self._capacity = TypeAdapter(PositiveCounter).validate_python(max_clients)
        if self._capacity > 64:
            raise ValueError('Market client capacity is bounded at 64')
        self._source = TypeAdapter(OpaqueKey).validate_python(source)
        self._active, self._healthy = 0, True

    @classmethod
    def from_internal(cls, *, host, port, token, registered_keys, source, max_clients=8):
        """Host bootstrap only. The service token never crosses a browser route."""
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError('Internal market connection requires loopback')
        secret = SecretStr(token)
        async def connect(ids):
            from gabfin.market.internal_stream import InternalMarketClient
            return await InternalMarketClient.connect(host, port, token=secret.get_secret_value(),
                instrument_ids=ids)
        return cls(connect, registered_keys=registered_keys, source=source, max_clients=max_clients)

    @classmethod
    def from_store(cls, *, host, port, store, registered_keys, source, max_clients=8):
        """Trusted host bootstrap: lease one read-only service session per connection.

        The authority is the S03 host's existing store, never browser input. New
        browser sessions can reconnect after older service sessions have expired.
        """
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError('Internal market connection requires loopback')
        actor_id = uuid4()
        async def connect(ids):
            from gabfin.market.internal_stream import InternalMarketClient
            # Complete issuance even on cancellation so its token can be revoked.
            issuing = asyncio.create_task(asyncio.to_thread(store.issue_service,
                actor_id=actor_id, role='research', scope=['read_market']))
            try:
                token, _ = await asyncio.shield(issuing)
            except asyncio.CancelledError:
                token, _ = await asyncio.shield(issuing)
                await _store_call(store.revoke, token)
                raise
            try:
                raw = await InternalMarketClient.connect(host, port, token=token, instrument_ids=ids)
                return _LeasedConnection(raw, store, token)
            except BaseException:
                await _store_call(store.revoke, token)
                raise
        return cls(connect, registered_keys=registered_keys, source=source, max_clients=max_clients)

    def validate_keys(self, keys):
        if any(key.identity not in self.registered for key in keys):
            raise PermissionError('Unregistered market key')

    @asynccontextmanager
    async def open(self, keys):
        self.validate_keys(keys)
        if not self._healthy:
            raise MarketUnavailable('Market connection cleanup unverified')
        if self._active >= self._capacity:
            raise MarketBusy('Market capacity reached')
        self._active += 1
        raw = None
        try:
            ids = tuple(sorted({key.instrument_id for key in keys}, key=str))
            raw = await asyncio.wait_for(self._connect(ids), 5)
            yield ScopedMarketConnection(raw, keys, self._source)
        finally:
            try:
                if raw is not None:
                    closing = asyncio.create_task(asyncio.wait_for(raw.close(), 3))
                    try:
                        await asyncio.shield(closing)
                    except asyncio.CancelledError:
                        await asyncio.shield(closing)
                        raise
            except Exception:
                self._healthy = False
                raise MarketUnavailable('Market cleanup failed') from None
            finally:
                self._active -= 1
