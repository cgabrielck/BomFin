"""Read-only analysis planes: indicators, macro, and feed capabilities.

The planes are pure functions of what they are given. A bar source, a
macro source, and a list of feed capabilities are injected, so these
tests need no network, no clock, and no stored history.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from gabfin.analysis.plane import (
    CANONICAL_ORDER,
    AnalysisUnavailable,
    CapabilityPlane,
    IndicatorPlane,
    MacroPlane,
)
from gabfin.contracts.market import Timeframe, TimeUnit
from gabfin.contracts.subscriptions import FeedCapabilities
from gabfin.indicators.inputs import PriceBar

NOW = datetime(2026, 3, 2, 21, 0, tzinfo=timezone.utc)
TIMEFRAME = Timeframe(count=1, unit=TimeUnit.TRADING_DAY)
INSTRUMENT = '11111111-1111-4111-8111-111111111111'


def bars(count=120, *, volume=True, start=None):
    """A deterministic run of finalized bars."""
    if start is None:
        start = NOW - timedelta(days=count)
    result = []
    for index in range(count):
        close = Decimal('100') + Decimal((index * 7) % 23) - Decimal(11) + Decimal(index) / Decimal(100)
        result.append(PriceBar(
            event_at=start + timedelta(days=index),
            open=close - Decimal('0.10'),
            high=close + Decimal('1.50'),
            low=close - Decimal('1.25'),
            close=close,
            volume=Decimal(1000 + (index * 37) % 500) if volume else None,
        ))
    return result


class StubBars:
    def __init__(self, rows):
        self._rows = tuple(rows)
        self.calls = []

    def bars(self, instrument_id, timeframe):
        self.calls.append((instrument_id, timeframe))
        return self._rows


def test_indicator_plane_reports_every_canonical_indicator_with_provenance():
    source = StubBars(bars())
    plane = IndicatorPlane(source, source_coverage='sip')
    response = plane.series(INSTRUMENT, TIMEFRAME)
    names = {series.indicator for series in response.series}
    assert names == set(CANONICAL_ORDER)
    assert response.source_coverage == 'sip'
    assert response.computed_by == 'local'
    for series in response.series:
        assert series.instrument_id == response.instrument_id
        assert series.timeframe == response.timeframe
        assert series.source_coverage == 'sip'
        assert series.points, series.indicator
        for point in series.points:
            assert point.value is not None
            assert point.computed_at >= point.event_at
            assert point.realtime is False


def test_indicator_plane_carries_exact_decimal_strings():
    response = IndicatorPlane(StubBars(bars()), source_coverage='iex').series(
        INSTRUMENT, TIMEFRAME, indicators=['sma'])
    point = response.series[0].points[0]
    assert isinstance(point.value, Decimal)
    assert str(point.value) == str(point.value)


def test_indicator_plane_says_why_an_indicator_has_no_value():
    plane = IndicatorPlane(StubBars(bars(5)), source_coverage='sip')
    response = plane.series(INSTRUMENT, TIMEFRAME, indicators=['rsi', 'sma'])
    assert response.series == ()
    assert {status.indicator for status in response.statuses} == {'rsi', 'sma'}
    for status in response.statuses:
        assert status.ready is False
        assert status.reason == 'insufficient_history'
        assert status.required_bars is not None
        assert status.observed_bars == 5


def test_indicator_plane_rejects_an_unknown_indicator():
    plane = IndicatorPlane(StubBars(bars()), source_coverage='sip')
    with pytest.raises(AnalysisUnavailable) as error:
        plane.series(INSTRUMENT, TIMEFRAME, indicators=['rsi', 'supertrend'])
    assert error.value.reason == 'unknown_indicator'
    assert 'supertrend' in error.value.detail


def test_indicator_plane_refuses_an_empty_history():
    plane = IndicatorPlane(StubBars([]), source_coverage='sip')
    with pytest.raises(AnalysisUnavailable) as error:
        plane.series(INSTRUMENT, TIMEFRAME)
    assert error.value.reason == 'insufficient_history'


def test_indicator_plane_refuses_an_out_of_range_limit():
    plane = IndicatorPlane(StubBars(bars()), source_coverage='sip')
    for limit in (0, -1, 100001):
        with pytest.raises(AnalysisUnavailable) as error:
            plane.series(INSTRUMENT, TIMEFRAME, limit=limit)
        assert error.value.reason == 'invalid_limit'


def test_indicator_plane_limits_the_number_of_returned_points():
    plane = IndicatorPlane(StubBars(bars(60)), source_coverage='sip')
    response = plane.series(INSTRUMENT, TIMEFRAME, indicators=['sma'], limit=5)
    assert len(response.series[0].points) == 5


def test_indicator_plane_is_deterministic_for_the_same_bars():
    first = IndicatorPlane(StubBars(bars()), source_coverage='sip').series(
        INSTRUMENT, TIMEFRAME, indicators=['sma', 'rsi'])
    second = IndicatorPlane(StubBars(bars()), source_coverage='sip').series(
        INSTRUMENT, TIMEFRAME, indicators=['sma', 'rsi'])
    assert [point.value for point in first.series[0].points] == [
        point.value for point in second.series[0].points]


def test_indicator_plane_does_not_invent_volume_indicators_without_volume():
    with_volume = IndicatorPlane(StubBars(bars(volume=True)), source_coverage='sip').series(
        INSTRUMENT, TIMEFRAME, indicators=['obv'])
    without = IndicatorPlane(StubBars(bars(volume=False)), source_coverage='sip').series(
        INSTRUMENT, TIMEFRAME, indicators=['obv'])
    assert with_volume.series[0].points
    assert without.series == ()
    assert without.statuses[0].reason == 'insufficient_history'


class StubMacro:
    def __init__(self, observations):
        self._observations = observations
        self.requested = []

    def observations(self, series_id):
        self.requested.append(series_id)
        return list(self._observations.get(series_id, []))


def test_macro_plane_returns_the_latest_point_released_by_the_requested_date():
    source = StubMacro({'DGS10': [
        {'date': '2026-01-02', 'value': '4.00', 'realtime_start': '2026-01-02'},
        {'date': '2026-02-02', 'value': '4.15', 'realtime_start': '2026-02-02'},
        {'date': '2026-03-02', 'value': '4.30', 'realtime_start': '2026-03-02'},
    ]})
    plane = MacroPlane(source, clock=lambda: NOW)
    response = plane.snapshot('DGS10', as_of=date(2026, 2, 15))
    assert len(response.points) == 1
    assert response.points[0].value == Decimal('4.15')
    assert response.points[0].release_date == date(2026, 2, 2)
    assert response.as_of == date(2026, 2, 15)


def test_macro_plane_never_returns_a_point_released_after_the_requested_date():
    source = StubMacro({'DGS10': [
        {'date': '2026-03-02', 'value': '4.30', 'realtime_start': '2026-03-02'},
    ]})
    plane = MacroPlane(source, clock=lambda: NOW)
    response = plane.snapshot('DGS10', as_of=date(2026, 1, 1))
    assert response.points == ()


def test_macro_plane_refuses_an_unknown_series():
    plane = MacroPlane(StubMacro({}), clock=lambda: NOW)
    with pytest.raises(AnalysisUnavailable) as error:
        plane.snapshot('NOT_A_SERIES', as_of=date(2026, 1, 1))
    assert error.value.reason == 'unknown_series'


def test_macro_plane_reads_every_built_in_series_when_none_is_named():
    source = StubMacro({})
    plane = MacroPlane(source, clock=lambda: NOW)
    response = plane.snapshot(as_of=date(2026, 1, 1))
    assert response.points == ()
    assert 'DGS10' in source.requested
    assert 'UNRATE' in source.requested


def capabilities(source='alpaca', **overrides):
    values = dict(
        schema_version='1.0',
        source=source,
        asset_classes=('equity',),
        sessions=('regular',),
        latency_label='delayed',
        max_subscriptions=None,
        history_limits=(),
        checked_at=NOW,
        permission_errors=(),
        sequence_rules=(),
        venue_coverage='sip',
        realtime=False,
        delay_minutes=15,
        tradable_for_entry=False,
        depth_levels=None,
        fee_class='none',
        unavailable_reason=None,
    )
    values.update(overrides)
    return FeedCapabilities(**values)


def test_capability_plane_reports_each_registered_source():
    plane = CapabilityPlane(lambda: (capabilities('alpaca'), capabilities('futu')))
    response = plane.snapshot()
    assert {source.source for source in response.sources} == {'alpaca', 'futu'}
    assert response.checked_at == NOW


def test_capability_plane_reports_nothing_when_no_source_is_registered():
    response = CapabilityPlane(lambda: ()).snapshot()
    assert response.sources == ()


def test_a_delayed_feed_can_never_claim_to_be_an_entry_basis():
    with pytest.raises(ValueError):
        capabilities('alpaca', tradable_for_entry=True)


def test_a_realtime_feed_must_not_carry_a_measured_delay():
    with pytest.raises(ValueError):
        capabilities('futu', latency_label='realtime', realtime=True, delay_minutes=15,
                     tradable_for_entry=True)


def test_an_indicator_plane_needs_a_coverage_or_a_resolver():
    with pytest.raises(ValueError):
        IndicatorPlane(StubBars(bars()))


def test_a_resolved_coverage_is_used_for_the_whole_series():
    plane = IndicatorPlane(
        StubBars(bars()),
        coverage_resolver=lambda instrument_id, timeframe: 'iex')
    response = plane.series(INSTRUMENT, TIMEFRAME, indicators=['sma'])
    assert response.source_coverage == 'iex'
    assert response.series[0].source_coverage == 'iex'
    assert response.series[0].points[0].source_coverage == 'iex'


def test_an_unknown_coverage_refuses_to_compute():
    plane = IndicatorPlane(
        StubBars(bars()),
        coverage_resolver=lambda instrument_id, timeframe: 'unknown')
    with pytest.raises(AnalysisUnavailable) as error:
        plane.series(INSTRUMENT, TIMEFRAME)
    assert error.value.reason == 'unknown_source_coverage'
