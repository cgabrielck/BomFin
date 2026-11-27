"""Private-stdio research fixture: real TLS, real harness, no provider network.

This fixture exists so the browser can drive the *whole* research
chain against a real server: real TLS, real session and CSRF, real
snapshot capture, real LangGraph orchestration, real harness verdicts
and a real durable store. Nothing here is stubbed out at the service
layer, and nothing here reaches a model provider.

Three properties make that claim checkable:

**No provider, no fake report.** The fixture supplies its own model
adapter. It is a local callable that answers with a report whose
findings cite evidence ids that really exist in the frozen snapshot,
because the adapter reads those ids out of the rendered prompt. When
the adapter cannot produce a valid report, the job fails with the
harness's own verdict. A fabricated "success" is impossible: the
adapter has to satisfy the same output schema and the same evidence
whitelist that a real provider would.

**The fixture owns its own data.** The tape, the quote, the account
and the risk limits are written into the fixture's own temporary
folder before the server starts. They are labelled `fixture`, they
are the only facts the snapshot can cite, and the account carries an
explicit equity balance so the portfolio role can be exercised. Every
figure is synthetic and says so.

**Absence stays absent.** A second fixture profile serves a stack with
no model and no capture source. The status route then answers
`configured: false` with a reason, the browser refuses to start a job,
and no report, snapshot or evidence appears anywhere. That is the
"unconfigured must not fake" case, and it needs a server that is
genuinely unconfigured rather than a mocked route.

Pairing codes travel only over the parent-owned pipe, exactly as in
`market-server.py`. There is no test-admin HTTP route.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from uuid import UUID, uuid4

import uvicorn

from gabfin.api.app import create_market_app
from gabfin.api.market_gateway import MarketGateway
from gabfin.api.sessions import SessionStore
from gabfin.contracts.events import QuoteMarketEvent
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.market.coordinator import MarketCoordinator
from gabfin.market.internal_stream import InternalMarketServer

#: The instruments the fixture serves. These are the same ids the front
#: end's candidate list already asks for, so the desk and the browser
#: agree on which instrument is AAPL.
IDS = {
    'AAPL': UUID('11111111-1111-4111-8111-111111111111'),
    'MSFT': UUID('22222222-2222-4222-8222-222222222222'),
    'NVDA': UUID('33333333-3333-4333-8333-333333333333'),
}

#: The symbol the fixture's research tape holds. One symbol only: a
#: research snapshot is about one instrument, and a tape that silently
#: served several would let a conclusion cite a history it never read.
RESEARCH_SYMBOL = 'AAPL'

#: The moment the fixture's own facts were true. Every fixture fact is
#: stamped at or before this moment, so a snapshot taken now is not
#: look-ahead relative to the fixture's own clock.
FIXTURE_AS_OF = datetime(2026, 11, 27, 21, 0, tzinfo=timezone.utc)

#: The venue the fixture tape claims. A named venue is what makes an
#: indicator computable; a fixture that claimed `unknown` would have no
#: indicators at all and could not exercise the technical role.
FIXTURE_VENUE = 'sip'

#: The model name the fixture reports. It names the fixture, so a reader
#: of the audit trail can tell at a glance that no real provider served
#: this run.
FIXTURE_MODEL = 'fixture-model-v1'


def emit(value):
    """One line of fixture output on stdout."""
    print(json.dumps(value), flush=True)


# --------------------------------------------------------------------------
# The fixture's own data
# --------------------------------------------------------------------------

def write_fixture_tape(root: Path, *, symbol: str = RESEARCH_SYMBOL, count: int = 60):
    """Write a deterministic tape the research capture can read.

    The bars are synthetic and follow a fixed rule, so the same tape
    produces the same indicators on every run. The venue is a named one
    because the technical role has to read real indicators, and a
    fixture that could not compute them would not test the technical
    role at all.
    """
    from gabfin.storage.manifest import write_manifest
    from gabfin.storage.tape import (
        build_manifest,
        manifest_path,
        new_series,
        write_partitions,
    )
    from gabfin.contracts.market import Timeframe, TimeUnit

    timeframe = Timeframe(count=1, unit=TimeUnit.TRADING_DAY)
    series = new_series(
        symbol,
        {'count': timeframe.count, 'unit': timeframe.unit.value},
        source='fixture',
        venue_coverage=FIXTURE_VENUE,
        adjustment='unadjusted',
        retention='rolling_2y',
    )
    start = FIXTURE_AS_OF - timedelta(days=count + 1)
    rows = []
    for index in range(count):
        close = Decimal('100') + Decimal((index * 7) % 23) - Decimal(11)
        rows.append({
            'event_at': start + timedelta(days=index),
            'open': close - Decimal('0.10'),
            'high': close + Decimal('1.50'),
            'low': close - Decimal('1.25'),
            'close': close,
            'volume': Decimal(1000 + index * 37),
        })
    written_at = FIXTURE_AS_OF - timedelta(days=1)
    written = write_partitions(root, series, rows, now=written_at)
    manifest = build_manifest(
        written.series, written.partitions, written_at=written_at)
    write_manifest(manifest_path(root, written.series), manifest)
    return manifest


def fixture_quote():
    """The quote the snapshot freezes. Synthetic and labelled."""
    return {
        'price': '210.00',
        'as_of': FIXTURE_AS_OF.isoformat().replace('+00:00', 'Z'),
        'source': 'fixture',
        'venue_coverage': FIXTURE_VENUE,
        'instrument_id': str(IDS[RESEARCH_SYMBOL]),
    }


def fixture_account():
    """The account the portfolio role reads.

    The equity balance is explicit and is the whole point: a snapshot
    without one makes the portfolio role fail, and the fixture needs to
    be able to exercise the successful portfolio path as well as the
    failing one.
    """
    return {
        'equity': '100000.00',
        'as_of': FIXTURE_AS_OF.isoformat().replace('+00:00', 'Z'),
        'source': 'fixture',
        'account_kind': 'fixture-paper',
        'position_count': 2,
        'max_weight': '0.25',
    }


def fixture_limits():
    """The risk limits the portfolio role reads."""
    return {
        'per_trade_risk': '0.01',
        'daily_loss': '0.02',
        'max_gross_exposure': '1.0',
        'source': 'fixture',
    }


def fixture_observations(as_of: datetime):
    """Macro observations that were released before the cutoff.

    Each row carries an explicit release date, because the builder
    refuses an observation without one. The rows are synthetic and say
    so in their text.
    """
    return [
        {
            'series_id': 'FIXTURE_CPI',
            'date': '2026-10-01',
            'value': '310.5',
            'release_date': '2026-11-20',
            'text': 'FIXTURE_CPI, period 2026-10-01, value 310.5, released 2026-11-20',
        },
        {
            'series_id': 'FIXTURE_CPI',
            'date': '2026-11-01',
            'value': '311.25',
            'release_date': '2026-11-26',
            'text': 'FIXTURE_CPI, period 2026-11-01, value 311.25, released 2026-11-26',
        },
    ]


# --------------------------------------------------------------------------
# The fixture model
# --------------------------------------------------------------------------

class FixtureModel:
    """A model adapter that answers from the prompt it was given.

    This is not a stub of the service: the runtime, the harness, the
    output schema validation and the evidence whitelist all run exactly
    as they do for a real provider. The adapter only replaces the
    network call.

    It reads the evidence ids out of the rendered user prompt and
    cites them, so a finding points at a fact the snapshot really
    holds. If the prompt carries no evidence id at all, the adapter
    cannot produce a finding, and it says so in `missing_data` instead
    of inventing one. That is what keeps the fixture honest: the
    evidence check in the harness has something real to check.
    """

    def __init__(self, *, model_version: str = FIXTURE_MODEL):
        self._model_version = model_version

    async def __call__(self, request, dispatch):
        """Answer one research turn.

        `request` is a `ModelRequest`; `dispatch` is the runtime's
        guarded tool callback. The fixture calls the tools it was
        given so the tool whitelist and the tool-call accounting are
        exercised on the real path.
        """
        from gabfin.research.model import ROLE_TOOLS
        from gabfin.research.nodes import ModelReply

        # The role's tool list is application-owned, not prompt-owned.
        # The fixture asks for the tools the role is allowed to use, and
        # every call goes through the runtime's own dispatcher, so a
        # forbidden tool would still be refused and a denied tool would
        # still be recorded by the harness.
        for name in ROLE_TOOLS.get(request.role, ()):
            try:
                await dispatch(name, {})
            except Exception:
                # A refused tool is a fact, not a reason to fail the
                # whole turn: the harness records it.
                pass

        evidence = _evidence_ids(request.user)
        text = request.user
        if not evidence:
            # Nothing citable was offered, so the honest answer is that
            # the data is missing. A finding without an evidence id would
            # be refused by the harness anyway.
            return ModelReply(
                {
                    'role': request.role,
                    'snapshot_id': _snapshot_id(text),
                    'findings': [],
                    'missing_data': ['fixture: no evidence id was available to cite'],
                },
                0, 0, self._model_version)

        return ModelReply(
            {
                'role': request.role,
                'snapshot_id': _snapshot_id(text),
                'findings': [
                    {
                        'text': f'fixture {request.role} finding over the frozen snapshot',
                        'evidence_id': evidence[0],
                    },
                ],
                'missing_data': [],
            },
            0, 0, self._model_version)


def _evidence_ids(prompt: str) -> list[str]:
    """Every evidence id the rendered prompt offers.

    The prompt is the adapter's only view of the snapshot, so this is
    the only place it can learn which evidence exists. Reading it out
    of the prompt is what makes the cited id real rather than invented.
    The snapshot id itself is excluded: it identifies the snapshot, not
    a fact inside it.
    """
    import re

    pattern = (r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
               r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b')
    snapshot = _snapshot_id(prompt)
    seen: list[str] = []
    for item in re.findall(pattern, prompt):
        if item == snapshot or item in seen:
            continue
        seen.append(item)
    return seen


def _snapshot_id(prompt: str) -> str:
    """The snapshot id the rendered prompt names.

    It is read from the line the prompt leads with, so the adapter
    never has to guess which of the many ids in the prompt is the one
    the output has to answer.
    """
    import re

    for line in prompt.splitlines():
        match = re.search(
            r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
            r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b',
            line,
        )
        if match:
            return match.group(0)
    return ''


# --------------------------------------------------------------------------
# The research stack
# --------------------------------------------------------------------------

def build_research_jobs(folder: Path, *, tape_root: Path, instrument_ids,
                       configured: bool = True, history_symbol: str | None = None):
    """The real research stack: store, capture, service and job queue.

    Everything here is the production class. The only substituted part
    is the model adapter, and the substituted part is the network call.
    The capture reads the fixture's own tape, the store is the real
    `ResearchStore`, and the queue is the real `ResearchJobs`.

    When `configured` is False the queue is built without a model and
    without a capture source. That is a genuinely unconfigured stack,
    not a mocked route: the real `ResearchJobs` then reports
    `configured: false` with the reason it gives, and the browser
    refuses to start a job because the server really cannot run one.

    `history_symbol` names the symbol the tape actually holds. When it
    is a symbol the tape never wrote, the capture refuses the request
    and the job fails for real, which is the failure path the browser
    has to survive.
    """
    from gabfin.contracts.market import Timeframe, TimeUnit
    from gabfin.research.capture import SnapshotCapture
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.service import ResearchService
    from gabfin.research.store import ResearchStore

    store = ResearchStore(folder / 'research.sqlite')
    bars = (_FixtureBars(tape_root) if history_symbol is None
            else _MissingHistoryBars(tape_root, history_symbol))
    capture = SnapshotCapture(
        store,
        bars=bars,
        observations=fixture_observations,
        quote=fixture_quote,
        account=fixture_account,
        limits=fixture_limits,
    )
    service = ResearchService(
        store,
        model=FixtureModel(),
        roles_dir=REPO / 'config' / 'agents',
        schema_dir=REPO / 'schemas' / 'research',
    )

    def freeze(instrument_id: UUID, as_of: datetime):
        """Freeze one snapshot at the server's own cutoff."""
        symbol = _symbol_of(instrument_id)
        outcome = capture.capture(
            instrument_id=instrument_id,
            symbol=symbol,
            timeframe=Timeframe(count=1, unit=TimeUnit.TRADING_DAY),
            as_of=as_of,
        )
        return outcome['snapshot_id']

    return ResearchJobs(
        store=store,
        # An unconfigured stack has no model and no capture source. The
        # real `ResearchJobs` then reports the reason itself, and the
        # routes refuse to start a job.
        service=service if configured else None,
        capture=freeze if configured else None,
        instrument_ids=instrument_ids,
        roles_dir=REPO / 'config' / 'agents',
        schema_dir=REPO / 'schemas' / 'research',
        db_path=folder / 'research-jobs.sqlite',
        # The research clock is pinned to the fixture's own moment, not
        # to the wall clock. The fixture's facts are stamped at that
        # moment, and a snapshot taken "now" would be looking at facts
        # from the future whenever the machine's clock is earlier than
        # the fixture's moment. Pinning the clock keeps the capture
        # honest and keeps every run reproducible.
        clock=lambda: FIXTURE_AS_OF,
    )


