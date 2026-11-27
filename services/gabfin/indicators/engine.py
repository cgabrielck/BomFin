"""The incremental indicator engine.

The engine holds one state per indicator. Feeding it a bar updates every
indicator in O(1) and returns the points that changed. A full recompute
over the same history must produce the same values, and that invariant is
what makes a seeded state safe to resume from.

The invariant holds because every indicator is a pure function of the
bars it has seen, updated in the same order. Seeding replays the bars
through the same update path, so a seeded state and a live state are
indistinguishable.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from gabfin.contracts.indicator import IndicatorPoint
from gabfin.contracts.market import Timeframe
from gabfin.indicators.inputs import PriceBar
from gabfin.indicators.macd import MovingAverageConvergenceDivergence
from gabfin.indicators.momentum import (
    Momentum,
    RateOfChange,
    RelativeStrengthIndex,
    StochasticOscillator,
)
from gabfin.indicators.moving_averages import (
    ExponentialMovingAverage,
    SimpleMovingAverage,
    WeightedMovingAverage,
)
from gabfin.indicators.volatility import (
    AverageTrueRange,
    BollingerBands,
    DonchianChannel,
    HistoricalVolatility,
)
from gabfin.indicators.volume import (
    MoneyFlowIndex,
    OnBalanceVolume,
    VolumeMovingAverage,
    VolumeWeightedAveragePrice,
)

#: The canonical parameter set. Fixing these matters: a chart that
#: defaults to RSI 12 and a backtest that assumes 14 are not the same
#: strategy, and the difference is invisible until it costs money.
CANONICAL_PARAMS = {
    'sma': {'period': '20'},
    'ema': {'period': '20'},
    'wma': {'period': '20'},
    'macd': {'fast': '12', 'slow': '26', 'signal': '9'},
    'rsi': {'period': '14'},
    'stochastic': {'period': '14', 'smoothing': '3'},
    'atr': {'period': '14'},
    'bollinger': {'period': '20', 'deviations': '2'},
    'donchian': {'period': '20'},
    'historical_volatility': {'period': '20', 'periods_per_year': '252'},
    'obv': {},
    'volume_sma': {'period': '20'},
    'mfi': {'period': '14'},
    'vwap': {},
    'roc': {'period': '14'},
    'momentum': {'period': '14'},
}


@dataclass
class EngineState:
    """The state of every indicator, at one point in a bar series."""

    instrument_id: UUID
    timeframe: Timeframe
    source_coverage: str
    bars_seen: int = 0
    last_event_at: datetime | None = None
    sma_20: SimpleMovingAverage = field(default_factory=lambda: SimpleMovingAverage(20))
    ema_20: ExponentialMovingAverage = field(
        default_factory=lambda: ExponentialMovingAverage(20)
    )
    wma_20: WeightedMovingAverage = field(default_factory=lambda: WeightedMovingAverage(20))
    macd: MovingAverageConvergenceDivergence = field(
        default_factory=MovingAverageConvergenceDivergence
    )
    rsi_14: RelativeStrengthIndex = field(default_factory=RelativeStrengthIndex)
    stochastic: StochasticOscillator = field(default_factory=StochasticOscillator)
    atr_14: AverageTrueRange = field(default_factory=AverageTrueRange)
    bollinger: BollingerBands = field(default_factory=BollingerBands)
    donchian: DonchianChannel = field(default_factory=DonchianChannel)
    historical_volatility: HistoricalVolatility = field(
        default_factory=HistoricalVolatility
    )
    obv: OnBalanceVolume = field(default_factory=OnBalanceVolume)
    volume_sma_20: VolumeMovingAverage = field(default_factory=VolumeMovingAverage)
    mfi_14: MoneyFlowIndex = field(default_factory=MoneyFlowIndex)
    vwap: VolumeWeightedAveragePrice = field(
        default_factory=VolumeWeightedAveragePrice
    )
    roc_14: RateOfChange = field(default_factory=RateOfChange)
    momentum_14: Momentum = field(default_factory=Momentum)


class IndicatorEngine:
    """Computes the canonical indicator set from finalized bars."""

    def __init__(
        self,
        instrument_id: UUID,
        timeframe: Timeframe,
        source_coverage: str,
    ):
        self.instrument_id = instrument_id
        self.timeframe = timeframe
        self.source_coverage = source_coverage

    def seed(self, bars: list[PriceBar]) -> EngineState:
        """Build a state from history without recomputing the whole series.

        The bars are replayed through the same update path a live bar
        takes, so the seeded state and a live state agree exactly.
        """
        state = EngineState(
            instrument_id=self.instrument_id,
            timeframe=self.timeframe,
            source_coverage=self.source_coverage,
        )
        for bar in bars:
            self._apply(state, bar)
        return state

    def update(self, state: EngineState, bar: PriceBar) -> tuple[IndicatorPoint, ...]:
        """Add one bar and return the indicator points it produced."""
        self._apply(state, bar)
        return self._points(state, bar)

    def _apply(self, state: EngineState, bar: PriceBar) -> None:
        if state.last_event_at is not None and bar.event_at <= state.last_event_at:
            raise ValueError('Indicator bars must arrive in increasing time order')
        state.bars_seen += 1
        state.last_event_at = bar.event_at
        state.sma_20.update(bar.close)
        state.ema_20.update(bar.close)
        state.wma_20.update(bar.close)
        state.macd.update(bar.close)
        state.rsi_14.update(bar)
        state.stochastic.update(bar)
        state.atr_14.update(bar)
        state.bollinger.update(bar.close)
        state.donchian.update(bar)
        state.historical_volatility.update(bar)
        state.roc_14.update(bar)
        state.momentum_14.update(bar)
        if bar.volume is not None:
            state.obv.update(bar)
            state.volume_sma_20.update(bar)
            state.mfi_14.update(bar)
            state.vwap.update(bar)

    def _points(
        self, state: EngineState, bar: PriceBar
    ) -> tuple[IndicatorPoint, ...]:
        computed_at = datetime.now(timezone.utc)
        values: list[tuple[str, dict[str, str], Decimal | None]] = [
            ('sma', CANONICAL_PARAMS['sma'], state.sma_20.value),
            ('ema', CANONICAL_PARAMS['ema'], state.ema_20.value),
            ('wma', CANONICAL_PARAMS['wma'], state.wma_20.value),
            ('macd', CANONICAL_PARAMS['macd'], state.macd.macd),
            ('macd_signal', CANONICAL_PARAMS['macd'], state.macd.signal),
            ('macd_histogram', CANONICAL_PARAMS['macd'], state.macd.histogram),
            ('rsi', CANONICAL_PARAMS['rsi'], state.rsi_14.value),
            ('stochastic_k', CANONICAL_PARAMS['stochastic'], state.stochastic.k),
            ('stochastic_d', CANONICAL_PARAMS['stochastic'], state.stochastic.d),
            ('stochastic_j', CANONICAL_PARAMS['stochastic'], state.stochastic.j),
            ('atr', CANONICAL_PARAMS['atr'], state.atr_14.value),
            ('bollinger_upper', CANONICAL_PARAMS['bollinger'], _band(state, 0)),
            ('bollinger_middle', CANONICAL_PARAMS['bollinger'], _band(state, 1)),
            ('bollinger_lower', CANONICAL_PARAMS['bollinger'], _band(state, 2)),
            ('bollinger_percent_b', CANONICAL_PARAMS['bollinger'], _percent_b(state, bar)),
            ('bollinger_bandwidth', CANONICAL_PARAMS['bollinger'], state.bollinger.bandwidth()),
            ('donchian_upper', CANONICAL_PARAMS['donchian'], state.donchian.upper),
            ('donchian_lower', CANONICAL_PARAMS['donchian'], state.donchian.lower),
            (
                'historical_volatility',
                CANONICAL_PARAMS['historical_volatility'],
                state.historical_volatility.value,
            ),
            ('obv', CANONICAL_PARAMS['obv'], state.obv.value),
            ('volume_sma', CANONICAL_PARAMS['volume_sma'], state.volume_sma_20.value),
            ('mfi', CANONICAL_PARAMS['mfi'], state.mfi_14.value),
            ('vwap', CANONICAL_PARAMS['vwap'], state.vwap.value),
            ('roc', CANONICAL_PARAMS['roc'], state.roc_14.value),
            ('momentum', CANONICAL_PARAMS['momentum'], state.momentum_14.value),
        ]
        points = []
        for name, params, value in values:
            if value is None:
                continue
            points.append(
                IndicatorPoint(
                    schema_version='1.0',
                    instrument_id=self.instrument_id,
                    indicator=name,
                    params=params,
                    timeframe=self.timeframe,
                    value=value,
                    event_at=bar.event_at,
                    computed_at=computed_at,
                    source_coverage=self.source_coverage,
                    computed_by='local',
                    realtime=False,
                )
            )
        return tuple(points)


def _band(state: EngineState, index: int) -> Decimal | None:
    bands = state.bollinger.bands()
    if bands is None:
        return None
    return bands[index]


def _percent_b(state: EngineState, bar: PriceBar) -> Decimal | None:
    return state.bollinger.percent_b(bar.close)
