"""Run the real GabFin desk locally: Massive quotes, the market engine, and the API.

This is the operator entry point. It starts one process that owns the
whole chain:

    Massive WebSocket (read-only quotes)
      -> MarketCoordinator (bounded state, gaps, cursors)
      -> InternalMarketServer (authenticated loopback stream)
      -> MarketGateway (server-owned read leases)
      -> FastAPI over TLS (pairing, market, analysis) + the built front end

The web front end is served by this process when `apps/desk-web/dist`
exists, so the desk and its API share one origin. That matters: the
browser refuses server mode over plain HTTP, and the session guard
requires the exact origin.

Four rules this launcher keeps:

- It subscribes to quotes only and never sends an order. The API exposes
  no trading route.
- A pairing code is printed once, to the console, and never written to
  a file or a log.
- Missing optional inputs (a tape, a FRED key) degrade one plane and
  leave the rest working. They never stop the market feed.
- A feed that was not measured is not reported. The capability plane
  reports only what was probed.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

REPO = Path(__file__).resolve().parents[1]
if str(REPO / 'services') not in sys.path:
    sys.path.insert(0, str(REPO / 'services'))

from gabfin.api.app import create_market_app  # noqa: E402
from gabfin.api.market_gateway import MarketGateway  # noqa: E402
from gabfin.api.sessions import SessionStore  # noqa: E402
from gabfin.contracts.analysis import CapabilitiesResponse  # noqa: E402
from gabfin.contracts.market import Instrument  # noqa: E402
from gabfin.contracts.subscriptions import SubscriptionKey  # noqa: E402
from gabfin.market.coordinator import MarketCoordinator  # noqa: E402
from gabfin.market.host import serve_market  # noqa: E402
from gabfin.providers.massive.adapter import MassiveQuoteAdapter  # noqa: E402
from gabfin.providers.futu.symbols import InstrumentCatalog  # noqa: E402

#: The instrument the desk serves by default. The id is the one the
#: front end's candidate list already asks for, so the desk and the
#: browser agree on which instrument is AAPL.
DEFAULT_INSTRUMENT = {
    'schema_version': '1.0',
    'instrument_id': '11111111-1111-4111-8111-111111111111',
    'asset_class': 'equity',
    'vendor_symbols': {'massive': 'AAPL'},
    'currency': 'USD',
    'tick_size': '0.01',
    'lot_size': '1',
    'option': None,
}


def emit(payload: dict) -> None:
    """One line of operator output. Nothing secret goes through here."""
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def read_instrument(path: Path | None) -> Instrument:
    """The canonical instrument this desk serves."""
    if path is None:
        return Instrument.model_validate(DEFAULT_INSTRUMENT)
    return Instrument.model_validate_json(path.read_text(encoding='utf-8'))


class MeasuredCapabilities:
    """A capability plane over one already-measured snapshot.

    The capability plane reports only what was probed. A feed that was
    never probed is absent from the list, so "we do not know" never
    looks like "we checked and it is fine".
    """

    def __init__(self, capabilities):
        self._capabilities = capabilities

    def snapshot(self) -> CapabilitiesResponse:
        return CapabilitiesResponse(
            schema_version='1.0', checked_at=self._capabilities.checked_at,
            sources=(self._capabilities,))


def build_analysis(instrument: Instrument, tape_root: Path | None):
    """The three analysis planes, wired to whatever this build actually has.

    A plane that cannot answer says so. An absent tape or an absent
    FRED key must not look like a source with no data, and it must
    never stop the market feed from running.
    """
    from gabfin.analysis.plane import CapabilityPlane, IndicatorPlane, MacroPlane

    planes: dict[str, object] = {}

    if tape_root is not None and tape_root.exists():
        from gabfin.analysis.runtime import InstrumentResolver, TapeHistory

        catalog = InstrumentCatalog([instrument])
        resolver = InstrumentResolver(catalog, namespace='massive')
        history = TapeHistory(tape_root, resolver, namespace='massive')
        planes['indicators'] = IndicatorPlane(
            history,
            coverage_resolver=lambda instrument_id, timeframe: history.coverage(
                instrument_id, timeframe),
        )
    else:
        # No tape means no history. The route answers "missing", which is
        # what the reader needs to hear: there is nothing to compute on.
        class _NoHistory:
            def bars(self, instrument_id, timeframe):
                return ()

            def coverage(self, instrument_id, timeframe):
                return 'unknown'

        planes['indicators'] = IndicatorPlane(_NoHistory(), source_coverage='unknown')

    macro_client = None
    try:
        from gabfin.providers.fred.client import FredClient

        candidate = FredClient(transport=_fred_transport())
        if candidate.configured:
            macro_client = candidate
    except Exception:
        macro_client = None

    if macro_client is not None:
        from gabfin.analysis.sources import FredMacroSource
        planes['macro'] = MacroPlane(FredMacroSource(macro_client))
    else:
        class _NoMacro:
            def observations(self, series_id):
                raise RuntimeError('macro_key_missing')

        planes['macro'] = MacroPlane(_NoMacro())

    planes['capabilities'] = CapabilityPlane(lambda: ())

    return planes


def build_research(instrument: Instrument, runtime: Path, tape_root: Path | None,
                   *, directory=None, history=None):
    """Always expose research readiness; only configured models can run jobs."""
    from pydantic import ValidationError
    from gabfin.research.jobs import ResearchJobs
    from gabfin.research.service import configured_service
    from gabfin.research.store import ResearchStore

    db = runtime / 'research.sqlite'
    research_store = ResearchStore(db)
    try:
        service = configured_service(research_store, roles_dir=REPO / 'config/agents',
                                     schema_dir=REPO / 'schemas/research')
    except ValidationError:
        service = None
    capture = build_capture(instrument, db, tape_root)
    if directory is not None:
        from gabfin.research.directory_capture import DirectoryCapture
        capture = DirectoryCapture(directory, research_store, tape_root or runtime / 'research-tape', history=history)
    jobs = ResearchJobs(store=research_store, service=service,
                        capture=capture, instrument_directory=directory,
                        instrument_ids=[instrument.instrument_id], db_path=db)
    return {'jobs': jobs}


def build_capture(instrument: Instrument, research_db: Path, tape_root: Path | None):
    """Bind snapshots to server-owned instrument metadata and local history."""
    from datetime import datetime, timezone
    from gabfin.analysis.sources import TapeBarSource
    from gabfin.contracts.market import Timeframe, TimeUnit
    from gabfin.research.capture import SnapshotCapture
    from gabfin.research.store import ResearchStore

    research_store = ResearchStore(research_db)
    symbol = instrument.vendor_symbols.get('massive')

    def capture(instrument_id, *, as_of=None):
        if instrument_id != instrument.instrument_id:
            raise ValueError('Unregistered research instrument')
        if tape_root is None:
            raise ValueError('Research history tape is unavailable')
        source = TapeBarSource(tape_root, symbol=symbol, source='massive')
        result = SnapshotCapture(research_store, bars=source).capture(
            instrument_id=instrument_id, symbol=symbol,
            timeframe=Timeframe(count=1, unit=TimeUnit.TRADING_DAY),
            as_of=as_of or datetime.now(timezone.utc))
        return result['snapshot_id']

    return capture


def _fred_transport():
    """The FRED transport, if the machine can make an HTTPS request.

    The key is in the query string because FRED requires it, so the
    transport is the one place that must never echo a URL.
    """
    import urllib.request

    from gabfin.providers.fred.client import Request, Response

    def transport(request: Request) -> Response:
        try:
            with urllib.request.urlopen(request.url, timeout=10) as handle:
                return Response(status=handle.status,
                                body=handle.read().decode('utf-8', 'replace'))
        except urllib.error.HTTPError as error:
            return Response(status=error.code,
                            body=error.read().decode('utf-8', 'replace'))
        except Exception:
            # The URL carries the key, so an exception that quotes it
            # would leak it. The client rebuilds the message from the
            # series and the error type, so nothing is echoed here.
            raise

    return transport


def build_feed(instrument: Instrument):
    symbol = instrument.vendor_symbols.get('massive')
    if instrument.asset_class != 'equity' or not symbol:
        raise ValueError('Massive equity symbol required')
    return MassiveQuoteAdapter(instrument_id=instrument.instrument_id, symbol=symbol)


async def run_http_server(server, on_ready, *, stop=None):
    """Publish readiness after bind and follow Uvicorn's own signal lifecycle."""
    serving = asyncio.create_task(server.serve())
    stopping = asyncio.create_task(stop.wait()) if stop is not None else None
    try:
        async with asyncio.timeout(30):
            while not server.started:
                if serving.done():
                    await serving
                    raise RuntimeError('http_server_not_started')
                await asyncio.sleep(.01)
        on_ready()
        if stopping is None:
            await serving
        else:
            await asyncio.wait((serving, stopping), return_when=asyncio.FIRST_COMPLETED)
    finally:
        server.should_exit = True
        if stopping is not None:
            stopping.cancel()
            await asyncio.gather(stopping, return_exceptions=True)
        try:
            await asyncio.wait_for(asyncio.shield(serving), timeout=10)
        except TimeoutError:
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)
            raise RuntimeError('http_server_shutdown_timeout') from None


