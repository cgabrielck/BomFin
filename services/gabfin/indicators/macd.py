"""The moving average convergence/divergence family.

MACD is a fast EMA minus a slow EMA. The signal line is an EMA of the
MACD line, and the histogram is the difference. All three are derived
from two exponential averages, so the whole family updates in O(1).
"""
from decimal import Decimal

from gabfin.indicators.moving_averages import ExponentialMovingAverage


class MovingAverageConvergenceDivergence:
    """MACD, its signal line and its histogram."""

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ):
        if fast_period <= 0 or slow_period <= 0 or signal_period <= 0:
            raise ValueError('MACD needs positive periods')
        if fast_period >= slow_period:
            raise ValueError('The fast period must be shorter than the slow one')
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self._fast = ExponentialMovingAverage(fast_period)
        self._slow = ExponentialMovingAverage(slow_period)
        self._signal = ExponentialMovingAverage(signal_period)
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def macd(self) -> Decimal | None:
        """The MACD line, once both averages have a value."""
        fast = self._fast.value
        slow = self._slow.value
        if fast is None or slow is None:
            return None
        return fast - slow

    @property
    def signal(self) -> Decimal | None:
        """The signal line, once the MACD line has been smoothed."""
        return self._signal.value

    @property
    def histogram(self) -> Decimal | None:
        macd = self.macd
        signal = self.signal
        if macd is None or signal is None:
            return None
        return macd - signal

    def update(self, close: Decimal) -> tuple[Decimal | None, ...]:
        """Add one close and return the MACD, signal and histogram."""
        self._fast.update(close)
        self._slow.update(close)
        self._count += 1
        macd = self.macd
        if macd is not None:
            self._signal.update(macd)
        return (macd, self.signal, self.histogram)
