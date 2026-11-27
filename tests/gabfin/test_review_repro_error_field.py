"""Reproduction: the backend returns `error`, the browser reads `reason`.

`_public` puts the sanitised failure under `error`. The browser's
`parseJob` reads `value.reason`. The failure reason therefore never
reaches the reader, and the panel falls back to "the server gave no
reason".

This test pins the two sides of the contract to each other.
"""
import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

ORIGIN = 'https://desk.test'
INSTRUMENT = '11111111-1111-4111-8111-111111111111'


def test_the_job_response_carries_the_failure_under_the_name_the_browser_reads(tmp_path):
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

    class Broken:
        async def run(self, snapshot_id, *, role=None):
            raise RuntimeError('https://provider.test/v1 key=sk-secret boom')

    jobs = ResearchJobs(store=research_store, service=Broken(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'),
                        schema_dir=Path('schemas/research'))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    with TestClient(app, base_url=ORIGIN) as client:
        code = session_store.create_pairing()
        client.post('/pair', json={'code': code}, headers={'Origin': ORIGIN})
        csrf = client.cookies.get('__Host-gabfin_csrf')
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'technical'},
                               headers={'Origin': ORIGIN, 'x-csrf-token': csrf}).json()
        body = client.get(f"/v1/research/jobs/{created['job_id']}").json()

    print('BODY:', json.dumps(body, ensure_ascii=False))
    assert body['status'] == 'failed'
    # The browser reads `reason`.
    assert body.get('reason'), (
        'the job response has no `reason`; the browser reads `reason` and '
        'would show "the server gave no reason". The backend puts it '
        f"under `error`: {body.get('error')!r}")
