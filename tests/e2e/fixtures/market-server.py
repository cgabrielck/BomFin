"""Private-stdio test harness: real TLS/API/internal sockets, synthetic prices.

Pairing codes travel only over the parent-owned pipe. No test-admin HTTP route.

The quote identity is derived the way a real provider derives it: from the
source facts, not from a random uuid. A provider that re-quotes the same
price at the same source instant must produce the same event id, so the
fixture has to behave that way for the deduplication paths to be exercised.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

import uvicorn

from gabfin.api.app import create_market_app
from gabfin.api.market_gateway import MarketGateway
from gabfin.api.sessions import SessionStore
from gabfin.contracts.events import QuoteMarketEvent, BarMarketEvent
from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.market.coordinator import MarketCoordinator
from gabfin.market.internal_stream import InternalMarketServer


IDS = {'AAPL':UUID('11111111-1111-4111-8111-111111111111'),
       'MSFT':UUID('22222222-2222-4222-8222-222222222222'),
       'NVDA':UUID('33333333-3333-4333-8333-333333333333')}


def analysis_planes(now):
    """Deterministic analysis planes for the browser tests.

    The fixture owns the truth here: the indicator plane computes from
    a fixed run of bars, the macro plane returns observations with the
    release dates they really have, and the capability plane reports the
    fixture feed exactly as it is. Nothing reaches the network.
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


def emit(value):
    print(json.dumps(value), flush=True)


async def run(args, folder):
    offset = [0]
    now = lambda: datetime.now(timezone.utc) + timedelta(seconds=offset[0])
    store = SessionStore(folder/'sessions.sqlite', owner_id=uuid4(), session_seconds=300,
        pairing_seconds=60, max_failures=10, clock=now)
    keys=[SubscriptionKey(instrument_id=value,channel='quote',timeframe=None) for value in IDS.values()]
    if args.bars: keys += [SubscriptionKey(instrument_id=value,channel='bar',timeframe=dict(count=1,unit='minute')) for value in IDS.values()]
    def new_market():
        return MarketCoordinator(IDS.values(), source='fixture', replay_capacity=100, max_bars=50, clock=now,required_keys=keys)
    market=new_market()
    bar_start=now().replace(second=0,microsecond=0)-timedelta(minutes=5)
    bar_events={}
    quote_events={}
    def publish_bar(item):
        symbol=item.get('symbol','AAPL');index=item.get('index',2);stamp=now();start=bar_start+timedelta(minutes=index)
        event=BarMarketEvent(schema_version='1.0',kind='bar',event_id=uuid4(),instrument_id=IDS[symbol],
            event_at=stamp,received_at=stamp,available_at=stamp,source='fixture',source_seq=None,
            dedup_key=str(uuid4()),payload=dict(schema_version='1.0',instrument_id=IDS[symbol],source='fixture',
                timeframe=dict(count=1,unit='minute'),session='regular',start=start,end=start+timedelta(minutes=1),
                open='100',high='110',low='95',close=item.get('close','103'),volume=item.get('volume','100'),
                status=item.get('status','forming'),revision=item.get('revision',0),corporate_action_policy='unadjusted-fixture',
                event_at=stamp,received_at=stamp,available_at=stamp))
        bar_events[(symbol,index)]=event;market.apply(event)
    def publish(symbol, price):
        stamp=now(); event=stamp-timedelta(seconds=2)
        # Same derivation as the real provider: code, source instant and price
        # decide the identity, so an identical re-quote yields an identical
        # event id and dedup_key.
        digest=sha256(f'{symbol}|{event.isoformat()}|{price}'.encode()).hexdigest()
        key='fixture:quote:'+digest
        quote=QuoteMarketEvent(schema_version='1.0', kind='quote',event_id=uuid5(NAMESPACE_URL,key),
            instrument_id=IDS[symbol],event_at=event,received_at=stamp,available_at=stamp,
            source='fixture',source_seq=None,dedup_key=key,payload=dict(schema_version='1.0',
                instrument_id=IDS[symbol],as_of=stamp,feed='fixture',session='unknown',bid=None,ask=None,
                last=dict(price=price,event_at=event,received_at=stamp,available_at=stamp,age_ms=2000),
                quality=['unknown','incomplete'],entitlements=dict(status='unknown',checked_at=None)))
        quote_events[(symbol,price)]=quote
        market.apply(quote)
    def seed(count=3):
        market.heartbeat(now())
        for symbol,price in [('AAPL','210.00'),('MSFT','420.00'),('NVDA','140.00')]: publish(symbol,price)
        if args.bars:
            for symbol in ('AAPL','MSFT'):
                for index in range(count):publish_bar(dict(symbol=symbol,index=index,status='final' if index<count-1 else 'forming'))
        else: market.recover_latest_quotes()
    seed()
    internal = InternalMarketServer(market,store); await internal.start()
    gateway=MarketGateway.from_store(host=internal.address[0],port=internal.address[1],store=store,
        registered_keys=keys,source='fixture')
    listener=socket.socket();listener.bind(('127.0.0.1',0))
    origin=f'https://127.0.0.1:{listener.getsockname()[1]}'
    app=create_market_app(store,allowed_origin=origin,gateway=gateway,static_dir=args.dist,
        analysis=analysis_planes(now))
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
        async def command(line):
            nonlocal market,internal
            item=None
            try:
                item=json.loads(line); action=item['action']; result={}
                if action=='pair': result={'code':store.create_pairing()}
                elif action=='price': publish(item['symbol'],item['price'])
                elif action=='bar': publish_bar(item)
                elif action=='repeat_bar': market.apply(bar_events[(item.get('symbol','AAPL'),item.get('index',2))])
                elif action=='reset_bars':
                    address=internal.address
                    await internal.close()
                    market=new_market();bar_events.clear();seed(item.get('count',1))
                    internal=InternalMarketServer(market,store,host=address[0],port=address[1]);await internal.start()
                elif action=='new_epoch':
                    # A fresh coordinator re-opens the epoch and drops the dedup
                    # evidence, so the same source facts can legitimately be
                    # published again under the same event id.
                    address=internal.address
                    await internal.close()
                    market=new_market()
                    internal=InternalMarketServer(market,store,host=address[0],port=address[1]);await internal.start()
                elif action=='replay_quote':
                    # Re-apply the stored event unchanged, so the event id
                    # repeats on purpose.
                    quote=quote_events.get((item.get('symbol','AAPL'),item.get('price','210.00')))
                    if quote is None: raise ValueError('No stored quote to replay')
                    market.apply(quote)
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
                asyncio.run_coroutine_threadsafe(command(line),loop)
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
    parser.add_argument('--openssl',type=Path,required=True);parser.add_argument('--bars',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='gabfin-tls-fixture-') as temp:
        folder=Path(temp)
        subprocess.run([str(args.openssl),'req','-x509','-newkey','rsa:2048','-nodes','-days','1',
            '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1',
            '-keyout',str(folder/'key.pem'),'-out',str(folder/'cert.pem')],check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        asyncio.run(run(args,folder))
