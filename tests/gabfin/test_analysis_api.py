"""The analysis routes at the HTTP boundary: origin handling and error shapes.

The planes themselves are tested in `test_analysis_planes.py`. What
matters here is the boundary a browser actually crosses: a same-origin
GET carries no `Origin` header, and `Origin` is a forbidden header
name, so a script cannot add one. A read that insists on the header
is unreachable from the browser.
"""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gabfin.api.sessions import SessionStore

ORIGIN = 'https://desk.test'
INSTRUMENT = '11111111-1111-4111-8111-111111111111'


def analysis_planes():
    """Deterministic planes. Nothing here reaches the network."""
    from gabfin.analysis.plane import CapabilityPlane, IndicatorPlane, MacroPlane
    from gabfin.contracts.market import Timeframe, TimeUnit
    from gabfin.contracts.subscriptions import FeedCapabilities

    class NoBars:
        def bars(self, instrument_id, timeframe):
            return ()

    class FixtureMacro:
        def observations(self, series_id):
            return [{'date': '2026-01-02', 'value': '4.00',
                     'realtime_start': '2026-01-02'}]

    def capabilities():
        return (FeedCapabilities(
            schema_version='1.0', source='fixture', asset_classes=('equity',),
            sessions=('regular',), latency_label='delayed', max_subscriptions=None,
            history_limits=(), checked_at=datetime.now(timezone.utc),
            permission_errors=(), sequence_rules=(), venue_coverage='sip',
            realtime=False, delay_minutes=15, tradable_for_entry=False,
            depth_levels=None, fee_class='none', unavailable_reason=None),)

    return {
        'indicators': IndicatorPlane(NoBars(), source_coverage='sip'),
        'macro': MacroPlane(FixtureMacro()),
        'capabilities': CapabilityPlane(capabilities),
    }


def setup(tmp_path):
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey

    store = SessionStore(tmp_path / 'sessions.sqlite', owner_id=uuid4(),
                         session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(
        lambda ids: None, registered_keys=[
            SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    app = create_market_app(store, allowed_origin=ORIGIN, gateway=gateway,
                            analysis=analysis_planes())
    return app, store


def pair(client, store):
    """Pair, then keep only the session cookie. No Origin header."""
    response = client.post('/pair', json={'code': store.create_pairing()},
                           headers={'Origin': ORIGIN})
    assert response.status_code == 200


def test_a_same_origin_read_without_an_origin_header_is_served(tmp_path):
    """A browser GET carries no Origin header, and it must still work."""
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/capabilities')
        assert response.status_code == 200
        body = response.json()
        assert body['schema_version'] == '1.0'
        assert body['sources'][0]['source'] == 'fixture'


def test_a_same_origin_indicator_read_without_an_origin_header_is_served(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get(
            f'/v1/indicators?instrument_id={INSTRUMENT}&timeframe=1day&indicator=sma')
        # The fixture has no bars, so the series is missing, not refused.
        assert response.status_code == 404
        assert response.json()['detail'] == 'Indicator series not found'


def test_a_same_origin_macro_read_without_an_origin_header_is_served(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/macro?series_id=DGS10&as_of=2026-03-01')
        assert response.status_code == 200
        assert response.json()['as_of'] == '2026-03-01'


def test_a_cross_origin_read_is_refused(tmp_path):
    """A stated origin that is not the allowed origin is still refused."""
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/capabilities',
                              headers={'Origin': 'https://evil.test'})
        assert response.status_code == 401


def test_the_allowed_origin_still_works_when_it_is_stated(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/capabilities', headers={'Origin': ORIGIN})
        assert response.status_code == 200


def test_a_read_without_a_session_is_refused(tmp_path):
    """Relaxing the origin does not relax the session."""
    app, _ = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get('/v1/capabilities').status_code == 401


def test_a_read_with_a_credential_in_the_query_is_refused(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        assert client.get('/v1/capabilities?token=secret').status_code == 401


def test_an_invalid_indicator_request_is_a_bad_request(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get(
            f'/v1/indicators?instrument_id={INSTRUMENT}&timeframe=banana')
        assert response.status_code == 400


def test_an_unknown_macro_series_is_missing(tmp_path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/macro?series_id=NOT_A_SERIES')
        assert response.status_code == 404
        assert response.json()['detail'] == 'Macro series not found'


@pytest.mark.parametrize('path', [
    '/v1/indicators', '/v1/macro', '/v1/capabilities'])
def test_every_analysis_route_refuses_a_foreign_origin(tmp_path, path):
    app, store = setup(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get(path, headers={'Origin': 'https://evil.test'})
        assert response.status_code == 401
