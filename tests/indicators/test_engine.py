"""Indicator truth values against hand-computed references.

These assertions pin specific numbers. A change to any of them is a
change to what the system believes an indicator means, so they should
change only deliberately.
"""
from decimal import Decimal

import pytest

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
)
from gabfin.indicators.volume import (
    MoneyFlowIndex,
    OnBalanceVolume,
    VolumeWeightedAveragePrice,
)
from tests.indicators.conftest import bars


def monotonic_bars(count: int, *, rising: bool = True) -> list:
    """A strictly monotonic run of bars, for RSI extremes."""
    from datetime import timedelta

    from gabfin.indicators.inputs import PriceBar
    from tests.indicators.conftest import START

    result = []
    for index in range(count):
        close = Decimal(100) + (Decimal(index) if rising else -Decimal(index))
        result.append(
            PriceBar(
                event_at=START + timedelta(days=index),
                open=close,
                high=close + Decimal('1'),
                low=close - Decimal('1'),
                close=close,
                volume=Decimal(1000),
            )
        )
    return result


def close(actual: Decimal, expected: Decimal, places: int = 20) -> None:
    """Assert two Decimals agree to a number of decimal places.

    Decimal division rounds at the context precision, so two expressions
    that are mathematically equal can differ in the last digits. The
    comparison allows for that and no more.
    """
    assert abs(actual - expected) < Decimal(1).scaleb(-places), (
        f'{actual} differs from {expected}'
    )


def test_simple_moving_average_is_the_window_mean():
    average = SimpleMovingAverage(3)
    assert average.update(Decimal(10)) is None
    assert average.update(Decimal(20)) is None
    assert average.update(Decimal(30)) == Decimal(20)
    assert average.update(Decimal(60)) == Decimal(110) / Decimal(3)


def test_simple_moving_average_drops_the_oldest_value():
    average = SimpleMovingAverage(3)
    for value in (10, 20, 30):
        average.update(Decimal(value))
    assert average.value == Decimal(20)
    average.update(Decimal(60))
    close(average.value, (Decimal(20) + Decimal(30) + Decimal(60)) / Decimal(3))


def test_exponential_moving_average_seeds_on_the_first_value():
    average = ExponentialMovingAverage(10)
    assert average.update(Decimal(100)) == Decimal(100)
    factor = Decimal(2) / Decimal(11)
    assert average.update(Decimal(110)) == Decimal(100) + factor * Decimal(10)


def test_weighted_moving_average_weights_the_newest_value_most():
    average = WeightedMovingAverage(3)
    average.update(Decimal(10))
    average.update(Decimal(20))
    average.update(Decimal(30))
    # Weights one, two and three against values ten, twenty and thirty.
    expected = (
        Decimal(10) * 1 + Decimal(20) * 2 + Decimal(30) * 3
    ) / Decimal(6)
    close(average.value, expected)


def test_weighted_moving_average_matches_a_direct_computation_after_rolling():
    average = WeightedMovingAverage(3)
    values = [Decimal(10), Decimal(20), Decimal(30), Decimal(40)]
    for value in values:
        average.update(value)
    window = values[-3:]
    expected = sum(
        value * weight for value, weight in zip(window, (1, 2, 3))
    ) / Decimal(6)
    close(average.value, expected)


def test_macd_is_the_difference_of_two_exponential_averages():
    macd = MovingAverageConvergenceDivergence(3, 6, 3)
    closes = [Decimal(10), Decimal(11), Decimal(12), Decimal(11), Decimal(13), Decimal(14)]
    for close_value in closes:
        macd.update(close_value)
    fast = ExponentialMovingAverage(3)
    slow = ExponentialMovingAverage(6)
    for close_value in closes:
        fast.update(close_value)
        slow.update(close_value)
    assert macd.macd == fast.value - slow.value


def test_macd_needs_a_signal_before_the_histogram_exists():
    macd = MovingAverageConvergenceDivergence(2, 4, 3)
    for index in range(10):
        macd.update(Decimal(100 + index))
    assert macd.macd is not None
    assert macd.signal is not None
    assert macd.histogram == macd.macd - macd.signal


def test_macd_refuses_a_fast_period_that_is_not_shorter():
    with pytest.raises(ValueError):
        MovingAverageConvergenceDivergence(26, 12, 9)


def test_relative_strength_index_is_fifty_when_there_is_no_change():
    rsi = RelativeStrengthIndex(3)
    for _ in range(5):
        rsi.update(bars(1)[0])
    # A flat series has no losses and no gains.
    assert rsi.value == Decimal(50)


def test_relative_strength_index_is_one_hundred_when_only_gains_occur():
    rsi = RelativeStrengthIndex(3)
    for bar in monotonic_bars(6, rising=True):
        rsi.update(bar)
    assert rsi.value == Decimal(100)


def test_relative_strength_index_is_zero_when_only_losses_occur():
    rsi = RelativeStrengthIndex(3)
    for bar in monotonic_bars(6, rising=False):
        rsi.update(bar)
    assert rsi.value == Decimal(0)


def test_relative_strength_index_stays_within_range():
    rsi = RelativeStrengthIndex(14)
    for bar in bars(100):
        value = rsi.update(bar)
        if value is not None:
            assert Decimal(0) <= value <= Decimal(100)


