from uuid import uuid4
from fastapi.testclient import TestClient

from test_research_api import app_with, pair, csrf_of, ORIGIN


def test_resolved_instrument_can_start_research_without_queue_restart(tmp_path):
    from gabfin.universe.directory import InstrumentDirectory
    from gabfin.api.universe import universe_router
    from gabfin.universe.store import CandidateStore
    directory = InstrumentDirectory(tmp_path / 'instruments.sqlite', lookup=lambda symbol: {
        'ticker': symbol, 'market': 'stocks', 'locale': 'us', 'active': True, 'currency_name': 'usd', 'name': 'Verified fixture'})
    app, sessions, jobs, snapshots = app_with(tmp_path)
    jobs.instrument_directory = directory
    app.include_router(universe_router(sessions, allowed_origin=ORIGIN,
        candidates=CandidateStore(tmp_path / 'candidates.sqlite'), lookup=directory.resolve))
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, sessions)
        headers = {'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)}
        resolved = client.post('/v1/universe/resolve', json={'symbols': 'MSFT'}, headers=headers)
        assert resolved.status_code == 200
        assert resolved.json()['results'][0]['name'] == 'Verified fixture'
        identity = resolved.json()['results'][0]['instrument_id']
        # The same directory identity is now available to the research authority.
        assert directory.by_id(identity)['symbol'] == 'MSFT'
        response = client.post('/v1/research/jobs', json={'instrument_id': identity, 'role': 'technical'}, headers=headers)
        assert response.status_code == 202
        job_id = response.json()['job_id']
        for _ in range(100):
            body = client.get('/v1/research/jobs/' + job_id).json()
            if body['status'] in ('completed', 'failed'):
                break
        assert body['status'] == 'completed'
        assert body['instrument_id'] == identity
        assert body['snapshot_id']
        assert client.post('/v1/research/jobs', json={'instrument_id': str(uuid4())}, headers=headers).status_code == 404
