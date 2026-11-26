"""Volatility and band indicators.

ATR uses Wilder's smoothing, which is a running average rather than a
moving window, so an update is O(1) and the seeded state reproduces a
full recomputation exactly.
"""
from collections import deque
from decimal import Decimal

from gabfin.indicators.inputs import PriceBar


class AverageTrueRange:
    """Wilder's average true range over `period` bars.

    The first value is the plain average of the first `period` true
    ranges. After that, each value is
    `(previous * (period - 1) + true_range) / period`, which is Wilder's
    smoothing. This is not the same as a moving average of true ranges,
    and the two disagree on real data.
    """

    def __init__(self, period: int = 14):
        if period <= 0:
            raise ValueError('ATR needs a positive period')
        self.period = period
        self._seed_ranges: list[Decimal] = []
        self._seed_total = Decimal(0)
        self._value: Decimal | None = None
        self._previous_close: Decimal | None = None
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

    def _true_range(self, bar: PriceBar) -> Decimal:
        if self._previous_close is None:
            return bar.high - bar.low
        previous = self._previous_close
        return max(
            bar.high - bar.low,
            abs(bar.high - previous),
            abs(bar.low - previous),
        )

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new ATR, or None if not ready."""
        true_range = self._true_range(bar)
        self._previous_close = bar.close
        self._count += 1
        if self._value is None:
            self._seed_ranges.append(true_range)
            self._seed_total += true_range
            if len(self._seed_ranges) == self.period:
                self._value = self._seed_total / Decimal(self.period)
            return None
        self._value = (
            self._value * Decimal(self.period - 1) + true_range
        ) / Decimal(self.period)
        return self._value


class BollingerBands:
    """Bollinger bands: a moving average plus a standard deviation band.

    The variance is maintained incrementally from the moving sum and the
    sum of squares, so no pass over the window is needed per bar.
    """

    def __init__(self, period: int = 20, deviations: Decimal = Decimal(2)):
        if period <= 0:
            raise ValueError('Bollinger bands need a positive period')
        if deviations <= 0:
            raise ValueError('The band width must be positive')
        self.period = period
        self.deviations = deviations
        self._window: deque[Decimal] = deque(maxlen=period)
        self._total = Decimal(0)
        self._squares = Decimal(0)

    @property
    def ready(self) -> bool:
        return len(self._window) == self.period

    @property
    def count(self) -> int:
        return len(self._window)

    @property
    def middle(self) -> Decimal | None:
        if not self.ready:
            return None
        return self._total / Decimal(self.period)

    @property
    def standard_deviation(self) -> Decimal | None:
        if not self.ready:
            return None
        count = Decimal(self.period)
        mean = self._total / count
        variance = (self._squares - count * mean * mean) / count
        if variance <= 0:
            return Decimal(0)
        return variance.sqrt()

    def bands(self) -> tuple[Decimal, Decimal, Decimal] | None:
        """The lower, middle and upper bands, or None if not ready."""
        middle = self.middle
        deviation = self.standard_deviation
        if middle is None or deviation is None:
            return None
        width = self.deviations * deviation
        return (middle - width, middle, middle + width)

    def percent_b(self, price: Decimal) -> Decimal | None:
        """Where the price sits between the bands, from 0 to 1."""
        bands = self.bands()
        if bands is None:
            return None
        lower, _, upper = bands
        width = upper - lower
        if width == 0:
            return None
        return (price - lower) / width

    def bandwidth(self) -> Decimal | None:
        """The band width relative to the middle, as a fraction."""
        bands = self.bands()
        if bands is None:
            return None
        lower, middle, upper = bands
        if middle == 0:
            return None
        return (upper - lower) / middle

    def update(self, value: Decimal) -> tuple[Decimal, Decimal, Decimal] | None:
        """Add one close and return the new bands, or None if not ready."""
        if len(self._window) == self.period:
            oldest = self._window[0]
            self._total -= oldest
            self._squares -= oldest * oldest
        self._window.append(value)
        self._total += value
        self._squares += value * value
        return self.bands()


class DonchianChannel:
    """The highest high and lowest low over a rolling window."""

    def __init__(self, period: int = 20):
        if period <= 0:
            raise ValueError('A Donchian channel needs a positive period')
        self.period = period
        self._highs: deque[Decimal] = deque(maxlen=period)
        self._lows: deque[Decimal] = deque(maxlen=period)

    @property
    def ready(self) -> bool:
        return len(self._highs) == self.period

    @property
    def count(self) -> int:
        return len(self._highs)

    @property
    def upper(self) -> Decimal | None:
        if not self.ready:
            return None
        return max(self._highs)

    @property
    def lower(self) -> Decimal | None:
        if not self.ready:
            return None
        return min(self._lows)

    def update(self, bar: PriceBar) -> tuple[Decimal, Decimal] | None:
        """Add one bar and return the new upper and lower, or None if not ready."""
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        if not self.ready:
            return None
        return (self.upper, self.lower)


class HistoricalVolatility:
    """The annualized standard deviation of log returns.

    The annualization factor is 252 trading days, which is the standard
    for daily equity bars.
    """

    def __init__(self, period: int = 20, periods_per_year: int = 252):
        if period <= 0:
            raise ValueError('Historical volatility needs a positive period')
        if periods_per_year <= 0:
            raise ValueError('The annualization factor must be positive')
        self.period = period
        self.periods_per_year = periods_per_year
        self._returns: deque[Decimal] = deque(maxlen=period)
        self._total = Decimal(0)
        self._squares = Decimal(0)
        self._previous_close: Decimal | None = None

    @property
    def ready(self) -> bool:
        return len(self._returns) == self.period

    @property
    def count(self) -> int:
        return len(self._returns)

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        count = Decimal(self.period)
        mean = self._total / count
        variance = (self._squares - count * mean * mean) / count
        if variance <= 0:
            return Decimal(0)
        return variance.sqrt() * (Decimal(self.periods_per_year) ** Decimal('0.5'))

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new volatility, or None if not ready."""
        if self._previous_close is None:
            self._previous_close = bar.close
            return None
        if self._previous_close <= 0:
            raise ValueError('A close cannot be zero or negative')
        change = (bar.close / self._previous_close).ln()
        self._previous_close = bar.close
        if len(self._returns) == self.period:
            oldest = self._returns[0]
            self._total -= oldest
            self._squares -= oldest * oldest
        self._returns.append(change)
        self._total += change
        self._squares += change * change
        return self.value
