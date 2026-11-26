"""Shared indicator fixtures; deterministic bars with no network or clock."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from gabfin.contracts.market import Timeframe
from gabfin.indicators.inputs import PriceBar

#: A start point well in the past, so a long fixture run stays in the past.
PAST = datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc)

#: A second start point for runs long enough to need their own window.
LONG_START = datetime(2020, 1, 2, 21, 0, tzinfo=timezone.utc)

#: The fixture bars start far enough back that a thousand bars still land
#: in the past. An indicator cannot be computed before its bar, so a
#: fixture that ran into the future would be rejected by the contract.
START = PAST

TIMEFRAME = Timeframe.model_validate({'count': 1, 'unit': 'trading_day'})

INSTRUMENT = '11111111-1111-4111-8111-111111111111'


def price_at(index: int) -> Decimal:
    """A deterministic but non-trivial price series.

    The values oscillate rather than trend, so a moving average, an
    exponential average and a standard deviation all exercise different
    paths and cannot accidentally agree.
    """
    base = Decimal('100')
    offset = Decimal((index * 7) % 23) - Decimal(11)
    return base + offset + (Decimal(index) / Decimal(100))


def bars(
    count: int = 120,
    *,
    volume: bool = True,
    start: datetime = START,
) -> list[PriceBar]:
    """A deterministic run of finalized bars."""
    result = []
    for index in range(count):
        close = price_at(index)
        high = close + Decimal('1.50')
        low = close - Decimal('1.25')
        result.append(
            PriceBar(
                event_at=start + timedelta(days=index),
                open=close - Decimal('0.10'),
                high=high,
                low=low,
                close=close,
                volume=Decimal(1000 + (index * 37) % 500) if volume else None,
            )
        )
    return result


def bar_after(source: PriceBar, days: int = 1) -> PriceBar:
    """A bar that follows another one, for feeding a seeded state."""
    return PriceBar(
        event_at=source.event_at + timedelta(days=days),
        open=source.open,
        high=source.high,
        low=source.low,
        close=source.close,
        volume=source.volume,
    )


@pytest.fixture
def price_bars():
    return bars()


@pytest.fixture
def timeframe():
    return TIMEFRAME


@pytest.fixture
def instrument_id():
    return INSTRUMENT
