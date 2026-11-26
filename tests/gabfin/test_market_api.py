"""Public HTTP/WebSocket boundary with an external market-connection fake."""
import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from gabfin.api.sessions import SessionStore
from gabfin.contracts.internal_stream import SnapshotFrame
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.contracts.feed import MarketUpdate
from gabfin.contracts.internal_stream import UpdateFrame
from test_market_coordinator import coordinator
from test_quote_stream import ID, NOW, observation

ORIGIN = 'https://desk.test'
KEY = SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)
BODY = dict(version=1, keys=[KEY.model_dump(mode='json')])


class ExternalConnection:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.closed = False
        self.first = True

    async def receive(self, *, timeout):
        if self.first:
            self.first = False
            return SnapshotFrame(version=1, kind='snapshot', payload=self.snapshot)
        await asyncio.sleep(timeout)
        raise TimeoutError

    async def close(self):
        self.closed = True


def setup(tmp_path, connection_type=ExternalConnection):
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    clock = [NOW]
    store = SessionStore(tmp_path/'sessions.sqlite', owner_id=uuid4(), session_seconds=60,
        pairing_seconds=30, max_failures=5, clock=lambda: clock[0])
    market = coordinator()
    market.apply(observation('100'))
    connections = []
    async def connect(ids):
        assert ids == (ID,)
        connection = connection_type(market.snapshot())
        connections.append(connection)
        return connection
    gateway = MarketGateway(connect, registered_keys=[KEY], source='test-feed', max_clients=2)
    app = create_market_app(store, allowed_origin=ORIGIN, gateway=gateway)
    return app, store, clock, connections


def test_snapshot_requires_session_before_opening_market_connection(tmp_path):
    app, _, _, connections = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post('/market/snapshot', json=BODY, headers={'Origin':ORIGIN})
        assert response.status_code == 401
        assert connections == []


def pair(client, store):
    response = client.post('/pair', json={'code':store.create_pairing()}, headers={'Origin':ORIGIN})
    assert response.status_code == 200
    return {'Origin':ORIGIN, 'X-CSRF-Token':response.json()['csrf']}


def test_authorized_snapshot_preserves_decimal_and_closes_read_only_connection(tmp_path):
    app, store, _, connections = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = pair(client, store)
        response = client.post('/market/snapshot', json=BODY, headers=headers)
        assert response.status_code == 200
        assert response.json()['quotes'][0]['payload']['last']['price'] == '100'
        assert response.headers['cache-control'] == 'no-store'
        assert len(connections) == 1 and connections[0].closed
        assert 'token' not in response.text and 'csrf' not in response.text


def test_websocket_starts_with_full_snapshot_and_cleans_up_on_disconnect(tmp_path):
    app, store, _, connections = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        with client.websocket_connect('wss://desk.test/market/stream', headers={'Origin':ORIGIN}) as ws:
            ws.send_json(BODY)
            frame = ws.receive_json()
            assert frame['kind'] == 'snapshot'
            assert frame['payload']['quotes'][0]['payload']['last']['price'] == '100'
        assert connections[0].closed


@pytest.mark.parametrize('failure', ['origin','csrf','query','expired'])
def test_snapshot_rejects_bad_authority_before_market_connect(tmp_path, failure):
    app, store, clock, connections = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = pair(client, store)
        url = '/market/snapshot'
        if failure == 'origin': headers['Origin'] = 'https://evil.test'
        if failure == 'csrf': headers.pop('X-CSRF-Token')
        if failure == 'query': url += '?token=fake'
        if failure == 'expired': clock[0] += timedelta(seconds=61)
        assert client.post(url, json=BODY, headers=headers).status_code == 401
        assert not connections


def test_chat_principal_cannot_read_prices_even_with_valid_session_and_csrf(tmp_path):
    app, store, _, connections = setup(tmp_path)
    token, csrf = store.issue_service(actor_id=uuid4(), role='chat', scope=['read_account'])
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set('gabfin_session', token)
        response = client.post('/market/snapshot', json=BODY, headers={'Origin':ORIGIN,'X-CSRF-Token':csrf})
        assert response.status_code == 403 and not connections


