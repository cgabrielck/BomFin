"""The whole-graph result shape, pinned across the HTTP boundary.

A job that names no role runs the whole graph, so the browser
receives one report per role. The backend's `_result_of` extracts
`result['reports']` and returns the map itself:

    {"discovery": {...}, "technical": {...}, "portfolio": {...}}

The browser's `collectResults` looks for `result.reports` first and
falls back to `'role' in result`. A bare role map has neither, so the
panel renders no conclusion at all for a whole-graph job.

This test reads the real backend response and asserts the shape the
browser can read.
"""
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

ORIGIN = 'https://desk.test'
INSTRUMENT = '11111111-1111-4111-8111-111111111111'


class GraphService:
    """The whole-graph result exactly as `build_research_graph` returns it."""

    async def run(self, snapshot_id, *, role=None):
        return {
            'reports': {
                'discovery': {'role': 'discovery', 'snapshot_id': str(snapshot_id),
                              'findings': [{'text': 'd', 'evidence_id': 'e'}],
                              'missing_data': []},
                'technical': {'role': 'technical', 'snapshot_id': str(snapshot_id),
                              'findings': [{'text': 't', 'evidence_id': 'e'}],
                              'missing_data': []},
                'portfolio': {'role': 'portfolio', 'snapshot_id': str(snapshot_id),
                              'findings': [], 'missing_data': ['no account']},
            },
            'status': 'success',
            'audit': [],
        }


def test_a_whole_graph_job_reaches_the_browser_in_a_readable_shape(tmp_path):
    """A whole-graph job must be readable as three role reports."""
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.api.sessions import SessionStore
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    session_store = SessionStore(tmp_path / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[
        SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=GraphService(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'),
                        schema_dir=Path('schemas/research'))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    with TestClient(app, base_url=ORIGIN) as client:
        client.post('/pair', json={'code': session_store.create_pairing()},
                    headers={'Origin': ORIGIN})
        csrf = client.cookies.get('__Host-gabfin_csrf')
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': None},
                               headers={'Origin': ORIGIN, 'x-csrf-token': csrf}).json()
        body = client.get(f"/v1/research/jobs/{created['job_id']}").json()

    assert body['status'] == 'completed', body
    result = body['result']
    assert result is not None, 'the whole-graph job stored no report'

    # The browser's collectResults, verbatim.
    def collect_results(value):
        if not value:
            return []
        if value.get('reports') and isinstance(value['reports'], dict):
            return [item for item in value['reports'].values()
                    if isinstance(item, dict) and 'role' in item]
        return [value] if 'role' in value else []

    roles = collect_results(result)
    print('stored result keys:', sorted(result.keys()))
    print('roles the browser would render:', [r['role'] for r in roles])
    assert len(roles) == 3, (
        'the browser renders no conclusion for a whole-graph job; the '
        f'stored shape is {sorted(result.keys())!r}')
