"""Bounded quote-only OpenD → S03 socket → authenticated browser API smoke.

HTTP/WS use TestClient; real HTTPS network/browser coverage is a separate fixture.
No trading contexts, broker credentials, or internal tokens are written to output.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from gabfin.api.app import create_market_app
from gabfin.api.market_gateway import MarketGateway
from gabfin.api.sessions import SessionStore
from gabfin.contracts.market import Instrument
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.market.coordinator import MarketCoordinator
from gabfin.market.freshness import FreshnessPolicy, entry_eligible
from gabfin.market.host import serve_market
from gabfin.providers.futu.adapter import FutuQuoteAdapter
from gabfin.providers.futu.symbols import InstrumentCatalog


async def run(sdk_python):
    identifier=UUID('11111111-1111-4111-8111-111111111111')
    instrument=Instrument(schema_version='1.0',instrument_id=identifier,asset_class='equity',
        vendor_symbols={'futu':'US.AAPL'},currency='USD',tick_size='0.01',lot_size='1')
    catalog=InstrumentCatalog([instrument])
    result=dict(started_at=datetime.now(timezone.utc).isoformat(),source='futu',
        instrument_metadata='diagnostic_fixture_only',http_ws_transport='in_process_testclient',
        internal_transport='real_loopback_tcp',ui_render_measured=False,trade_context_opened=False)
    async def metadata():
        probe=FutuQuoteAdapter(catalog,identifier,python=sdk_python)
        try:
            await probe.capabilities()
            return probe.observed_metadata
        finally: await probe.close()
    result['before_metadata']=await metadata()
    before=result['before_metadata']
    if (before is None or before['status']!='metadata_available' or before['errors']
            or before['quote_logged_in'] is not True or (before['remaining_quota'] or 0)<1):
        return result|dict(error='quote_preflight_failed')
    feeds=[]
    def factory():
        feed=FutuQuoteAdapter(catalog,identifier,python=sdk_python);feeds.append(feed);return feed
    market=MarketCoordinator([identifier],source='futu',replay_capacity=100,max_bars=50)
    key=SubscriptionKey(instrument_id=identifier,channel='quote',timeframe=None)
    try:
        with tempfile.TemporaryDirectory(prefix='gabfin-api-smoke-') as folder:
            store=SessionStore(Path(folder)/'sessions.sqlite',owner_id=uuid4(),session_seconds=180,
                pairing_seconds=30,max_failures=5)
            async with serve_market(market,store,factory,[key],heartbeat_timeout=25,retry_delay=1,
                    backfill_timeout=10,max_attempts=1) as address:
                async with asyncio.timeout(25):
                    while not market.snapshot().quotes: await asyncio.sleep(.1)
                gateway=MarketGateway.from_store(host=address[0],port=address[1],store=store,
                    registered_keys=[key],source='futu')
                origin='https://desk.test'
                app=create_market_app(store,allowed_origin=origin,gateway=gateway)
                def consume():
                    with TestClient(app,base_url=origin) as client:
                        response=client.post('/pair',json={'code':store.create_pairing()},headers={'Origin':origin})
                        assert response.status_code==200
                        headers={'Origin':origin,'X-CSRF-Token':response.json()['csrf']}
                        body={'version':1,'keys':[key.model_dump(mode='json')]}
                        response=client.post('/market/snapshot',json=body,headers=headers)
                        assert response.status_code==200
                        snapshot=response.json()
                        assert snapshot['health']['source']=='futu' and snapshot['quotes']
                        with client.websocket_connect('wss://desk.test/market/stream',headers={'Origin':origin}) as ws:
                            ws.send_json(body);frame=ws.receive_json()
                            assert frame['kind']=='snapshot' and frame['payload']['quotes']
                            assert frame['payload']['quotes'][0]['instrument_id']==str(identifier)
                        assert client.post('/logout',headers=headers).status_code==200
                        assert client.post('/market/snapshot',json=body,headers=headers).status_code==401
                        return {'http_snapshot':snapshot,'websocket_snapshot':True,'logout_revoked':True}
                result['api']=await asyncio.wait_for(asyncio.to_thread(consume),15)
                snapshot=market.snapshot()
                policy=FreshnessPolicy(schema_version='1.0',version='diagnostic-unapproved',approved=False,
                    max_quote_age_ms=5000,max_heartbeat_age_ms=25000,max_entitlement_age_ms=60000,
                    allowed_sessions=('regular',))
                result['freshness']=entry_eligible(snapshot.quotes[0].payload,policy,now=market.now(),
                    health=snapshot.health).model_dump(mode='json')
    except Exception:
        result['error']='live_api_chain_failed'
    result['feeds']=[dict(running=feed.running,result=feed.result,failure=feed.failure,stats=feed.stats) for feed in feeds]
    result['after_metadata']=await metadata()
    result['ended_at']=datetime.now(timezone.utc).isoformat()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sdk-python',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=asyncio.run(run(args.sdk_python))
    success=bool(not result.get('error') and result.get('api',{}).get('websocket_snapshot') and
        all(not feed['running'] and feed['result'] and feed['result']['cleanup']=='unsubscribed'
            and feed['result']['closed'] and not feed['result']['errors'] for feed in result.get('feeds',[])))
    result['success']=success;args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'success':success,'source':'futu','trade_context_opened':False,
        'entry_eligible':result.get('freshness',{}).get('eligible')}))
    raise SystemExit(0 if success else 2)
