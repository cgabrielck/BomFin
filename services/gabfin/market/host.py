"""Foreground quote-only market host. Importing this module starts nothing."""
import asyncio
from contextlib import asynccontextmanager
import json

from gabfin.market.internal_stream import InternalMarketServer
from gabfin.market.supervisor import FeedSupervisor


@asynccontextmanager
async def serve_market(market, sessions, factory, keys, *, heartbeat_timeout, retry_delay,
                       backfill_timeout, host='127.0.0.1', port=0, max_attempts=None, backfill=None,
                       finished=None):
    """Own the listener and exactly one supervisor; await cleanup before release."""
    server = InternalMarketServer(market, sessions, host=host, port=port)
    supervisor = FeedSupervisor(market, factory, keys, heartbeat_timeout=heartbeat_timeout,
                                retry_delay=retry_delay, backfill_timeout=backfill_timeout)
    stop = asyncio.Event()
    await server.start()
    task = asyncio.create_task(supervisor.run(stop, max_attempts=max_attempts, backfill=backfill))
    async def observe():
        try:
            await task
        except Exception:
            market.disconnected('host_feed_failed')
            await server.close()
        finally:
            if finished is not None:
                finished.set()
    watcher = asyncio.create_task(observe())
    try:
        yield server.address
    finally:
        stop.set()
        market.disconnected('host_stopping')
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.shield(task)
            raise
        finally:
            await server.close()
            await watcher


async def _run(args):
    from gabfin.api.sessions import SessionStore
    from gabfin.contracts.market import Instrument
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.market.coordinator import MarketCoordinator
    from gabfin.providers.futu.adapter import FutuQuoteAdapter
    from gabfin.providers.futu.symbols import InstrumentCatalog
    with args.instrument.open('rb') as handle:
        data = handle.read(65537)
    if len(data) > 65536:
        raise ValueError('Instrument input exceeds capacity')
    instrument = Instrument.model_validate_json(data)
    catalog = InstrumentCatalog([instrument])
    store = SessionStore(args.session_db, owner_id=args.owner, session_seconds=args.session_seconds,
                         pairing_seconds=60, max_failures=5)
    market = MarketCoordinator([instrument.instrument_id], source='futu', replay_capacity=1000, max_bars=500)
    key = SubscriptionKey(instrument_id=instrument.instrument_id, channel='quote', timeframe=None)
    def factory():
        return FutuQuoteAdapter(catalog, instrument.instrument_id, python=args.sdk_python, port=args.opend_port)
    probe = factory()
    try:
        await probe.capabilities()
        metadata = probe.observed_metadata
        if (metadata is None or metadata['status'] != 'metadata_available' or metadata['errors']
                or metadata['quote_logged_in'] is not True
                or metadata['remaining_quota'] is None or metadata['remaining_quota'] < 1):
            raise ValueError('Quote login/quota preflight failed')
    finally:
        await probe.close()
    finished = asyncio.Event()
    async with serve_market(market, store, factory, [key], heartbeat_timeout=25,
                            retry_delay=2, backfill_timeout=20, host=args.host, port=args.port,
                            max_attempts=None if args.serve else 1, finished=finished) as address:
        print(json.dumps(dict(status='listening', host=address[0], port=address[1], source='futu',
                              entitlement='unverified')), flush=True)
        # No implicit history proof: an unavailable backfill leaves gaps open.
        if args.serve:
            await finished.wait()
        else:
            try:
                await asyncio.wait_for(finished.wait(), args.seconds)
            except TimeoutError:
                pass


def main():
    import argparse
    import math
    from pathlib import Path
    from uuid import UUID
    parser = argparse.ArgumentParser(description='Read-only single-equity market host; never opens a trade context')
    parser.add_argument('--sdk-python', type=Path, required=True)
    parser.add_argument('--instrument', type=Path, required=True, help='Canonical Instrument JSON; caller verifies metadata')
    parser.add_argument('--session-db', type=Path, required=True)
    parser.add_argument('--owner', type=UUID, required=True)
    parser.add_argument('--session-seconds', type=int, default=300)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--opend-port', type=int, default=11111)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--seconds', type=float)
    mode.add_argument('--serve', action='store_true', help='Run in the foreground until cancelled; operator explicitly opts in')
    args = parser.parse_args()
    if args.seconds is not None and (not math.isfinite(args.seconds) or not 0 < args.seconds <= 120):
        parser.error('Diagnostic duration must be positive and at most 120 seconds')
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0
    except Exception:
        print('market_host_failed')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
