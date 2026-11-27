"""The desk binds research to its registered instrument and local tape."""
import importlib.util
from pathlib import Path
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[2]
ID = UUID('11111111-1111-4111-8111-111111111111')


def launcher():
    spec = importlib.util.spec_from_file_location('desk_server', ROOT / 'scripts/desk-server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_directory_wiring_accepts_resolved_non_seed_symbol(tmp_path, monkeypatch):
    from gabfin.universe.directory import InstrumentDirectory
    from uuid import uuid4
    for name in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL'):
        monkeypatch.delenv(name, raising=False)
    desk = launcher()
    directory = InstrumentDirectory(tmp_path / 'symbols.sqlite')
    identity = uuid4()
    directory.seed('MSFT', identity)
    jobs = desk.build_research(desk.read_instrument(None), tmp_path, None, directory=directory)['jobs']
    assert str(identity) in jobs.instrument_ids
    assert jobs.capture.directory is directory


def test_desk_research_is_explicitly_unconfigured_without_model(tmp_path, monkeypatch):
    for name in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL'):
        monkeypatch.delenv(name, raising=False)
    desk = launcher()
    wiring = desk.build_research(desk.read_instrument(None), tmp_path, None)
    assert wiring['jobs'].configured is False


def test_model_configuration_wires_service_without_making_requests(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'fixture-key')
    monkeypatch.setenv('LLM_BASE_URL', 'https://example.test/v1')
    monkeypatch.setenv('LLM_MODEL', 'fixture-model')
    desk = launcher()
    jobs = desk.build_research(desk.read_instrument(None), tmp_path, None)['jobs']
    assert jobs.configured
    assert jobs.service.model.config.model == 'fixture-model'


def test_desk_capture_refuses_missing_tape_instead_of_making_history(tmp_path):
    desk = launcher()
    capture = desk.build_capture(desk.read_instrument(None), tmp_path / 'research.sqlite', None)
    with pytest.raises(ValueError, match='history|tape|series'):
        capture(ID)


def test_owner_identity_is_stable_across_restarts_and_code_minting(tmp_path):
    desk = launcher()
    first = desk.runtime_owner(tmp_path)
    assert desk.runtime_owner(tmp_path) == first
    assert isinstance(first, UUID)


def test_desk_capture_registers_real_local_tape_and_keeps_unknown_coverage(tmp_path):
    from datetime import datetime, timezone
    from gabfin.storage.tape import new_series, write_partitions, build_manifest, manifest_path
    from gabfin.storage.manifest import write_manifest
    from gabfin.research.store import ResearchStore
    now = datetime.now(timezone.utc)
    source = new_series('AAPL', {'count': 1, 'unit': 'trading_day'}, source='massive',
                        venue_coverage='unknown', adjustment='unadjusted', retention='rolling_2y')
    tape = tmp_path / 'tape'
    written = write_partitions(tape, source, [dict(event_at=now.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        open=100, high=102, low=99, close=101, volume=1000)], now=now)
    write_manifest(manifest_path(tape, written.series), build_manifest(written.series, written.partitions, written_at=now))
    desk = launcher()
    db = tmp_path / 'research.sqlite'
    snapshot_id = desk.build_capture(desk.read_instrument(None), db, tape)(ID, as_of=now)
    snapshot = ResearchStore(db).get_snapshot(snapshot_id)
    assert snapshot['context']['source_coverage'] == 'unknown'
    assert 'source_coverage_unknown' in snapshot['data_quality']
    assert snapshot['context']['account'] is None


def test_offline_market_starts_internal_listener_without_provider(tmp_path):
    import asyncio
    from uuid import uuid4
    from gabfin.api.sessions import SessionStore
    from gabfin.market.coordinator import MarketCoordinator
    desk = launcher()
    async def run():
        sessions = SessionStore(tmp_path / 'sessions.sqlite', owner_id=uuid4(),
            session_seconds=60, pairing_seconds=60, max_failures=5)
        market = MarketCoordinator([ID], source='massive', replay_capacity=10, max_bars=10)
        async with desk.offline_market(market, sessions) as address:
            assert address[0] == '127.0.0.1'
            assert address[1] > 0
    asyncio.run(run())


def test_desk_capture_refuses_an_unregistered_instrument(tmp_path):
    desk = launcher()
    capture = desk.build_capture(desk.read_instrument(None), tmp_path / 'research.sqlite', None)
    with pytest.raises((KeyError, ValueError)):
        capture(UUID('22222222-2222-4222-8222-222222222222'))
