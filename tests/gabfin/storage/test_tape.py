"""Tape storage: round trip, atomicity, retention, append and manifest merges."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from gabfin.contracts.tape import TapeManifest
from gabfin.storage import manifest as manifest_store
from gabfin.storage import tape as tape_store

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def series(retention='full_history', symbol='AAPL'):
    return tape_store.new_series(
        symbol,
        {'count': 1, 'unit': 'trading_day'},
        source='alpaca:sip',
        venue_coverage='sip',
        adjustment='all',
        retention=retention,
    )


def rows(count=3, start=NOW - timedelta(days=10)):
    values = []
    for index in range(count):
        stamp = start + timedelta(days=index)
        values.append(
            {
                'event_at': stamp,
                'open': Decimal('100.00') + index,
                'high': Decimal('102.00') + index,
                'low': Decimal('99.00') + index,
                'close': Decimal('101.00') + index,
                'volume': Decimal('12345.5'),
            }
        )
    return values


def write(root: Path, declared, source, now=NOW):
    """Write rows and return the manifest that describes them."""
    result = tape_store.write_partitions(root, declared, source, now=now)
    return tape_store.build_manifest(
        declared, list(result.partitions), written_at=now
    )


def partition_path(root: Path, name: str) -> Path:
    return root / 'equity' / 'AAPL' / '1day' / name


def test_round_trip_preserves_values_and_types(tmp_path: Path):
    declared = series()
    source = rows(3)
    manifest = write(tmp_path, declared, source)
    stored = tape_store.read_partitions(tmp_path, declared, manifest=manifest)
    assert stored.rows == 3
    assert stored.min_event_at == source[0]['event_at']
    assert stored.max_event_at == source[-1]['event_at']
    assert stored.rows_outside_retention == 0


def test_written_file_holds_the_declared_schema(tmp_path: Path):
    declared = series()
    write(tmp_path, declared, rows(2))
    path = partition_path(tmp_path, f'{NOW.strftime("%Y-%m")}.parquet')
    assert path.exists()
    table = pq.read_table(path)
    assert table.schema.equals(tape_store.SCHEMA)
    assert table.num_rows == 2


def test_decimal_values_survive_the_float_storage(tmp_path: Path):
    declared = series()
    write(tmp_path, declared, rows(1))
    path = partition_path(tmp_path, f'{NOW.strftime("%Y-%m")}.parquet')
    values = pq.read_table(path).to_pydict()
    assert values['open'][0] == pytest.approx(100.0)


def test_manifest_records_the_precision_policy(tmp_path: Path):
    declared = series()
    manifest = write(tmp_path, declared, rows(2))
    assert manifest.precision_policy == 'float64-storage-decimal-on-read'


def test_manifest_index_is_written_and_describes_the_files(tmp_path: Path):
    declared = series()
    manifest = write(tmp_path, declared, rows(3))
    manifest_store.write_manifest(tape_store.manifest_path(tmp_path, declared), manifest)
    stored = manifest_store.read_manifest(tape_store.manifest_path(tmp_path, declared))
    assert stored == manifest
    assert stored.complete is True
    assert stored.series.row_count == 3
    assert len(stored.partitions) == 1
    assert (tmp_path / stored.partitions[0].path).exists()


def test_a_read_without_a_manifest_is_an_error_not_a_guess(tmp_path: Path):
    declared = series()
    write(tmp_path, declared, rows(2))
    with pytest.raises(FileNotFoundError):
        tape_store.read_partitions(tmp_path, declared)


def test_a_read_finds_the_manifest_beside_the_partitions(tmp_path: Path):
    declared = series()
    manifest = write(tmp_path, declared, rows(2))
    manifest_store.write_manifest(tape_store.manifest_path(tmp_path, declared), manifest)
    stored = tape_store.read_partitions(tmp_path, declared)
    assert stored.rows == 2


def test_interrupted_write_leaves_no_half_file(tmp_path: Path, monkeypatch):
    declared = series()
    write(tmp_path, declared, rows(2))
    path = partition_path(tmp_path, f'{NOW.strftime("%Y-%m")}.parquet')
    original = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(tape_store, '_write_table', fail)
    with pytest.raises(OSError):
        tape_store.write_partitions(
            tmp_path, declared, rows(3, NOW - timedelta(days=20)), now=NOW
        )
    assert path.read_bytes() == original
    assert not list(path.parent.glob('*.tmp'))


def test_a_failed_digest_leaves_the_live_file_unchanged(tmp_path: Path, monkeypatch):
    declared = series()
    write(tmp_path, declared, rows(2))
    path = partition_path(tmp_path, f'{NOW.strftime("%Y-%m")}.parquet')
    original = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError('read failure')

    monkeypatch.setattr(tape_store, 'sha256', fail)
    with pytest.raises(OSError):
        tape_store.write_partitions(
            tmp_path, declared, rows(3, NOW - timedelta(days=20)), now=NOW
        )
    assert path.read_bytes() == original


def test_manifest_write_is_atomic(tmp_path: Path):
    declared = series()
    path = tape_store.manifest_path(tmp_path, declared)
    manifest = TapeManifest(
        schema_version='1.0',
        series=declared,
        partitions=(),
        written_at=NOW,
        complete=False,
    )
    manifest_store.write_manifest(path, manifest)
    assert manifest_store.read_manifest(path) == manifest
    assert not list(path.parent.glob('*.tmp'))


def test_missing_manifest_is_reported_not_guessed(tmp_path: Path):
    declared = series()
    path = tape_store.manifest_path(tmp_path, declared)
    with pytest.raises(FileNotFoundError):
        manifest_store.read_manifest(path)


def test_manifest_sits_beside_the_partitions_it_describes(tmp_path: Path):
    declared = series()
    write(tmp_path, declared, rows(2))
    path = tape_store.manifest_path(tmp_path, declared)
    assert path.parent == partition_path(tmp_path, 'anything.parquet').parent
    assert path.name == 'manifest.json'


def test_rolling_retention_drops_rows_before_the_window(tmp_path: Path):
    declared = series(retention='rolling_2y')
    old = rows(1, NOW - timedelta(days=800))
    recent = rows(1, NOW - timedelta(days=10))
    result = tape_store.write_partitions(tmp_path, declared, old + recent, now=NOW)
    assert result.dropped_outside_retention == 1
    manifest = tape_store.build_manifest(
        declared, list(result.partitions), written_at=NOW
    )
    stored = tape_store.read_partitions(tmp_path, declared, manifest=manifest)
    assert stored.rows == 1


def test_full_history_retention_keeps_everything(tmp_path: Path):
    declared = series(retention='full_history')
    old = rows(1, NOW - timedelta(days=3000))
    result = tape_store.write_partitions(tmp_path, declared, old, now=NOW)
    assert result.dropped_outside_retention == 0
    manifest = tape_store.build_manifest(
        declared, list(result.partitions), written_at=NOW
    )
    stored = tape_store.read_partitions(tmp_path, declared, manifest=manifest)
    assert stored.rows == 1


def test_a_write_with_nothing_inside_the_window_is_an_error(tmp_path: Path):
    declared = series(retention='rolling_2y')
    old = rows(1, NOW - timedelta(days=800))
    with pytest.raises(ValueError):
        tape_store.write_partitions(tmp_path, declared, old, now=NOW)


def test_a_backfill_older_than_the_window_is_dropped(tmp_path: Path):
    """The rolling window is anchored to the write clock, not to the data."""
    declared = series(retention='rolling_2y')
    source = rows(3, NOW - timedelta(days=800))
    with pytest.raises(ValueError):
        tape_store.write_partitions(tmp_path, declared, source, now=NOW)


def test_a_backfill_partly_outside_the_window_keeps_the_rest(tmp_path: Path):
    declared = series(retention='rolling_2y')
    old = rows(1, NOW - timedelta(days=800))
    recent = rows(2, NOW - timedelta(days=10))
    result = tape_store.write_partitions(tmp_path, declared, old + recent, now=NOW)
    assert result.dropped_outside_retention == 1
    manifest = tape_store.build_manifest(
        declared, list(result.partitions), written_at=NOW
    )
    stored = tape_store.read_partitions(tmp_path, declared, manifest=manifest)
    assert stored.rows == 2


def test_rows_outside_the_window_are_reported_not_silently_dropped(tmp_path: Path):
    """A full_history tape read under a rolling window reports, not hides."""
    source = rows(3, NOW - timedelta(days=800))
    kept = series(retention='full_history')
    full = tape_store.write_partitions(tmp_path, kept, source, now=NOW)
    full_manifest = tape_store.build_manifest(
        kept, list(full.partitions), written_at=NOW
    )
    rolling = full_manifest.model_copy(
        update={
            'series': full_manifest.series.model_copy(
                update={'retention': 'rolling_2y'}
            )
        }
    )
    stored = tape_store.read_partitions(tmp_path, kept, manifest=rolling)
    assert stored.rows == 0
    assert stored.rows_outside_retention == 3


def test_range_read_returns_only_rows_inside_the_range(tmp_path: Path):
    declared = series()
    source = rows(10)
    manifest = write(tmp_path, declared, source)
    stored = tape_store.read_partitions(
        tmp_path,
        declared,
        source[3]['event_at'],
        source[6]['event_at'],
        manifest=manifest,
    )
    assert stored.rows == 4
    assert stored.min_event_at == source[3]['event_at']
    assert stored.max_event_at == source[6]['event_at']


def test_append_keeps_old_rows_and_adds_new_ones(tmp_path: Path):
    declared = series()
    first = rows(3, NOW - timedelta(days=10))
    write(tmp_path, declared, first)
    second = rows(2, NOW - timedelta(days=1))
    result = tape_store.write_partitions(tmp_path, declared, second, now=NOW)
    manifest = tape_store.build_manifest(
        declared, list(result.partitions), written_at=NOW
    )
    stored = tape_store.read_partitions(tmp_path, declared, manifest=manifest)
    assert stored.rows == 5
    assert stored.min_event_at == first[0]['event_at']
    assert stored.max_event_at == second[-1]['event_at']


def test_appending_the_same_rows_twice_does_not_duplicate(tmp_path: Path):
    declared = series()
    source = rows(3, NOW - timedelta(days=10))
    manifest = write(tmp_path, declared, source)
    write(tmp_path, declared, source)
    stored = tape_store.read_partitions(tmp_path, declared, manifest=manifest)
    assert stored.rows == 3


def test_monthly_partitions_are_separate_files(tmp_path: Path):
    declared = series()
    october = rows(1, datetime(2026, 10, 5, tzinfo=timezone.utc))
    november = rows(1, datetime(2026, 11, 5, tzinfo=timezone.utc))
    write(tmp_path, declared, october + november)
    files = sorted(
        path.name
        for path in (tmp_path / 'equity' / 'AAPL' / '1day').glob('*.parquet')
    )
    assert files == ['2026-10.parquet', '2026-11.parquet']


def test_equity_and_option_tapes_do_not_share_a_path(tmp_path: Path):
    equity = series()
    option = tape_store.new_series(
        'AAPL',
        {'count': 1, 'unit': 'trading_day'},
        source='alpaca:sip',
        venue_coverage='sip',
        adjustment='all',
        retention='full_history',
        asset_class='option',
    )
    assert tape_store.series_key(equity) != tape_store.series_key(option)
    assert tape_store.series_directory(tmp_path, equity) != tape_store.series_directory(
        tmp_path, option
    )


def test_merging_manifests_keeps_old_partitions(tmp_path: Path):
    declared = series()
    first = write(tmp_path, declared, rows(2, NOW - timedelta(days=40)))
    second = write(tmp_path, declared, rows(2, NOW - timedelta(days=5)))
    merged = tape_store.merge_manifest(first, second)
    assert len(merged.partitions) == 2
    assert merged.series.coverage_start == first.series.coverage_start
    assert merged.series.coverage_end == second.series.coverage_end
    for partition in merged.partitions:
        assert (tmp_path / partition.path).exists()


def test_merging_different_series_is_rejected(tmp_path: Path):
    left = TapeManifest(
        schema_version='1.0',
        series=series(symbol='AAPL'),
        partitions=(),
        written_at=NOW,
        complete=False,
    )
    right = TapeManifest(
        schema_version='1.0',
        series=series(symbol='MSFT'),
        partitions=(),
        written_at=NOW,
        complete=False,
    )
    with pytest.raises(ValueError):
        tape_store.merge_manifest(left, right)


def test_an_incomplete_manifest_is_not_read_as_history(tmp_path: Path):
    declared = series()
    manifest = write(tmp_path, declared, rows(2))
    incomplete = manifest.model_copy(update={'complete': False})
    with pytest.raises(ValueError):
        tape_store.read_partitions(tmp_path, declared, manifest=incomplete)


def test_a_missing_partition_is_an_error_not_a_short_read(tmp_path: Path):
    declared = series()
    manifest = write(tmp_path, declared, rows(2))
    (tmp_path / manifest.partitions[0].path).unlink()
    with pytest.raises(FileNotFoundError):
        tape_store.read_partitions(tmp_path, declared, manifest=manifest)


def test_a_manifest_for_another_series_is_rejected(tmp_path: Path):
    declared = series()
    manifest = write(tmp_path, declared, rows(2))
    other = series(symbol='MSFT')
    with pytest.raises(ValueError):
        tape_store.read_partitions(tmp_path, other, manifest=manifest)
