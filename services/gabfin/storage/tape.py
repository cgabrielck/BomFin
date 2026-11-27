"""Append-only Parquet tape with a manifest index.

Storage boundary
----------------
- The tape is **append-only derived data**. It can be deleted wholesale and
  rebuilt from the provider. The manifest is an index of the tape, never the
  authority for what the tape contains.
- Tape lives under `runtime/` and is not tracked in git.
- A backtest dataset must record the manifest's `sha256` to be reproducible.
- Rows outside the retention window are not an error. A read that finds them
  reports "outside the retention window" rather than silently truncating, so
  a caller cannot mistake a clipped read for complete history.

Money is stored as float64 and converted back to Decimal on read, so the
stored bytes stay cheap to read and the contract keeps decimal semantics.
The manifest records this precision policy; a caller that needs exact
decimal arithmetic must re-read the provider, not trust the tape's floats.

Retention is enforced before writing, not by a later cleanup scan: rows
older than the retention window are dropped as they are written, so a write
never has to rewrite history.
"""
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as pq

from gabfin.contracts.market import AssetClass, Timeframe, TimeUnit
from gabfin.contracts.tape import (
    TapeManifest,
    TapePartition,
    TapeReadResult,
    TapeSeries,
    TapeWriteResult,
)

RETENTION_WINDOWS = {'rolling_2y': timedelta(days=730)}

SCHEMA = pa.schema(
    [
        ('event_at', pa.timestamp('us', tz='UTC')),
        ('open', pa.float64()),
        ('high', pa.float64()),
        ('low', pa.float64()),
        ('close', pa.float64()),
        ('volume', pa.float64()),
    ]
)

PRECISION_POLICY = 'float64-storage-decimal-on-read'

# Directory names for timeframes. Short and stable, so a path stays readable.
TIMEFRAME_DIRECTORIES = {
    TimeUnit.SECOND: 'sec',
    TimeUnit.MINUTE: 'min',
    TimeUnit.HOUR: 'hour',
    TimeUnit.TRADING_DAY: 'day',
    TimeUnit.WEEK: 'week',
    TimeUnit.MONTH: 'month',
    TimeUnit.YEAR: 'year',
}


def _timeframe_key(timeframe: Timeframe) -> str:
    return f'{timeframe.count}{TIMEFRAME_DIRECTORIES[timeframe.unit]}'


def series_key(series: TapeSeries) -> str:
    """A stable, safe manifest key for one series."""
    return f'{series.asset_class.value}-{series.symbol}-{_timeframe_key(series.timeframe)}'


def series_directory(root: Path, series: TapeSeries) -> Path:
    """The directory holding one series' partitions and its manifest."""
    return root / series.asset_class.value / series.symbol / _timeframe_key(series.timeframe)


def _partition_path(root: Path, series: TapeSeries, stamp: datetime) -> Path:
    """Partition by asset class, symbol and timeframe; month is a file name."""
    return series_directory(root, series) / f'{stamp.strftime("%Y-%m")}.parquet'


def _retention_floor(series: TapeSeries, anchor: datetime) -> datetime | None:
    """The earliest instant the series may keep; None means keep everything.

    The window is anchored to an explicit instant the caller supplies: the
    write clock when writing, the manifest's `written_at` when reading. A
    read therefore never depends on a hidden wall clock, and a write of
    three-year-old bars is dropped rather than silently kept.
    """
    window = RETENTION_WINDOWS.get(series.retention)
    if window is None:
        return None
    return anchor - window


def _rows_to_table(rows: list[dict]) -> pa.Table:
    """Build a table with the fixed schema; missing volume stays null.

    Decimal values are converted to float64 for storage. The conversion is
    explicit rather than implicit so the precision loss is a stated policy
    recorded in the manifest, not a surprise.
    """

    def number(value):
        return None if value is None else float(value)

    columns = {
        'event_at': [row['event_at'] for row in rows],
        'open': [number(row['open']) for row in rows],
        'high': [number(row['high']) for row in rows],
        'low': [number(row['low']) for row in rows],
        'close': [number(row['close']) for row in rows],
        'volume': [number(row.get('volume')) for row in rows],
    }
    return pa.Table.from_pydict(columns, schema=SCHEMA)


def _table_to_rows(table: pa.Table) -> list[dict]:
    """Convert stored floats back to the contract's decimal values."""
    values = table.to_pydict()
    rows = []
    for index in range(table.num_rows):
        row = {'event_at': values['event_at'][index]}
        for field in ('open', 'high', 'low', 'close'):
            value = values[field][index]
            row[field] = None if value is None else Decimal(str(value))
        volume = values['volume'][index]
        row['volume'] = None if volume is None else Decimal(str(volume))
        rows.append(row)
    return rows


