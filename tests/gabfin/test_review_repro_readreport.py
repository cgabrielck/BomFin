"""Reproduction: the job list route leaks the report body without READ_REPORT.

A principal that may start a research job but may not read a report
should see only the job's identity and status in the list. The single
job route enforces that with `authorize(..., READ_REPORT)`. The list
route does not.
"""
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

ORIGIN = 'https://desk.test'
INSTRUMENT = '11111111-1111-4111-8111-111111111111'


def test_the_list_route_hides_the_report_from_a_principal_without_read_report(tmp_path):
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

    class PortfolioService:
        """A service whose report carries an account-derived fact."""

        async def run(self, snapshot_id, *, role=None):
            return {
                'status': 'success',
                'report': {
                    'role': role,
                    'snapshot_id': str(snapshot_id),
                    'findings': [
                        {'text': 'account equity is 987654.32',
                         'evidence_id': '11111111-2222-4333-8444-555555555555'},
                    ],
                    'missing_data': [],
                },
            }

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=PortfolioService(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'),
                        schema_dir=Path('schemas/research'))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})

    # A principal that may START research but may NOT read a report.
    token, csrf = session_store.issue_service(
        actor_id=uuid4(), role='research', scope=['start_research'])
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set('gabfin_session', token)
        client.cookies.set('__Host-gabfin_csrf', csrf)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'portfolio'},
                               headers={'Origin': ORIGIN, 'x-csrf-token': csrf}).json()
        # The single job route refuses: no READ_REPORT.
        single = client.get(f"/v1/research/jobs/{created['job_id']}")
        assert single.status_code == 403, single.status_code
        # The list route must refuse the report body too.
        listed = client.get('/v1/research/jobs')
        assert listed.status_code == 200, listed.status_code
        body = listed.json()
        print('LIST BODY:', body)
        assert body['jobs'], 'the job should be listed'
        assert '987654.32' not in str(body), (
            'LEAK: the list route returned the report body to a principal '
            'without read_report')
