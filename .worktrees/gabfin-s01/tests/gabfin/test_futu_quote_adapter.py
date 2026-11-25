"""A real isolated process stands in for the external SDK runtime."""
import asyncio
import sys
from pathlib import Path
import pytest

from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.providers.futu.adapter import FutuQuoteAdapter
from gabfin.providers.futu.symbols import InstrumentCatalog
from test_symbols import equity, AAPL


def fake_worker(tmp_path, body):
    worker = tmp_path / 'sdk_stub.py'
    worker.write_text("import sys,json\nc=json.loads(sys.stdin.readline())\n" + body, encoding='utf-8')
    return worker


def test_adapter_delivers_callback_while_worker_is_still_running_then_closes(tmp_path):
    worker = fake_worker(tmp_path, """
print(json.dumps(dict(version=1,kind='ready')),flush=True)
print(json.dumps(dict(version=1,kind='quote',code='US.AAPL',price='100.25',event_at='2020-11-25T14:59:58Z',received_at='2020-11-25T15:00:00Z')),flush=True)
sys.stdin.readline()
print(json.dumps(dict(version=1,kind='closed',cleanup='unsubscribed',closed=True,errors=[],callbacks=1,coalesced=0,rejected=0)),flush=True)
""")

    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        key = SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)
        await adapter.subscribe([key])
        iterator = adapter.events()
        event = await asyncio.wait_for(anext(iterator), 5)
        assert event.payload.last.price == 100.25
        assert adapter.snapshot().dedup_key == event.dedup_key
        assert adapter.running
        await adapter.unsubscribe([key])
        await adapter.close()
        assert not adapter.running
        assert adapter.result['cleanup'] == 'unsubscribed'
        assert adapter.result['closed'] is True
        await iterator.aclose()
    asyncio.run(scenario())


def test_close_before_subscribe_is_terminal(tmp_path):
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL, python=Path(sys.executable))
        await adapter.close()
        with pytest.raises(RuntimeError, match='single-use'):
            await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        assert not adapter.running
    asyncio.run(scenario())


def test_cancel_waiting_consumer_waits_for_worker_cleanup(tmp_path):
    worker = fake_worker(tmp_path, """
print(json.dumps(dict(version=1,kind='ready')),flush=True)
sys.stdin.readline()
print(json.dumps(dict(version=1,kind='closed',cleanup='unsubscribed',closed=True,errors=[],callbacks=0,coalesced=0,rejected=0)),flush=True)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        iterator = adapter.events()
        task = asyncio.create_task(anext(iterator))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        assert not adapter.running
        assert adapter.result['cleanup'] == 'unsubscribed'
        await adapter.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('body', [
    "print('raw private SDK failure',flush=True)",
    "print(json.dumps(dict(version=2,kind='ready')),flush=True)",
    "print('x'*5000,flush=True)",
    "raise RuntimeError('private SDK error')",
])
def test_bad_or_failed_worker_is_reaped_and_reports_only_fixed_error(tmp_path, body):
    worker = fake_worker(tmp_path, body)
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        with pytest.raises(RuntimeError, match='could not subscribe'):
            await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        assert not adapter.running
        assert adapter.failure == 'quote_worker_failed'
        assert adapter.result is None
    asyncio.run(scenario())


def test_incomplete_cleanup_stays_visible_and_cannot_claim_success(tmp_path):
    worker = fake_worker(tmp_path, """
print(json.dumps(dict(version=1,kind='ready')),flush=True)
sys.stdin.readline()
print(json.dumps(dict(version=1,kind='closed',cleanup='release_pending',closed=True,errors=['unsubscribe_failed'],callbacks=0,coalesced=0,rejected=0)),flush=True)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        await adapter.close()
        assert adapter.failure == 'quote_cleanup_incomplete'
        assert adapter.result['cleanup'] == 'release_pending'
        iterator = adapter.events()
        with pytest.raises(RuntimeError, match='quote_cleanup_incomplete'):
            await anext(iterator)
    asyncio.run(scenario())


@pytest.mark.parametrize('key', [
    SubscriptionKey(instrument_id=AAPL, channel='trade', timeframe=None),
    SubscriptionKey(instrument_id='22222222-2222-4222-8222-222222222222', channel='quote', timeframe=None),
])
def test_foreign_instrument_and_non_quote_channel_never_start_worker(key):
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL, python=Path(sys.executable))
        with pytest.raises(ValueError):
            await adapter.subscribe([key])
        assert not adapter.running
        caps = await adapter.capabilities()
        assert caps.latency_label == 'unknown' and caps.max_subscriptions is None
        assert caps.permission_errors == ('live_manifest_unverified',)
        await adapter.close()
    asyncio.run(scenario())
