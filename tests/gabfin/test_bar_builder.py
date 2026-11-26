from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from decimal import localcontext, Decimal
from zoneinfo import ZoneInfo
import pytest

from gabfin.contracts.events import TradeMarketEvent
from gabfin.contracts.feed import CalendarSnapshot
from gabfin.contracts.market import Timeframe
from gabfin.market.bars import BarBuilder

ID = UUID('11111111-1111-4111-8111-111111111111')
START = datetime(2026, 11, 25, 14, 30, tzinfo=timezone.utc)


def calendar():
    return CalendarSnapshot(schema_version='1.0', calendar_id='fixture-XNYS', version='test-2026',
                            coverage_start=START, coverage_end=START + timedelta(days=3),
                            windows=[dict(schema_version='1.0', session='regular', start=START,
                                          end=START + timedelta(hours=6, minutes=30))])


def trade(index, seconds, price, quantity='2', *, received_seconds=None):
    capture = START + timedelta(seconds=seconds if received_seconds is None else received_seconds)
    return TradeMarketEvent(schema_version='1.0', event_id=uuid4(), instrument_id=ID,
                            kind='trade', source='fixture', source_seq=str(index),
                            dedup_key=f'fixture:trade:{index}', event_at=START + timedelta(seconds=seconds),
                            received_at=capture, available_at=capture,
                            payload=dict(schema_version='1.0', instrument_id=ID, price=price,
                                         quantity=quantity, trade_id=str(index)))


def builder(**kwargs):
    return BarBuilder(ID, source='fixture', calendar=calendar(),
                      timeframe=Timeframe(count=1, unit='minute'),
                      max_bars=3, max_trades=10, corporate_action_policy='unadjusted', **kwargs)


def test_duplicate_print_does_not_increase_volume_and_late_print_corrects_its_bar():
    bars = builder()
    first = trade(1, 10, '100')
    bars.apply(first)
    assert bars.apply(first) == []
    bars.apply(trade(2, 40, '102', '3'))
    bars.advance(START + timedelta(seconds=61))
    assert bars.snapshot()[0].status == 'final'
    updates = bars.apply(trade(3, 5, '99', '1', received_seconds=70))
    corrected = updates[-1]
    assert corrected.start == START
    assert (corrected.open, corrected.high, corrected.low, corrected.close, corrected.volume) == (99, 102, 99, 102, 6)
    assert corrected.status == 'corrected' and corrected.revision == 1
    assert corrected.available_at == START + timedelta(seconds=70)


def test_first_finalization_includes_the_arriving_trade_in_one_update():
    bars = builder()
    bars.apply(trade(1, 10, '100'))
    updates = bars.apply(trade(2, 40, '102', received_seconds=65))
    assert len(updates) == 1
    assert updates[0].status == 'final' and updates[0].volume == 4


def test_bounded_retention_cannot_resurrect_an_evicted_print():
    bars = builder()
    for i in range(4):
        bars.apply(trade(i, i * 60 + 1, str(100 + i)))
    assert len(bars.snapshot()) == 3
    with pytest.raises(ValueError, match='evicted'):
        bars.apply(trade(99, 10, '90', received_seconds=240))


def test_capacity_failure_does_not_silently_drop_or_change_volume():
    bars = builder()
    for i in range(10):
        bars.apply(trade(i, i, '100'))
    with pytest.raises(ValueError, match='capacity'):
        bars.apply(trade(11, 11, '100'))
    assert bars.snapshot()[0].volume == 20


def test_conflicting_trade_identity_and_quote_input_are_rejected():
    bars = builder()
    event = trade(1, 10, '100')
    bars.apply(event)
    with pytest.raises(ValueError, match='conflict'):
        bars.apply(trade(1, 10, '101'))
    from test_quote_stream import observation
    with pytest.raises(ValueError):
        bars.apply(observation())
    assert bars.snapshot()[0].volume == 2


def test_market_closed_or_outside_calendar_coverage_never_creates_a_bar():
    bars = builder()
    with pytest.raises(ValueError, match='market_closed'):
        bars.apply(trade(1, 86400, '100'))
    with pytest.raises(ValueError, match='calendar_unavailable'):
        bars.apply(trade(2, 86400 * 4, '100'))
    assert bars.snapshot() == ()


@pytest.mark.parametrize('day,utc_hour', [(datetime(2026, 3, 9), 13), (datetime(2026, 11, 2), 14)])
def test_exchange_calendar_utc_windows_preserve_new_york_dst(day, utc_hour):
    opened = day.replace(hour=9, minute=30, tzinfo=ZoneInfo('America/New_York'))
    closed = opened + timedelta(hours=6, minutes=30)
    snapshot = CalendarSnapshot(schema_version='1.0', calendar_id='fixture-XNYS', version='2026',
                                coverage_start=opened, coverage_end=closed,
                                windows=[dict(schema_version='1.0', session='regular', start=opened, end=closed)])
    bars = BarBuilder(ID, source='fixture', calendar=snapshot,
                      timeframe=Timeframe(count=1, unit='minute'), max_bars=2, max_trades=10,
                      corporate_action_policy='unadjusted')
    event = trade(1, 10, '100')
    event = event.model_copy(update=dict(event_at=opened.astimezone(timezone.utc),
                                         received_at=opened.astimezone(timezone.utc), available_at=opened.astimezone(timezone.utc)))
    result = bars.apply(event)[0]
    assert result.start.hour == utc_hour and result.start.minute == 30


def test_volume_is_exact_under_low_ambient_decimal_precision():
    bars = builder()
    with localcontext() as context:
        context.prec = 2
        bars.apply(trade(1, 1, '100', '123456789.123456789'))
        result = bars.apply(trade(2, 2, '101', '0.000000001'))[-1]
    assert result.volume == Decimal('123456789.123456790')


def test_ambiguous_simultaneous_prices_need_a_provider_order():
    bars = builder()
    bars.apply(trade(1, 1, '100').model_copy(update={'source_seq': None}))
    with pytest.raises(ValueError, match='ambiguous'):
        bars.apply(trade(2, 1, '101').model_copy(update={'source_seq': None}))
    assert bars.snapshot()[0].volume == 2


def test_retained_dedup_key_cannot_be_reassigned_to_another_trade_id():
    bars = builder()
    first = trade(1, 1, '100')
    bars.apply(first)
    changed = first.model_copy(update={'payload': first.payload.model_copy(update={'trade_id': 'different'})})
    with pytest.raises(ValueError, match='conflict'):
        bars.apply(changed)
    assert bars.snapshot()[0].volume == 2
