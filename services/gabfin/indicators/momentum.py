"""Momentum oscillators.

RSI uses Wilder's smoothing, the same convention as ATR. The
stochastic oscillator needs the highest high and lowest low over a
window, so it keeps a rolling window of both.
"""
from collections import deque
from decimal import Decimal

from gabfin.indicators.inputs import PriceBar


class RelativeStrengthIndex:
    """Wilder's relative strength index over `period` bars.

    The seed is the simple average of the first `period` gains and
    losses. After that, both averages are smoothed recursively, which is
    what makes this differ from a simple moving average of the ratio.
    """

    def __init__(self, period: int = 14):
        if period <= 0:
            raise ValueError('RSI needs a positive period')
        self.period = period
        self._gains: list[Decimal] = []
        self._losses: list[Decimal] = []
        self._gain_total = Decimal(0)
        self._loss_total = Decimal(0)
        self._average_gain: Decimal | None = None
        self._average_loss: Decimal | None = None
        self._previous_close: Decimal | None = None
        self._count = 0

    @property
    def ready(self) -> bool:
        return self._average_gain is not None and self._average_loss is not None

    @property
    def count(self) -> int:
        return self._count

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        if self._average_loss == 0:
            if self._average_gain == 0:
                return Decimal(50)
            return Decimal(100)
        relative = self._average_gain / self._average_loss
        return Decimal(100) - Decimal(100) / (Decimal(1) + relative)

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new RSI, or None if not ready."""
        if self._previous_close is None:
            self._previous_close = bar.close
            return None
        change = bar.close - self._previous_close
        self._previous_close = bar.close
        self._count += 1
        gain = change if change > 0 else Decimal(0)
        loss = -change if change < 0 else Decimal(0)
        if self._average_gain is None:
            self._gains.append(gain)
            self._losses.append(loss)
            self._gain_total += gain
            self._loss_total += loss
            if len(self._gains) == self.period:
                self._average_gain = self._gain_total / Decimal(self.period)
                self._average_loss = self._loss_total / Decimal(self.period)
            return None
        period = Decimal(self.period)
        self._average_gain = (self._average_gain * (period - 1) + gain) / period
        self._average_loss = (self._average_loss * (period - 1) + loss) / period
        return self.value


class StochasticOscillator:
    """The stochastic oscillator, %K and %D.

    %K is the close's position within the window's high-low range. %D is
    a simple moving average of %K.
    """

    def __init__(self, period: int = 14, smoothing: int = 3):
        if period <= 0:
            raise ValueError('The stochastic needs a positive period')
        if smoothing <= 0:
            raise ValueError('The stochastic smoothing needs a positive period')
        self.period = period
        self.smoothing = smoothing
        self._highs: deque[Decimal] = deque(maxlen=period)
        self._lows: deque[Decimal] = deque(maxlen=period)
        self._k_window: deque[Decimal] = deque(maxlen=smoothing)
        self._k_total = Decimal(0)

    @property
    def ready(self) -> bool:
        return len(self._highs) == self.period

    @property
    def count(self) -> int:
        return len(self._highs)

    @property
    def k(self) -> Decimal | None:
        if not self.ready:
            return None
        highest = max(self._highs)
        lowest = min(self._lows)
        width = highest - lowest
        if width == 0:
            return Decimal(50)
        return (self._close - lowest) / width * Decimal(100)

    @property
    def d(self) -> Decimal | None:
        if len(self._k_window) < self.smoothing:
            return None
        return self._k_total / Decimal(self.smoothing)

    @property
    def j(self) -> Decimal | None:
        k = self.k
        d = self.d
        if k is None or d is None:
            return None
        return 3 * k - 2 * d

    _close: Decimal = Decimal(0)

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new %K, or None if not ready."""
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._close = bar.close
        k = self.k
        if k is None:
            return None
        if len(self._k_window) == self.smoothing:
            self._k_total -= self._k_window[0]
        self._k_window.append(k)
        self._k_total += k
        return k


class RateOfChange:
    """The percentage change over `period` bars."""

    def __init__(self, period: int = 14):
        if period <= 0:
            raise ValueError('ROC needs a positive period')
        self.period = period
        self._closes: deque[Decimal] = deque(maxlen=period + 1)
        self._count = 0

    @property
    def ready(self) -> bool:
        return len(self._closes) == self.period + 1

    @property
    def count(self) -> int:
        return self._count

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        oldest = self._closes[0]
        if oldest == 0:
            return None
        return (self._closes[-1] - oldest) / oldest * Decimal(100)

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new ROC, or None if not ready."""
        self._closes.append(bar.close)
        self._count += 1
        return self.value


class Momentum:
    """The absolute price change over `period` bars."""

    def __init__(self, period: int = 14):
        if period <= 0:
            raise ValueError('Momentum needs a positive period')
        self.period = period
        self._closes: deque[Decimal] = deque(maxlen=period + 1)
        self._count = 0

    @property
    def ready(self) -> bool:
        return len(self._closes) == self.period + 1

    @property
    def count(self) -> int:
        return self._count

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        return self._closes[-1] - self._closes[0]

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new momentum, or None if not ready."""
        self._closes.append(bar.close)
        self._count += 1
        return self.value