@pytest.mark.parametrize('failure', ['version_bool','version_float','unknown_key','duplicate','oversize','content_type'])
def test_invalid_snapshot_input_does_not_open_market_client(tmp_path, failure):
    app, store, _, connections = setup(tmp_path)
    body = dict(BODY)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = pair(client, store)
        expected = 400
        if failure == 'version_bool': body['version'] = True
        if failure == 'version_float': body['version'] = 1.0
        if failure == 'duplicate': body['keys'] = body['keys'] * 2
        if failure == 'unknown_key':
            body['keys'] = [KEY.model_copy(update={'instrument_id':uuid4()}).model_dump(mode='json')]
            expected = 403
        if failure == 'oversize':
            response = client.post('/market/snapshot', content=b'x'*17000, headers=headers|{'Content-Type':'application/json'})
            expected = 413
        elif failure == 'content_type':
            response = client.post('/market/snapshot', content=b'{}', headers=headers|{'Content-Type':'text/plain'})
            expected = 415
        else:
            response = client.post('/market/snapshot', json=body, headers=headers)
        assert response.status_code == expected and not connections


def test_plain_http_cannot_even_pair(tmp_path):
    app, store, _, connections = setup(tmp_path)
    with TestClient(app, base_url='http://desk.test') as client:
        assert client.post('/pair', json={'code':store.create_pairing()}, headers={'Origin':ORIGIN}).status_code == 401
        assert not connections


class UpdatingConnection(ExternalConnection):
    offset = 1
    async def receive(self, *, timeout):
        if self.first: return await super().receive(timeout=timeout)
        return UpdateFrame(version=1, kind='update', payload=MarketUpdate(schema_version='1.0',
            epoch=self.snapshot.epoch, sequence=self.snapshot.cursor+self.offset,
            processed_at=NOW+timedelta(seconds=1), event=observation('101'),
            health=self.snapshot.health, gap=self.snapshot.gap))


def test_updates_follow_snapshot_with_exact_decimal_payload(tmp_path):
    app, store, _, connections = setup(tmp_path, UpdatingConnection)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        with client.websocket_connect('wss://desk.test/market/stream', headers={'Origin':ORIGIN}) as ws:
            ws.send_json(BODY)
            assert ws.receive_json()['kind'] == 'snapshot'
            frame = ws.receive_json()
            assert frame['kind'] == 'update'
            assert frame['payload']['event']['payload']['last']['price'] == '101'
        assert connections[0].closed


def test_sequence_gap_requests_new_full_snapshot_instead_of_forwarding_bad_update(tmp_path):
    class Hole(UpdatingConnection): offset = 2
    app, store, _, connections = setup(tmp_path, Hole)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        for _ in range(2):
            with client.websocket_connect('wss://desk.test/market/stream', headers={'Origin':ORIGIN}) as ws:
                ws.send_json(BODY)
                assert ws.receive_json()['kind'] == 'snapshot'
                frame = ws.receive_json()
                assert frame == dict(version=1,kind='error',code='snapshot_required')
                with pytest.raises(WebSocketDisconnect): ws.receive_json()
        assert len(connections) == 2 and all(connection.closed for connection in connections)


@pytest.mark.parametrize('action', ['expire','logout','write'])
def test_quiet_websocket_expires_revokes_or_refuses_writes(tmp_path, action):
    app, store, clock, connections = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = pair(client, store)
        with client.websocket_connect('wss://desk.test/market/stream', headers={'Origin':ORIGIN}) as ws:
            ws.send_json(BODY)
            assert ws.receive_json()['kind'] == 'snapshot'
            if action == 'expire': clock[0] += timedelta(seconds=61)
            if action == 'logout': assert client.post('/logout', headers=headers).status_code == 200
            if action == 'write': ws.send_json({'kind':'submit_order'})
            with pytest.raises(WebSocketDisconnect) as error: ws.receive_json()
            assert error.value.code == 1008
        assert connections[0].closed


def test_client_capacity_is_bounded_and_returns_to_pool_after_close(tmp_path):
    app, store, _, connections = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = pair(client, store)
        with client.websocket_connect('wss://desk.test/market/stream', headers={'Origin':ORIGIN}) as a:
            a.send_json(BODY); a.receive_json()
            with client.websocket_connect('wss://desk.test/market/stream', headers={'Origin':ORIGIN}) as b:
                b.send_json(BODY); b.receive_json()
                assert client.post('/market/snapshot', json=BODY, headers=headers).status_code == 503
        assert client.post('/market/snapshot', json=BODY, headers=headers).status_code == 200
        assert all(connection.closed for connection in connections)


