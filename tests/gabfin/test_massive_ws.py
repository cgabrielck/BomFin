"""Concurrent control and market reads share exactly one wire reader."""
import asyncio
import json

import pytest

from gabfin.providers.massive.config import MassiveConfig
from gabfin.providers.massive.ws import MassiveWebSocket, MassiveWebSocketError


class Wire:
    def __init__(self):
        self.frames = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.reject = False

    async def send(self, message):
        command = json.loads(message)
        self.sent.append(command)
        await self.frames.put(json.dumps({'status': 'error' if self.reject else 'ok',
                                          'message': 'subscribed'}))

    async def recv(self):
        return await self.frames.get()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True


def session(wire, **kwargs):
    cfg = MassiveConfig(base_url='https://proxy.example.test', api_key='fixture', **kwargs)
    return MassiveWebSocket(cfg, connect=lambda url, key: wire)


def test_quiet_receive_does_not_block_dynamic_subscription_and_close_wakes_reader():
    async def scenario():
        wire = Wire()
        stream = session(wire)
        async with stream:
            reader = asyncio.create_task(stream.receive())
            await asyncio.sleep(0)
            await asyncio.wait_for(stream.subscribe(['Q.AAPL']), .3)
            await wire.frames.put('{"ev":"Q","sym":"AAPL"}')
            assert json.loads(await asyncio.wait_for(reader, .3))[0]['sym'] == 'AAPL'
            waiting = asyncio.create_task(stream.receive())
            await asyncio.sleep(0)
        with pytest.raises(MassiveWebSocketError):
            await asyncio.wait_for(waiting, .3)
        assert wire.closed
    asyncio.run(scenario())


def test_cancel_during_connection_enter_waits_and_closes_acquired_context():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Connecting(Wire):
            async def __aenter__(self):
                entered.set()
                await release.wait()
                return self
        wire = Connecting()
        stream = session(wire)
        task = asyncio.create_task(stream.__aenter__())
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert wire.closed
        assert stream.closed
    asyncio.run(scenario())


def test_capacity_deduplication_and_rejection_do_not_consume_slots():
    async def scenario():
        wire = Wire()
        stream = session(wire, max_subscriptions=2)
        async with stream:
            wire.reject = True
            with pytest.raises(MassiveWebSocketError, match='subscription_rejected'):
                await stream.subscribe(['Q.MSFT'])
            wire.reject = False
            await stream.subscribe(['Q.AAPL', 'Q.AAPL'])
            await stream.subscribe(['T.AAPL'])
            with pytest.raises(ValueError, match='capacity'):
                await stream.subscribe(['Q.MSFT'])
            assert stream.stats['subscribed_parameters'] == 2
            assert len(wire.sent) == 3
    asyncio.run(scenario())


def test_connected_status_cannot_ack_subscription_and_mixed_quotes_survive():
    async def scenario():
        class Controlled(Wire):
            async def send(self, message):
                self.sent.append(json.loads(message))
                await self.frames.put('{"status":"ok","message":"connected"}')
        wire = Controlled()
        async with session(wire) as stream:
            task = asyncio.create_task(stream.subscribe(['Q.AAPL']))
            for _ in range(5):
                await asyncio.sleep(0)
            assert not task.done()
            await wire.frames.put('[{"ev":"status","status":"success","message":"subscribed to: Q.AAPL"},'
                                  '{"ev":"Q","sym":"AAPL"}]')
            await asyncio.wait_for(task, .3)
            assert json.loads(await stream.receive())[0]['sym'] == 'AAPL'
    asyncio.run(scenario())


def test_recorded_live_ack_confirms_exact_subscription():
    from pathlib import Path
    recorded = (Path(__file__).parents[1] / 'fixtures/massive/recorded_ack_2026_11_27.json').read_text()
    async def scenario():
        class Recorded(Wire):
            async def send(self, message):
                self.sent.append(json.loads(message))
                await self.frames.put(recorded)
        wire = Recorded()
        async with session(wire) as stream:
            await asyncio.wait_for(stream.subscribe(['Q.AAPL']), .3)
            assert stream.stats['subscribed_parameters'] == 1
        assert wire.closed
    asyncio.run(scenario())


def test_explicit_ack_for_other_parameters_cannot_confirm_pending_subscription():
    async def scenario():
        class WrongAck(Wire):
            async def send(self, message):
                await self.frames.put('{"status":"ok","message":"subscribed to: Q.MSFT"}')
        wire = WrongAck()
        async with session(wire) as stream:
            task = asyncio.create_task(stream.subscribe(['Q.AAPL']))
            for _ in range(5):
                await asyncio.sleep(0)
            try:
                assert not task.done()
                await wire.frames.put('{"status":"ok","message":"subscribed to: Q.AAPL"}')
                await asyncio.wait_for(task, .3)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def test_cancelled_control_poison_session_so_late_ack_cannot_confirm_next_command():
    async def scenario():
        class Silent(Wire):
            async def send(self, message):
                self.sent.append(json.loads(message))
        wire = Silent()
        async with session(wire) as stream:
            task = asyncio.create_task(stream.subscribe(['Q.AAPL']))
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await wire.frames.put('{"status":"ok","message":"subscribed"}')
            with pytest.raises(MassiveWebSocketError, match='subscription_uncertain'):
                await stream.subscribe(['Q.MSFT'])
            assert stream.stats['subscribed_parameters'] == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('parameter', ['Q.*', 'Q.O:SPY*', 'X.AAPL', 'Q.AAPL,T.MSFT', ''])
def test_invalid_parameters_rejected_before_send(parameter):
    async def scenario():
        with pytest.raises(ValueError):
            await session(Wire()).subscribe([parameter])
    asyncio.run(scenario())