class _FixtureBars:
    """The tape's bars, read through the real `TapeBarSource`.

    The source is the production one; only the root is the fixture's
    own folder. The coverage is read the same way, so the capture
    computes real indicators over real stored bars.
    """

    def __init__(self, root: Path):
        from gabfin.analysis.sources import TapeBarSource

        self._source = TapeBarSource(root, symbol=RESEARCH_SYMBOL, source='fixture')

    def bars(self, instrument_id, timeframe):
        return self._source.bars(instrument_id, timeframe)

    def coverage_of(self, timeframe):
        return self._source.coverage_of(timeframe)


class _MissingHistoryBars:
    """A tape that never held this instrument's series.

    The capture refuses a series that was never written, because an
    empty history looks like a market with no bars. That refusal is the
    failure the browser has to survive: the job fails, and the failure
    says so instead of producing a conclusion.
    """

    def __init__(self, root: Path, symbol: str):
        from gabfin.analysis.sources import TapeBarSource

        self._source = TapeBarSource(root, symbol=symbol, source='fixture')

    def bars(self, instrument_id, timeframe):
        return self._source.bars(instrument_id, timeframe)

    def coverage_of(self, timeframe):
        return self._source.coverage_of(timeframe)


def _symbol_of(instrument_id: UUID) -> str:
    """The symbol an instrument id stands for."""
    for symbol, value in IDS.items():
        if value == instrument_id:
            return symbol
    return RESEARCH_SYMBOL


