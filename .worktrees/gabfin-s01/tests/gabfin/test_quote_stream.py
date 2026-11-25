"""Public callback/cache behavior; no live SDK or account context."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
import asyncio

import pytest

from gabfin.market.stream import QuoteStream

ID = UUID('00000000-0000-0000-0000-000000000001')
NOW = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)


def wire(price='100.25', source='2026-11-25T14:59:58Z', received='2026-11-25T15:00:00Z'):
    return dict(version=1, kind='quote', code='US.AAPL', price=price,
                event_at=source, received_at=received)


def test_callback_becomes_typed_snapshot_with_honest_provenance():
    stream = QuoteStream(ID, 'US.AAPL')
    assert stream.accept(wire(), available_at=NOW)
    event = stream.snapshot()
    assert event.instrument_id == ID
    assert event.event_at == NOW - timedelta(seconds=2)
    assert event.payload.last.price == Decimal('100.25')
    assert event.payload.last.age_ms == 2000
    assert event.payload.bid is event.payload.ask is None
    assert event.payload.session == 'unknown'
    assert event.payload.entitlements.status == 'unknown'
    assert 'unknown' in event.payload.quality


def test_slow_consumer_has_one_pending_latest_and_snapshot_is_defensive():
    async def scenario():
        stream = QuoteStream(ID, 'US.AAPL')
        for price in range(100, 1100):
            assert stream.accept(wire(str(price)), available_at=NOW)
        assert stream.pending_count == 1
        assert stream.coalesced == 999
        iterator = stream.events()
        event = await anext(iterator)
        assert event.payload.last.price == 1099
        with pytest.raises(ValueError):
            event.payload.last.price = Decimal('1')
        assert stream.snapshot().payload.last.price == 1099
        stream.close()
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)
    asyncio.run(scenario())


@pytest.mark.parametrize('patch', [
    {'code': 'US.MSFT'}, {'version': 2}, {'version': True}, {'price': True},
    {'price': 1.25}, {'price': '-1'}, {'price': 'NaN'}, {'price': 'Infinity'},
    {'event_at': '2026-11-25T14:59:58'}, {'event_at': None},
    {'event_at': '2026-11-25T15:00:01Z'}, {'received_at': '2026-11-25T15:00:01Z'},
    {'secret': 'must_not_be_retained'},
])
def test_invalid_input_does_not_replace_cache(patch):
    stream = QuoteStream(ID, 'US.AAPL')
    assert stream.accept(wire(), available_at=NOW)
    assert not stream.accept(wire() | patch, available_at=NOW)
    assert stream.snapshot().payload.last.price == Decimal('100.25')
    assert stream.rejected == 1


def test_late_and_duplicate_quotes_do_not_regress_or_refresh_age():
    stream = QuoteStream(ID, 'US.AAPL')
    assert stream.accept(wire(), available_at=NOW)
    assert not stream.accept(wire('50', source='2026-11-25T14:00:00Z'), available_at=NOW)
    assert not stream.accept(wire('100.250'), available_at=NOW + timedelta(minutes=1))
    assert stream.snapshot().payload.last.age_ms == 2000
    assert stream.accept(wire('100.26'), available_at=NOW)


def test_empty_reader_wakes_on_close_and_cancel_allows_another_reader():
    async def scenario():
        stream = QuoteStream(ID, 'US.AAPL')
        first = stream.events()
        task = asyncio.create_task(anext(first))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        second = stream.events()
        task = asyncio.create_task(anext(second))
        await asyncio.sleep(0)
        stream.close()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(task, 1)
        assert not stream.accept(wire(), available_at=NOW)
    asyncio.run(scenario())
