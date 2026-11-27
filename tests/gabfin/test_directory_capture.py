from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest


def test_capture_new_symbol_fetches_local_tape_then_freezes(tmp_path):
    from gabfin.universe.directory import InstrumentDirectory
    from gabfin.research.directory_capture import DirectoryCapture
    from gabfin.research.store import ResearchStore
    from gabfin.storage.tape import new_series, write_partitions, build_manifest, manifest_path
    from gabfin.storage.manifest import write_manifest
    directory = InstrumentDirectory(tmp_path / 'symbols.sqlite')
    identity = uuid4()
    directory.seed('MSFT', identity)
    calls = []
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    class History:
        def store(self, root, symbol, *, timeframe, start, end, now):
            calls.append(symbol)
            series = new_series(symbol, timeframe.model_dump(mode='json'), source='massive', venue_coverage='unknown', adjustment='adjusted', retention='rolling_2y')
            written = write_partitions(root, series, [dict(event_at=now.replace(day=1, hour=0), open=100, high=102, low=99, close=101, volume=1000)], now=now)
            write_manifest(manifest_path(root, written.series), build_manifest(written.series, written.partitions, written_at=now))
    store = ResearchStore(tmp_path / 'research.sqlite')
    capture = DirectoryCapture(directory, store, tmp_path / 'tape', history=History())
    sid = capture(identity, as_of=now)
    snapshot = store.get_snapshot(sid)
    assert snapshot['context']['symbols'] == ['MSFT']
    assert snapshot['context']['source_coverage'] == 'unknown'
    assert calls == ['MSFT']
    capture(identity, as_of=now)
    assert calls == ['MSFT']
    with pytest.raises(KeyError):
        capture(uuid4(), as_of=now)


def test_new_directory_id_is_accepted_without_rebuilding_queue(tmp_path):
    from gabfin.universe.directory import InstrumentDirectory
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore
    directory = InstrumentDirectory(tmp_path / 'symbols.sqlite')
    directory.seed('AAPL', uuid4())
    jobs = ResearchJobs(store=ResearchStore(tmp_path / 'r.sqlite'), service=object(), capture=lambda iid: uuid4(),
                        instrument_ids=(), instrument_directory=directory)
    identity = uuid4()
    directory.seed('MSFT', identity)
    assert str(identity) in jobs.instrument_ids
    assert jobs.configured


def test_sync_capture_is_offloaded_so_http_loop_stays_responsive(tmp_path):
    import asyncio
    import threading
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.store import ResearchStore
    thread = threading.get_ident()
    observed = []
    sid = uuid4()
    def capture(identity, *, as_of):
        observed.append(threading.get_ident())
        return sid
    jobs = ResearchJobs(store=ResearchStore(tmp_path / 'r.sqlite'), capture=capture)
    assert asyncio.run(jobs._capture(uuid4(), datetime.now(timezone.utc))) == sid
    assert observed[0] != thread