def test_failed_cleanup_prevents_another_source_connection(tmp_path):
    class Unclosed(ExternalConnection):
        async def close(self): raise RuntimeError('private upstream detail')
    app, store, _, connections = setup(tmp_path, Unclosed)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = pair(client, store)
        for _ in range(2):
            response = client.post('/market/snapshot', json=BODY, headers=headers)
            assert response.status_code == 503 and 'private' not in response.text
        assert len(connections) == 1


def test_actual_internal_socket_bridge_retains_single_market_authority(tmp_path):
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.market.internal_stream import InternalMarketServer
    async def scenario():
        store = SessionStore(tmp_path/'real-socket.sqlite', owner_id=uuid4(), session_seconds=60,
            pairing_seconds=30,max_failures=5)
        token, _ = store.issue_service(actor_id=uuid4(),role='research',scope=['read_market'])
        market = coordinator(); market.apply(observation('123.45'))
        server = InternalMarketServer(market, store); await server.start()
        gateway = MarketGateway.from_internal(host=server.address[0],port=server.address[1],
            token=token,registered_keys=[KEY],source='test-feed')
        app = create_market_app(store,allowed_origin=ORIGIN,gateway=gateway)
        def consumer():
            with TestClient(app,base_url=ORIGIN) as client:
                headers=pair(client,store)
                assert client.post('/market/snapshot',json=BODY,headers=headers).json()['quotes'][0]['payload']['last']['price']=='123.45'
                with client.websocket_connect('wss://desk.test/market/stream',headers={'Origin':ORIGIN}) as ws:
                    ws.send_json(BODY)
                    assert ws.receive_json()['payload']['quotes'][0]['payload']['last']['price']=='123.45'
        try:
            await asyncio.wait_for(asyncio.to_thread(consumer),10)
        finally:
            await server.close()
    asyncio.run(scenario())


def test_csrf_cookie_supports_reload_without_exposing_authentication_token(tmp_path):
    app, store, _, connections = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post('/pair', json={'code':store.create_pairing()}, headers={'Origin':ORIGIN})
        cookies = response.headers.get_list('set-cookie')
        auth = next(value for value in cookies if value.startswith('gabfin_session='))
        nonce = next(value for value in cookies if value.startswith('__Host-gabfin_csrf='))
        assert 'HttpOnly' in auth and 'HttpOnly' not in nonce
        assert all('Secure' in value and 'SameSite=strict' in value and 'Path=/' in value for value in cookies)
        assert 'Domain=' not in nonce
        assert client.cookies.get('__Host-gabfin_csrf') == response.json()['csrf']
        headers = {'Origin':ORIGIN, 'X-CSRF-Token':client.cookies.get('__Host-gabfin_csrf')}
        assert client.get('/session').status_code == 200
        assert client.post('/market/snapshot', json=BODY, headers=headers).status_code == 200
        assert client.post('/market/snapshot', json=BODY, headers=headers|{'X-CSRF-Token':'wrong'}).status_code == 401
        assert client.post('/logout', headers=headers).status_code == 200
        assert not client.cookies.get('__Host-gabfin_csrf') and not client.cookies.get('gabfin_session')


def test_new_browser_pair_can_connect_after_previous_service_lease_expires(tmp_path):
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.market.internal_stream import InternalMarketServer
    async def scenario():
        clock=[NOW]
        store=SessionStore(tmp_path/'leases.sqlite',owner_id=uuid4(),session_seconds=60,
            pairing_seconds=30,max_failures=5,clock=lambda:clock[0])
        market=coordinator();market.apply(observation('123.45'))
        server=InternalMarketServer(market,store);await server.start()
        gateway=MarketGateway.from_store(host=server.address[0],port=server.address[1],
            store=store,registered_keys=[KEY],source='test-feed')
        app=create_market_app(store,allowed_origin=ORIGIN,gateway=gateway)
        def request():
            with TestClient(app,base_url=ORIGIN) as client:
                headers=pair(client,store)
                response=client.post('/market/snapshot',json=BODY,headers=headers)
                assert response.status_code == 200
                assert response.json()['quotes'][0]['payload']['last']['price']=='123.45'
        try:
            await asyncio.wait_for(asyncio.to_thread(request),10)
            clock[0]+=timedelta(seconds=61)
            await asyncio.wait_for(asyncio.to_thread(request),10)
        finally: await server.close()
    asyncio.run(scenario())
