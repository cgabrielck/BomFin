"""Fixed-symbol diagnostics only; no native realtime/final-bar eligibility claim."""
from datetime import datetime,timezone,date,time as daytime
from decimal import Decimal,InvalidOperation
import time
CODE='US.AAPL'
ERRORS={'symbol_failed','subscribe_failed','quote_failed','bar_failed','quote_data_incomplete','bar_data_incomplete','unsubscribe_failed','cleanup_verify_failed','close_failed'}
def number(v):
    if isinstance(v,bool) or v is None:return None
    try:
        d=Decimal(str(v))
        return str(d) if d.is_finite() and d>=0 else None
    except (InvalidOperation,ValueError):return None

def rows(response):
    if not isinstance(response,tuple) or len(response)!=2 or type(response[0]) is not int or response[0]!=0:raise ValueError()
    value=response[1]
    records=value if isinstance(value,list) else value.to_dict(orient='records')
    if not isinstance(records,list) or len(records)>2 or any(not isinstance(r,dict) or r.get('code')!=CODE for r in records):raise ValueError()
    return records

def ok(response):return isinstance(response,tuple) and len(response)==2 and type(response[0]) is int and response[0]==0

def validate_smoke(m):
    if not isinstance(m,dict) or set(m)!={'kind','code','checked_at','symbol_verified','last_price','data_date','data_time','bars','source_timezone','latency','cleanup','errors'}:raise ValueError()
    if m['kind']!='equity_smoke' or m['code']!=CODE or type(m['symbol_verified']) is not bool or m['source_timezone']!='America/New_York' or m['latency']!='unverified':raise ValueError()
    if datetime.fromisoformat(m['checked_at']).tzinfo is None:raise ValueError()
    if m['cleanup'] not in ('not_subscribed','unsubscribed','release_pending'):raise ValueError()
    if not isinstance(m['errors'],list) or any(type(e) is not str or e not in ERRORS for e in m['errors']):raise ValueError()
    if m['last_price'] is not None and (type(m['last_price']) is not str or number(m['last_price']) is None):raise ValueError()
    if m['data_date'] is not None:date.fromisoformat(m['data_date'])
    if m['data_time'] is not None:daytime.fromisoformat(m['data_time'])
    if not isinstance(m['bars'],list) or len(m['bars'])>2:raise ValueError()
    for b in m['bars']:
        if not isinstance(b,dict) or set(b)!={'time','open','high','low','close'} or type(b['time']) is not str:raise ValueError()
        datetime.fromisoformat(b['time'])
        for f in ('open','high','low','close'):
            if b[f] is not None and (type(b[f]) is not str or number(b[f]) is None):raise ValueError()
    return m

def inspect_equity(context,sdk,*,sleep=time.sleep):
    r=dict(kind='equity_smoke',code=CODE,checked_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),symbol_verified=False,last_price=None,data_date=None,data_time=None,bars=[],source_timezone='America/New_York',latency='unverified',cleanup='not_subscribed',errors=[])
    attempted=False;subscribed=False
    try:
        try:
            basic=rows(context.get_stock_basicinfo(sdk.US,sdk.STOCK,code_list=[CODE]))
            if len(basic)!=1 or basic[0].get('stock_type')!=sdk.STOCK:raise ValueError()
            r['symbol_verified']=True
        except Exception:r['errors'].append('symbol_failed');return r
        attempted=True
        try:
            if not ok(context.subscribe([CODE],[sdk.QUOTE,sdk.K_DAY],is_first_push=False,subscribe_push=False,extended_time=False,session=sdk.RTH)):raise ValueError()
            subscribed=True
        except Exception:r['errors'].append('subscribe_failed')
        if subscribed:
            try:
                q=rows(context.get_stock_quote([CODE]))
                if len(q)!=1:raise ValueError()
                r['last_price']=number(q[0].get('last_price'))
                d=q[0].get('data_date');t=q[0].get('data_time')
                date.fromisoformat(d);daytime.fromisoformat(t)
                r['data_date']=d;r['data_time']=t
                if r['last_price'] is None:r['errors'].append('quote_data_incomplete')
            except Exception:r['errors'].append('quote_failed')
            try:
                for b in rows(context.get_cur_kline(CODE,2,ktype=sdk.K_DAY,autype=sdk.NONE)):
                    timestamp=b.get('time_key');datetime.fromisoformat(timestamp)
                    bar={'time':timestamp,**{f:number(b.get(f)) for f in ('open','high','low','close')}}
                    if any(bar[f] is None for f in ('open','high','low','close')):r['errors'].append('bar_data_incomplete')
                    r['bars'].append(bar)
                if not r['bars']:r['errors'].append('bar_data_incomplete')
            except Exception:r['errors'].append('bar_failed')
    finally:
        try:
            if attempted:
                if subscribed:sleep(61)
                r['cleanup']='release_pending'
                if ok(context.unsubscribe([CODE],[sdk.QUOTE,sdk.K_DAY])):
                    response=context.query_subscription(is_all_conn=False)
                    if ok(response) and isinstance(response[1],dict) and type(response[1].get('own_used')) is int and response[1]['own_used']==0:r['cleanup']='unsubscribed'
                    else:r['errors'].append('cleanup_verify_failed')
                else:r['errors'].append('unsubscribe_failed')
        except Exception:r['errors'].append('unsubscribe_failed')
        finally:
            try:context.close()
            except Exception:r['errors'].append('close_failed')
    return r
