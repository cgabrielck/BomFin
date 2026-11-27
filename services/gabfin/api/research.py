"""Research job routes for the browser.

These routes start and read research jobs. They never decide what a
job concludes, and they never hand the browser a raw snapshot: the
snapshot may carry an account balance, so only its identity, its
cutoff, its data quality and a hash of its content are reported.

The authority is the same one the market and analysis routes use: a
session, an exact origin, and a capability in scope. A job belongs to
the actor who asked for it, and a report that names an account needs
the capability that names a report.

Every failure has a shape the browser can act on:

- No session, a foreign origin or a credential in the query: 401.
- A write without the anti-CSRF nonce: 403.
- A principal without the capability, or another owner's job: 403.
- An unknown instrument, an unknown job: 404.
- An unknown field, an unknown role, a malformed body: 422.
- A stack with no model configured: 503.
"""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from gabfin.api.auth import read_origin, validate_request
from gabfin.api.capabilities import authorize, require_scope
from gabfin.contracts.identity import Capability, Resource
from gabfin.research.jobs import (
    DEFAULT_LIST_LIMIT,
    ROLES,
    JobError,
    JobNotFound,
    JobQueueFull,
)

#: Query names that would carry a credential. The auth guard refuses a
#: request that puts a secret in the URL, so these are checked and the
#: rest of the query is free to carry research parameters.
CREDENTIAL_QUERY_NAMES = frozenset({
    'token', 'csrf', 'session', 'authorization', 'gabfin_session',
    'gabfin_csrf', 'access_token', 'api_key',
})

#: The body of a job request. Every field the browser may name is
#: listed here, and `extra='forbid'` refuses anything else: a client
#: that could name its own snapshot could cite evidence it was never
#: given.
class ResearchJobRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    instrument_id: UUID
    role: str | None = None


def _guarded_query(params) -> dict[str, str]:
    """The credential-bearing part of a query, which the guard refuses."""
    return {
        key: value for key, value in params.items()
        if key.lower() in CREDENTIAL_QUERY_NAMES
    }


def research_router(store, *, allowed_origin, jobs):
    """The research job routes.

    The job queue is injected, so the routes own no model client, no
    capture source and no stored history.
    """
    router = APIRouter()

    def principal(request: Request):
        token = request.cookies.get('gabfin_session')
        try:
            return validate_request(
                store, token,
                origin=read_origin(request.headers.get('origin'), allowed_origin),
                allowed_origin=allowed_origin, write=False,
                query=_guarded_query(request.query_params), csrf=None)
        except PermissionError:
            raise HTTPException(401, 'Unauthorized') from None

    def writing_principal(request: Request):
        """A principal for a write, checked against the CSRF nonce.

        The three refusals are told apart, because the browser acts on
        them differently: a request with no session, a foreign origin
        or a credential in the URL is unauthorized (401), and a
        request that is authenticated but carries no valid anti-CSRF
        nonce is forbidden (403).
        """
        token = request.cookies.get('gabfin_session')
        origin = request.headers.get('origin')
        query = _guarded_query(request.query_params)
        if not token or origin != allowed_origin or query:
            raise HTTPException(401, 'Unauthorized')
        try:
            return validate_request(
                store, token,
                origin=origin,
                allowed_origin=allowed_origin, write=True,
                query=query,
                csrf=request.headers.get('x-csrf-token'))
        except PermissionError:
            raise HTTPException(403, 'Forbidden') from None

    @router.get('/v1/research/status')
    async def research_status(request: Request):
        """Whether research can run at all, and why not when it cannot.

        The route exists whether or not the stack is configured, so a
        browser never has to guess from a 404.
        """
        principal(request)
        return {'configured': jobs.configured, 'reason': jobs.reason}

    @router.post('/v1/research/jobs', status_code=202)
    async def create_job(request: Request):
        """Queue one research job for one instrument."""
        user = writing_principal(request)
        try:
            authorize(user, Capability.START_RESEARCH,
                     Resource(schema_version='1.0', kind='research_job',
                              id=UUID(int=0), owner=user.actor_id))
        except PermissionError:
            raise HTTPException(403, 'Research access denied') from None
        if not jobs.configured:
            raise HTTPException(503, 'Research model not configured')
        body = await _json_body(request)
        try:
            payload = ResearchJobRequest.model_validate(body)
        except ValidationError:
            raise HTTPException(422, 'Invalid research job request') from None
        if payload.role is not None and payload.role not in ROLES:
            raise HTTPException(422, 'Invalid research job request')
        instrument_id = str(payload.instrument_id)
        if instrument_id not in jobs.instrument_ids:
            raise HTTPException(404, 'Instrument not found')
        try:
            job_id = jobs.enqueue(owner=str(user.actor_id),
                                  instrument_id=payload.instrument_id,
                                  role=payload.role)
        except JobQueueFull:
            raise HTTPException(503, 'Research capacity reached') from None
        except JobError:
            raise HTTPException(503, 'Research model not configured') from None
        await jobs.start(job_id)
        return {
            'job_id': job_id,
            'status': 'queued',
            'snapshot_id': None,
            'instrument_id': instrument_id,
            'role': payload.role,
            'result': None,
            'reason': None,
            'error': None,
            'checks': [],
            'snapshot': None,
        }

    @router.get('/v1/research/jobs')
    async def list_jobs(request: Request):
        """The caller's own jobs, newest first.

        A report body needs the capability that names a report. A
        principal that may start a job but not read one still sees its
        own jobs, but only their identity and state: the body of a
        report may carry an account-derived fact, and the list route
        must not be a way around the single job route's check.
        """
        user = principal(request)
        try:
            require_scope(user, Capability.START_RESEARCH)
        except PermissionError:
            raise HTTPException(403, 'Research access denied') from None
        records = jobs.list_for(str(user.actor_id), limit=DEFAULT_LIST_LIMIT)
        may_read = _may_read_reports(user)
        return {'jobs': [_public(record, jobs if may_read else None,
                                include_result=may_read)
                         for record in records]}
    @router.get('/v1/research/jobs/{job_id}')
    async def read_job(job_id: str, request: Request):
        """One job, with its result and the harness verdicts behind it."""
        user = principal(request)
        try:
            record = jobs.get(job_id)
        except JobNotFound:
            raise HTTPException(404, 'Research job not found') from None
        if str(record['owner']) != str(user.actor_id):
            # Another owner's job is not merely hidden: it does not
            # exist for this caller, and saying so would confirm that
            # the id is real.
            raise HTTPException(404, 'Research job not found') from None
        try:
            authorize(user, Capability.READ_REPORT,
                     Resource(schema_version='1.0', kind='research_report',
                              id=UUID(record['job_id']), owner=user.actor_id))
        except PermissionError:
            raise HTTPException(403, 'Research access denied') from None
        except ValueError:
            # A stored id that is not a UUID is a damaged record, not
            # a request the caller can fix. It is refused as missing.
            raise HTTPException(404, 'Research job not found') from None
        return _public(record, jobs)

    return router


