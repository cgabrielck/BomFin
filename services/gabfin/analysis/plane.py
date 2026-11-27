"""Read-only analysis planes: indicators, macro, and feed capabilities.

Each plane answers one question, and each answers it with the
provenance attached. An indicator says what it was computed from. A
macro observation says when it was released. A feed says whether its
price may be used to enter.

The planes never write. They read stored history, or they read a
provider, and they return contracts. Nothing here decides, orders, or
allocates.
"""
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Callable, Iterable, Protocol, Sequence
from uuid import UUID

from gabfin.contracts.analysis import (
    CapabilitiesResponse,
    IndicatorResponse,
    MacroResponse,
)
from gabfin.contracts.indicator import (
    ComputedBy,
    IndicatorName,
    IndicatorPoint,
    IndicatorSeries,
    IndicatorStatus,
    SourceCoverage,
)
from gabfin.contracts.macro import MacroPoint
from gabfin.contracts.market import Timeframe
from gabfin.contracts.subscriptions import FeedCapabilities
from gabfin.indicators.engine import CANONICAL_PARAMS, IndicatorEngine
from gabfin.indicators.inputs import PriceBar
from gabfin.providers.fred.fetch import as_of as released_by
from gabfin.providers.fred.fetch import to_points
from gabfin.providers.fred.series import ids as macro_series_ids
from gabfin.providers.fred.series import known as macro_series_known