@asynccontextmanager
async def offline_market(market, sessions):
    """Serve an honest disconnected desk without acquiring a provider connection."""
    from gabfin.market.internal_stream import InternalMarketServer
    listener = InternalMarketServer(market, sessions, host='127.0.0.1', port=0)
    await listener.start()
    try:
        yield listener.address
    finally:
        await listener.close()


async def serve(args) -> int:
    instrument = read_instrument(args.instrument)
    # This host serves quotes; REST history is wired separately from live keys.
    keys = [
        SubscriptionKey(instrument_id=instrument.instrument_id, channel='quote',
                        timeframe=None),
    ]

    runtime = Path(args.runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    store = SessionStore(runtime / 'sessions.sqlite', owner_id=runtime_owner(runtime),
                         session_seconds=args.session_seconds,
                         pairing_seconds=args.pairing_seconds, max_failures=10)

    market = MarketCoordinator([instrument.instrument_id], source='massive',
                                replay_capacity=1000, max_bars=500,
                                required_keys=keys)

    def factory():
        return build_feed(instrument)

    # The probe is a separate adapter so that a failed probe is a
    # reported fact rather than a silent empty feed.
    probe = None if args.offline else factory()
    capabilities = None
    try:
        if probe is None:
            raise RuntimeError('offline_mode')
        capabilities = await probe.capabilities()
        emit({'kind': 'capabilities', 'source': 'massive',
              'entitlement': 'unverified',
              'max_subscriptions': capabilities.max_subscriptions,
              'permission_errors': list(capabilities.permission_errors)})
    except Exception as error:
        emit({'kind': 'capabilities', 'source': 'massive',
              'error': type(error).__name__})
    finally:
        try:
            if probe is not None:
                await probe.close()
        except Exception:
            emit({'kind': 'notice', 'message': 'Capability probe cleanup failed'})

    from gabfin.storage.events import EventLedger
    ledger = EventLedger(runtime / 'market-events.sqlite')
    market_context = (offline_market(market, store) if args.offline else
        serve_market(market, store, factory, keys,
                     heartbeat_timeout=25, retry_delay=2, backfill_timeout=20,
                     host='127.0.0.1', port=0, event_sink=ledger.append))
    async with market_context as address:
        gateway = MarketGateway.from_store(
            host=address[0], port=address[1], store=store,
            registered_keys=keys, source='massive')

        planes = build_analysis(instrument, Path(args.tape) if args.tape else None)
        planes['capabilities'] = (MeasuredCapabilities(capabilities)
                                  if capabilities is not None
                                  else MeasuredCapabilities(_no_capabilities()))

        origin = f'https://{args.host}:{args.port}'
        static_dir = Path(args.dist) if args.dist else None
        if static_dir is not None and not static_dir.exists():
            emit({'kind': 'notice', 'message':
                  'The front end is not built; run npm.cmd run build'})
            static_dir = None
        from gabfin.universe.store import CandidateStore
        from gabfin.universe.directory import InstrumentDirectory
        reference = history = None
        if not args.offline:
            from gabfin.providers.massive.config import load_config
            from gabfin.providers.massive.rest import MassiveRestClient
            from gabfin.providers.massive.reference import MassiveReference
            from gabfin.providers.massive.history import MassiveHistory
            client = MassiveRestClient(load_config())
            reference, history = MassiveReference(client), MassiveHistory(client)
        directory = InstrumentDirectory(runtime / 'instruments.sqlite',
                                        lookup=reference.lookup if reference else None)
        directory.seed(instrument.vendor_symbols['massive'], instrument.instrument_id)
        universe = {'candidates': CandidateStore(runtime / 'candidates.sqlite'),
                    'lookup': directory.resolve, 'directory': directory}
        app = create_market_app(store, allowed_origin=origin, gateway=gateway,
                                static_dir=static_dir, analysis=planes, universe=universe,
                                research=build_research(instrument, runtime,
                                    Path(args.tape) if args.tape else None,
                                    directory=directory, history=history))

        import uvicorn

        config = uvicorn.Config(app, host=args.host, port=args.port,
                                 log_config=None, access_log=False,
                                 log_level='warning', proxy_headers=False,
                                 ssl_certfile=str(Path(args.cert)),
                                 ssl_keyfile=str(Path(args.key)),
                                 ws_max_size=16384, limit_concurrency=32,
                                 timeout_graceful_shutdown=5)
        server = uvicorn.Server(config)

        def ready():
            pairing_code = store.create_pairing()
            emit({'kind': 'ready', 'origin': origin,
                  'internal': f'{address[0]}:{address[1]}',
                  'instrument_id': str(instrument.instrument_id),
                  'pairing_code': pairing_code,
                  'pairing_expires_in_seconds': args.pairing_seconds,
                  'serving_front_end': static_dir is not None})

        await run_http_server(server, ready)
    return 0


def _no_capabilities():
    """A capability snapshot for a feed that was never measured."""
    from datetime import datetime, timezone

    from gabfin.contracts.subscriptions import FeedCapabilities

    return FeedCapabilities(
        schema_version='1.0', source='massive', asset_classes=('equity',),
        sessions=(), latency_label='unknown', max_subscriptions=None,
        history_limits=(), checked_at=datetime.now(timezone.utc),
        permission_errors=('capability_probe_failed',))


def runtime_owner(runtime: Path) -> UUID:
    """A stable local owner preserves report ownership across desk restarts."""
    runtime.mkdir(parents=True, exist_ok=True)
    owner_file = runtime / 'owner-id'
    try:
        with owner_file.open('x', encoding='ascii') as handle:
            owner = uuid4()
            handle.write(str(owner))
            return owner
    except FileExistsError:
        return UUID(owner_file.read_text(encoding='ascii').strip())


def mint_pairing_code(runtime: Path, *, pairing_seconds: int) -> str:
    """Print a fresh pairing code for a running desk.

    A pairing code is single-use, so a desk that has already paired
    needs a new one. The session store is a file, so a second process
    can issue a code without disturbing the running feed. The code goes
    to the console and nowhere else.
    """
    from gabfin.api.sessions import SessionStore

    if not (runtime / 'sessions.sqlite').is_file():
        raise ValueError('Existing desk session database required')
    store = SessionStore(runtime / 'sessions.sqlite', owner_id=runtime_owner(runtime),
                         session_seconds=3600, pairing_seconds=pairing_seconds,
                         max_failures=10)
    return store.create_pairing()


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Run the GabFin desk: Massive quotes, the market engine, and the API')
    parser.add_argument('--instrument', type=Path,
                        help='Canonical Instrument JSON; AAPL is used without it')
    parser.add_argument('--runtime', default=str(REPO / 'runtime'),
                        help='Where the session database lives')
    parser.add_argument('--tape',
                        help='The tape root the indicator plane reads')
    parser.add_argument('--dist', default=str(REPO / 'apps/desk-web/dist'),
                        help='The built front end to serve')
    parser.add_argument('--cert', help='The TLS certificate (required to serve)')
    parser.add_argument('--key', help='The TLS private key (required to serve)')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=19443)
    parser.add_argument('--offline', action='store_true',
                        help='Serve the desk without opening any provider connection')
    parser.add_argument('--session-seconds', type=int, default=3600)
    parser.add_argument('--pairing-seconds', type=int, default=900)
    parser.add_argument('--mint-pairing-code', action='store_true',
                        help='Print a fresh pairing code for a running desk and exit')
    args = parser.parse_args()

    if args.mint_pairing_code:
        try:
            code = mint_pairing_code(Path(args.runtime).resolve(),
                                     pairing_seconds=args.pairing_seconds)
        except Exception:
            print('Cannot mint pairing code: existing desk session database required and must be accessible',
                  file=sys.stderr)
            return 2
        print(code)
        return 0

    if args.cert is None or args.key is None:
        parser.error('--cert and --key are required to serve the TLS desk')
    for label, path in (('certificate', args.cert), ('private key', args.key)):
        if not Path(path).exists():
            print(f'The {label} does not exist: {path}', file=sys.stderr)
            return 2
    try:
        return asyncio.run(serve(args))
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        print(f'desk_server_failed: {type(error).__name__}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
