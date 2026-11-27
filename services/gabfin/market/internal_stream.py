"""Authenticated read-only loopback NDJSON stream, bounded by cursor retention.

There is no per-client event queue. A lagging cursor requires a new snapshot;
write buffers/timeouts bound slow readers. This is not a public browser endpoint.
"""
import asyncio
import ipaddress
import json
import math
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from pydantic import TypeAdapter

from gabfin.api.capabilities import authorize
from gabfin.contracts.feed import MarketCursor
from gabfin.contracts.identity import Capability, Resource
from gabfin.contracts.internal_stream import (StreamHello, SnapshotFrame, UpdateFrame,
    ResumeFrame, ErrorFrame, InternalFrame)
from gabfin.contracts.market import PositiveCounter
from gabfin.market.coordinator import SnapshotRequired


def _loopback(host):
    if not ipaddress.ip_address(host).is_loopback:
        raise ValueError('Internal market stream binds/connects only to loopback')


@dataclass(frozen=True)
class ResumeCheckpoint:
    epoch: UUID
    floor: int
    ceiling: int


class InternalMarketServer:
    def __init__(self, market, sessions, *, host='127.0.0.1', port=0, max_clients=8,
                 frame_bytes=1048576, write_timeout=2, max_resume_sessions=128):
        _loopback(host)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError('Invalid listener port')
        counter = TypeAdapter(PositiveCounter)
        self._max_clients = counter.validate_python(max_clients)
        self._frame_bytes = counter.validate_python(frame_bytes)
        self._max_resume = counter.validate_python(max_resume_sessions)
        self._checkpoints = OrderedDict()
        if frame_bytes < 4096 or type(write_timeout) not in (int, float) or not math.isfinite(write_timeout) or write_timeout <= 0:
            raise ValueError('Invalid transport limits')
        self._market, self._sessions = market, sessions
        self._host, self._port = host, port
        self._write_timeout = write_timeout
        self._server = None
        self._starting = None
        self._close_task = None
        self._clients = set()

    async def start(self):
        if self._starting is not None or self._close_task is not None:
            raise RuntimeError('Stream listener already started')
        self._starting = asyncio.create_task(asyncio.start_server(self._handle, self._host, self._port, limit=4096))
        try:
            self._server = await asyncio.shield(self._starting)
        except BaseException:
            await self.close()
            raise
        if self._close_task is not None:
            await self.close()
            self._server = None
            raise RuntimeError('Listener closed during startup')

    @property
    def address(self):
        if self._server is None:
            raise RuntimeError('Listener is not running')
        address = self._server.sockets[0].getsockname()
        return address[0], address[1]

    async def close(self):
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close_all())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            await asyncio.shield(self._close_task)
            raise

    async def _close_all(self):
        listener = self._server
        if listener is None and self._starting is not None:
            try:
                listener = await asyncio.shield(self._starting)
            except Exception:
                pass
        if listener is not None:
            listener.close()
        self._server = None
        tasks = tuple(self._clients)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if listener is not None:
            await listener.wait_closed()

    def _authorize(self, hello):
        principal = self._sessions.resolve(hello.token.get_secret_value())
        for identifier in hello.instrument_ids:
            authorize(principal, Capability.READ_MARKET,
                      Resource(schema_version='1.0', kind='instrument', id=identifier, owner=principal.actor_id))
        return self._sessions.remaining(hello.token.get_secret_value())

    async def _authorize_async(self, hello):
        # SQLite I/O runs away from ingestion, but cancellation must still wait
        # for its connection to close before a session database can be removed.
        query = asyncio.create_task(asyncio.to_thread(self._authorize, hello))
        try:
            return await asyncio.shield(query)
        except asyncio.CancelledError:
            await asyncio.shield(query)
            raise

    async def _send(self, writer, frame, *, remaining=None):
        data = frame.model_dump_json().encode() + b'\n'
        if len(data) > self._frame_bytes:
            raise ValueError('frame_capacity')
        writer.write(data)
        await asyncio.wait_for(writer.drain(), min(self._write_timeout, remaining) if remaining is not None else self._write_timeout)

    @staticmethod
    def _resume_key(hello):
        return (sha256(hello.token.get_secret_value().encode()).digest(),
                tuple(sorted(hello.instrument_ids, key=str)))

    def _checkpoint(self, key, position, *, snapshot=False):
        previous = self._checkpoints.get(key)
        if snapshot:
            self._checkpoints[key] = ResumeCheckpoint(position.epoch, position.sequence, position.sequence)
        elif previous is not None and previous.epoch == position.epoch:
            self._checkpoints[key] = ResumeCheckpoint(previous.epoch, previous.floor,
                                                       max(previous.ceiling, position.sequence))
        if key in self._checkpoints:
            self._checkpoints.move_to_end(key)
        if len(self._checkpoints) > self._max_resume:
            self._checkpoints.popitem(last=False)

    async def _handle(self, reader, writer):
        task = asyncio.current_task()
        incoming = None
        if self._close_task is not None or len(self._clients) >= self._max_clients:
            writer.close()
            await writer.wait_closed()
            return
        self._clients.add(task)
        writer.transport.set_write_buffer_limits(high=self._frame_bytes, low=self._frame_bytes // 2)
        error = None
        resume_key = None
        invalidate = False
        established = False
        try:
            line = await asyncio.wait_for(reader.readline(), 3)
            if not line or len(line) > 4096:
                raise ValueError('invalid_hello')
            hello = StreamHello.model_validate_json(line)
            remaining = await self._authorize_async(hello)
            resume_key = self._resume_key(hello)
            snapshot = self._market.snapshot(hello.instrument_ids)
            position = snapshot.position
            if hello.epoch is None:
                established = True
                await self._send(writer, SnapshotFrame(version=1, kind='snapshot', payload=snapshot), remaining=remaining)
                self._checkpoint(resume_key, position, snapshot=True)
            else:
                position = MarketCursor(epoch=hello.epoch, sequence=hello.cursor)
                checkpoint = self._checkpoints.get(resume_key)
                if (checkpoint is None or checkpoint.epoch != position.epoch
                        or not checkpoint.floor <= position.sequence <= checkpoint.ceiling):
                    raise SnapshotRequired('snapshot_required')
                established = True
                self._market.replay(position)
                await self._send(writer, ResumeFrame(version=1, kind='resumed', epoch=position.epoch, cursor=position.sequence), remaining=remaining)
            incoming = asyncio.create_task(reader.read(1))
            while True:
                if incoming.done():
                    if incoming.result():
                        raise ValueError('read_only_protocol')
                    return
                remaining = await self._authorize_async(hello)
                updates = await self._market.wait_for_update(position, timeout=min(.25, remaining))
                for update in updates:
                    remaining = await self._authorize_async(hello)
                    if update.event is not None and update.event.instrument_id not in hello.instrument_ids:
                        update = update.model_copy(update={'event': None})
                    await self._send(writer, UpdateFrame(version=1, kind='update', payload=update), remaining=remaining)
                    position = update.position
                    self._checkpoint(resume_key, position)
        except SnapshotRequired:
            error = 'snapshot_required'
        except PermissionError:
            error = 'unauthorized'
        except TimeoutError:
            error = 'slow_consumer'
        except (ValueError, TypeError):
            error = 'invalid_request'
        except (ConnectionError, asyncio.CancelledError):
            invalidate = True
        except Exception:
            error = 'unauthorized'  # Auth/storage errors fail closed without raw details.
        finally:
            if established and resume_key is not None and (error is not None or invalidate):
                self._checkpoints.pop(resume_key, None)
            try:
                if incoming is not None:
                    incoming.cancel()
                    await asyncio.gather(incoming, return_exceptions=True)
                if error is not None:
                    try:
                        await self._send(writer, ErrorFrame(version=1, kind='error', code=error))
                    except (ConnectionError, TimeoutError, ValueError):
                        pass
            finally:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), self._write_timeout)
                except (ConnectionError, TimeoutError, asyncio.CancelledError):
                    writer.transport.abort()
                finally:
                    self._clients.discard(task)


