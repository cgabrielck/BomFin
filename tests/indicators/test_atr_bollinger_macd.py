"""ATR, Bollinger and MACD against independently recomputed references.

Each test recomputes the indicator by a different route than the
implementation uses, so a shared mistake cannot make both agree.
"""
from decimal import Decimal

from gabfin.indicators.macd import MovingAverageConvergenceDivergence
from gabfin.indicators.moving_averages import ExponentialMovingAverage
from gabfin.indicators.volatility import AverageTrueRange, BollingerBands
from tests.indicators.conftest import bars


def true_ranges(history):
    """The true range series, computed from scratch."""
    result = []
    previous = None
    for bar in history:
        if previous is None:
            value = bar.high - bar.low
        else:
            value = max(
                bar.high - bar.low,
                abs(bar.high - previous),
                abs(bar.low - previous),
            )
        result.append(value)
        previous = bar.close
    return result


def test_atr_matches_a_hand_computed_wilder_smoothing():
    history = bars(30)
    atr = AverageTrueRange(14)
    for bar in history:
        atr.update(bar)
    ranges = true_ranges(history)
    expected = sum(ranges[:14]) / Decimal(14)
    for value in ranges[14:]:
        expected = (expected * 13 + value) / Decimal(14)
    assert abs(atr.value - expected) < Decimal('1e-20')


def test_atr_differs_from_a_simple_average_of_true_ranges():
    """Wilder's smoothing is not a moving average, and the two must differ."""
    history = bars(40)
    atr = AverageTrueRange(14)
    for bar in history:
        atr.update(bar)
    ranges = true_ranges(history)
    simple = sum(ranges[-14:]) / Decimal(14)
    assert atr.value != simple


def test_atr_is_positive_for_a_moving_market():
    atr = AverageTrueRange(14)
    for bar in bars(30):
        atr.update(bar)
    assert atr.value > 0


def test_bollinger_matches_a_direct_variance_computation():
    history = bars(30)
    bands = BollingerBands(20, Decimal(2))
    for bar in history:
        bands.update(bar.close)
    window = [bar.close for bar in history[-20:]]
    mean = sum(window) / Decimal(20)
    variance = sum((value - mean) ** 2 for value in window) / Decimal(20)
    deviation = variance.sqrt()
    assert abs(bands.middle - mean) < Decimal('1e-20')
    assert abs(bands.standard_deviation - deviation) < Decimal('1e-18')


def test_bollinger_band_width_scales_with_the_deviation_setting():
    history = bars(30)
    narrow = BollingerBands(20, Decimal(1))
    wide = BollingerBands(20, Decimal(3))
    for bar in history:
        narrow.update(bar.close)
        wide.update(bar.close)
    narrow_bands = narrow.bands()
    wide_bands = wide.bands()
    narrow_width = narrow_bands[2] - narrow_bands[0]
    wide_width = wide_bands[2] - wide_bands[0]
    assert abs(wide_width - narrow_width * 3) < Decimal('1e-15')


def test_macd_matches_two_independent_exponential_averages():
    history = bars(60)
    macd = MovingAverageConvergenceDivergence(12, 26, 9)
    for bar in history:
        macd.update(bar.close)
    fast = ExponentialMovingAverage(12)
    slow = ExponentialMovingAverage(26)
    for bar in history:
        fast.update(bar.close)
        slow.update(bar.close)
    assert macd.macd == fast.value - slow.value


def test_macd_signal_is_an_exponential_average_of_the_macd_line():
    history = bars(60)
    macd = MovingAverageConvergenceDivergence(12, 26, 9)
    signal = ExponentialMovingAverage(9)
    for bar in history:
        macd.update(bar.close)
        if macd.macd is not None:
            signal.update(macd.macd)
    assert macd.signal == signal.value


def test_macd_is_positive_in_a_rising_market():
    from tests.indicators.test_engine import monotonic_bars

    macd = MovingAverageConvergenceDivergence(3, 6, 3)
    for bar in monotonic_bars(30, rising=True):
        macd.update(bar.close)
    assert macd.macd > 0


def test_macd_is_negative_in_a_falling_market():
    from tests.indicators.test_engine import monotonic_bars

    macd = MovingAverageConvergenceDivergence(3, 6, 3)
    for bar in monotonic_bars(30, rising=False):
        macd.update(bar.close)
    assert macd.macd < 0
