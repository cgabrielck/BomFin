"""Moving averages over a fixed window.

Each class keeps the state an incremental update needs and nothing more.
A rolling window is a deque with a running sum, so an update is O(1):
push one value, subtract the value that fell out.
"""
from collections import deque
from decimal import Decimal


class SimpleMovingAverage:
    """A simple moving average over the last `period` values."""

    def __init__(self, period: int):
        if period <= 0:
            raise ValueError('A moving average needs a positive period')
        self.period = period
        self._window: deque[Decimal] = deque(maxlen=period)
        self._total = Decimal(0)

    @property
    def ready(self) -> bool:
        return len(self._window) == self.period

    @property
    def count(self) -> int:
        return len(self._window)

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        return self._total / Decimal(self.period)

    def update(self, value: Decimal) -> Decimal | None:
        """Add one value and return the new average, or None if not ready."""
        if len(self._window) == self.period:
            self._total -= self._window[0]
        self._window.append(value)
        self._total += value
        return self.value


class WeightedMovingAverage:
    """A linearly weighted moving average; the newest value counts most.

    The oldest value in a full window has weight one and the newest has
    weight `period`. The weighted sum is maintained in O(1): while the
    window is filling, positions do not move, so the new value simply
    arrives with the next weight. Once the window is full, the oldest
    value leaves and every survivor shifts down one position, which
    removes the window's plain total from the weighted sum.
    """

    def __init__(self, period: int):
        if period <= 0:
            raise ValueError('A moving average needs a positive period')
        self.period = period
        self._window: deque[Decimal] = deque(maxlen=period)
        self._total = Decimal(0)
        self._weighted = Decimal(0)

    @property
    def ready(self) -> bool:
        return len(self._window) == self.period

    @property
    def count(self) -> int:
        return len(self._window)

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        weight_total = Decimal(self.period * (self.period + 1) // 2)
        return self._weighted / weight_total

    def update(self, value: Decimal) -> Decimal | None:
        """Add one value and return the new average, or None if not ready."""
        if len(self._window) == self.period:
            # The oldest value leaves and every survivor shifts down one
            # position, which subtracts the window's plain total.
            self._weighted -= self._total
            self._total -= self._window[0]
            self._window.append(value)
            self._total += value
            self._weighted += value * Decimal(self.period)
        else:
            self._window.append(value)
            self._total += value
            self._weighted += value * Decimal(len(self._window))
        return self.value


class ExponentialMovingAverage:
    """An exponential moving average with Wilder-style smoothing.

    The smoothing factor is `2 / (period + 1)`, the convention used by
    MACD and by most charting tools. The seed is the first value seen,
    which is what makes a seeded state reproduce a full recomputation.
    """

    def __init__(self, period: int):
        if period <= 0:
            raise ValueError('A moving average needs a positive period')
        self.period = period
        self.factor = Decimal(2) / Decimal(period + 1)
        self._value: Decimal | None = None
        self._count = 0

    @property
    def ready(self) -> bool:
        return self._value is not None

    @property
    def count(self) -> int:
        return self._count

    @property
    def value(self) -> Decimal | None:
        return self._value

    def update(self, value: Decimal) -> Decimal | None:
        """Add one value and return the new average."""
        if self._value is None:
            self._value = value
        else:
            self._value = self._value + self.factor * (value - self._value)
        self._count += 1
        return self._value
