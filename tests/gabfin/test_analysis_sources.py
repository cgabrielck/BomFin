"""The concrete analysis sources: the tape, FRED, and measured capabilities.

These are the pieces that connect the planes to what this build
actually has. A missing series, a missing release date and an unprobed
feed must each look different, because a browser that cannot tell them
apart will draw an empty chart and call it a market with no history.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from gabfin.analysis.runtime import InstrumentResolver, TapeHistory, indicator_plane
from gabfin.analysis.sources import TapeBarSource
from gabfin.contracts.market import Timeframe, TimeUnit
from gabfin.contracts.subscriptions import FeedCapabilities

NOW = datetime(2026, 3, 2, 21, 0, tzinfo=timezone.utc)
TIMEFRAME = Timeframe(count=1, unit=TimeUnit.TRADING_DAY)
INSTRUMENT = '11111111-1111-4111-8111-111111111111'


def write_tape(root: Path, symbol='AAPL', *, count=40, venue='sip', source='fixture'):
    """Write a deterministic series into the tape and return its manifest."""
    from gabfin.storage.manifest import write_manifest
    from gabfin.storage.tape import (
        build_manifest,
        manifest_path,
        new_series,
        write_partitions,
    )

    series = new_series(
        symbol, {'count': 1, 'unit': 'trading_day'}, source=source,
        venue_coverage=venue, adjustment='unadjusted', retention='rolling_2y')
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        close = Decimal('100') + Decimal((index * 7) % 23) - Decimal(11)
        rows.append({
            'event_at': start + timedelta(days=index),
            'open': close - Decimal('0.10'),
            'high': close + Decimal('1.50'),
            'low': close - Decimal('1.25'),
            'close': close,
            'volume': Decimal(1000 + index * 37),
        })
    written = write_partitions(root, series, rows, now=datetime(2026, 2, 1, tzinfo=timezone.utc))
    manifest = build_manifest(written.series, written.partitions,
                              written_at=datetime(2026, 2, 1, tzinfo=timezone.utc))
    write_manifest(manifest_path(root, written.series), manifest)
    return manifest


def test_the_tape_bar_source_returns_the_stored_rows(tmp_path):
    write_tape(tmp_path, count=10)
    source = TapeBarSource(tmp_path, symbol='AAPL', source='fixture')
    rows = source.bars(INSTRUMENT, TIMEFRAME)
    assert len(rows) == 10
    assert rows[0].close == Decimal('89')
    assert rows[-1].volume == Decimal(1000 + 9 * 37)
    assert all(row.event_at.tzinfo is not None for row in rows)


def test_the_tape_bar_source_reports_the_stored_venue(tmp_path):
    write_tape(tmp_path, venue='iex')
    source = TapeBarSource(tmp_path, symbol='AAPL', source='fixture')
    assert source.coverage_of(TIMEFRAME) == 'iex'


def test_a_series_written_with_an_unknown_venue_yields_unknown_coverage(tmp_path):
    write_tape(tmp_path, venue='something-else')
    source = TapeBarSource(tmp_path, symbol='AAPL', source='fixture')
    assert source.coverage_of(TIMEFRAME) == 'unknown'


def test_a_missing_series_raises_rather_than_returning_nothing(tmp_path):
    source = TapeBarSource(tmp_path, symbol='AAPL', source='fixture')
    with pytest.raises(FileNotFoundError):
        source.bars(INSTRUMENT, TIMEFRAME)
    assert source.coverage_of(TIMEFRAME) == 'unknown'


def test_the_indicator_plane_computes_from_the_tape(tmp_path):
    write_tape(tmp_path, symbol='US.AAPL', count=40, venue='sip')

    class Catalog:
        def get(self, instrument_id):
            class Instrument:
                vendor_symbols = {'futu': 'US.AAPL'}
            return Instrument()

    plane = indicator_plane(tmp_path, InstrumentResolver(Catalog()))
    response = plane.series(INSTRUMENT, TIMEFRAME, indicators=['sma', 'rsi'])
    assert response.source_coverage == 'sip'
    assert {series.indicator for series in response.series} == {'sma', 'rsi'}
    assert response.series[0].points


def test_the_indicator_plane_refuses_a_series_with_an_unknown_venue(tmp_path):
    write_tape(tmp_path, symbol='US.AAPL', count=40, venue='something-else')

    class Catalog:
        def get(self, instrument_id):
            class Instrument:
                vendor_symbols = {'futu': 'US.AAPL'}
            return Instrument()

    from gabfin.analysis.plane import AnalysisUnavailable

    plane = indicator_plane(tmp_path, InstrumentResolver(Catalog()))
    with pytest.raises(AnalysisUnavailable) as error:
        plane.series(INSTRUMENT, TIMEFRAME, indicators=['sma'])
    assert error.value.reason == 'unknown_source_coverage'


def test_the_resolver_refuses_an_instrument_it_does_not_know(tmp_path):
    class Catalog:
        def get(self, instrument_id):
            return None

    resolver = InstrumentResolver(Catalog())
    with pytest.raises(KeyError):
        resolver.symbol_of(INSTRUMENT)


def test_the_resolver_refuses_an_instrument_with_no_symbol_in_the_namespace(tmp_path):
    class Catalog:
        def get(self, instrument_id):
            class Instrument:
                vendor_symbols = {'alpaca': 'AAPL'}
            return Instrument()

    resolver = InstrumentResolver(Catalog())
    with pytest.raises(KeyError):
        resolver.symbol_of(INSTRUMENT)