class AnalysisUnavailable(RuntimeError):
    """The plane cannot answer right now, and says why."""

    def __init__(self, reason: str, detail: str | None = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class BarSource(Protocol):
    """Where an indicator's bars come from."""

    def bars(self, instrument_id: UUID, timeframe: Timeframe) -> Sequence[PriceBar]: ...


class MacroSource(Protocol):
    """Where a macro observation comes from."""

    def observations(self, series_id: str) -> list[dict]: ...


#: The indicators the engine produces, in the order a chart wants them.
CANONICAL_ORDER: tuple[IndicatorName, ...] = (
    'sma', 'ema', 'wma',
    'macd', 'macd_signal', 'macd_histogram',
    'rsi',
    'stochastic_k', 'stochastic_d', 'stochastic_j',
    'atr',
    'bollinger_upper', 'bollinger_middle', 'bollinger_lower',
    'bollinger_percent_b', 'bollinger_bandwidth',
    'donchian_upper', 'donchian_lower',
    'historical_volatility',
    'obv', 'volume_sma', 'mfi', 'vwap',
    'roc', 'momentum',
)

#: How many bars each indicator needs before it has a value. An
#: indicator that has not reached its period has no value, and the UI
#: is told so rather than shown a blank chart.
REQUIRED_BARS: dict[str, int] = {
    'sma': 20, 'ema': 20, 'wma': 20,
    'macd': 26, 'macd_signal': 26, 'macd_histogram': 26,
    'rsi': 14,
    'stochastic_k': 14, 'stochastic_d': 14, 'stochastic_j': 14,
    'atr': 14,
    'bollinger_upper': 20, 'bollinger_middle': 20, 'bollinger_lower': 20,
    'bollinger_percent_b': 20, 'bollinger_bandwidth': 20,
    'donchian_upper': 20, 'donchian_lower': 20,
    'historical_volatility': 20,
    'obv': 1, 'volume_sma': 20, 'mfi': 14, 'vwap': 1,
    'roc': 14, 'momentum': 14,
}

#: Which parameter set each canonical indicator belongs to.
PARAMETER_KEYS: dict[str, str] = {
    **{name: name for name in (
        'sma', 'ema', 'wma', 'rsi', 'atr', 'obv', 'mfi', 'vwap', 'roc', 'momentum')},
    **{name: 'macd' for name in ('macd', 'macd_signal', 'macd_histogram')},
    **{name: 'stochastic' for name in ('stochastic_k', 'stochastic_d', 'stochastic_j')},
    **{name: 'bollinger' for name in (
        'bollinger_upper', 'bollinger_middle', 'bollinger_lower',
        'bollinger_percent_b', 'bollinger_bandwidth')},
    **{name: 'donchian' for name in ('donchian_upper', 'donchian_lower')},
    'historical_volatility': 'historical_volatility',
    'volume_sma': 'volume_sma',
}


class IndicatorPlane:
    """Computes the canonical indicator set from stored bars.

    The computation is local and reproducible: the same bars produce the
    same values, and the values say which source coverage they came
    from. A caller cannot ask for an indicator without also seeing the
    provenance that makes it interpretable.

    The coverage may be fixed or resolved per request. A resolved
    coverage is what the tape needs: each stored series names its own
    venue, and a series whose venue is not one the contract accepts is
    refused rather than labelled with a guess.
    """

    def __init__(self, bars: BarSource, *, source_coverage: SourceCoverage | None = None,
                 coverage_resolver: Callable[[UUID, Timeframe], SourceCoverage] | None = None,
                 computed_by: ComputedBy = 'local',
                 clock: Callable[[], datetime] | None = None):
        if source_coverage is None and coverage_resolver is None:
            raise ValueError('An indicator plane needs a coverage or a resolver')
        self._bars = bars
        self._source_coverage = source_coverage
        self._coverage_resolver = coverage_resolver
        self._computed_by = computed_by
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _coverage(self, instrument_id: UUID, timeframe: Timeframe) -> SourceCoverage:
        if self._coverage_resolver is not None:
            return self._coverage_resolver(instrument_id, timeframe)
        return self._source_coverage

    def series(self, instrument_id: UUID, timeframe: Timeframe, *,
               indicators: Iterable[str] | None = None,
               limit: int = 500) -> IndicatorResponse:
        requested = tuple(indicators) if indicators else CANONICAL_ORDER
        unknown = [name for name in requested if name not in CANONICAL_ORDER]
        if unknown:
            raise AnalysisUnavailable('unknown_indicator', ','.join(sorted(unknown)))
        if limit < 1 or limit > 100000:
            raise AnalysisUnavailable('invalid_limit')

        bars = tuple(self._bars.bars(instrument_id, timeframe))
        if not bars:
            raise AnalysisUnavailable('insufficient_history', 'no stored bars')
        coverage = self._coverage(instrument_id, timeframe)
        if coverage == 'unknown':
            # An indicator without a venue is not comparable with anything.
            raise AnalysisUnavailable('unknown_source_coverage')
        engine = IndicatorEngine(instrument_id, timeframe, coverage)
        state = engine.seed([])
        grouped: dict[str, list[IndicatorPoint]] = defaultdict(list)
        for bar in bars:
            for point in engine.update(state, bar):
                grouped[point.indicator].append(point)

        series: list[IndicatorSeries] = []
        statuses: list[IndicatorStatus] = []
        for name in requested:
            found = grouped.get(name, [])
            params = CANONICAL_PARAMS[PARAMETER_KEYS[name]]
            if found:
                series.append(IndicatorSeries(
                    instrument_id=instrument_id, indicator=name, params=params,
                    timeframe=timeframe, source_coverage=coverage,
                    points=tuple(found[-limit:])))
            else:
                statuses.append(IndicatorStatus(
                    indicator=name, params=params, ready=False,
                    reason='insufficient_history',
                    required_bars=REQUIRED_BARS.get(name, 1), observed_bars=len(bars)))
        return IndicatorResponse(
            schema_version='1.0', instrument_id=instrument_id, timeframe=timeframe,
            source_coverage=coverage, computed_by=self._computed_by,
            series=tuple(series), statuses=tuple(statuses))


class MacroPlane:
    """Reads macro observations and keeps their release dates honest.

    A caller that asks about a past date gets only what had been
    released by then. The observation date and the release date travel
    together, because a number without its release date is a stale
    number with no indication of it.
    """

    def __init__(self, source: MacroSource, *, clock: Callable[[], datetime] | None = None):
        self._source = source
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(self, series_id: str | None = None, *,
                 as_of: date | None = None) -> MacroResponse:
        wanted = (series_id,) if series_id else macro_series_ids()
        for name in wanted:
            if not macro_series_known(name):
                raise AnalysisUnavailable('unknown_series', name)
        moment = as_of or self._clock().astimezone(timezone.utc).date()
        points: list[MacroPoint] = []
        for name in wanted:
            observations = self._source.observations(name)
            converted = to_points(observations, series_id=name)
            visible = released_by(converted, moment)
            if visible:
                points.append(max(visible, key=lambda point: (point.release_date, point.observation_date)))
        return MacroResponse(
            schema_version='1.0', observed_at=self._clock(), as_of=moment,
            points=tuple(points))


class CapabilityPlane:
    """Reports what each feed can do, as measured rather than promised."""

    def __init__(self, sources: Callable[[], Iterable[FeedCapabilities]]):
        self._sources = sources

    def snapshot(self) -> CapabilitiesResponse:
        found = tuple(self._sources())
        return CapabilitiesResponse(
            schema_version='1.0', checked_at=self._observed_at(found), sources=found)

    @staticmethod
    def _observed_at(sources: Sequence[FeedCapabilities]) -> datetime:
        stamps = [source.checked_at for source in sources]
        return max(stamps) if stamps else datetime.now(timezone.utc)
