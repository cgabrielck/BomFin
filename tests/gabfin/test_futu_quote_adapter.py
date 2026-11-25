"""A real isolated process stands in for the external SDK runtime."""
import asyncio
import sys
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
import pytest

from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.providers.futu.adapter import FutuQuoteAdapter
from gabfin.providers.futu.symbols import InstrumentCatalog
from test_symbols import equity, AAPL


def fake_worker(tmp_path, body):
    worker = tmp_path / 'sdk_stub.py'
    worker.write_text("""
import sys,json
c=json.loads(sys.stdin.readline())
def ready():
    print(json.dumps(dict(version=1,kind='ready')),flush=True)
def finish(*,cleanup='unsubscribed',errors=None,callbacks=0):
    print(json.dumps(dict(version=1,kind='closed',cleanup=cleanup,closed=True,
                          errors=errors or [],callbacks=callbacks,coalesced=0,rejected=0)),flush=True)
""" + body, encoding='utf-8')
    return worker


def test_adapter_delivers_callback_while_worker_is_still_running_then_closes(tmp_path):
    worker = fake_worker(tmp_path, """
ready()
print(json.dumps(dict(version=1,kind='quote',code='US.AAPL',price='100.25',event_at='2020-11-25T14:59:58Z',received_at='2020-11-25T15:00:00Z')),flush=True)
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=1)
""")

    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        key = SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)
        await adapter.subscribe([key])
        iterator = adapter.events()
        event = await asyncio.wait_for(anext(iterator), 5)
        assert event.payload.last.price == 100.25
        assert event.event_at == datetime(2020, 11, 25, 14, 59, 58, tzinfo=timezone.utc)
        assert event.received_at == datetime(2020, 11, 25, 15, tzinfo=timezone.utc)
        assert event.payload.bid is event.payload.ask is None
        assert event.payload.session == 'unknown'
        assert event.payload.entitlements.status == 'unknown'
        assert event.source == event.payload.feed == 'futu'
        assert event.payload.last.age_ms > 365 * 86400 * 1000  # old source remains old
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
ready()
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=0)
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
ready()
sys.stdin.readline()
finish(cleanup='release_pending', errors=['unsubscribe_failed'], callbacks=0)
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


def test_parallel_subscribers_share_the_same_pending_acknowledgement(tmp_path):
    worker = fake_worker(tmp_path, """
import time
from pathlib import Path
while not Path(__file__).with_suffix('.gate').exists(): time.sleep(.01)
ready()
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=0)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        keys = [SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)]
        first = asyncio.create_task(adapter.subscribe(keys))
        async with asyncio.timeout(5):
            while not adapter.running:
                await asyncio.sleep(.01)
        second = asyncio.create_task(adapter.subscribe(keys))
        await asyncio.sleep(0)
        premature = second.done()
        worker.with_suffix('.gate').touch()
        await asyncio.gather(first, second)
        await adapter.close()
        assert not premature
    asyncio.run(scenario())


def test_rejecting_an_extra_reader_does_not_close_the_authorized_reader(tmp_path):
    worker = fake_worker(tmp_path, """
ready()
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=0)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        first = asyncio.create_task(anext(adapter.events()))
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match='One event consumer'):
            await anext(adapter.events())
        healthy = adapter.running and not first.done()
        first.cancel()
        try:
            await first
        except (asyncio.CancelledError, StopAsyncIteration):
            pass
        await adapter.close()
        assert healthy
    asyncio.run(scenario())


@pytest.mark.parametrize('price', [123, 1.25, True])
def test_non_string_decimal_on_private_ipc_is_rejected(tmp_path, price):
    body = """
ready()
print(json.dumps(dict(version=1,kind='quote',code='US.AAPL',price=PRICE,event_at='2020-11-25T14:59:58Z',received_at='2020-11-25T15:00:00Z')),flush=True)
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=1)
""".replace('PRICE', repr(price))
    worker = fake_worker(tmp_path, body)
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        # Close drains the complete pipe, including the malformed quote.
        async with asyncio.timeout(5):
            while not (adapter.stats['accepted'] or adapter.stats['rejected']):
                await asyncio.sleep(.01)
        await adapter.close()
        assert adapter.snapshot() is None
        assert adapter.stats['rejected'] == 1
    asyncio.run(scenario())


