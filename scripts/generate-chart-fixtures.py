"""Explicit synthetic 1m chart snapshots, validated by canonical Python models."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL

from gabfin.contracts.events import BarMarketEvent
from gabfin.contracts.feed import MarketSnapshot


def main():
    folder=Path(__file__).resolve().parents[1]/'apps/desk-web/public/demo/bars'
    folder.mkdir(parents=True,exist_ok=True)
    stamp=datetime(2026,11,25,21,tzinfo=timezone.utc)
    for symbol,digit,base in [('AAPL','1','208'),('MSFT','2','418'),('NVDA','3','138')]:
        identifier=UUID(f'{digit*8}-{digit*4}-4{digit*3}-8{digit*3}-{digit*12}')
        bars=[]
        if symbol!='NVDA':
            for index in range(30):
                start=stamp-timedelta(minutes=30-index)
                price=Decimal(base)+Decimal(index)*Decimal('.06')+Decimal(index%4)*Decimal('.04')
                closing=price+(Decimal('.12') if index%3 else Decimal('-.08'))
                payload=dict(schema_version='1.0',instrument_id=identifier,source='demo',
                    timeframe=dict(count=1,unit='minute'),session='regular',start=start,end=start+timedelta(minutes=1),
                    open=str(price),high=str(max(price,closing)+Decimal('.10')),low=str(min(price,closing)-Decimal('.10')),
                    close=str(closing),volume=str(1000+index*37),status='final',revision=0,
                    corporate_action_policy='synthetic-unadjusted',event_at=start+timedelta(minutes=1),
                    received_at=stamp,available_at=stamp)
                bars.append(BarMarketEvent(schema_version='1.0',kind='bar',
                    event_id=uuid5(NAMESPACE_URL,f'gabfin-demo-{symbol}-{index}'),instrument_id=identifier,
                    event_at=payload['event_at'],received_at=stamp,available_at=stamp,source='demo',
                    source_seq=None,dedup_key=f'{symbol}-bar-{index}',payload=payload))
        snapshot=MarketSnapshot(schema_version='1.0',epoch=uuid5(NAMESPACE_URL,'gabfin-chart-demo'),
            cursor=30,as_of=stamp,quotes=[],bars=bars,gap=None,health=dict(schema_version='1.0',source='demo',
                connected=False,heartbeat_at=None,gap_pending=False))
        (folder/f'{symbol}.json').write_text(snapshot.model_dump_json(indent=2)+'\n',encoding='utf-8')
    print('3 canonical synthetic bar snapshots generated (NVDA intentionally empty)')


if __name__=='__main__':main()