def _merge_existing(path: Path, rows: list[dict]) -> list[dict]:
    """Append rows to an existing partition, keeping the old rows intact.

    A rewrite of one partition file is the cost of appending; a rewrite of
    the whole series is not. Rows already present are not duplicated.
    """
    if not path.exists():
        return sorted(rows, key=lambda row: row['event_at'])
    existing = _table_to_rows(pq.read_table(path))
    seen = {row['event_at'] for row in existing}
    merged = existing + [row for row in rows if row['event_at'] not in seen]
    merged.sort(key=lambda row: row['event_at'])
    return merged


def _write_table(path: Path, table: pa.Table) -> str:
    """Replace a partition file atomically and return its digest.

    The digest is taken from the temporary file, before it replaces the
    live one. If anything fails after the write but before the replace, the
    live file still holds the previous bytes and the manifest still
    describes them.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    pq.write_table(table, temporary, compression='zstd')
    digest = sha256(temporary.read_bytes()).hexdigest()
    temporary.replace(path)
    return digest


def _partition_from(
    path: Path, root: Path, table: pa.Table, digest: str
) -> TapePartition:
    stamps = table.column('event_at').to_pylist()
    return TapePartition(
        path=path.relative_to(root).as_posix(),
        rows=table.num_rows,
        min_event_at=min(stamps) if stamps else None,
        max_event_at=max(stamps) if stamps else None,
        sha256=digest,
    )


def write_partitions(
    root: Path,
    series: TapeSeries,
    rows: list[dict],
    *,
    now: datetime,
) -> TapeWriteResult:
    """Write rows into partitioned Parquet files.

    Rows outside the retention window are dropped before they reach disk.
    The caller writes the returned manifest; the manifest is written last so
    an interrupted write leaves the previous manifest describing the
    previous state.
    """
    if now.tzinfo is None:
        raise ValueError('A tape write needs an aware clock')
    floor = _retention_floor(series, now)
    kept = [row for row in rows if floor is None or row['event_at'] >= floor]
    dropped = len(rows) - len(kept)
    if not kept:
        raise ValueError('No tape rows survived the retention window')

    by_month: dict[str, list[dict]] = {}
    for row in kept:
        by_month.setdefault(row['event_at'].strftime('%Y-%m'), []).append(row)

    partitions: list[TapePartition] = []
    for month in sorted(by_month):
        month_rows = by_month[month]
        path = _partition_path(root, series, month_rows[0]['event_at'])
        merged = _merge_existing(path, month_rows)
        table = _rows_to_table(merged)
        digest = _write_table(path, table)
        partitions.append(_partition_from(path, root, table, digest))

    stored = _series_from_partitions(series, partitions)
    return TapeWriteResult(
        series=stored,
        partitions=tuple(partitions),
        dropped_outside_retention=dropped,
    )


def _series_from_partitions(
    series: TapeSeries,
    partitions: list[TapePartition],
) -> TapeSeries:
    """The series as the stored files actually hold it."""
    rows = sum(partition.rows for partition in partitions)
    starts = [
        partition.min_event_at
        for partition in partitions
        if partition.min_event_at is not None
    ]
    ends = [
        partition.max_event_at
        for partition in partitions
        if partition.max_event_at is not None
    ]
    return series.model_copy(
        update={
            'coverage_start': min(starts) if starts else None,
            'coverage_end': max(ends) if ends else None,
            'row_count': rows,
            'complete': True,
        }
    )


def build_manifest(
    series: TapeSeries,
    partitions: list[TapePartition],
    *,
    written_at: datetime,
    complete: bool = True,
) -> TapeManifest:
    """Build a manifest that agrees with the stored files."""
    return TapeManifest(
        schema_version='1.0',
        series=_series_from_partitions(series, partitions) if complete else series,
        partitions=tuple(partitions),
        written_at=written_at,
        complete=complete,
        precision_policy=PRECISION_POLICY,
    )


def manifest_path(root: Path, series: TapeSeries) -> Path:
    """Where the manifest for one series lives, beside its partitions."""
    from gabfin.storage.manifest import manifest_path as _manifest_path

    return _manifest_path(series_directory(root, series))


def read_partitions(
    root: Path,
    series: TapeSeries,
    start: datetime | None = None,
    end: datetime | None = None,
    *,
    manifest: TapeManifest | None = None,
) -> TapeReadResult:
    """Read stored rows, optionally clipped to a time range.

    The manifest is the index of the tape. If none is passed, it is loaded
    from the series directory; a missing manifest is an error, because a
    reader with no index does not guess which files exist.
    """
    if manifest is None:
        from gabfin.storage.manifest import read_manifest

        manifest = read_manifest(manifest_path(root, series))
    if not manifest.complete:
        raise ValueError('An incomplete tape manifest must not be read as history')
    if manifest.series.symbol != series.symbol or (
        manifest.series.timeframe != series.timeframe
    ):
        raise ValueError('The manifest does not describe this series')

    # The window is anchored to the manifest's write time, and the retention
    # policy comes from the manifest, because the manifest is the durable
    # index of what was actually stored.
    floor = _retention_floor(manifest.series, manifest.written_at)
    rows: list[dict] = []
    outside = 0
    for partition in manifest.partitions:
        path = root / partition.path
        if not path.exists():
            raise FileNotFoundError(f'Tape partition is missing: {partition.path}')
        # The range clip is a Parquet-level filter, so a clipped read does not
        # materialize the whole partition.
        conditions = []
        if start is not None:
            conditions.append(('event_at', '>=', start))
        if end is not None:
            conditions.append(('event_at', '<=', end))
        table = pq.read_table(path, filters=conditions or None)
        stored = _table_to_rows(table)
        for row in stored:
            if floor is not None and row['event_at'] < floor:
                outside += 1
                continue
            rows.append(row)
    rows.sort(key=lambda row: row['event_at'])
    return TapeReadResult(
        series=manifest.series,
        rows=len(rows),
        min_event_at=rows[0]['event_at'] if rows else None,
        max_event_at=rows[-1]['event_at'] if rows else None,
        rows_outside_retention=outside,
    )


def read_rows(
    root: Path,
    series: TapeSeries,
    start: datetime | None = None,
    end: datetime | None = None,
    *,
    manifest: TapeManifest | None = None,
) -> list[dict]:
    """Read the stored rows themselves, not just their count.

    `read_partitions` answers "how much history is there"; this answers
    "what is in it". A caller that computes on history needs the rows,
    and must not have to re-implement the retention and ordering rules
    to get them.
    """
    if manifest is None:
        from gabfin.storage.manifest import read_manifest

        manifest = read_manifest(manifest_path(root, series))
    if not manifest.complete:
        raise ValueError('An incomplete tape manifest must not be read as history')
    if manifest.series.symbol != series.symbol or (
        manifest.series.timeframe != series.timeframe
    ):
        raise ValueError('The manifest does not describe this series')

    floor = _retention_floor(manifest.series, manifest.written_at)
    rows: list[dict] = []
    for partition in manifest.partitions:
        path = root / partition.path
        if not path.exists():
            raise FileNotFoundError(f'Tape partition is missing: {partition.path}')
        conditions = []
        if start is not None:
            conditions.append(('event_at', '>=', start))
        if end is not None:
            conditions.append(('event_at', '<=', end))
        table = pq.read_table(path, filters=conditions or None)
        for row in _table_to_rows(table):
            if floor is not None and row['event_at'] < floor:
                continue
            rows.append(row)
    rows.sort(key=lambda row: row['event_at'])
    return rows


def merge_manifest(old: TapeManifest, new: TapeManifest) -> TapeManifest:
    """Combine two manifests for the same series.

    Coverage is the union; overlapping rows are the new reading's answer.
    Old partitions are kept, never deleted: the tape is history and a
    delete is not recoverable from the manifest alone.
    """
    if old.series.symbol != new.series.symbol or (
        old.series.timeframe != new.series.timeframe
    ):
        raise ValueError('Cannot merge manifests for different series')
    paths = {partition.path: partition for partition in old.partitions}
    for partition in new.partitions:
        paths[partition.path] = partition
    partitions = [paths[path] for path in sorted(paths)]
    merged = TapeSeries(
        schema_version='1.0',
        series_id=new.series.series_id,
        asset_class=new.series.asset_class,
        symbol=new.series.symbol,
        timeframe=new.series.timeframe,
        source=new.series.source,
        venue_coverage=new.series.venue_coverage,
        adjustment=new.series.adjustment,
        retention=new.series.retention,
        coverage_start=_bound(partitions, 'min_event_at'),
        coverage_end=_bound(partitions, 'max_event_at', latest=True),
        row_count=sum(partition.rows for partition in partitions),
        complete=new.complete and old.complete,
    )
    return TapeManifest(
        schema_version='1.0',
        series=merged,
        partitions=tuple(partitions),
        written_at=max(old.written_at, new.written_at),
        complete=new.complete and old.complete,
        precision_policy=new.precision_policy,
    )


def _bound(partitions: list[TapePartition], field: str, latest: bool = False):
    values = [
        getattr(partition, field)
        for partition in partitions
        if getattr(partition, field) is not None
    ]
    if not values:
        return None
    return max(values) if latest else min(values)


def new_series(
    symbol: str,
    timeframe: dict,
    *,
    source: str,
    venue_coverage: str,
    adjustment: str,
    retention: str,
    asset_class: str = 'equity',
) -> TapeSeries:
    """Build a series declaration for a first write."""
    return TapeSeries(
        schema_version='1.0',
        series_id=uuid4(),
        asset_class=AssetClass(asset_class),
        symbol=symbol,
        timeframe=Timeframe.model_validate(timeframe),
        source=source,
        venue_coverage=venue_coverage,
        adjustment=adjustment,
        retention=retention,
        coverage_start=None,
        coverage_end=None,
        row_count=0,
        complete=False,
    )
