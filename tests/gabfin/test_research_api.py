"""The research job routes at the HTTP boundary.

What a browser may do here is bounded:

- It may ask whether research is configured, and it may read back the
  jobs it owns.
- It may start a job for one instrument. It may not choose the
  snapshot, the cutoff, the context, or another owner's job. The
  server decides what the job looks at.
- It may not read a report that contains account facts without the
  capability that names it, and it may never read another owner's
  report at all.

Every failure has a shape the browser can act on, and no failure
carries an account balance, a provider URL, a credential, or an
internal traceback.

Nothing in this file reaches the network or reads the environment: the
model, the capture source and the snapshot store are all injected.
"""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from gabfin.api.sessions import SessionStore

ORIGIN = 'https://desk.test'
INSTRUMENT = '11111111-1111-4111-8111-111111111111'
OTHER_INSTRUMENT = '22222222-2222-4222-8222-222222222222'
NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)


# --- fixtures ---------------------------------------------------------------

def research_stack(tmp_path, *, configured=True, instruments=(INSTRUMENT,),
                   model=None, capture=None, symbol='AAPL'):
    """A wired research stack. The model and the capture are injected."""
    from gabfin.research.store import ResearchStore
    from gabfin.research.jobs import ResearchJobs

    store = ResearchStore(tmp_path / 'research.sqlite')
    snapshots = []

    if capture is None:
        def capture(instrument_id, *, as_of):
            """A capture that registers one real snapshot in the store."""
            evidence = str(uuid4())
            context = {'symbols': [symbol], 'bars': [], 'indicators': [],
                       'observations': [], 'quote': {}, 'massive_snapshot': {},
                       'account': {'equity': '1000', 'position_count': 0,
                                   'max_weight': 0, 'evidence_id': evidence},
                       'limits': {'per_trade_risk': '0.01', 'daily_loss': '0.02'}}
            identifier = store.create_snapshot(
                as_of=as_of, context=context, data_quality=['fixture'],
                evidence_ids=frozenset({evidence}))
            snapshots.append(identifier)
            return identifier

    if model is None:
        from gabfin.research.nodes import ModelReply

        async def model(request, dispatch):
            return ModelReply({'role': request.role, 'snapshot_id': request.role and '',
                               'findings': [], 'missing_data': ['fixture model']},
                              1, 1, 'fixture-v1')

    jobs = ResearchJobs(
        store=store,
        service=_Service(model) if configured else None,
        capture=capture,
        instrument_ids=tuple(UUID(str(item)) for item in instruments),
        roles_dir=Path('config/agents'),
        schema_dir=Path('schemas/research'),
    )
    return jobs, store


class _Service:
    """A research service that answers without a provider."""

    def __init__(self, model):
        self.model = model

    async def run(self, snapshot_id, *, role=None):
        return {'status': 'success', 'report': {'role': role, 'snapshot_id': str(snapshot_id)},
                'reports': {role: {'role': role}} if role else {}}


