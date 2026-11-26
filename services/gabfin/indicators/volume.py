"""Volume-based indicators.

These are the indicators that make the source coverage matter. OBV and
MFI are computed from volume, and IEX and SIP report different volume
for the same session. A value computed on one basis and compared against
the other is not a comparison, it is a mistake.
"""
from collections import deque
from decimal import Decimal

from gabfin.indicators.inputs import PriceBar
from gabfin.indicators.moving_averages import SimpleMovingAverage


class OnBalanceVolume:
    """On-balance volume: the running sum of signed volume."""

    def __init__(self):
        self._total = Decimal(0)
        self._previous_close: Decimal | None = None
        self._count = 0

    @property
    def ready(self) -> bool:
        return self._count > 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        return self._total

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new OBV."""
        if bar.volume is None:
            raise ValueError('OBV needs volume')
        if self._previous_close is None:
            self._previous_close = bar.close
            self._count += 1
            return self._total
        if bar.close > self._previous_close:
            self._total += bar.volume
        elif bar.close < self._previous_close:
            self._total -= bar.volume
        self._previous_close = bar.close
        self._count += 1
        return self._total


class VolumeMovingAverage:
    """A simple moving average of volume."""

    def __init__(self, period: int = 20):
        if period <= 0:
            raise ValueError('A volume average needs a positive period')
        self.period = period
        self._average = SimpleMovingAverage(period)

    @property
    def ready(self) -> bool:
        return self._average.ready

    @property
    def count(self) -> int:
        return self._average.count

    @property
    def value(self) -> Decimal | None:
        return self._average.value

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new average, or None if not ready."""
        if bar.volume is None:
            raise ValueError('A volume average needs volume')
        return self._average.update(bar.volume)


class MoneyFlowIndex:
    """The money flow index over `period` bars.

    Like RSI, it uses Wilder's smoothing on the positive and negative
    money flows. The raw money flow is the typical price times the
    volume.
    """

    def __init__(self, period: int = 14):
        if period <= 0:
            raise ValueError('MFI needs a positive period')
        self.period = period
        self._positive: list[Decimal] = []
        self._negative: list[Decimal] = []
        self._positive_total = Decimal(0)
        self._negative_total = Decimal(0)
        self._average_positive: Decimal | None = None
        self._average_negative: Decimal | None = None
        self._previous_typical: Decimal | None = None
        self._count = 0

    @property
    def ready(self) -> bool:
        return self._average_positive is not None

    @property
    def count(self) -> int:
        return self._count

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        if self._average_negative == 0:
            if self._average_positive == 0:
                return Decimal(50)
            return Decimal(100)
        ratio = self._average_positive / self._average_negative
        return Decimal(100) - Decimal(100) / (Decimal(1) + ratio)

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new MFI, or None if not ready."""
        if bar.volume is None:
            raise ValueError('MFI needs volume')
        typical = bar.typical_price
        if self._previous_typical is None:
            self._previous_typical = typical
            self._count += 1
            return None
        flow = typical * bar.volume
        if typical > self._previous_typical:
            positive, negative = flow, Decimal(0)
        elif typical < self._previous_typical:
            positive, negative = Decimal(0), flow
        else:
            positive, negative = Decimal(0), Decimal(0)
        self._previous_typical = typical
        self._count += 1
        if self._average_positive is None:
            self._positive.append(positive)
            self._negative.append(negative)
            self._positive_total += positive
            self._negative_total += negative
            if len(self._positive) == self.period:
                self._average_positive = self._positive_total / Decimal(self.period)
                self._average_negative = self._negative_total / Decimal(self.period)
            return None
        period = Decimal(self.period)
        self._average_positive = (
            self._average_positive * (period - 1) + positive
        ) / period
        self._average_negative = (
            self._average_negative * (period - 1) + negative
        ) / period
        return self.value


class VolumeWeightedAveragePrice:
    """The session's volume-weighted average price.

    The accumulation resets when the session changes, so a day bar's VWAP
    is that day's VWAP rather than an average over all history.
    """

    def __init__(self):
        self._session: str | None = None
        self._total = Decimal(0)
        self._volume = Decimal(0)
        self._count = 0

    @property
    def ready(self) -> bool:
        return self._volume > 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def value(self) -> Decimal | None:
        if not self.ready:
            return None
        return self._total / self._volume

    def update(self, bar: PriceBar) -> Decimal | None:
        """Add one bar and return the new session VWAP."""
        if bar.volume is None:
            raise ValueError('VWAP needs volume')
        session = bar.session
        if session != self._session:
            self._session = session
            self._total = Decimal(0)
            self._volume = Decimal(0)
        self._total += bar.typical_price * bar.volume
        self._volume += bar.volume
        self._count += 1
        return self.value