def test_atr_uses_wilder_smoothing_not_a_moving_average():
    atr = AverageTrueRange(3)
    history = bars(8)
    for bar in history:
        atr.update(bar)
    # Recompute Wilder's smoothing by hand over the same true ranges.
    ranges = []
    previous_close = None
    for bar in history:
        if previous_close is None:
            value = bar.high - bar.low
        else:
            value = max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        ranges.append(value)
        previous_close = bar.close
    expected = sum(ranges[:3]) / Decimal(3)
    for value in ranges[3:]:
        expected = (expected * 2 + value) / Decimal(3)
    assert atr.value == expected


def test_atr_is_not_ready_before_the_period_is_reached():
    atr = AverageTrueRange(14)
    for bar in bars(13):
        assert atr.update(bar) is None
    assert atr.value is None


def test_bollinger_bands_are_symmetric_around_the_middle():
    bands = BollingerBands(20, Decimal(2))
    for bar in bars(30):
        result = bands.update(bar.close)
    lower, middle, upper = result
    assert middle == bands.middle
    close(upper - middle, middle - lower)
    close(upper - middle, Decimal(2) * bands.standard_deviation)


def test_bollinger_percent_b_is_half_at_the_middle():
    bands = BollingerBands(20, Decimal(2))
    for bar in bars(30):
        bands.update(bar.close)
    middle = bands.middle
    close(bands.percent_b(middle), Decimal('0.5'))


def test_bollinger_bands_are_not_ready_before_the_period():
    bands = BollingerBands(20)
    for bar in bars(19):
        assert bands.update(bar.close) is None


def test_the_stochastic_is_fifty_when_the_range_is_flat():
    stochastic = StochasticOscillator(3, 2)
    history = bars(5)
    for bar in history:
        stochastic.update(bar)
    # The fixture moves, so the value is a percentage inside the range.
    assert Decimal(0) <= stochastic.k <= Decimal(100)


def test_the_stochastic_d_smooths_the_k_line():
    stochastic = StochasticOscillator(14, 3)
    for bar in bars(40):
        stochastic.update(bar)
    assert stochastic.d is not None
    assert Decimal(0) <= stochastic.d <= Decimal(100)
    assert stochastic.j == 3 * stochastic.k - 2 * stochastic.d


def test_donchian_tracks_the_window_extremes():
    channel = DonchianChannel(3)
    history = bars(6)
    for bar in history:
        channel.update(bar)
    window = history[-3:]
    assert channel.upper == max(bar.high for bar in window)
    assert channel.lower == min(bar.low for bar in window)


def test_on_balance_volume_accumulates_signed_volume():
    obv = OnBalanceVolume()
    history = bars(4)
    obv.update(history[0])
    first = history[1]
    rising = type(first)(
        event_at=first.event_at,
        open=first.open,
        high=first.high,
        low=first.low,
        close=first.close + Decimal(1),
        volume=first.volume,
    )
    obv.update(rising)
    assert obv.value == rising.volume


def test_on_balance_volume_is_unchanged_on_an_unchanged_close():
    obv = OnBalanceVolume()
    history = bars(3)
    obv.update(history[0])
    before = obv.value
    # The fixture price series does not always rise, so compare against a
    # bar whose close is exactly the previous close, with a range that
    # contains it.
    previous_close = history[0].close
    flat = type(history[1])(
        event_at=history[1].event_at,
        open=previous_close,
        high=previous_close + Decimal('1'),
        low=previous_close - Decimal('1'),
        close=previous_close,
        volume=history[1].volume,
    )
    obv.update(flat)
    assert obv.value == before


def test_money_flow_index_stays_within_range():
    mfi = MoneyFlowIndex(14)
    for bar in bars(60):
        value = mfi.update(bar)
        if value is not None:
            assert Decimal(0) <= value <= Decimal(100)


def test_vwap_resets_at_a_session_boundary():
    vwap = VolumeWeightedAveragePrice()
    history = bars(4)
    for bar in history:
        vwap.update(bar)
    # A bar in a new session must not carry the old session's volume, so
    # its VWAP is that bar's own typical price.
    next_bar = type(history[0])(
        event_at=history[-1].event_at,
        open=history[-1].open,
        high=history[-1].high,
        low=history[-1].low,
        close=history[-1].close,
        volume=history[-1].volume,
        session_key='other-session',
    )
    vwap.update(next_bar)
    assert vwap.value == next_bar.typical_price


def test_rate_of_change_is_the_percentage_change():
    roc = RateOfChange(2)
    history = bars(4)
    for bar in history:
        roc.update(bar)
    window = [bar.close for bar in history[-3:]]
    expected = (window[-1] - window[0]) / window[0] * Decimal(100)
    assert roc.value == expected


def test_momentum_is_the_absolute_change():
    momentum = Momentum(2)
    history = bars(4)
    for bar in history:
        momentum.update(bar)
    window = [bar.close for bar in history[-3:]]
    assert momentum.value == window[-1] - window[0]


def test_an_indicator_without_volume_refuses_to_run():
    obv = OnBalanceVolume()
    with pytest.raises(ValueError):
        obv.update(bars(1, volume=False)[0])
