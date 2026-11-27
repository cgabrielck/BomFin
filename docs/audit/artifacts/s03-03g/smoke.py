"""Bounded one-equity callback demonstration; stores only sanitized observations.

Catalog tick/lot are diagnostic fixture values, not verified security-master
facts and never inputs to orders. This script neither imports nor opens trade.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID

from gabfin.contracts.market import Instrument
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.providers.futu.adapter import FutuQuoteAdapter
from gabfin.providers.futu.symbols import InstrumentCatalog


async def run(python, seconds):
    identifier = UUID('11111111-1111-4111-8111-111111111111')
    instrument = Instrument(schema_version='1.0', instrument_id=identifier, asset_class='equity',
                            vendor_symbols={'futu': 'US.AAPL'}, currency='USD', tick_size='0.01', lot_size='1')
    adapter = FutuQuoteAdapter(InstrumentCatalog([instrument]), identifier, python=python)
    started = datetime.now(timezone.utc)
    events = []
    error = None
    try:
        await adapter.subscribe([SubscriptionKey(instrument_id=identifier, channel='quote', timeframe=None)])

        async def receive():
            async for event in adapter.events():
                # Evidence is bounded independently from the actual stream.
                if len(events) < 3:
                    events.append(event.model_dump(mode='json'))

        task = asyncio.create_task(receive())
        await asyncio.sleep(seconds)
        await adapter.close()
        await task
    except Exception as exc:
        # Only our exception class is evidence; raw external strings are omitted.
        error = type(exc).__name__
    finally:
        await adapter.close()
    snapshot = adapter.snapshot()
    return dict(started_at=started.isoformat(), ended_at=datetime.now(timezone.utc).isoformat(),
                observation_seconds=seconds, code='US.AAPL', error=error, failure=adapter.failure,
                running=adapter.running, stats=adapter.stats, result=adapter.result,
                initial_samples=events, latest=snapshot.model_dump(mode='json') if snapshot else None,
                latency='unverified', session='unknown', catalog_metadata='diagnostic_fixture_only')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=8, choices=range(1, 16))
    args = parser.parse_args()
    result = asyncio.run(run(args.python, args.seconds))
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('error', 'failure', 'running', 'stats', 'result')}))
    raise SystemExit(0 if not result['error'] and not result['failure'] and result['stats']['accepted'] > 0 else 2)
