"""Operator defaults and supervisor use Massive without contacting Futu."""
import asyncio
import importlib.util
from pathlib import Path
from uuid import uuid4

from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.market.coordinator import MarketCoordinator
from gabfin.market.supervisor import FeedSupervisor
from gabfin.providers.massive.adapter import MassiveQuoteAdapter
from gabfin.providers.massive.config import MassiveConfig


def desk_module():
    spec = importlib.util.spec_from_file_location('desk_server', Path(__file__).parents[2] / 'scripts/desk-server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operator_factory_and_analysis_resolve_massive_symbols(monkeypatch, tmp_path):
    monkeypatch.setenv('MASSIVE_BASE_URL', 'https://proxy.example.test')
    monkeypatch.setenv('MASSIVE_API_KEY', 'fixture')
    desk = desk_module()
    instrument = desk.read_instrument(None)
    assert instrument.vendor_symbols == {'massive': 'AAPL'}
    adapter = desk.build_feed(instrument)
    assert isinstance(adapter, MassiveQuoteAdapter)
    assert adapter.key.instrument_id == instrument.instrument_id
    # A missing tape is reported through the existing coverage API.
    planes = desk.build_analysis(instrument, None)
    assert 'indicators' in planes


def test_adapter_rejects_cleartext_wire_before_connecting():
    import pytest
    with pytest.raises(ValueError):
        MassiveQuoteAdapter(instrument_id=uuid4(), symbol='AAPL',
                            api_key='fixture', ws_url='ws://proxy.example.test/ws')


def test_mint_pairing_requires_existing_desk_but_not_tls_arguments(monkeypatch, tmp_path, capsys):
    import sys
    desk = desk_module()
    runtime = tmp_path / 'desk'
    runtime.mkdir()
    from gabfin.api.sessions import SessionStore
    store = SessionStore(runtime / 'sessions.sqlite', owner_id=uuid4(),
                         session_seconds=3600, pairing_seconds=900, max_failures=10)
    monkeypatch.setattr(sys, 'argv', ['desk-server.py', '--mint-pairing-code', '--runtime', str(runtime)])
    assert desk.main() == 0
    code = capsys.readouterr().out.strip()
    token, _ = store.issue_session(code)
    assert store.resolve(token)


def test_mint_missing_runtime_reports_safe_error_without_creating_desk(monkeypatch, tmp_path, capsys):
    import sys
    desk = desk_module()
    runtime = tmp_path / 'absent'
    monkeypatch.setattr(sys, 'argv', ['desk-server.py', '--mint-pairing-code',
                                    '--runtime', str(runtime), '--cert', 'unused', '--key', 'unused'])
    assert desk.main() == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert 'Traceback' not in captured.err
    assert 'session' in captured.err.lower()
    assert not runtime.exists()


def test_desk_ready_waits_for_bind_and_follows_server_exit():
    async def scenario():
        desk = desk_module()
        bound, exit_server = asyncio.Event(), asyncio.Event()
        notices = []
        class Server:
            started = False
            should_exit = False
            async def serve(self):
                await bound.wait()
                self.started = True
                await exit_server.wait()
        server = Server()
        task = asyncio.create_task(desk.run_http_server(server, lambda: notices.append('ready')))
        await asyncio.sleep(.03)
        assert notices == []
        bound.set()
        async with asyncio.timeout(1):
            while not notices:
                await asyncio.sleep(.01)
        exit_server.set()
        await asyncio.wait_for(task, 1)
        assert notices == ['ready']
    asyncio.run(scenario())


def test_desk_stop_requests_graceful_server_exit():
    async def scenario():
        desk = desk_module()
        stop = asyncio.Event()
        class Server:
            started = False
            should_exit = False
            closed = False
            async def serve(self):
                self.started = True
                while not self.should_exit:
                    await asyncio.sleep(.01)
                self.closed = True
        server = Server()
        await asyncio.wait_for(desk.run_http_server(server, stop.set, stop=stop), 1)
        assert server.closed
    asyncio.run(scenario())


def test_desk_failed_start_never_emits_ready():
    import pytest
    async def scenario():
        desk = desk_module()
        class Server:
            started = False
            should_exit = False
            async def serve(self):
                return
        notices = []
        with pytest.raises(RuntimeError, match='http_server_not_started'):
            await desk.run_http_server(Server(), lambda: notices.append('ready'))
        assert not notices
    asyncio.run(scenario())


def test_market_host_cli_no_longer_requires_futu_sdk():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-m', 'gabfin.market.host', '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert '--sdk-python' not in result.stdout
    assert '--opend-port' not in result.stdout


def test_adapter_close_does_not_cancel_in_progress_cleanup_twice():
    async def scenario():
        entered, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        class Wire:
            async def __aenter__(self):
                entered.set()
                await release.wait()
                return self
            async def __aexit__(self, *args):
                cleaning.set()
            async def recv(self):
                await asyncio.Event().wait()
            async def send(self, message):
                pass
        feed = MassiveQuoteAdapter(instrument_id=uuid4(), symbol='AAPL',
            config=MassiveConfig(base_url='https://proxy.example.test', api_key='fixture'),
            _connect=lambda url, key: Wire())
        starting = asyncio.create_task(feed.subscribe([feed.key]))
        await entered.wait()
        starting.cancel()
        await asyncio.gather(starting, return_exceptions=True)
        closing = asyncio.create_task(feed.close())
        await asyncio.sleep(0)
        release.set()
        await asyncio.wait_for(closing, 1)
        assert cleaning.is_set()
        assert feed.cleanup.release_confirmed
    asyncio.run(scenario())


def test_supervisor_owns_one_connection_and_verifies_release():
    async def scenario():
        identifier = uuid4()
        key = SubscriptionKey(instrument_id=identifier, channel='quote', timeframe=None)
        market = MarketCoordinator([identifier], source='massive', replay_capacity=10,
                                   max_bars=10, required_keys=[key])
        stop = asyncio.Event()
        wires = []
        class Wire:
            def __init__(self):
                self.frames = asyncio.Queue()
                self.closed = False
            async def send(self, message):
                await self.frames.put('{"status":"ok","message":"subscribed"}')
                await self.frames.put('{"ev":"Q","sym":"AAPL","bp":100,"t":1000}')
            async def recv(self):
                return await self.frames.get()
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                self.closed = True
        feeds = []
        def connect(url, key):
            wire = Wire()
            wires.append(wire)
            return wire
        def factory():
            feed = MassiveQuoteAdapter(instrument_id=identifier, symbol='AAPL',
                config=MassiveConfig(base_url='https://proxy.example.test', api_key='fixture'), _connect=connect)
            feeds.append(feed)
            return feed
        supervisor = FeedSupervisor(market, factory, [key], heartbeat_timeout=5,
                                    retry_delay=.01, backfill_timeout=1)
        task = asyncio.create_task(supervisor.run(stop, max_attempts=1))
        try:
            async with asyncio.timeout(2):
                while not feeds or feeds[0].stats['accepted'] != 1:
                    await asyncio.sleep(.01)
            stop.set()
            await task
            assert supervisor.last_error is None
            assert len(wires) == 1 and wires[0].closed
            assert feeds[0].cleanup.release_confirmed
        finally:
            stop.set()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())