class InternalMarketClient:
    def __init__(self, reader, writer, *, frame_bytes):
        self._reader, self._writer = reader, writer
        self._frame_bytes = frame_bytes

    @classmethod
    async def connect(cls, host, port, *, token, instrument_ids, epoch=None, cursor=None, frame_bytes=1048576):
        _loopback(host)
        hello = StreamHello(version=1, token=token, instrument_ids=instrument_ids, epoch=epoch, cursor=cursor)
        reader, writer = await asyncio.open_connection(host, port, limit=frame_bytes)
        try:
            message = dict(version=1, token=hello.token.get_secret_value(),
                           instrument_ids=[str(value) for value in hello.instrument_ids],
                           epoch=str(epoch) if epoch is not None else None, cursor=cursor)
            data = json.dumps(message).encode() + b'\n'
            if len(data) > 4096:
                raise ValueError('hello_capacity')
            writer.write(data)
            await writer.drain()
            return cls(reader, writer, frame_bytes=frame_bytes)
        except BaseException:
            writer.close()
            await writer.wait_closed()
            raise

    async def receive(self, *, timeout=5):
        line = await asyncio.wait_for(self._reader.readline(), timeout)
        if not line:
            raise EOFError('market_stream_closed')
        if len(line) > self._frame_bytes:
            raise ValueError('frame_capacity')
        message = json.loads(line)
        if not isinstance(message, dict) or type(message.get('version')) is not int or message['version'] != 1:
            raise ValueError('unsupported_stream_version')
        return TypeAdapter(InternalFrame).validate_json(line)

    async def close(self):
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except ConnectionError:
            pass