def production_worker_with_fake_sdk(tmp_path, mode):
    import gabfin.providers.futu.quote_worker as entrypoint
    # Replace only the external SDK and wall-clock boundary. Run the actual
    # production worker entrypoint/control thread in a real isolated process.
    worker = tmp_path / 'external_sdk_stub.py'
    worker.write_text("""
import sys,types,runpy,importlib.metadata,time
from pathlib import Path
futu=types.ModuleType('futu')
class Config:
    @staticmethod
    def enable_console_log(value): pass
class Context:
    def __init__(self,**kwargs):
        self.owned=OWNED
        Path(__file__).with_suffix('.opened').touch()
    def set_sync_query_connect_timeout(self,value): pass
    def query_subscription(self,**kwargs): return 0,dict(own_used=self.owned)
    def set_handler(self,handler): return 0
    def subscribe(self,*args,**kwargs): self.owned=1; return 0,None
    def unsubscribe(self,*args,**kwargs): self.owned=0; return 0,None
    def close(self): pass
futu.OpenQuoteContext=Context
futu.SysConfig=Config
futu.StockQuoteHandlerBase=object
futu.SubType=types.SimpleNamespace(QUOTE='QUOTE')
futu.Session=types.SimpleNamespace(RTH='RTH')
sys.modules['futu']=futu
original_version=importlib.metadata.version
importlib.metadata.version=lambda name: '10.12.7208' if name=='futu-api' else original_version(name)
virtual=[time.monotonic()]
time.monotonic=lambda:virtual[0]
def advance(seconds): virtual[0]+=seconds
time.sleep=advance
runpy.run_path(ENTRYPOINT,run_name='__main__')
""".replace('OWNED', '2' if mode == 'existing' else '0')
            .replace('ENTRYPOINT', repr(str(Path(entrypoint.__file__)))), encoding='utf-8')
    return worker


@pytest.mark.parametrize('mode', ['existing', 'natural'])
def test_real_worker_can_end_without_parent_stop_and_without_buffered_stdin_crash(tmp_path, mode):
    worker = production_worker_with_fake_sdk(tmp_path, mode)
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        if mode == 'existing':
            with pytest.raises(RuntimeError):
                await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        else:
            await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
            async with asyncio.timeout(10):
                while adapter.running:
                    await asyncio.sleep(.01)
            await adapter.close()
        assert adapter.result['closed'] is True
        assert adapter.failure == ('quote_cleanup_incomplete' if mode == 'existing' else None)
    asyncio.run(scenario())


@pytest.mark.parametrize('patch', [
    {'version': True}, {'version': 1.0}, {'version': 2}, {'extra': 'unexpected'},
    {'port': True}, {'port': 65536}, {'host': '0.0.0.0'},
    {'code': 'US.AAPL261225C350000'}, {'deadline': float('inf')},
])
def test_worker_rejects_bad_private_config_before_opening_sdk_context(tmp_path, patch):
    worker = production_worker_with_fake_sdk(tmp_path, 'existing')
    config = dict(version=1, code='US.AAPL', host='127.0.0.1', port=11111,
                  deadline=time.monotonic() + 110) | patch
    process = subprocess.run([sys.executable, '-I', str(worker)],
                             input=json.dumps(config).encode() + b'\n',
                             capture_output=True, timeout=10, check=True)
    assert not worker.with_suffix('.opened').exists()
    message = json.loads(process.stdout)
    assert message['errors'] == ['stream_failed'] and message['cleanup'] == 'not_subscribed'


