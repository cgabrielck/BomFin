"""Public callback/cache behavior; no live SDK or account context."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
import asyncio

import pytest

from gabfin.market.stream import QuoteStream
from gabfin.contracts.events import QuoteMarketEvent

ID = UUID('00000000-0000-0000-0000-000000000001')
NOW = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)


def observation(price='100.25', source='2026-11-25T14:59:58Z', age=2000):
    return QuoteMarketEvent.model_validate(dict(
        schema_version='1.0', event_id=uuid4(), instrument_id=ID, kind='quote',
        event_at=source, received_at=NOW, available_at=NOW, source='test-feed',
        source_seq=None, dedup_key=f'test:{source}:{price}',
        payload=dict(schema_version='1.0', instrument_id=ID, as_of=NOW, feed='test-feed',
                     session='unknown', bid=None, ask=None,
                     last=dict(price=price, event_at=source, received_at=NOW,
                               available_at=NOW, age_ms=age), quality=('unknown', 'incomplete'),
                     entitlements=dict(status='unknown', checked_at=None))))


def test_typed_snapshot_retains_capture_time_and_provider_provenance():
    stream = QuoteStream(ID)
    assert stream.apply(observation())
    event = stream.snapshot()
    assert event.instrument_id == ID
    assert event.event_at == NOW - timedelta(seconds=2)
    assert event.payload.last.price == Decimal('100.25')
    assert event.payload.last.age_ms == 2000
    assert event.payload.bid is event.payload.ask is None
    assert event.payload.session == 'unknown'
    assert event.payload.entitlements.status == 'unknown'
    assert 'unknown' in event.payload.quality
    assert event.source == 'test-feed' and event.payload.feed == 'test-feed'


def test_slow_consumer_has_one_pending_latest_and_snapshot_is_defensive():
    async def scenario():
        stream = QuoteStream(ID)
        for price in range(100, 1100):
            assert stream.apply(observation(str(price)))
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


@pytest.mark.parametrize('value', [None, {}, observation().model_copy(update={'instrument_id': uuid4()})])
def test_untyped_or_foreign_observation_does_not_replace_cache(value):
    stream = QuoteStream(ID)
    assert stream.apply(observation())
    assert not stream.apply(value)
    assert stream.snapshot().payload.last.price == Decimal('100.25')
    assert stream.rejected == 1


def test_late_and_duplicate_quotes_do_not_regress_or_refresh_age():
    stream = QuoteStream(ID)
    event = observation()
    assert stream.apply(event)
    assert not stream.apply(observation('50', source='2026-11-25T14:00:00Z', age=3600000))
    assert not stream.apply(event.model_copy(update={'available_at': NOW + timedelta(minutes=1)}))
    assert stream.snapshot().payload.last.age_ms == 2000
    assert stream.apply(observation('100.26'))


def test_empty_reader_wakes_on_close_and_cancel_allows_another_reader():
    async def scenario():
        stream = QuoteStream(ID)
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
        assert not stream.apply(observation())
    asyncio.run(scenario())
