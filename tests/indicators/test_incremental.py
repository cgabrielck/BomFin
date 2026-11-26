"""The engine's load-bearing invariant: incremental equals a full recompute.

A seeded state and a live state must agree exactly. If they do not, a
backtest and a live chart are running different indicators, and no
amount of parameter tuning fixes that.
"""
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from gabfin.indicators.engine import IndicatorEngine
from gabfin.indicators.inputs import PriceBar
from tests.indicators.conftest import (
    INSTRUMENT,
    LONG_START,
    TIMEFRAME,
    bars,
)

SOURCE = 'sip'


def engine() -> IndicatorEngine:
    return IndicatorEngine(
        instrument_id=UUID(INSTRUMENT),
        timeframe=TIMEFRAME,
        source_coverage=SOURCE,
    )


def full_recompute(history: list[PriceBar]) -> dict[str, Decimal]:
    """Recompute every indicator from scratch, bar by bar, keeping the last."""
    machine = engine()
    state = machine.seed([])
    latest: dict[str, Decimal] = {}
    for bar in history:
        for point in machine.update(state, bar):
            latest[point.indicator] = point.value
    return latest


def incremental(history: list[PriceBar], seed_at: int) -> dict[str, Decimal]:
    """Seed from a prefix, then feed the rest one bar at a time."""
    machine = engine()
    state = machine.seed(history[:seed_at])
    latest: dict[str, Decimal] = {}
    for bar in history[seed_at:]:
        for point in machine.update(state, bar):
            latest[point.indicator] = point.value
    return latest


@pytest.mark.parametrize('seed_at', [0, 1, 19, 20, 40, 60, 119])
def test_a_seeded_state_equals_a_full_recompute(seed_at):
    history = bars(120)
    assert incremental(history, seed_at) == full_recompute(history)


def test_seeding_alone_produces_the_same_values_as_feeding_every_bar():
    history = bars(120)
    machine = engine()
    seeded = machine.seed(history)
    live = machine.seed([])
    for bar in history:
        machine.update(live, bar)
    assert _values(seeded) == _values(live)


def test_the_update_cost_does_not_grow_with_the_state():
    """Feeding a bar to a long state must not cost more than to a short one.

    A full recomputation would be linear in the history length. This is
    the property that keeps the live path cheap as the tape grows.
    """
    import time

    # The feed must stay in the past: an indicator cannot be computed
    # before the bar it describes, and the contract refuses that.
    history = bars(1000, start=LONG_START)
    machine = engine()
    short = machine.seed(history[:1])
    long = machine.seed(history)

    short_feed = bars(200, start=history[1].event_at)
    long_feed = bars(200, start=history[-1].event_at + timedelta(days=1))

    started = time.monotonic()
    for bar in short_feed:
        machine.update(short, bar)
    short_cost = time.monotonic() - started

    started = time.monotonic()
    for bar in long_feed:
        machine.update(long, bar)
    long_cost = time.monotonic() - started

    # The bound is loose because this is a timing test, but a linear scan
    # over a thousand bars would blow past it.
    assert long_cost < short_cost * 20 + 1.0


def test_a_long_state_updates_in_constant_time():
    """A state seeded from a thousand bars updates as fast as a fresh one."""
    import time

    short_history = bars(20)
    long_history = bars(1000, start=LONG_START)
    machine = engine()
    short = machine.seed(short_history)
    long = machine.seed(long_history)

    short_feed = bars(500, start=short_history[-1].event_at + timedelta(days=1))
    long_feed = bars(500, start=long_history[-1].event_at + timedelta(days=1))

    started = time.monotonic()
    for bar in short_feed:
        machine.update(short, bar)
    short_cost = time.monotonic() - started

    started = time.monotonic()
    for bar in long_feed:
        machine.update(long, bar)
    long_cost = time.monotonic() - started

    assert long_cost < short_cost * 20 + 1.0


def _values(state) -> dict[str, Decimal]:
    return {
        'sma': state.sma_20.value,
        'ema': state.ema_20.value,
        'wma': state.wma_20.value,
        'macd': state.macd.macd,
        'signal': state.macd.signal,
        'histogram': state.macd.histogram,
        'rsi': state.rsi_14.value,
        'k': state.stochastic.k,
        'd': state.stochastic.d,
        'atr': state.atr_14.value,
        'middle': state.bollinger.middle,
        'upper': state.bollinger.bands()[0],
        'lower': state.bollinger.bands()[2],
        'obv': state.obv.value,
        'mfi': state.mfi_14.value,
        'vwap': state.vwap.value,
    }


def test_bars_must_arrive_in_order():
    machine = engine()
    history = bars(5)
    state = machine.seed(history[:2])
    with pytest.raises(ValueError):
        machine.update(state, history[0])


def test_a_repeated_bar_is_refused():
    machine = engine()
    history = bars(3)
    state = machine.seed(history[:2])
    with pytest.raises(ValueError):
        machine.update(state, history[1])


def test_the_state_counts_the_bars_it_saw():
    machine = engine()
    history = bars(37)
    state = machine.seed(history)
    assert state.bars_seen == 37
    assert state.last_event_at == history[-1].event_at


def test_points_carry_the_source_coverage():
    machine = engine()
    history = bars(60)
    state = machine.seed(history[:-1])
    points = machine.update(state, history[-1])
    assert points
    for point in points:
        assert point.source_coverage == SOURCE
        assert point.computed_by == 'local'
        assert point.realtime is False


def test_points_are_not_emitted_before_an_indicator_is_ready():
    machine = engine()
    history = bars(3)
    state = machine.seed(history[:1])
    points = machine.update(state, history[1])
    names = {point.indicator for point in points}
    # With two bars, only the indicators that need one bar have a value.
    assert 'sma' not in names
    assert 'ema' in names
    assert 'macd' in names
