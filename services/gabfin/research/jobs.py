"""Durable research jobs: one queue, one SQLite record per job.

A research job is a request to run the harness over one frozen
snapshot. The browser may ask for one; it may not decide what the job
looks at. The snapshot, the cutoff and the context are the server's to
choose, because a client that could name its own snapshot could cite
evidence it was never given.

The rules this module holds:

- **The queue is bounded.** A research run costs money, so an
  unbounded queue is an unbounded bill. The queue holds a fixed number
  of waiting jobs and a fixed number of running ones; a caller that
  exceeds either is refused rather than queued forever.
- **A job survives the process.** The record is written before the job
  runs, so a crash leaves a record that says what was in flight. A job
  that was queued or running when the process died is failed on the
  next open, because nothing is running any more.
- **A failure is sanitised.** The stored error names the kind of
  failure, never the message, so a provider URL, a key or a traceback
  cannot reach the browser or the database.
- **The snapshot is the server's.** The capture callable is called
  with the instrument id and the server's own cutoff. The client never
  supplies either.

Nothing here reaches the network or reads the environment. The model,
the capture source and the snapshot store are all injected.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import sqlite3
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

#: The job states a job may be in. A job is created `queued`, moves to
#: `running` while the harness works, and ends in `completed` or
#: `failed`. It never ends in any other state.
JOB_STATES = ('queued', 'running', 'completed', 'failed')

#: The roles the harness knows. A role outside this set is not a
#: request the server can honour.
ROLES = ('discovery', 'technical', 'portfolio')

#: The maximum number of jobs that may be waiting or running at once.
DEFAULT_MAX_QUEUE = 8
#: The maximum number of jobs that may run at the same time.
DEFAULT_MAX_CONCURRENCY = 2
#: The wall-clock limit on one job, in seconds. The role card also
#: carries a per-node deadline; this is the outer bound on the whole
#: job, so a job cannot run forever whatever the roles do.
DEFAULT_JOB_DEADLINE_SECONDS = 300.0
#: The number of jobs the list route returns.
DEFAULT_LIST_LIMIT = 20


class JobError(RuntimeError):
    """A job request cannot be honoured. The message never carries a payload."""


class JobQueueFull(JobError):
    """The queue is full; the request is refused rather than queued forever."""


class JobNotFound(JobError):
    """No such job."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _text(value: Any) -> str:
    """JSON text for one stored document, or empty text for nothing."""
    if value is None:
        return ''
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      default=str)


def _sanitise_error(error: BaseException) -> str:
    """A stored description of a failure that leaks nothing.

    Only the kind of failure is kept. A provider message may carry an
    endpoint, a key or a request body, and none of those belong in a
    database the browser may read.
    """
    return f'{type(error).__name__}'


def _uuid_text(value: Any) -> str:
    return str(UUID(str(value)))


def _store_path(store: Any) -> Path | None:
    """The database the snapshot store owns, when it names one.

    The job records live beside the snapshots they point at, so a
    restart finds both together. A store that keeps its database
    somewhere else is honoured through the explicit `db_path`.
    """
    path = getattr(store, 'path', None)
    return Path(path) if path is not None else None