#: The repository root, so the fixture reads the real role cards and the
#: real schemas rather than a copy that could drift.
REPO = Path(__file__).resolve().parents[3]


def analysis_planes(now):
    """The same deterministic analysis planes the market fixture serves.

    They are copied rather than imported so this fixture stays a
    standalone file, and they are identical in behaviour: the
    indicator plane computes from a fixed run of bars, the macro plane
    returns observations with the release dates they really have, and
    the capability plane reports the fixture feed exactly as it is.
    Nothing reaches the network.
    """
    from decimal import Decimal

    from gabfin.analysis.plane import CapabilityPlane, IndicatorPlane, MacroPlane
    from gabfin.contracts.market import Timeframe, TimeUnit
    from gabfin.contracts.subscriptions import FeedCapabilities
    from gabfin.indicators.inputs import PriceBar

    timeframe = Timeframe(count=1, unit=TimeUnit.TRADING_DAY)

    class FixtureBars:
        def bars(self, instrument_id, requested):
            if requested != timeframe:
                return ()
            start = datetime(2026, 1, 1, tzinfo=timezone.utc)
            result = []
            for index in range(40):
                close = Decimal('100') + Decimal((index * 7) % 23) - Decimal(11)
                result.append(PriceBar(
                    event_at=start + timedelta(days=index),
                    open=close - Decimal('0.10'),
                    high=close + Decimal('1.50'),
                    low=close - Decimal('1.25'),
                    close=close,
                    volume=Decimal(1000 + index * 37),
                ))
            return tuple(result)

    class FixtureMacro:
        def observations(self, series_id):
            return [
                {'date': '2026-01-02', 'value': '4.00', 'realtime_start': '2026-01-02'},
                {'date': '2026-02-02', 'value': '4.15', 'realtime_start': '2026-02-02'},
            ]

    def capabilities():
        return (FeedCapabilities(
            schema_version='1.0', source='fixture', asset_classes=('equity',),
            sessions=('regular',), latency_label='delayed', max_subscriptions=None,
            history_limits=(), checked_at=now(), permission_errors=(), sequence_rules=(),
            venue_coverage='sip', realtime=False, delay_minutes=15,
            tradable_for_entry=False, depth_levels=None, fee_class='none',
            unavailable_reason=None),)

    return {
        'indicators': IndicatorPlane(FixtureBars(), source_coverage='sip'),
        'macro': MacroPlane(FixtureMacro(), clock=now),
        'capabilities': CapabilityPlane(capabilities),
    }