def _may_read_reports(user) -> bool:
    """Whether this principal may see the body of a report.

    The scope is checked with the same authority the single job route
    uses. The resource ownership cannot be checked here, because the
    list route spans several jobs; the owner check is made per job
    before the job is listed at all.
    """
    try:
        require_scope(user, Capability.READ_REPORT)
    except PermissionError:
        return False
    return True


def _public(record, jobs=None, *, include_result: bool = True) -> dict:
    """The job as the browser may see it.

    The snapshot is described, never quoted: it may carry an account
    balance, so what is shown is its identity, its cutoff, its data
    quality, how much evidence it holds and a hash of its content. The
    harness verdicts are shown because they say what was checked, not
    what the account holds.

    `include_result` is false for a principal that may not read a
    report. The report body is then left out entirely rather than
    emptied, because a half-report is still a report.
    """
    job_id = record['job_id']
    snapshot_id = record.get('snapshot_id')
    failure = record.get('error')
    body = {
        'job_id': job_id,
        'status': record['status'],
        'instrument_id': record['instrument_id'],
        'role': record.get('role'),
        'snapshot_id': snapshot_id,
        'result': record.get('result') if include_result else None,
        # `reason` is the name the browser reads, and `error` is kept
        # for a caller that reads the old name. They carry the same
        # sanitised text: a failure kind, never a provider message.
        'reason': failure,
        'error': failure,
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at'),
        'checks': [],
        'snapshot': None,
    }
    if jobs is None or not snapshot_id:
        return body
    try:
        body['snapshot'] = jobs.describe_snapshot(UUID(snapshot_id))
    except (KeyError, ValueError):
        body['snapshot'] = None
    try:
        body['checks'] = jobs.checks_for(UUID(snapshot_id))
    except (KeyError, ValueError):
        body['checks'] = []
    return body


async def _json_body(request: Request) -> dict:
    """The request body as a JSON object, or a refusal."""
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise HTTPException(415, 'JSON required')
    data = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                if len(data) + len(chunk) > 16384:
                    raise HTTPException(413, 'Research request too large')
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, 'Research request timed out') from None
    try:
        parsed = json.loads(bytes(data) or b'{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(422, 'Invalid research job request') from None
    if not isinstance(parsed, dict):
        raise HTTPException(422, 'Invalid research job request')
    return parsed
