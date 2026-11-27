"""Reproduction: a hanging capture holds a queue slot forever.

The job deadline (`deadline_seconds`) wraps only `service.run`. The
capture is awaited with no timeout, so a capture that never returns
keeps the job in `running` forever, holds a concurrency slot forever,
and keeps the queue's paid-run count occupied forever.

This matters because the capture is the step that reads the tape and
the provider. It is exactly the step that can hang.
"""
import asyncio
from pathlib import Path
from uuid import UUID, uuid4

INSTRUMENT = '11111111-1111-4111-8111-111111111111'


def test_a_capture_that_never_returns_is_stopped_by_the_deadline(tmp_path):
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    async def hanging_capture(instrument_id, *, as_of):
        await asyncio.sleep(3600)

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=object(),
                        capture=hanging_capture,
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'),
                        schema_dir=Path('schemas/research'),
                        deadline_seconds=0.05)

    job_id = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)

    async def scenario():
        await asyncio.wait_for(jobs._execute(job_id), 5)
        return jobs.get(job_id)

    record = asyncio.run(scenario())
    print('record status:', record['status'], 'error:', record['error'])
    assert record['status'] == 'failed', (
        'the capture was not bounded by the job deadline; the job stayed '
        f"in {record['status']}")
    assert record['error'] == 'DeadlineExceeded'


def test_a_hanging_capture_holds_a_concurrency_slot(tmp_path):
    """A capture that hangs also holds one of the running slots."""
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore

    async def hanging_capture(instrument_id, *, as_of):
        await asyncio.sleep(3600)

    research_store = ResearchStore(Path(tmp_path) / 'research.sqlite')
    jobs = ResearchJobs(store=research_store, service=object(),
                        capture=hanging_capture,
                        instrument_ids=(UUID(INSTRUMENT),),
                        roles_dir=Path('config/agents'),
                        schema_dir=Path('schemas/research'),
                        deadline_seconds=0.05, max_concurrency=1)

    async def scenario():
        first = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
        second = jobs.enqueue(owner=str(uuid4()), instrument_id=UUID(INSTRUMENT), role=None)
        await jobs.start(first)
        await asyncio.sleep(0.5)
        # The second job cannot even start: the single slot is held.
        print('second status while first hangs:', jobs.get(second)['status'])
        await jobs.shutdown()
        return first, second

    first, second = asyncio.run(scenario())
    assert jobs.get(first)['status'] == 'failed'
