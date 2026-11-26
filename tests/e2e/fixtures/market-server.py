"""Private-stdio test harness: real TLS/API/internal sockets, synthetic prices.

Pairing codes travel only over the parent-owned pipe. No test-admin HTTP route.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
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


IDS = {'AAPL':UUID('11111111-1111-4111-8111-111111111111'),
       'MSFT':UUID('22222222-2222-4222-8222-222222222222'),
       'NVDA':UUID('33333333-3333-4333-8333-333333333333')}


def emit(value):
    print(json.dumps(value), flush=True)


async def run(args, folder):
    offset = [0]
    now = lambda: datetime.now(timezone.utc) + timedelta(seconds=offset[0])
    store = SessionStore(folder/'sessions.sqlite', owner_id=uuid4(), session_seconds=300,
        pairing_seconds=60, max_failures=10, clock=now)
    market = MarketCoordinator(IDS.values(), source='fixture', replay_capacity=100, max_bars=50, clock=now)
    def publish(symbol, price):
        stamp=now(); event=stamp-timedelta(seconds=2)
        market.apply(QuoteMarketEvent(schema_version='1.0', kind='quote',event_id=uuid4(),
            instrument_id=IDS[symbol],event_at=event,received_at=stamp,available_at=stamp,
            source='fixture',source_seq=None,dedup_key=str(uuid4()),payload=dict(schema_version='1.0',
                instrument_id=IDS[symbol],as_of=stamp,feed='fixture',session='unknown',bid=None,ask=None,
                last=dict(price=price,event_at=event,received_at=stamp,available_at=stamp,age_ms=2000),
                quality=['unknown','incomplete'],entitlements=dict(status='unknown',checked_at=None))))
    market.heartbeat(now())
    for symbol,price in [('AAPL','210.00'),('MSFT','420.00'),('NVDA','140.00')]: publish(symbol,price)
    market.recover_latest_quotes()
    internal = InternalMarketServer(market,store); await internal.start()
    keys=[SubscriptionKey(instrument_id=value,channel='quote',timeframe=None) for value in IDS.values()]
    gateway=MarketGateway.from_store(host=internal.address[0],port=internal.address[1],store=store,
        registered_keys=keys,source='fixture')
    listener=socket.socket();listener.bind(('127.0.0.1',0))
    origin=f'https://127.0.0.1:{listener.getsockname()[1]}'
    app=create_market_app(store,allowed_origin=origin,gateway=gateway,static_dir=args.dist)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',log_config=None,access_log=False,
        log_level='critical',proxy_headers=False,ssl_certfile=str(folder/'cert.pem'),
        ssl_keyfile=str(folder/'key.pem'),ws_max_size=16384,limit_concurrency=32))
    serving=asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(15):
            while not server.started:
                if serving.done(): await serving; raise RuntimeError('TLS fixture failed')
                await asyncio.sleep(.01)
        loop=asyncio.get_running_loop()
        def command(line):
            item=None
            try:
                item=json.loads(line); action=item['action']; result={}
                if action=='pair': result={'code':store.create_pairing()}
                elif action=='price': publish(item['symbol'],item['price'])
                elif action=='expire': offset[0]+=301
                elif action=='gap': market.disconnected('fixture_disconnect')
                elif action=='heartbeat': market.heartbeat(now())
                elif action=='stop': server.should_exit=True
                else: raise ValueError('Invalid private command')
                emit({'id':item['id'],'ok':True,**result})
            except Exception:
                emit({'id':item.get('id') if isinstance(item,dict) else None,'ok':False})
        def controls():
            for line in sys.stdin:
                loop.call_soon_threadsafe(command,line)
            loop.call_soon_threadsafe(setattr,server,'should_exit',True)
        threading.Thread(target=controls,daemon=True).start()
        emit({'kind':'ready','origin':origin})
        await serving
    finally:
        server.should_exit=True
        await asyncio.gather(serving,return_exceptions=True)
        await internal.close()
        listener.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--dist',type=Path,required=True)
    parser.add_argument('--openssl',type=Path,required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='gabfin-tls-fixture-') as temp:
        folder=Path(temp)
        subprocess.run([str(args.openssl),'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1',
            '-keyout',str(folder/'key.pem'),'-out',str(folder/'cert.pem')],check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        asyncio.run(run(args,folder))