# --------------------------------------------------------------------------
# The server
# --------------------------------------------------------------------------

async def run(args, folder: Path):
    offset = [0]

    def now():
        return datetime.now(timezone.utc) + timedelta(seconds=offset[0])

    store = SessionStore(folder / 'sessions.sqlite', owner_id=uuid4(),
                         session_seconds=300, pairing_seconds=60,
                         max_failures=10, clock=now)
    keys = [SubscriptionKey(instrument_id=value, channel='quote', timeframe=None)
            for value in IDS.values()]

    def new_market():
        return MarketCoordinator(IDS.values(), source='fixture',
                                 replay_capacity=100, max_bars=50, clock=now,
                                 required_keys=keys)

    market = new_market()

    def publish(symbol, price):
        stamp = now()
        event = stamp - timedelta(seconds=2)
        from hashlib import sha256
        from uuid import NAMESPACE_URL, uuid5
        digest = sha256(f'{symbol}|{event.isoformat()}|{price}'.encode()).hexdigest()
        key = 'fixture:quote:' + digest
        quote = QuoteMarketEvent(
            schema_version='1.0', kind='quote', event_id=uuid5(NAMESPACE_URL, key),
            instrument_id=IDS[symbol], event_at=event, received_at=stamp,
            available_at=stamp, source='fixture', source_seq=None, dedup_key=key,
            payload=dict(schema_version='1.0', instrument_id=IDS[symbol], as_of=stamp,
                         feed='fixture', session='unknown', bid=None, ask=None,
                         last=dict(price=price, event_at=event, received_at=stamp,
                                   available_at=stamp, age_ms=2000),
                         quality=['unknown', 'incomplete'],
                         entitlements=dict(status='unknown', checked_at=None)))
        market.apply(quote)

    def seed():
        market.heartbeat(now())
        for symbol, price in [('AAPL', '210.00'), ('MSFT', '420.00'), ('NVDA', '140.00')]:
            publish(symbol, price)
        market.recover_latest_quotes()

    seed()
    internal = InternalMarketServer(market, store)
    await internal.start()
    gateway = MarketGateway.from_store(
        host=internal.address[0], port=internal.address[1], store=store,
        registered_keys=keys, source='fixture')

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    origin = f'https://127.0.0.1:{listener.getsockname()[1]}'

    # The research stack. The unconfigured profile serves a stack with no
    # model and no capture source, so the status route answers
    # `configured: false` and the browser cannot start a job. The routes
    # are mounted in both profiles: a browser must be able to ask
    # whether research can run, and it must be able to ask even when
    # the answer is no.
    tape_root = folder / 'tape'
    tape_root.mkdir(parents=True, exist_ok=True)
    write_fixture_tape(tape_root)
    jobs = build_research_jobs(
        folder, tape_root=tape_root, instrument_ids=tuple(IDS.values()),
        configured=not args.unconfigured,
        history_symbol='NOT_TAPED' if args.no_history else None)

    app = create_market_app(store, allowed_origin=origin, gateway=gateway,
                             static_dir=args.dist, analysis=analysis_planes(now),
                             research={'jobs': jobs})

    server = uvicorn.Server(uvicorn.Config(
        app, host='127.0.0.1', log_config=None, access_log=False,
        log_level='critical', proxy_headers=False,
        ssl_certfile=str(folder / 'cert.pem'), ssl_keyfile=str(folder / 'key.pem'),
        ws_max_size=16384, limit_concurrency=32))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(15):
            while not server.started:
                if serving.done():
                    await serving
                    raise RuntimeError('TLS fixture failed')
                await asyncio.sleep(.01)
        loop = asyncio.get_running_loop()

        async def command(line):
            nonlocal market, internal
            item = None
            try:
                item = json.loads(line)
                action = item['action']
                result = {}
                if action == 'pair':
                    result = {'code': store.create_pairing()}
                elif action == 'price':
                    publish(item['symbol'], item['price'])
                elif action == 'expire':
                    offset[0] += 301
                elif action == 'heartbeat':
                    market.heartbeat(now())
                elif action == 'stop':
                    server.should_exit = True
                elif action == 'checks':
                    # The durable audit trail, read straight from the
                    # research store. The browser never sees a snapshot
                    # context; the audit verdicts are what a reader is
                    # allowed to see.
                    result = {'checks': _checks_for(jobs, item.get('snapshot_id'))}
                else:
                    raise ValueError('Invalid private command')
                emit({'id': item['id'], 'ok': True, **result})
            except Exception:
                emit({'id': item.get('id') if isinstance(item, dict) else None,
                      'ok': False})

        def controls():
            for line in sys.stdin:
                asyncio.run_coroutine_threadsafe(command(line), loop)
            loop.call_soon_threadsafe(setattr, server, 'should_exit', True)

        threading.Thread(target=controls, daemon=True).start()
        emit({'kind': 'ready', 'origin': origin,
              'configured': jobs.configured,
              'model': FIXTURE_MODEL if jobs.configured else None})
        await serving
    finally:
        server.should_exit = True
        await asyncio.gather(serving, return_exceptions=True)
        await jobs.shutdown()
        await internal.close()
        listener.close()


def _checks_for(jobs, snapshot_id):
    """The audit verdicts for one snapshot, as plain JSON."""
    if jobs is None or not snapshot_id:
        return []
    try:
        return jobs.checks_for(UUID(str(snapshot_id)))
    except Exception:
        return []


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--openssl', type=Path, required=True)
    parser.add_argument('--unconfigured', action='store_true',
                        help='Serve a research stack with no model and no capture source')
    parser.add_argument('--no-history', action='store_true',
                        help='Serve a stack whose tape never held the requested series')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='gabfin-research-fixture-') as temp:
        folder = Path(temp)
        subprocess.run([str(args.openssl), 'req', '-x509', '-newkey', 'rsa:2048',
                        '-nodes', '-days', '1', '-subj', '/CN=localhost',
                        '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1',
                        '-keyout', str(folder / 'key.pem'), '-out', str(folder / 'cert.pem')],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        asyncio.run(run(args, folder))