def test_terminal_worker_cannot_reuse_old_successful_subscription_ack(tmp_path):
    worker = fake_worker(tmp_path, """
from pathlib import Path
import time
ready()
finish(cleanup='unsubscribed', errors=[], callbacks=0)
while not Path(__file__).with_suffix('.gate').exists(): time.sleep(.01)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        key = SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)
        await adapter.subscribe([key])
        async with asyncio.timeout(5):
            while adapter.result is None:
                await asyncio.sleep(.01)
        try:
            with pytest.raises(RuntimeError, match='single-use'):
                await adapter.subscribe([key])
        finally:
            worker.with_suffix('.gate').touch()
            await adapter.close()
    asyncio.run(scenario())


def test_clean_cancel_before_any_subscription_is_not_a_cleanup_failure(tmp_path):
    worker = fake_worker(tmp_path, """
sys.stdin.readline()
finish(cleanup='not_subscribed', errors=[], callbacks=0)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        task = asyncio.create_task(adapter.subscribe([
            SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)]))
        async with asyncio.timeout(5):
            while not adapter.running:
                await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert adapter.result['cleanup'] == 'not_subscribed'
        assert adapter.failure is None
    asyncio.run(scenario())


@pytest.mark.parametrize('patch', [
    {'code': 'US.MSFT'}, {'price': '-1'}, {'price': 'NaN'}, {'price': 'Infinity'},
    {'event_at': '2020-11-25T14:59:58'}, {'event_at': None},
    {'event_at': '2020-11-25T15:00:01Z'}, {'received_at': '2099-11-25T15:00:01Z'},
    {'secret': 'must_not_be_retained'},
])
def test_malformed_observation_cannot_enter_market_cache(tmp_path, patch):
    message = dict(version=1, kind='quote', code='US.AAPL', price='100.25',
                   event_at='2020-11-25T14:59:58Z', received_at='2020-11-25T15:00:00Z') | patch
    body = """
ready()
print(MESSAGE,flush=True)
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=1)
""".replace('MESSAGE', repr(json.dumps(message)))
    worker = fake_worker(tmp_path, body)
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        async with asyncio.timeout(5):
            while adapter.stats['rejected'] == 0:
                await asyncio.sleep(.01)
        await adapter.close()
        assert adapter.snapshot() is None
        assert adapter.stats['accepted'] == 0
    asyncio.run(scenario())


def test_economically_equal_decimal_spellings_are_duplicates(tmp_path):
    worker = fake_worker(tmp_path, """
ready()
for price in ['100.25','100.250']:
    print(json.dumps(dict(version=1,kind='quote',code='US.AAPL',price=price,event_at='2020-11-25T14:59:58Z',received_at='2020-11-25T15:00:00Z')),flush=True)
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=2)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        async with asyncio.timeout(5):
            while adapter.stats['rejected'] == 0:
                await asyncio.sleep(.01)
        await adapter.close()
        assert adapter.stats['accepted'] == adapter.stats['rejected'] == 1
    asyncio.run(scenario())


def test_unresponsive_sdk_process_is_killed_reaped_and_not_reported_clean(tmp_path):
    worker = fake_worker(tmp_path, """
import time
ready()
time.sleep(1000)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        loop = asyncio.get_running_loop()
        real_clock = loop.time
        # Time is an external seam; advance the actual loop deadline rather
        # than replacing our reader/cleanup/timeout implementation.
        loop.time = lambda: real_clock() + 200
        try:
            await adapter.close()
        finally:
            loop.time = real_clock
        assert not adapter.running
        assert adapter.failure == 'quote_worker_timeout'
        assert adapter.result is None
    asyncio.run(scenario())


def test_active_consumer_sees_late_process_failure_even_when_close_started_first(tmp_path):
    worker = fake_worker(tmp_path, """
ready()
sys.stdin.readline()
finish(cleanup='unsubscribed', errors=[], callbacks=0)
raise SystemExit(1)
""")
    async def scenario():
        adapter = FutuQuoteAdapter(InstrumentCatalog([equity()]), AAPL,
                                   python=Path(sys.executable), _worker=worker)
        await adapter.subscribe([SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None)])
        task = asyncio.create_task(anext(adapter.events()))
        await asyncio.sleep(0)
        await adapter.close()
        with pytest.raises(RuntimeError, match='quote_worker_failed'):
            await task
    asyncio.run(scenario())
