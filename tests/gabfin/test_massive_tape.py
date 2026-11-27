"""Massive history reaches stored analysis without inventing coverage."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import pytest

from gabfin.analysis.sources import TapeBarSource
from gabfin.analysis.plane import IndicatorPlane, AnalysisUnavailable
from gabfin.contracts.market import Timeframe
from gabfin.providers.massive.config import MassiveConfig
from gabfin.providers.massive.history import MassiveHistory
from gabfin.providers.massive.rest import MassiveRestClient, Response
from gabfin.storage.tape import new_series, write_partitions, build_manifest, manifest_path
from gabfin.storage.manifest import write_manifest

NOW = datetime(2026, 11, 27, tzinfo=timezone.utc)
TF = Timeframe(count=1, unit='trading_day')


def test_recorded_massive_history_roundtrip_keeps_unknown_coverage(tmp_path):
    fixture = json.loads((Path(__file__).parents[1] / 'fixtures/massive/recorded_rest_2026_11_27.json').read_text())
    client = MassiveRestClient(MassiveConfig(base_url='https://proxy.example.test', api_key='fixture'),
        transport=lambda request: Response(200, fixture['history']))
    history = MassiveHistory(client)
    manifest = history.store(tmp_path, 'AAPL', timeframe=TF,
        start=date(2026, 11, 23), end=date(2026, 11, 25), now=NOW)
    assert manifest.series.source == 'massive'
    assert manifest.series.adjustment == 'adjusted'
    assert manifest.series.venue_coverage == 'unknown'
    assert manifest.series.row_count == 3
    source = TapeBarSource(tmp_path, symbol='AAPL', source='massive')
    bars = source.bars(uuid4(), TF)
    assert len(bars) == 3
    assert str(bars[-1].close) == '355.58'
    assert source.coverage_of(TF) == 'unknown'
    with pytest.raises(AnalysisUnavailable, match='unknown'):
        IndicatorPlane(source, coverage_resolver=lambda i, t: source.coverage_of(t)).series(uuid4(), TF)
    again = history.store(tmp_path, 'AAPL', timeframe=TF,
        start=date(2026, 11, 23), end=date(2026, 11, 25), now=NOW)
    assert again.series.row_count == 3


@pytest.mark.parametrize('changes', [
    {'source': 'other'}, {'event_at': datetime(2027, 1, 1, tzinfo=timezone.utc)},
])
def test_ingestion_rejects_wrong_source_or_out_of_range_before_writing(tmp_path, changes):
    row = dict(event_at=NOW, source='massive', open=1, high=2, low=1, close=2, volume=10)
    row.update(changes)
    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            return (row,)
    with pytest.raises(ValueError):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=date(2026, 11, 27),
                            end=date(2026, 11, 27), now=NOW)
    assert not list(tmp_path.rglob('*.parquet'))


def test_ingestion_rejects_duplicate_timestamps_before_writing(tmp_path):
    row = dict(event_at=NOW, source='massive', open=1, high=2, low=1, close=2, volume=10)
    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            return (row, row)
    with pytest.raises(ValueError, match='Duplicate'):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=date(2026, 11, 27),
                            end=date(2026, 11, 27), now=NOW)
    assert not list(tmp_path.rglob('*.parquet'))


def test_reader_rejects_partition_bytes_changed_after_manifest(tmp_path):
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive', venue_coverage='sip',
                        adjustment='adjusted', retention='rolling_2y')
    written = write_partitions(tmp_path, series,
        [dict(event_at=NOW, open=1, high=2, low=1, close=2, volume=10)], now=NOW)
    write_manifest(manifest_path(tmp_path, series), build_manifest(written.series, list(written.partitions), written_at=NOW))
    import pyarrow as pa
    import pyarrow.parquet as pq
    partition = tmp_path / written.partitions[0].path
    table = pq.read_table(partition).set_column(4, 'close', pa.array([1.5]))
    pq.write_table(table, partition)
    with pytest.raises(ValueError, match='checksum'):
        TapeBarSource(tmp_path, symbol='AAPL', source='massive').bars(uuid4(), TF)


def test_store_refuses_corrupt_existing_partition_before_import(tmp_path):
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive', venue_coverage='unknown',
                        adjustment='adjusted', retention='rolling_2y')
    written = write_partitions(tmp_path, series,
        [dict(event_at=NOW, open=1, high=2, low=1, close=2, volume=10)], now=NOW)
    write_manifest(manifest_path(tmp_path, series), build_manifest(written.series, list(written.partitions), written_at=NOW))
    partition = tmp_path / written.partitions[0].path
    partition.write_bytes(b'corrupt')
    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            raise AssertionError('must verify stored bytes before fetching')
    with pytest.raises(ValueError, match='checksum'):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=date(2026, 11, 27),
                            end=date(2026, 11, 27), now=NOW)


def test_store_rejects_revised_history_before_changing_any_files(tmp_path):
    from decimal import Decimal
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive',
                        venue_coverage='unknown', adjustment='adjusted', retention='rolling_2y')
    row = dict(event_at=NOW, source='massive', open=Decimal('1.1'), high=2,
               low=1, close=Decimal('1.9'), volume=10)
    written = write_partitions(tmp_path, series, [row], now=NOW)
    path = write_manifest(manifest_path(tmp_path, series),
        build_manifest(written.series, list(written.partitions), written_at=NOW))
    before = {item: item.read_bytes() for item in tmp_path.rglob('*') if item.is_file()}
    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            return ({**row, 'close': Decimal('1.8')},)
    with pytest.raises(ValueError, match='conflict'):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(), now=NOW)
    assert {item: item.read_bytes() for item in before} == before


def test_interrupted_manifest_commit_is_detected_by_reader(tmp_path, monkeypatch):
    from gabfin.storage import manifest as manifests
    row = dict(event_at=NOW, source='massive', open=1, high=2, low=1, close=2, volume=10)
    class History(MassiveHistory):
        rows = (row,)
        def bars(self, *args, **kwargs):
            return self.rows
    history = History(None)
    history.store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(), now=NOW)
    from datetime import timedelta
    history.rows = (row, {**row, 'event_at': NOW + timedelta(hours=1)})
    def fail(*args, **kwargs):
        raise OSError('interrupted manifest commit')
    monkeypatch.setattr(manifests, 'write_manifest', fail)
    with pytest.raises(OSError, match='interrupted'):
        history.store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(),
                      now=NOW + timedelta(hours=2))
    with pytest.raises(ValueError, match='checksum'):
        TapeBarSource(tmp_path, symbol='AAPL', source='massive').bars(uuid4(), TF)
    with pytest.raises(ValueError, match='checksum'):
        history.store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(),
                      now=NOW + timedelta(hours=2))


def test_interrupted_cross_month_import_is_refused_by_reader_and_reimport(tmp_path, monkeypatch):
    """A month written but never committed leaves the index and the tape apart.

    The new month lands in its own partition file. The manifest still names
    only the old one, so the reader would silently drop a month of history
    and a later import would bless the uncommitted values. Both refuse.
    """
    from gabfin.storage import manifest as manifests
    from datetime import timedelta
    row = dict(event_at=NOW, source='massive', open=1, high=2, low=1, close=2, volume=10)
    class History(MassiveHistory):
        rows = (row,)
        def bars(self, *args, **kwargs):
            return self.rows
    history = History(None)
    history.store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(), now=NOW)
    # A bar in a later month, so the write lands in a different partition file.
    later = NOW + timedelta(days=40)
    history.rows = (row, {**row, 'event_at': later})
    def fail(*args, **kwargs):
        raise OSError('interrupted manifest commit')
    monkeypatch.setattr(manifests, 'write_manifest', fail)
    with pytest.raises(OSError, match='interrupted'):
        history.store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=later.date(),
                      now=later)
    # The manifest still names only the first month; the second exists on disk.
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive',
                        venue_coverage='unknown', adjustment='adjusted', retention='rolling_2y')
    from gabfin.storage.manifest import read_manifest
    manifest = read_manifest(manifest_path(tmp_path, series))
    assert len(manifest.partitions) == 1
    assert len(list(tmp_path.rglob('*.parquet'))) == 2
    before = {item: item.read_bytes() for item in tmp_path.rglob('*') if item.is_file()}

    with pytest.raises(ValueError, match='partition'):
        TapeBarSource(tmp_path, symbol='AAPL', source='massive').bars(uuid4(), TF)
    with pytest.raises(ValueError, match='partition'):
        history.store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=later.date(),
                      now=later)
    assert {item: item.read_bytes() for item in before} == before


def test_history_cli_exposes_explicit_import_arguments():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-m', 'gabfin.providers.massive.history', '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert '--tape' in result.stdout
    assert '--start' in result.stdout
    assert '--end' in result.stdout


def test_store_refuses_unsafe_symbol_before_path_access(tmp_path):
    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            raise AssertionError('must validate before transport')
    with pytest.raises(ValueError):
        History(None).store(tmp_path, '../escape', timeframe=TF, start=date(2026, 11, 27),
                            end=date(2026, 11, 27), now=NOW)


def test_store_refuses_existing_foreign_series_without_changing_bytes(tmp_path):
    series = new_series('AAPL', TF.model_dump(mode='json'), source='other', venue_coverage='sip',
                        adjustment='adjusted', retention='rolling_2y')
    written = write_partitions(tmp_path, series,
        [dict(event_at=NOW, open=1, high=2, low=1, close=2, volume=10)], now=NOW)
    path = write_manifest(manifest_path(tmp_path, series), build_manifest(written.series, list(written.partitions), written_at=NOW))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='provenance'):
        MassiveHistory(None).store(tmp_path, 'AAPL', timeframe=TF, start=date(2026, 11, 27),
                                  end=date(2026, 11, 27), now=NOW)
    assert path.read_bytes() == before


def test_stored_indicator_incremental_matches_full_for_every_split(tmp_path):
    from datetime import timedelta
    from decimal import Decimal
    from gabfin.indicators.engine import IndicatorEngine
    # Explicit synthetic SIP fixture verifies arithmetic only, never Massive entitlement.
    series = new_series('AAPL', TF.model_dump(mode='json'), source='fixture', venue_coverage='sip',
                        adjustment='adjusted', retention='rolling_2y')
    rows = []
    for index in range(65):
        price = Decimal(100) + Decimal(index % 7) / 10 + Decimal(index) / 20
        rows.append(dict(event_at=NOW - timedelta(days=70-index), open=price,
                         high=price+2, low=price-1, close=price+1, volume=1000+index))
    written = write_partitions(tmp_path, series, rows, now=NOW)
    write_manifest(manifest_path(tmp_path, series), build_manifest(written.series, list(written.partitions), written_at=NOW))
    bars = list(TapeBarSource(tmp_path, symbol='AAPL', source='fixture').bars(uuid4(), TF))
    engine = IndicatorEngine(uuid4(), TF, 'sip')
    def values(points):
        return {point.indicator: point.value for point in points}
    expected = values(engine.update(engine.seed(bars[:-1]), bars[-1]))
    for split in (0, 1, 14, 20, 26, 33, 64):
        state = engine.seed(bars[:split])
        for bar in bars[split:]:
            actual = engine.update(state, bar)
        assert values(actual) == expected
    assert expected['rsi'] is not None
    assert expected['atr'] is not None
    assert expected['macd'] is not None


def test_massive_reader_refuses_other_provider_tape(tmp_path):
    series = new_series('AAPL', TF.model_dump(mode='json'), source='other', venue_coverage='sip',
                        adjustment='adjusted', retention='rolling_2y')
    rows = [dict(event_at=NOW, open=1, high=2, low=1, close=2, volume=10)]
    written = write_partitions(tmp_path, series, rows, now=NOW)
    write_manifest(manifest_path(tmp_path, series), build_manifest(written.series, list(written.partitions), written_at=NOW))
    source = TapeBarSource(tmp_path, symbol='AAPL', source='massive')
    assert source.coverage_of(TF) == 'unknown'
    with pytest.raises(ValueError, match='source'):
        source.bars(uuid4(), TF)


def test_store_rejects_a_revised_bar_outside_the_retention_window(tmp_path):
    """A changed bar must be a conflict even when the retention window hides it.

    The conflict check reads the stored rows through the manifest's rolling
    window. A bar older than that window is invisible to the check, so a
    revised price for it would be written silently. The check must compare
    against every stored bar.
    """
    from decimal import Decimal
    from datetime import timedelta
    stored_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    row = dict(event_at=stored_at, source='massive', open=Decimal('1.1'), high=2,
               low=1, close=Decimal('1.9'), volume=10)
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive',
                        venue_coverage='unknown', adjustment='adjusted', retention='rolling_2y')
    written = write_partitions(tmp_path, series, [row], now=NOW)
    path = write_manifest(manifest_path(tmp_path, series),
        build_manifest(written.series, list(written.partitions), written_at=NOW))
    # Re-date the manifest so the stored bar falls outside its rolling window.
    from gabfin.storage.manifest import read_manifest
    manifest = read_manifest(path)
    write_manifest(path, manifest.model_copy(update={'written_at': NOW + timedelta(days=2000)}))
    before = {item: item.read_bytes() for item in tmp_path.rglob('*') if item.is_file()}

    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            return ({**row, 'close': Decimal('9.9')},)

    with pytest.raises(ValueError, match='conflict'):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=stored_at.date(),
                            end=stored_at.date(), now=NOW)
    assert {item: item.read_bytes() for item in before} == before


def test_store_refuses_a_partition_on_disk_that_the_manifest_does_not_list(tmp_path):
    """An unlisted partition means the index and the tape disagree.

    A month written but never committed to the manifest is history the
    index does not describe. Re-importing on top of it would bless values
    nobody vouched for, so the write refuses instead.
    """
    from datetime import timedelta
    row = dict(event_at=NOW, source='massive', open=1, high=2, low=1, close=2, volume=10)
    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            return (row,)
    History(None).store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(), now=NOW)
    # Write a later month straight to disk, without committing the manifest.
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive',
                        venue_coverage='unknown', adjustment='adjusted', retention='rolling_2y')
    write_partitions(tmp_path, series,
        [dict(event_at=NOW + timedelta(days=40), source='massive', open=1, high=2, low=1,
              close=2, volume=10)], now=NOW + timedelta(days=40))
    before = {item: item.read_bytes() for item in tmp_path.rglob('*') if item.is_file()}

    with pytest.raises(ValueError, match='partition'):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(),
                            now=NOW)
    assert {item: item.read_bytes() for item in before} == before


def test_store_refuses_a_deleted_manifest_while_partitions_remain(tmp_path):
    """A missing manifest with partitions on disk is not a writable tape.

    The manifest is the index of the tape. Without it, a write would
    rebuild an index that silently drops what is already stored.
    """
    row = dict(event_at=NOW, source='massive', open=1, high=2, low=1, close=2, volume=10)
    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            return (row,)
    History(None).store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(), now=NOW)
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive',
                        venue_coverage='unknown', adjustment='adjusted', retention='rolling_2y')
    manifest_path(tmp_path, series).unlink()
    before = {item: item.read_bytes() for item in tmp_path.rglob('*') if item.is_file()}

    with pytest.raises(ValueError, match='partition'):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(),
                            now=NOW)
    assert {item: item.read_bytes() for item in before} == before


def test_store_refuses_a_manifest_claiming_a_venue_massive_does_not_have(tmp_path):
    """Massive history has no named venue, so a manifest may not claim one.

    A manifest written with `sip` would let a series that was never tied to
    a venue be read as if it were. The write refuses such a series.
    """
    series = new_series('AAPL', TF.model_dump(mode='json'), source='massive', venue_coverage='sip',
                        adjustment='adjusted', retention='rolling_2y')
    written = write_partitions(tmp_path, series,
        [dict(event_at=NOW, open=1, high=2, low=1, close=2, volume=10)], now=NOW)
    path = write_manifest(manifest_path(tmp_path, series),
        build_manifest(written.series, list(written.partitions), written_at=NOW))
    before = path.read_bytes()

    class History(MassiveHistory):
        def bars(self, *args, **kwargs):
            return (dict(event_at=NOW, source='massive', open=1, high=2, low=1, close=2, volume=10),)

    with pytest.raises(ValueError, match='venue'):
        History(None).store(tmp_path, 'AAPL', timeframe=TF, start=NOW.date(), end=NOW.date(), now=NOW)
    assert path.read_bytes() == before
