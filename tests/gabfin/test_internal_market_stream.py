import asyncio
import json
from uuid import uuid4
from datetime import timedelta
import pytest

from gabfin.api.sessions import SessionStore
from gabfin.market.internal_stream import InternalMarketServer, InternalMarketClient
from test_market_coordinator import coordinator
from test_quote_stream import observation, ID, NOW


def sessions(tmp_path, clock=None):
    return SessionStore(tmp_path / 'sessions.sqlite', owner_id=uuid4(), session_seconds=60,
                        pairing_seconds=60, max_failures=5, clock=clock)


def test_authenticated_read_only_socket_receives_snapshot_then_typed_update(tmp_path):
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        market = coordinator()
        server = InternalMarketServer(market, store)
        await server.start()
        client = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID])
        try:
            snapshot = await client.receive(timeout=2)
            assert snapshot.kind == 'snapshot' and snapshot.payload.quotes == ()
            market.apply(observation('123'))
            update = await client.receive(timeout=2)
            assert update.kind == 'update' and update.payload.event.payload.last.price == 123
        finally:
            await client.close()
            await server.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('mode', ['invalid_token', 'wrong_scope', 'unknown_instrument'])
def test_unauthorized_or_outside_universe_client_never_receives_prices(tmp_path, mode):
    async def scenario():
        store = sessions(tmp_path)
        role, scope = ('chat', ['read_account']) if mode == 'wrong_scope' else ('research', ['read_market'])
        token, _ = store.issue_service(actor_id=uuid4(), role=role, scope=scope)
        market = coordinator(); market.apply(observation('123'))
        server = InternalMarketServer(market, store); await server.start()
        client = await InternalMarketClient.connect(*server.address,
            token='invalid-token-long-enough' if mode == 'invalid_token' else token,
            instrument_ids=[uuid4()] if mode == 'unknown_instrument' else [ID])
        try:
            response = await client.receive(timeout=2)
            assert response.kind == 'error'
            assert response.code == ('invalid_request' if mode == 'unknown_instrument' else 'unauthorized')
            assert '123' not in response.model_dump_json() and token not in response.model_dump_json()
        finally:
            await client.close(); await server.close()
    asyncio.run(scenario())


def test_expired_session_is_closed_even_with_no_market_events(tmp_path):
    async def scenario():
        now = [NOW]
        store = sessions(tmp_path, clock=lambda: now[0])
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        server = InternalMarketServer(coordinator(), store); await server.start()
        client = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID])
        try:
            assert (await client.receive(timeout=2)).kind == 'snapshot'
            now[0] += timedelta(seconds=61)
            result = await client.receive(timeout=2)
            assert result.kind == 'error' and result.code == 'unauthorized'
        finally:
            await client.close(); await server.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('version', [True, 1.0, 2])
def test_incompatible_or_non_integer_handshake_version_is_refused(tmp_path, version):
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        server = InternalMarketServer(coordinator(), store); await server.start()
        reader, writer = await asyncio.open_connection(*server.address)
        try:
            writer.write(json.dumps(dict(version=version, token=token, instrument_ids=[str(ID)])).encode() + b'\n')
            await writer.drain()
            result = json.loads(await asyncio.wait_for(reader.readline(), 2))
            assert result == dict(version=1, kind='error', code='invalid_request')
        finally:
            writer.close(); await writer.wait_closed(); await server.close()
    asyncio.run(scenario())


def test_replay_resume_and_lagging_cursor_require_explicit_snapshot(tmp_path):
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        market = coordinator()
        for i in range(2): market.apply(observation(str(100 + i)))
        snapshot = market.snapshot()
        server = InternalMarketServer(market, store); await server.start()
        initial = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID])
        assert (await initial.receive(timeout=2)).kind == 'snapshot'
        for i in range(2,5): market.apply(observation(str(100 + i)))
        for _ in range(3): assert (await initial.receive(timeout=2)).kind == 'update'
        await initial.close()
        stale = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID],
                                                   epoch=snapshot.epoch, cursor=1)
        resumed = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID],
                                                     epoch=snapshot.epoch, cursor=2)
        try:
            assert (await stale.receive(timeout=2)).code == 'snapshot_required'
            assert (await resumed.receive(timeout=2)).kind == 'resumed'
            sequences = [(await resumed.receive(timeout=2)).payload.sequence for _ in range(3)]
            assert sequences == [3, 4, 5]
        finally:
            await stale.close(); await resumed.close(); await server.close()
    asyncio.run(scenario())


def test_resume_cursor_cannot_switch_its_snapshot_instrument_set(tmp_path):
    from gabfin.market.coordinator import MarketCoordinator
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        second = uuid4()
        market = MarketCoordinator([ID, second], source='test-feed', replay_capacity=10, max_bars=3, clock=lambda: NOW)
        event = observation('222')
        market.apply(event.model_copy(update={'instrument_id': second,
            'payload': event.payload.model_copy(update={'instrument_id': second})}))
        server = InternalMarketServer(market, store); await server.start()
        first = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID])
        frame = await first.receive(timeout=2)
        await first.close()
        switched = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[second],
            epoch=frame.payload.epoch, cursor=frame.payload.cursor)
        try:
            response = await switched.receive(timeout=2)
            assert response.kind == 'error' and response.code == 'snapshot_required'
        finally:
            await switched.close(); await server.close()
    asyncio.run(scenario())


