from uuid import uuid4

from fastapi.testclient import TestClient

from gabfin.api.app import create_market_app
from gabfin.api.sessions import SessionStore
from gabfin.api.market_gateway import MarketGateway
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.universe.store import CandidateStore

ORIGIN = 'https://desk.test'
ID = str(uuid4())


def test_universe_routes_are_authenticated_and_resolution_is_bounded(tmp_path):
    sessions = SessionStore(tmp_path / 'sessions.sqlite', owner_id=uuid4(), session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)], source='fixture')
    app = create_market_app(sessions, allowed_origin=ORIGIN, gateway=gateway,
        universe={'candidates': CandidateStore(tmp_path / 'u.sqlite'),
                  'lookup': lambda symbol: {'instrument_id': ID} if symbol == 'AAPL' else None})
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get('/v1/universe').status_code == 401
        assert client.post('/pair', json={'code': sessions.create_pairing()}, headers={'Origin': ORIGIN}).status_code == 200
        assert client.get('/v1/universe').json()['candidates'] == []
        assert client.post('/v1/universe/resolve', json={'symbols': 'AAPL'}).status_code == 401
        assert client.post('/v1/universe/resolve', json={'symbols': 'AAPL'}, headers={'Origin': ORIGIN}).status_code == 403
        headers = {'Origin': ORIGIN, 'x-csrf-token': client.cookies.get('__Host-gabfin_csrf')}
        response = client.post('/v1/universe/resolve', json={'symbols': 'AAPL MSFT !'}, headers=headers)
        assert response.status_code == 200
        assert [row['status'] for row in response.json()['results']] == ['resolved', 'unknown', 'invalid']
        assert client.post('/v1/universe/resolve', json={'symbols': 'AAPL', 'owner': 'x'}, headers=headers).status_code == 422
        assert client.get('/v1/universe', headers={'Origin': 'https://evil.test'}).status_code == 401