class ResearchJobs:
    """The research job queue, its durable records, and its runner.

    `store` holds the immutable snapshots and the audit trail; it is
    the research authority. `service` runs the harness over a snapshot.
    `capture` freezes one snapshot for an instrument at the server's
    own cutoff. All three are injected, so this module owns no
    provider client and no environment.
    """

    _SCHEMA = (
        """CREATE TABLE IF NOT EXISTS research_jobs(
             job_id TEXT PRIMARY KEY,
             owner TEXT NOT NULL,
             instrument_id TEXT NOT NULL,
             role TEXT,
             status TEXT NOT NULL,
             snapshot_id TEXT,
             result TEXT,
             error TEXT,
             created_at TEXT NOT NULL,
             updated_at TEXT NOT NULL)""",
    )

    def __init__(self, *, store, service=None, capture=None,
                 instrument_ids: Sequence[UUID] = (),
                 roles_dir: Path | None = None, schema_dir: Path | None = None,
                 db_path: Path | None = None,
                 max_queue: int = DEFAULT_MAX_QUEUE,
                 max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
                 deadline_seconds: float = DEFAULT_JOB_DEADLINE_SECONDS,
                 clock: Callable[[], datetime] | None = None,
                 instrument_directory=None):
        self.store = store
        self.service = service
        self.capture = capture
        self._instrument_ids = frozenset(str(item) for item in instrument_ids)
        self.instrument_directory = instrument_directory
        self.roles_dir = roles_dir
        self.schema_dir = schema_dir
        self.max_queue = max(1, int(max_queue))
        self.max_concurrency = max(1, int(max_concurrency))
        self.deadline_seconds = float(deadline_seconds)
        self._clock = clock or _now
        self._db_path = Path(db_path) if db_path is not None else _store_path(store)
        self._tasks: set[asyncio.Task] = set()
        self._semaphore: asyncio.Semaphore | None = None
        if self._db_path is not None:
            self._ensure_schema()
            self._fail_interrupted()

    # --- configuration ----------------------------------------------------

    @property
    def instrument_ids(self):
        if self.instrument_directory is None:
            return self._instrument_ids
        return self._instrument_ids | frozenset(self.instrument_directory.instrument_ids)

    @property
    def configured(self) -> bool:
        """Whether this stack can actually run a job.

        A stack without a model, without a capture source or without a
        known instrument cannot produce a report. Saying so is the
        honest answer; a fake report is not.
        """
        return (self.service is not None and self.capture is not None
                and bool(self.instrument_ids))

    @property
    def reason(self) -> str | None:
        """Why the stack is not configured, or None when it is."""
        if self.service is None:
            return 'model_not_configured'
        if self.capture is None:
            return 'capture_not_configured'
        if not self.instrument_ids:
            return 'no_instruments'
        return None

    # --- persistence ------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if self._db_path is None:
            raise JobError('No job database was configured')
        connection = sqlite3.connect(self._db_path, timeout=5)
        connection.execute('pragma journal_mode=WAL')
        connection.execute('pragma busy_timeout=5000')
        return connection

    def _ensure_schema(self) -> None:
        connection = self._connect()
        try:
            with connection:
                for statement in self._SCHEMA:
                    connection.execute(statement)
        finally:
            connection.close()

    def _fail_interrupted(self) -> None:
        """Fail every job that was in flight when the process died.

        A job that was queued or running when the process stopped has
        nothing running it any more. Leaving it queued would promise
        work that will never happen, so it is failed on the next open.
        """
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    "UPDATE research_jobs SET status='failed', error=?, updated_at=?"
                    " WHERE status IN ('queued','running')",
                    ('InterruptedByRestart', self._clock().isoformat()))
        finally:
            connection.close()

    def _update(self, job_id: str, **fields: Any) -> None:
        allowed = ('status', 'snapshot_id', 'result', 'error', 'updated_at')
        columns = [name for name in allowed if name in fields]
        if not columns:
            return
        assignments = ', '.join(f'{name}=?' for name in columns)
        values = [fields[name] for name in columns]
        values.append(job_id)
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    f"UPDATE research_jobs SET {assignments} WHERE job_id=?", values)
        finally:
            connection.close()

    def _row_to_record(self, row: Sequence[Any]) -> dict[str, Any]:
        (job_id, owner, instrument_id, role, status, snapshot_id, result,
         error, created_at, updated_at) = row
        return {
            'job_id': job_id,
            'owner': owner,
            'instrument_id': instrument_id,
            'role': role,
            'status': status,
            'snapshot_id': snapshot_id,
            'result': json.loads(result) if result else None,
            'error': error or None,
            'created_at': created_at,
            'updated_at': updated_at,
        }

    # --- the queue --------------------------------------------------------

    def enqueue(self, *, owner: str, instrument_id: UUID, role: str | None) -> str:
        """Record one queued job and return its id.

        The record is written before the job runs, so a crash leaves
        evidence of what was asked for.

        The queue bound and the write happen in one transaction, so two
        callers racing for the last slot cannot both take it: a
        research run costs money, and a queue that overflows under
        concurrency overflows the bill.
        """
        if not self.configured:
            raise JobError('Research is not configured')
        identifier = str(uuid.uuid4())
        moment = self._clock().isoformat()
        record = {
            'job_id': identifier,
            'owner': owner,
            'instrument_id': str(instrument_id),
            'role': role,
            'status': 'queued',
            'snapshot_id': None,
            'result': None,
            'error': None,
            'created_at': moment,
            'updated_at': moment,
        }
        connection = self._connect()
        try:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(
                "SELECT count(*) FROM research_jobs WHERE status IN ('queued','running')"
            ).fetchone()
            if row and int(row[0]) >= self.max_queue:
                connection.rollback()
                raise JobQueueFull('The research queue is full')
            connection.execute(
                "INSERT OR REPLACE INTO research_jobs"
                "(job_id, owner, instrument_id, role, status, snapshot_id,"
                " result, error, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (record['job_id'], record['owner'], record['instrument_id'],
                 record['role'], record['status'], record['snapshot_id'],
                 record.get('result') or '', record.get('error') or '',
                 record['created_at'], record['updated_at']))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return identifier

    def queued_count(self) -> int:
        """How many jobs are waiting or running right now."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT count(*) FROM research_jobs WHERE status IN ('queued','running')"
            ).fetchone()
        finally:
            connection.close()
        return int(row[0]) if row else 0

    def get(self, job_id: str) -> dict[str, Any]:
        """One job record, or an error when there is no such job."""
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT job_id, owner, instrument_id, role, status, snapshot_id,"
                " result, error, created_at, updated_at FROM research_jobs WHERE job_id=?",
                (str(job_id),)).fetchone()
        finally:
            connection.close()
        if row is None:
            raise JobNotFound('No such job')
        return self._row_to_record(row)

    def list_for(self, owner: str, *, limit: int = DEFAULT_LIST_LIMIT) -> list[dict[str, Any]]:
        """The caller's own jobs, newest first, bounded by `limit`."""
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT job_id, owner, instrument_id, role, status, snapshot_id,"
                " result, error, created_at, updated_at FROM research_jobs"
                " WHERE owner=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (str(owner), int(limit))).fetchall()
        finally:
            connection.close()
        return [self._row_to_record(row) for row in rows]

    # --- the snapshot -----------------------------------------------------

    def describe_snapshot(self, snapshot_id: UUID) -> dict[str, Any]:
        """What may be said about a snapshot without quoting its content.

        The snapshot may carry an account balance, so the raw context
        is never handed out. What is handed out is the identity of the
        snapshot, the moment it was taken, its data quality, the number
        of evidence ids it holds and a hash of its content. A hash says
        "this is the same snapshot" without saying what is in it.
        """
        identifier = _uuid_text(snapshot_id)
        payload = self.store.get_snapshot(UUID(identifier))
        evidence = self.store.evidence_ids(UUID(identifier))
        content = payload.get('context') or {}
        digest = hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, default=str).encode('utf-8')).hexdigest()
        return {
            'snapshot_id': identifier,
            'as_of': payload.get('as_of').isoformat() if payload.get('as_of') else None,
            'data_quality': list(payload.get('data_quality') or []),
            'evidence_count': len(evidence),
            'content_hash': digest,
        }

    def checks_for(self, snapshot_id: UUID) -> list[dict[str, Any]]:
        """The harness verdicts for one snapshot, in order."""
        try:
            records = self.store.checks(UUID(_uuid_text(snapshot_id)))
        except KeyError:
            return []
        return [record.model_dump(mode='json') for record in records]

    # --- the run ----------------------------------------------------------

    async def start(self, job_id: str) -> None:
        """Run one queued job in the background.

        The caller does not wait: the browser is told the job was
        queued and polls for it. The run is bounded by the semaphore
        and by the job deadline, and it is cancelled when the process
        shuts down.
        """
        task = asyncio.create_task(self._run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        """Cancel every running job and wait for them to stop."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run(self, job_id: str) -> None:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrency)
        try:
            async with self._semaphore:
                # The job is running only once it holds a slot. A job
                # waiting for one is still queued, and saying so is
                # honest: it has not started.
                self._update(job_id, status='running',
                             updated_at=self._clock().isoformat())
                await self._execute(job_id)
        except asyncio.CancelledError:
            self._update(job_id, status='failed', error='Cancelled',
                         updated_at=self._clock().isoformat())
            raise
        except BaseException as error:  # noqa: BLE001 - a failure is a fact
            self._update(job_id, status='failed', error=_sanitise_error(error),
                         updated_at=self._clock().isoformat())

    async def _execute(self, job_id: str) -> None:
        """Run one job from queued to a terminal state.

        The whole job is bounded, not just the model call. The capture
        reads the tape and the provider, so it is exactly the step
        that can hang, and a capture that never returns must not hold
        a concurrency slot for ever.
        """
        record = self.get(job_id)
        cutoff = self._clock()
        try:
            snapshot_id = await asyncio.wait_for(
                self._capture(UUID(record['instrument_id']), cutoff),
                self.deadline_seconds)
        except asyncio.TimeoutError:
            self._update(job_id, status='failed', error='DeadlineExceeded',
                         updated_at=self._clock().isoformat())
            return
        except asyncio.CancelledError:
            raise
        except BaseException as error:  # noqa: BLE001 - a failure is a fact
            self._update(job_id, status='failed', error=_sanitise_error(error),
                         updated_at=self._clock().isoformat())
            return
        self._update(job_id, snapshot_id=str(snapshot_id),
                     updated_at=self._clock().isoformat())
        try:
            result = await asyncio.wait_for(
                self.service.run(snapshot_id, role=record['role']),
                self.deadline_seconds)
        except asyncio.TimeoutError:
            self._update(job_id, status='failed', error='DeadlineExceeded',
                         updated_at=self._clock().isoformat())
            return
        except asyncio.CancelledError:
            # A cancellation is the process going away, not a failure of
            # the job. It is recorded by the caller, which knows why.
            raise
        except BaseException as error:  # noqa: BLE001 - a failure is a fact
            self._update(job_id, status='failed', error=_sanitise_error(error),
                         updated_at=self._clock().isoformat())
            return
        status = 'completed' if _is_success(result) else 'failed'
        self._update(job_id, status=status,
                     result=_text(_result_of(result)),
                     error=None if status == 'completed' else 'HarnessRejected',
                     updated_at=self._clock().isoformat())

    async def _capture(self, instrument_id: UUID, cutoff: datetime) -> UUID:
        """Freeze one snapshot at the server's own cutoff.

        The capture source is called with the instrument id and the
        cutoff. A source that takes only the instrument id is honoured
        too: the cutoff is then the source's own, which is still the
        server's choice and never the client's.
        """
        if inspect.iscoroutinefunction(self.capture):
            outcome = _call_capture(self.capture, instrument_id, cutoff)
        else:
            outcome = await asyncio.to_thread(_call_capture, self.capture, instrument_id, cutoff)
        if asyncio.iscoroutine(outcome) or isinstance(outcome, asyncio.Future):
            outcome = await outcome
        return UUID(str(outcome))


def _call_capture(capture: Callable, instrument_id: UUID, cutoff: datetime) -> Any:
    """Call a capture source, with the cutoff when it takes one.

    A source that takes only the instrument id is honoured too. The
    cutoff is then the source's own, which is still the server's
    choice and never the client's. The signature is inspected rather
    than the failure guessed at, so a TypeError raised inside the
    source is not mistaken for a wrong signature.
    """
    try:
        parameters = inspect.signature(capture).parameters
    except (TypeError, ValueError):
        return capture(instrument_id, as_of=cutoff)
    accepts_cutoff = (
        'as_of' in parameters
        or any(parameter.kind is inspect.Parameter.VAR_KEYWORD
               for parameter in parameters.values())
    )
    if accepts_cutoff:
        return capture(instrument_id, as_of=cutoff)
    return capture(instrument_id)


def _is_success(result: Any) -> bool:
    """Whether a harness run produced a report worth keeping."""
    if isinstance(result, Mapping):
        return result.get('status') == 'success'
    return False


def _result_of(result: Any) -> Any:
    """The part of a harness run that may be stored and shown."""
    if not isinstance(result, Mapping):
        return None
    if 'report' in result and isinstance(result.get('report'), Mapping):
        return dict(result['report'])
    reports = result.get('reports')
    if isinstance(reports, Mapping):
        return {'reports': {str(key): value for key, value in reports.items()},
                'status': result.get('status')}
    return None