def test_write_timeout_invalidates_resume_until_another_full_snapshot(tmp_path, monkeypatch):
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        market = coordinator()
        server = InternalMarketServer(market, store); await server.start()
        address = server.address
        first = await InternalMarketClient.connect(*address, token=token, instrument_ids=[ID])
        snapshot = (await first.receive(timeout=2)).payload
        original = asyncio.StreamWriter.drain
        async def stalled(writer):
            if writer.get_extra_info('sockname') == address:
                raise TimeoutError('external stalled socket')
            await original(writer)
        monkeypatch.setattr(asyncio.StreamWriter, 'drain', stalled)
        market.apply(observation('123'))
        # The timed-out write may already have reached the peer; consume to EOF.
        try:
            while True: await first.receive(timeout=2)
        except EOFError:
            pass
        await first.close()
        monkeypatch.setattr(asyncio.StreamWriter, 'drain', original)
        resumed = await InternalMarketClient.connect(*address, token=token, instrument_ids=[ID],
            epoch=snapshot.epoch, cursor=snapshot.cursor)
        try:
            response = await resumed.receive(timeout=2)
            assert response.kind == 'error' and response.code == 'snapshot_required'
        finally:
            await resumed.close(); await server.close()
    asyncio.run(scenario())


def test_lagging_reader_resets_instead_of_accumulating_unbounded_queue(tmp_path):
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        market = coordinator(); server = InternalMarketServer(market, store, frame_bytes=4096)
        await server.start()
        client = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID])
        try:
            assert (await client.receive(timeout=2)).kind == 'snapshot'
            for i in range(1000): market.apply(observation(str(i + 1)))
            assert (await client.receive(timeout=2)).code == 'snapshot_required'
            assert market.snapshot().quotes[0].payload.last.price == 1000
        finally:
            await client.close(); await server.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('host', ['0.0.0.0', '192.168.1.1', '8.8.8.8'])
def test_market_listener_rejects_public_and_lan_binding_before_network_use(tmp_path, host):
    with pytest.raises(ValueError, match='loopback'):
        InternalMarketServer(coordinator(), sessions(tmp_path), host=host)


def test_default_transport_can_send_a_normal_retained_500_bar_snapshot(tmp_path):
    from gabfin.contracts.events import BarMarketEvent
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.market.coordinator import MarketCoordinator
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        market = MarketCoordinator([ID], source='test-feed', replay_capacity=3, max_bars=500,
            required_keys=(SubscriptionKey(instrument_id=ID, channel='bar', timeframe=dict(count=1, unit='minute')),),
            clock=lambda: NOW)
        for i in range(500):
            start = NOW - timedelta(minutes=501 - i)
            market.apply(BarMarketEvent(schema_version='1.0', event_id=uuid4(), instrument_id=ID,
                source='test-feed', source_seq=None, dedup_key=f'bar:{i}', kind='bar',
                event_at=start + timedelta(minutes=1), received_at=NOW, available_at=NOW,
                payload=dict(schema_version='1.0', instrument_id=ID, source='test-feed',
                    timeframe=dict(count=1, unit='minute'), session='unknown', start=start,
                    end=start + timedelta(minutes=1), open='100', high='100', low='100', close='100',
                    volume=None, status='final', revision=0, corporate_action_policy='fixture-unadjusted',
                    event_at=start + timedelta(minutes=1), received_at=NOW, available_at=NOW)))
        server = InternalMarketServer(market, store); await server.start()
        client = await InternalMarketClient.connect(*server.address, token=token, instrument_ids=[ID])
        try:
            frame = await client.receive(timeout=3)
            assert frame.kind == 'snapshot' and len(frame.payload.bars) == 500
        finally:
            await client.close(); await server.close()
    asyncio.run(scenario())


def test_listener_close_waits_for_an_inflight_auth_database_read():
    import threading
    from gabfin.contracts.identity import Principal
    started = threading.Event()
    release = threading.Event()
    class DatabaseBoundary:
        def resolve(self, token):
            started.set(); release.wait(5)
            return Principal(schema_version='1.0', actor_id=uuid4(), role='research', scope=['read_market'])
        def remaining(self, token): return 60
    async def scenario():
        server = InternalMarketServer(coordinator(), DatabaseBoundary())
        await server.start()
        client = await InternalMarketClient.connect(*server.address, token='x' * 32, instrument_ids=[ID])
        async with asyncio.timeout(2):
            while not started.is_set(): await asyncio.sleep(.01)
        closing = asyncio.create_task(server.close())
        await asyncio.sleep(.03)
        early = closing.done()
        release.set()
        completed = True
        try:
            await asyncio.wait_for(asyncio.shield(closing), 1)
        except TimeoutError:
            completed = False
        finally:
            await client.close()
            await asyncio.wait_for(closing, 2)
        assert not early
        assert completed
    asyncio.run(scenario())
