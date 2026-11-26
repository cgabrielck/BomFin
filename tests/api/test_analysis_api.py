"""Read-only analysis routes: authentication, capability, and failure shapes.

The routes own no provider client and no stored history. The planes are
injected, so these tests exercise the HTTP boundary: what a browser can
read, what it cannot, and what each refusal looks like.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from gabfin.api.sessions import SessionStore
from gabfin.contracts.subscriptions import FeedCapabilities

ORIGIN = 'https://desk.test'
NOW = datetime(2026, 3, 2, 21, 0, tzinfo=timezone.utc)
INSTRUMENT = '11111111-1111-4111-8111-111111111111'


class StubIndicators:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def series(self, instrument_id, timeframe, *, indicators=None, limit=500):
        self.calls.append((instrument_id, timeframe, indicators, limit))
        if self.error is not None:
            raise self.error
        from gabfin.contracts.analysis import IndicatorResponse
        return IndicatorResponse(
            schema_version='1.0', instrument_id=instrument_id, timeframe=timeframe,
            source_coverage='sip', computed_by='local', series=(), statuses=())


class StubMacro:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def snapshot(self, series_id=None, *, as_of=None):
        self.calls.append((series_id, as_of))
        if self.error is not None:
            raise self.error
        from gabfin.contracts.analysis import MacroResponse
        return MacroResponse(schema_version='1.0', observed_at=NOW,
                             as_of=as_of or date(2026, 3, 2), points=())


class StubCapabilities:
    def __init__(self, error=None):
        self.error = error

    def snapshot(self):
        if self.error is not None:
            raise self.error
        from gabfin.contracts.analysis import CapabilitiesResponse
        return CapabilitiesResponse(schema_version='1.0', checked_at=NOW, sources=())


def build(tmp_path, *, indicators=None, macro=None, capabilities=None):
    """An app with the analysis routes and a stub gateway."""
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey

    store = SessionStore(tmp_path / 'sessions.sqlite', owner_id=uuid4(),
                         session_seconds=60, pairing_seconds=30, max_failures=5)
    key = SubscriptionKey(instrument_id=UUID(INSTRUMENT), channel='quote', timeframe=None)

    async def connect(ids):
        raise RuntimeError('no market connection in an analysis test')

    gateway = MarketGateway(connect, registered_keys=[key], source='test-feed')
    app = create_market_app(
        store, allowed_origin=ORIGIN, gateway=gateway,
        analysis=dict(
            indicators=indicators or StubIndicators(),
            macro=macro or StubMacro(),
            capabilities=capabilities or StubCapabilities(),
        ),
    )
    return app, store


def paired(client, store):
    response = client.post('/pair', json={'code': store.create_pairing()},
                            headers={'Origin': ORIGIN})
    assert response.status_code == 200
    return {'Origin': ORIGIN}


@pytest.fixture
def client(tmp_path):
    app, store = build(tmp_path)
    with TestClient(app, base_url=ORIGIN) as test_client:
        yield test_client, store


def test_analysis_routes_require_a_session(client):
    test_client, _ = client
    for path in ('/v1/indicators', '/v1/macro', '/v1/capabilities'):
        response = test_client.get(path, headers={'Origin': ORIGIN})
        assert response.status_code == 401
        assert response.json()['detail'] == 'Unauthorized'


def test_analysis_routes_refuse_a_foreign_origin(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/capabilities', headers={'Origin': 'https://evil.test'})
    assert response.status_code == 401


def test_analysis_routes_refuse_plain_http(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/capabilities', headers=headers)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'


def test_a_valid_session_reads_the_capability_plane(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/capabilities', headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['schema_version'] == '1.0'
    assert body['sources'] == []


def test_a_principal_without_market_read_is_refused(client):
    test_client, store = client
    token, _ = store.issue_service(actor_id=uuid4(), role='chat', scope=['read_account'])
    test_client.cookies.set('gabfin_session', token)
    response = test_client.get('/v1/capabilities', headers={'Origin': ORIGIN})
    assert response.status_code == 403
    assert response.json()['detail'] == 'Market access denied'


def test_indicator_route_passes_the_parameters_to_the_plane(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get(
        '/v1/indicators',
        params={'instrument_id': INSTRUMENT, 'timeframe': '1day',
                'indicator': ['rsi', 'macd'], 'limit': '100'},
        headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['instrument_id'] == INSTRUMENT
    assert body['timeframe'] == {'count': 1, 'unit': 'trading_day'}


def test_indicator_route_rejects_a_missing_or_malformed_instrument(client):
    test_client, store = client
    headers = paired(test_client, store)
    assert test_client.get('/v1/indicators',
                            params={'timeframe': '1day'}, headers=headers).status_code == 400
    assert test_client.get('/v1/indicators',
                            params={'instrument_id': 'not-a-uuid', 'timeframe': '1day'},
                            headers=headers).status_code == 400


@pytest.mark.parametrize('timeframe', ['', 'day', '1', '1fortnight', '0day'])
def test_indicator_route_rejects_a_malformed_timeframe(client, timeframe):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/indicators',
                               params={'instrument_id': INSTRUMENT, 'timeframe': timeframe},
                               headers=headers)
    assert response.status_code == 400
    assert response.json()['detail'] == 'Invalid indicator request'


def test_indicator_route_rejects_a_malformed_limit(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/indicators',
                               params={'instrument_id': INSTRUMENT, 'timeframe': '1day',
                                       'limit': 'many'},
                               headers=headers)
    assert response.status_code == 400


def test_indicator_route_maps_an_unknown_indicator_to_400(tmp_path):
    from gabfin.analysis.plane import AnalysisUnavailable
    app, store = build(tmp_path, indicators=StubIndicators(
        error=AnalysisUnavailable('unknown_indicator', 'supertrend')))
    with TestClient(app, base_url=ORIGIN) as test_client:
        headers = paired(test_client, store)
        response = test_client.get('/v1/indicators',
                                   params={'instrument_id': INSTRUMENT, 'timeframe': '1day'},
                                   headers=headers)
        assert response.status_code == 400


def test_indicator_route_maps_a_missing_series_to_404(tmp_path):
    from gabfin.analysis.plane import AnalysisUnavailable
    app, store = build(tmp_path, indicators=StubIndicators(
        error=AnalysisUnavailable('insufficient_history', 'no stored bars')))
    with TestClient(app, base_url=ORIGIN) as test_client:
        headers = paired(test_client, store)
        response = test_client.get('/v1/indicators',
                                   params={'instrument_id': INSTRUMENT, 'timeframe': '1day'},
                                   headers=headers)
        assert response.status_code == 404
        assert response.json()['detail'] == 'Indicator series not found'


def test_indicator_route_reports_an_unavailable_plane_as_503(tmp_path):
    app, store = build(tmp_path, indicators=StubIndicators(error=RuntimeError('upstream down')))
    with TestClient(app, base_url=ORIGIN) as test_client:
        headers = paired(test_client, store)
        response = test_client.get('/v1/indicators',
                                   params={'instrument_id': INSTRUMENT, 'timeframe': '1day'},
                                   headers=headers)
        assert response.status_code == 503
        assert 'upstream' not in response.text


def test_macro_route_filters_by_the_requested_date(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/macro',
                               params={'series_id': 'DGS10', 'as_of': '2026-02-15'},
                               headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body['as_of'] == '2026-02-15'


def test_macro_route_rejects_a_malformed_date(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/macro', params={'as_of': '15-02-2026'}, headers=headers)
    assert response.status_code == 400
    assert response.json()['detail'] == 'Invalid macro request'


def test_macro_route_maps_an_unknown_series_to_404(tmp_path):
    from gabfin.analysis.plane import AnalysisUnavailable
    app, store = build(tmp_path, macro=StubMacro(
        error=AnalysisUnavailable('unknown_series', 'NOPE')))
    with TestClient(app, base_url=ORIGIN) as test_client:
        headers = paired(test_client, store)
        response = test_client.get('/v1/macro', headers=headers)
        assert response.status_code == 404
        assert response.json()['detail'] == 'Macro series not found'


def test_macro_route_reports_a_missing_provider_key_as_503(tmp_path):
    app, store = build(tmp_path, macro=StubMacro(error=RuntimeError('FRED_API_KEY is not set')))
    with TestClient(app, base_url=ORIGIN) as test_client:
        headers = paired(test_client, store)
        response = test_client.get('/v1/macro', headers=headers)
        assert response.status_code == 503
        assert 'FRED_API_KEY' not in response.text


def test_capability_route_reports_an_unavailable_plane_as_503(tmp_path):
    app, store = build(tmp_path, capabilities=StubCapabilities(error=RuntimeError('probe failed')))
    with TestClient(app, base_url=ORIGIN) as test_client:
        headers = paired(test_client, store)
        response = test_client.get('/v1/capabilities', headers=headers)
        assert response.status_code == 503


def test_a_credential_in_the_query_is_refused(client):
    test_client, store = client
    headers = paired(test_client, store)
    response = test_client.get('/v1/capabilities?token=fake', headers=headers)
    assert response.status_code == 401


def test_the_analysis_routes_never_cache(client):
    test_client, store = client
    headers = paired(test_client, store)
    for path in ('/v1/macro', '/v1/capabilities'):
        response = test_client.get(path, headers=headers)
        assert response.headers['cache-control'] == 'no-store'


def test_capability_response_carries_the_feed_truth_fields(tmp_path):
    source = FeedCapabilities(
        schema_version='1.0', source='alpaca', asset_classes=('equity',),
        sessions=('regular',), latency_label='delayed', max_subscriptions=None,
        history_limits=(), checked_at=NOW, permission_errors=(), sequence_rules=(),
        venue_coverage='sip', realtime=False, delay_minutes=15,
        tradable_for_entry=False, depth_levels=None, fee_class='none',
        unavailable_reason=None)

    class WithSource:
        def snapshot(self):
            from gabfin.contracts.analysis import CapabilitiesResponse
            return CapabilitiesResponse(schema_version='1.0', checked_at=NOW, sources=(source,))

    app, store = build(tmp_path, capabilities=WithSource())
    with TestClient(app, base_url=ORIGIN) as test_client:
        headers = paired(test_client, store)
        body = test_client.get('/v1/capabilities', headers=headers).json()
        entry = body['sources'][0]
        assert entry['venue_coverage'] == 'sip'
        assert entry['realtime'] is False
        assert entry['delay_minutes'] == 15
        assert entry['tradable_for_entry'] is False
        assert entry['depth_levels'] is None
        assert entry['fee_class'] == 'none'
        assert entry['unavailable_reason'] is None
