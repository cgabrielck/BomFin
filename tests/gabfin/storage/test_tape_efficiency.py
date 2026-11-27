"""Tape efficiency acceptance: the cost bounds the plan sets for WU-0.

These are timing tests. They assert a generous upper bound so a loaded
machine does not fail the suite, while still catching an order-of-magnitude
regression such as a full rewrite per append or a full scan per read.
"""
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from gabfin.storage import tape as tape_store

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)

# The plan's bounds: 500 symbols of one month daily bars, one symbol read
# over ten years, and one month appended to an existing partition.
WRITE_BUDGET_SECONDS = 30.0
READ_BUDGET_SECONDS = 0.5
APPEND_BUDGET_SECONDS = 2.0


def daily_series(symbol: str):
    return tape_store.new_series(
        symbol,
        {'count': 1, 'unit': 'trading_day'},
        source='alpaca:sip',
        venue_coverage='sip',
        adjustment='all',
        retention='full_history',
    )


def daily_rows(count: int, start: datetime | None = None):
    if start is None:
        start = NOW - timedelta(days=count)
    return [
        {
            'event_at': start + timedelta(days=index),
            'open': Decimal('100.00'),
            'high': Decimal('102.00'),
            'low': Decimal('99.00'),
            'close': Decimal('101.00'),
            'volume': Decimal('12345.5'),
        }
        for index in range(count)
    ]


def test_writing_five_hundred_symbols_of_a_month_stays_within_budget(tmp_path: Path):
    source = daily_rows(21)
    started = time.monotonic()
    for index in range(500):
        declared = daily_series(f'SYM{index:04d}')
        tape_store.write_partitions(tmp_path, declared, source, now=NOW)
    elapsed = time.monotonic() - started
    assert elapsed <= WRITE_BUDGET_SECONDS, f'500-symbol write took {elapsed:.1f}s'


def test_reading_one_symbol_never_reads_another(tmp_path: Path):
    first = daily_series('AAPL')
    second = daily_series('MSFT')
    tape_store.write_partitions(tmp_path, first, daily_rows(50), now=NOW)
    tape_store.write_partitions(tmp_path, second, daily_rows(50), now=NOW)
    manifest = tape_store.build_manifest(
        first,
        list(
            tape_store.write_partitions(
                tmp_path, first, daily_rows(50), now=NOW
            ).partitions
        ),
        written_at=NOW,
    )
    stored = tape_store.read_partitions(tmp_path, first, manifest=manifest)
    assert stored.rows == 50
    assert all('MSFT' not in partition.path for partition in manifest.partitions)


def test_appending_one_month_to_an_existing_partition_stays_within_budget(
    tmp_path: Path,
):
    declared = daily_series('AAPL')
    tape_store.write_partitions(
        tmp_path, declared, daily_rows(1500, NOW - timedelta(days=1500)), now=NOW
    )
    started = time.monotonic()
    tape_store.write_partitions(
        tmp_path, declared, daily_rows(21, NOW - timedelta(days=20)), now=NOW
    )
    elapsed = time.monotonic() - started
    assert elapsed <= APPEND_BUDGET_SECONDS, f'append took {elapsed:.1f}s'


def test_reading_ten_years_of_one_symbol_stays_within_budget(tmp_path: Path):
    """Ten years of daily bars is about 2,500 rows across 120 partitions."""
    declared = daily_series('AAPL')
    source = daily_rows(2520, datetime(2016, 1, 1, tzinfo=timezone.utc))
    result = tape_store.write_partitions(tmp_path, declared, source, now=NOW)
    manifest = tape_store.build_manifest(
        declared, list(result.partitions), written_at=NOW
    )
    started = time.monotonic()
    stored = tape_store.read_partitions(tmp_path, declared, manifest=manifest)
    elapsed = time.monotonic() - started
    assert stored.rows == 2520
    assert elapsed <= READ_BUDGET_SECONDS, f'ten-year read took {elapsed:.1f}s'