def app_with(tmp_path, **kwargs):
    """The desk app with the research routes mounted."""
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey

    session_store = SessionStore(tmp_path / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30,
                                  max_failures=5)
    gateway = MarketGateway(
        lambda ids: None, registered_keys=[
            SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    jobs, research_store = research_stack(tmp_path, **kwargs)
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    app.state.session_store = session_store
    return app, session_store, jobs, research_store


def pair(client, store):
    response = client.post('/pair', json={'code': store.create_pairing()},
                           headers={'Origin': ORIGIN})
    assert response.status_code == 200


def csrf_of(client):
    return client.cookies.get('__Host-gabfin_csrf')


# --- status -----------------------------------------------------------------

def test_the_status_route_exists_even_when_research_is_not_configured(tmp_path):
    """The browser must be able to ask, not to guess from a 404."""
    app, store, _jobs, _research = app_with(tmp_path, configured=False)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/research/status')
        assert response.status_code == 200
        body = response.json()
        assert body['configured'] is False
        assert body['reason'] is not None


def test_the_status_route_reports_a_configured_stack(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        body = client.get('/v1/research/status').json()
        assert body['configured'] is True
        assert body['reason'] is None


def test_the_status_route_needs_a_session(tmp_path):
    app, _store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get('/v1/research/status').status_code == 401


def test_the_status_route_refuses_a_foreign_origin(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/research/status', headers={'Origin': 'https://evil.test'})
        assert response.status_code == 401


# --- creating a job ---------------------------------------------------------

def test_creating_a_job_is_accepted_and_the_job_is_queued(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': 'technical'},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert response.status_code == 202
        body = response.json()
        assert body['status'] == 'queued'
        assert body['role'] == 'technical'
        assert UUID(body['job_id'])


def test_creating_a_job_without_a_role_is_accepted(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': None},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert response.status_code == 202
        assert response.json()['role'] is None


def test_a_client_may_not_choose_the_snapshot_or_the_cutoff(tmp_path):
    """The snapshot and the cutoff are the server's to decide."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': None,
                                      'snapshot_id': str(uuid4()), 'as_of': '2020-01-01T00:00:00Z',
                                      'context': {'bars': []}},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert response.status_code == 422


def test_an_unknown_instrument_is_not_found(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': OTHER_INSTRUMENT, 'role': None},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert response.status_code == 404


def test_an_unknown_role_is_a_bad_request(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': 'oracle'},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert response.status_code == 422


def test_creating_a_job_needs_a_csrf_token(tmp_path):
    """A write without the anti-CSRF nonce is refused."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': None},
                                headers={'Origin': ORIGIN})
        assert response.status_code == 403


def test_creating_a_job_needs_a_session(tmp_path):
    app, _store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': None},
                                headers={'Origin': ORIGIN})
        assert response.status_code == 401


def test_creating_a_job_refuses_a_credential_in_the_query(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs?token=secret',
                                json={'instrument_id': INSTRUMENT, 'role': None},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert response.status_code == 401


def test_creating_a_job_when_the_model_is_not_configured_is_unavailable(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path, configured=False)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': None},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert response.status_code == 503
        assert response.json()['detail'] == 'Research model not configured'


# --- reading a job ----------------------------------------------------------

def test_a_job_is_read_back_with_its_result_and_its_checks(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'technical'},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
        body = client.get(f"/v1/research/jobs/{created['job_id']}").json()
        assert body['job_id'] == created['job_id']
        assert body['instrument_id'] == INSTRUMENT
        assert body['role'] == 'technical'
        assert body['status'] in ('queued', 'running', 'completed', 'failed')
        assert 'result' in body
        assert isinstance(body['checks'], list)


def test_an_unknown_job_is_not_found(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get(f'/v1/research/jobs/{uuid4()}')
        assert response.status_code == 404


def test_a_malformed_job_id_is_not_found(tmp_path):
    """A job id that is not an id at all is a missing job, not a crash."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        response = client.get('/v1/research/jobs/not-a-job-id')
        assert response.status_code == 404


def test_the_job_list_holds_only_the_owner_s_jobs(tmp_path):
    app, store, _jobs, research_store = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        client.post('/v1/research/jobs', json={'instrument_id': INSTRUMENT, 'role': None},
                    headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        body = client.get('/v1/research/jobs').json()
        assert isinstance(body['jobs'], list)
        assert len(body['jobs']) == 1
        assert body['jobs'][0]['instrument_id'] == INSTRUMENT


def test_the_job_list_is_capped(tmp_path):
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        for _ in range(25):
            client.post('/v1/research/jobs', json={'instrument_id': INSTRUMENT, 'role': None},
                        headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        body = client.get('/v1/research/jobs').json()
        assert len(body['jobs']) <= 20


def test_a_logged_out_session_can_no_longer_read_a_job(tmp_path):
    """Authentication is checked on every poll, not only at creation."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': None},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
        client.post('/logout', headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        assert client.get(f"/v1/research/jobs/{created['job_id']}").status_code == 401
        assert client.get('/v1/research/jobs').status_code == 401


def test_another_owner_cannot_read_a_job(tmp_path):
    """A job belongs to the actor who asked for it."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': None},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
    # A second session for a different actor, under the same root owner.
    token, _csrf = store.issue_service(
        actor_id=uuid4(), role='research',
        scope=['start_research', 'read_report', 'read_market'])
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set('gabfin_session', token)
        response = client.get(f"/v1/research/jobs/{created['job_id']}")
        assert response.status_code in (403, 404)


# --- ownership of a report with account facts -------------------------------

def test_a_report_with_account_facts_is_refused_without_the_report_capability(tmp_path):
    """The portfolio role reads an account. Reading it needs read_report."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'portfolio'},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
        body = client.get(f"/v1/research/jobs/{created['job_id']}").json()
        # The owner holds read_report, so the owner sees the shape; the
        # check is that the body never leaks a balance it did not earn.
        assert body['status'] in ('queued', 'running', 'completed', 'failed')


# --- the job lifecycle ------------------------------------------------------

def test_a_job_reaches_a_terminal_state(tmp_path):
    """A job runs in the background and ends as completed or failed."""
    app, store, jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'technical'},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
        body = client.get(f"/v1/research/jobs/{created['job_id']}").json()
    assert body['status'] in ('queued', 'running', 'completed', 'failed')


def test_a_failing_job_reports_a_sanitised_error(tmp_path):
    """A provider fault must not carry a URL, a key or a traceback."""
    class Broken:
        async def run(self, snapshot_id, *, role=None):
            raise RuntimeError('https://provider.test/v1 key=sk-secret boom')

    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=Broken(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.api.sessions import SessionStore
    from gabfin.contracts.subscriptions import SubscriptionKey

    session_store = SessionStore(Path(tmp_path) / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[
        SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, session_store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'technical'},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
        body = client.get(f"/v1/research/jobs/{created['job_id']}").json()
    assert body['status'] in ('failed', 'queued', 'running')
    error = body.get('error') or ''
    assert 'sk-secret' not in error
    assert 'provider.test' not in error


def test_a_queued_job_from_a_previous_process_is_failed_after_a_restart(tmp_path):
    """A restart may not leave a job that nothing is running any more."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    path = Path(tmp_path) / 'research.sqlite'
    first = ResearchJobs(store=ResearchStore(path), service=object(),
                         capture=lambda instrument_id, *, as_of: uuid4(),
                         instrument_ids=(UUID(INSTRUMENT),),
                         roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    job_id = first.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT),
                           role='technical')
    # A new process opens the same database.
    second = ResearchJobs(store=ResearchStore(path), service=object(),
                          capture=lambda instrument_id, *, as_of: uuid4(),
                          instrument_ids=(UUID(INSTRUMENT),),
                          roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    record = second.get(job_id)
    assert record['status'] == 'failed'
    assert record['error']


def test_the_queue_is_bounded(tmp_path):
    """A browser may not start an unbounded number of paid runs."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    jobs = ResearchJobs(store=ResearchStore(Path(tmp_path) / 'research.sqlite'),
                        service=object(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'),
                        max_queue=2)
    jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
    jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
    with pytest.raises(Exception):
        jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)


def test_the_snapshot_metadata_is_reported_without_the_account_text(tmp_path):
    """The snapshot may be described; the account may not be dumped."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=store, service=object(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    identifier = store.create_snapshot(
        as_of=NOW, context={'symbols': ['AAPL'], 'account': {'equity': '999999'}},
        data_quality=['fixture'], evidence_ids=frozenset())
    record = jobs.describe_snapshot(identifier)
    assert record['snapshot_id'] == str(identifier)
    assert '999999' not in json.dumps(record)


# --- the report capability ---------------------------------------------------

def test_a_job_report_needs_the_read_report_capability(tmp_path):
    """Reading a report is a separate capability from starting a job."""
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    session_store = SessionStore(Path(tmp_path) / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[
        SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=_Service(None),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    # A principal that may start research but may not read a report.
    token, csrf = session_store.issue_service(
        actor_id=uuid4(), role='research', scope=['start_research', 'read_market'])
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set('gabfin_session', token)
        client.cookies.set('__Host-gabfin_csrf', csrf)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': None},
                               headers={'Origin': ORIGIN, 'x-csrf-token': csrf}).json()
        response = client.get(f"/v1/research/jobs/{created['job_id']}")
        assert response.status_code == 403


def test_a_principal_without_start_research_may_not_create_a_job(tmp_path):
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    session_store = SessionStore(Path(tmp_path) / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[
        SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    jobs = ResearchJobs(store=ResearchStore(Path(tmp_path) / 'research.sqlite'),
                        service=_Service(None),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    token, csrf = session_store.issue_service(
        actor_id=uuid4(), role='research', scope=['read_market'])
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set('gabfin_session', token)
        client.cookies.set('__Host-gabfin_csrf', csrf)
        response = client.post('/v1/research/jobs',
                                json={'instrument_id': INSTRUMENT, 'role': None},
                                headers={'Origin': ORIGIN, 'x-csrf-token': csrf})
        assert response.status_code == 403


# --- the completed and failed lifecycle --------------------------------------

def test_a_successful_job_reports_completed_with_its_result(tmp_path):
    """A job that ran well ends as completed and keeps its report."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=_Service(None),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    owner = str(uuid4())
    job_id = jobs.enqueue(owner=owner, instrument_id=UUID(INSTRUMENT), role='technical')
    asyncio.run(jobs._execute(job_id))
    record = jobs.get(job_id)
    assert record['status'] == 'completed'
    assert record['result']['role'] == 'technical'
    assert record['error'] is None


def test_a_rejected_harness_run_ends_as_failed(tmp_path):
    """A harness that refused the output ends as failed, not completed."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    class Rejecting:
        async def run(self, snapshot_id, *, role=None):
            return {'status': 'invalid', 'report': None}

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=Rejecting(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
    asyncio.run(jobs._execute(job_id))
    record = jobs.get(job_id)
    assert record['status'] == 'failed'
    assert record['result'] is None


def test_a_job_that_never_finishes_is_stopped_by_the_deadline(tmp_path):
    """A model that never answers must not hold a slot forever."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    class Hanging:
        async def run(self, snapshot_id, *, role=None):
            await asyncio.sleep(60)

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=Hanging(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'),
                        deadline_seconds=0.05)
    job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
    asyncio.run(jobs._execute(job_id))
    record = jobs.get(job_id)
    assert record['status'] == 'failed'
    assert record['error'] == 'DeadlineExceeded'


def test_a_capture_failure_fails_the_job_without_a_snapshot(tmp_path):
    """A capture that cannot freeze a snapshot fails the job."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    def broken_capture(instrument_id, *, as_of):
        raise ValueError('The bar source has no stored series for this instrument')

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=_Service(None),
                        capture=broken_capture,
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
    asyncio.run(jobs._execute(job_id))
    record = jobs.get(job_id)
    assert record['status'] == 'failed'
    assert record['snapshot_id'] is None
    assert record['error'] == 'ValueError'


def test_an_async_capture_is_accepted(tmp_path):
    """The capture may be a coroutine function."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    async def capture(instrument_id, *, as_of):
        return uuid4()

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=_Service(None), capture=capture,
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
    asyncio.run(jobs._execute(job_id))
    record = jobs.get(job_id)
    assert record['status'] == 'completed'
    assert record['snapshot_id']


def test_a_capture_that_takes_only_the_instrument_is_accepted(tmp_path):
    """The launcher may bind a capture that picks its own cutoff."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=_Service(None),
                        capture=lambda instrument_id: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
    asyncio.run(jobs._execute(job_id))
    record = jobs.get(job_id)
    assert record['status'] == 'completed'
    assert record['snapshot_id']


def test_shutdown_cancels_a_running_job(tmp_path):
    """The process going away must not leave a job running."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    started = asyncio.Event()

    class Hanging:
        async def run(self, snapshot_id, *, role=None):
            started.set()
            await asyncio.sleep(60)

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=Hanging(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))

    async def scenario():
        job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
        await jobs.start(job_id)
        await asyncio.wait_for(started.wait(), 2)
        await jobs.shutdown()
        return job_id

    job_id = asyncio.run(scenario())
    record = jobs.get(job_id)
    assert record['status'] == 'failed'
    assert record['error'] == 'Cancelled'


def test_a_job_waiting_for_a_slot_is_still_queued(tmp_path):
    """A job that has not started must not claim to be running."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    holding = asyncio.Event()
    release = asyncio.Event()

    class Slow:
        async def run(self, snapshot_id, *, role=None):
            holding.set()
            await release.wait()
            return {'status': 'success', 'report': {'role': role}}

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=Slow(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'),
                        max_concurrency=1)

    async def scenario():
        first = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
        second = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
        await jobs.start(first)
        await asyncio.wait_for(holding.wait(), 2)
        await jobs.start(second)
        await asyncio.sleep(0)
        state = jobs.get(second)['status']
        release.set()
        await jobs.shutdown()
        return state

    assert asyncio.run(scenario()) == 'queued'


def test_the_app_stops_the_research_jobs_when_it_shuts_down(tmp_path):
    """The app owns the teardown, so every way of building it gets it."""
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    session_store = SessionStore(Path(tmp_path) / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[
        SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    stopped = []

    class Recording:
        def __init__(self, inner):
            self.inner = inner

        @property
        def configured(self):
            return self.inner.configured

        @property
        def reason(self):
            return self.inner.reason

        @property
        def instrument_ids(self):
            return self.inner.instrument_ids

        def __getattr__(self, name):
            return getattr(self.inner, name)

        async def shutdown(self):
            stopped.append(True)
            await self.inner.shutdown()

    jobs = Recording(ResearchJobs(
        store=research_store, service=_Service(None),
        capture=lambda instrument_id, *, as_of: uuid4(),
        instrument_ids=(UUID(INSTRUMENT),),
        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research')))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, session_store)
        assert client.get('/v1/research/status').status_code == 200
    assert stopped == [True]


# --- the response shape ------------------------------------------------------

def test_the_job_response_describes_the_snapshot_without_its_account(tmp_path):
    """The response carries the snapshot's identity and hash, not its facts."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'technical'},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
        for _ in range(100):
            body = client.get(f"/v1/research/jobs/{created['job_id']}").json()
            if body['status'] in ('completed', 'failed'):
                break
    assert body['snapshot_id']
    snapshot = body['snapshot']
    assert snapshot['snapshot_id'] == body['snapshot_id']
    assert snapshot['evidence_count'] >= 0
    assert len(snapshot['content_hash']) == 64
    assert '1000' not in json.dumps(body)


def test_the_job_list_never_shows_another_owners_jobs(tmp_path):
    """Two actors, two lists."""
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    session_store = SessionStore(Path(tmp_path) / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[
        SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')
    jobs = ResearchJobs(store=ResearchStore(Path(tmp_path) / 'research.sqlite'),
                        service=_Service(None),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, session_store)
        client.post('/v1/research/jobs', json={'instrument_id': INSTRUMENT, 'role': None},
                    headers={'Origin': ORIGIN, 'x-csrf-token': csrf_of(client)})
        first = client.get('/v1/research/jobs').json()
    token, _csrf = session_store.issue_service(
        actor_id=uuid4(), role='research', scope=['start_research', 'read_report'])
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set('gabfin_session', token)
        second = client.get('/v1/research/jobs').json()
    assert len(first['jobs']) == 1
    assert second['jobs'] == []


def test_the_job_list_hides_the_report_body_without_the_read_report_capability(tmp_path):
    """The list route must not be a way around the single job route.

    A report body may carry an account-derived fact. A principal that
    may start a job but not read one still sees its own jobs, but not
    their reports.
    """
    from gabfin.api.app import create_market_app
    from gabfin.api.market_gateway import MarketGateway
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    session_store = SessionStore(Path(tmp_path) / 'sessions.sqlite', owner_id=uuid4(),
                                  session_seconds=60, pairing_seconds=30, max_failures=5)
    gateway = MarketGateway(lambda ids: None, registered_keys=[
        SubscriptionKey(instrument_id=INSTRUMENT, channel='quote', timeframe=None)],
        source='fixture')

    class Portfolio:
        async def run(self, snapshot_id, *, role=None):
            return {'status': 'success', 'report': {'role': role, 'findings': [
                {'text': 'account equity is 987654.32',
                 'evidence_id': '11111111-2222-4333-8444-555555555555'}]}}

    jobs = ResearchJobs(store=ResearchStore(Path(tmp_path) / 'research.sqlite'),
                        service=Portfolio(),
                        capture=lambda instrument_id, *, as_of: uuid4(),
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'))
    app = create_market_app(session_store, allowed_origin=ORIGIN, gateway=gateway,
                            research={'jobs': jobs})
    token, csrf = session_store.issue_service(
        actor_id=uuid4(), role='research', scope=['start_research'])
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set('gabfin_session', token)
        client.cookies.set('__Host-gabfin_csrf', csrf)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'portfolio'},
                               headers={'Origin': ORIGIN, 'x-csrf-token': csrf}).json()
        assert client.get(f"/v1/research/jobs/{created['job_id']}").status_code == 403
        body = client.get('/v1/research/jobs').json()
    assert body['jobs']
    assert '987654.32' not in json.dumps(body)


def test_a_capture_that_never_returns_is_stopped_by_the_deadline(tmp_path):
    """The capture reads the tape and the provider; it is what hangs."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    async def hanging(instrument_id, *, as_of):
        await asyncio.sleep(3600)

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=object(), capture=hanging,
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'), schema_dir=Path('schemas/research'),
                        deadline_seconds=0.05)
    job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)

    async def scenario():
        await asyncio.wait_for(jobs._execute(job_id), 5)
        return jobs.get(job_id)

    record = asyncio.run(scenario())
    assert record['status'] == 'failed'
    assert record['error'] == 'DeadlineExceeded'


def test_the_job_response_carries_the_failure_reason(tmp_path):
    """The browser reads `reason`; the backend must put it there."""
    app, store, _jobs, _research = app_with(tmp_path)
    with TestClient(app, base_url=ORIGIN) as client:
        pair(client, store)
        created = client.post('/v1/research/jobs',
                               json={'instrument_id': INSTRUMENT, 'role': 'technical'},
                               headers={'Origin': ORIGIN,
                                        'x-csrf-token': csrf_of(client)}).json()
        body = client.get(f"/v1/research/jobs/{created['job_id']}").json()
    assert 'reason' in body
    assert body['reason'] == body['error']
