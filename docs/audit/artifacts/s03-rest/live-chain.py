"""Bounded SDK → market → independent authenticated consumer demonstration."""
import argparse
import asyncio
from datetime import datetime, timezone
from importlib.util import find_spec
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import UUID, uuid4

from gabfin.api.sessions import SessionStore
from gabfin.contracts.market import Instrument
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.market.coordinator import MarketCoordinator
from gabfin.market.freshness import FreshnessPolicy, entry_eligible
from gabfin.market.host import serve_market
from gabfin.providers.futu.adapter import FutuQuoteAdapter
from gabfin.providers.futu.symbols import InstrumentCatalog


async def run(sdk_python):
    identifier = UUID('11111111-1111-4111-8111-111111111111')
    instrument = Instrument(schema_version='1.0', instrument_id=identifier, asset_class='equity',
        vendor_symbols={'futu':'US.AAPL'}, currency='USD', tick_size='0.01', lot_size='1')
    catalog = InstrumentCatalog([instrument])
    result = dict(started_at=datetime.now(timezone.utc).isoformat(), source='futu',
                  instrument_metadata='diagnostic_fixture_only', ui_render_measured=False,
                  host_has_sdk=find_spec('futu') is not None, host_has_pandas=find_spec('pandas') is not None)
    probe = FutuQuoteAdapter(catalog, identifier, python=sdk_python)
    try:
        result['capabilities'] = (await probe.capabilities()).model_dump(mode='json')
        result['before_metadata'] = probe.observed_metadata
    finally:
        await probe.close()
    if result['before_metadata'] is None or result['before_metadata']['status'] != 'metadata_available':
        return result | dict(error='metadata_unavailable')
    feeds = []
    def factory():
        feed = FutuQuoteAdapter(catalog, identifier, python=sdk_python)
        feeds.append(feed)
        return feed
    market = MarketCoordinator([identifier], source='futu', replay_capacity=1000, max_bars=500)
    key = SubscriptionKey(instrument_id=identifier, channel='quote', timeframe=None)
    try:
        with tempfile.TemporaryDirectory(prefix='gabfin-stream-smoke-') as folder:
            store = SessionStore(Path(folder)/'sessions.sqlite', owner_id=uuid4(),
                session_seconds=180, pairing_seconds=30, max_failures=5)
            token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
            async with serve_market(market, store, factory, [key], heartbeat_timeout=25,
                retry_delay=1, backfill_timeout=10, max_attempts=1) as address:
                env = {key:value for key,value in os.environ.items()
                       if key.upper() in ('SYSTEMROOT','WINDIR','COMSPEC')}
                env.update(TEMP=folder,TMP=folder,APPDATA=folder,LOCALAPPDATA=folder,PYTHONUTF8='1')
                child = await asyncio.create_subprocess_exec(sys.executable, '-I',
                    str(Path(__file__).with_name('consumer.py')), stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, cwd=folder,
                    env=env, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                private = dict(host=address[0],port=address[1],token=token,
                               instrument_id=str(identifier),seconds=12)
                try:
                    output, _ = await asyncio.wait_for(child.communicate(json.dumps(private).encode()), 35)
                    if len(output) > 32768: raise ValueError('consumer_output_capacity')
                    result['consumer'] = json.loads(output)
                finally:
                    if child.returncode is None:
                        child.kill(); await child.wait()
                snapshot = market.snapshot()
                if snapshot.quotes:
                    policy = FreshnessPolicy(schema_version='1.0', version='diagnostic-unapproved',
                        approved=False,max_quote_age_ms=5000,max_heartbeat_age_ms=25000,
                        max_entitlement_age_ms=60000,allowed_sessions=('regular',))
                    result['freshness'] = entry_eligible(snapshot.quotes[0].payload, policy,
                        now=market.now(), health=snapshot.health).model_dump(mode='json')
                result['during_health'] = snapshot.health.model_dump(mode='json')
    except Exception:
        result['error'] = 'live_chain_failed'
    result['feeds'] = [dict(running=feed.running,result=feed.result,failure=feed.failure,stats=feed.stats) for feed in feeds]
    probe = FutuQuoteAdapter(catalog, identifier, python=sdk_python)
    try:
        await probe.capabilities()
        result['after_metadata'] = probe.observed_metadata
    finally:
        await probe.close()
    result['ended_at'] = datetime.now(timezone.utc).isoformat()
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sdk-python',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    result=asyncio.run(run(args.sdk_python))
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    consumer=result.get('consumer',{})
    success=(not result.get('error') and consumer.get('quote_observations',0)>0
             and not consumer.get('errors') and consumer.get('connected_seen')
             and all(not feed['running'] and feed['result'] and feed['result']['cleanup']=='unsubscribed'
                     and feed['result']['closed'] and not feed['result']['errors'] for feed in result.get('feeds',[])))
    print(json.dumps(dict(success=bool(success),quote_observations=consumer.get('quote_observations',0),
                         connected=consumer.get('connected_seen'),resynced=consumer.get('resynced_seen'))))
    raise SystemExit(0 if success else 2)
