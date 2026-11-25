import pytest
class C:
 def __init__(self,fail=False):self.closed=False;self.unsub=False;self.fail=fail
 def get_stock_basicinfo(self,*a,**k):return 0,[{'code':'US.AAPL','stock_type':'STOCK','private':'secret'}]
 def subscribe(self,*a,**k):return (1,'secret') if self.fail else (0,None)
 def get_stock_quote(self,*a):return 0,[{'code':'US.AAPL','last_price':123.45,'data_date':'2026-11-25','data_time':'10:00:00','private':'secret'}]
 def get_cur_kline(self,*a,**k):return 0,[{'code':'US.AAPL','time_key':'2026-11-24 00:00:00','open':120,'high':125,'low':119,'close':123}]
 def unsubscribe(self,*a):self.unsub=True;return 0,None
 def query_subscription(self,**k):return 0,{'own_used':0}
 def close(self):self.closed=True
class S:QUOTE='QUOTE';K_DAY='K_DAY';STOCK='STOCK';US='US';NONE='NONE';RTH='RTH'
def test_smoke_wait_cleanup_and_allowlist():
 from gabfin.providers.futu.equity import inspect_equity
 c=C();waits=[];r=inspect_equity(c,S,sleep=waits.append)
 assert c.closed and c.unsub and waits==[61]
 assert r['symbol_verified'] and r['cleanup']=='unsubscribed' and r['last_price']=='123.45'
 assert 'secret' not in str(r) and r['latency']=='unverified'
def test_subscribe_failure_no_wait():
 from gabfin.providers.futu.equity import inspect_equity
 c=C(True);waits=[];r=inspect_equity(c,S,sleep=waits.append)
 assert c.closed and c.unsub and not waits and 'subscribe_failed' in r['errors']
def test_parent_rejects_private_fields():
 from gabfin.providers.futu.equity import validate_smoke
 with pytest.raises(ValueError):validate_smoke({'account':'secret'})
def test_symbol_mismatch_never_subscribes():
 from gabfin.providers.futu.equity import inspect_equity
 c=C();c.get_stock_basicinfo=lambda *a,**k:(0,[{'code':'US.AAPL','stock_type':'OPTION'}]);c.subscribe=lambda *a,**k:pytest.fail('must not subscribe')
 r=inspect_equity(c,S,sleep=lambda n:None);assert c.closed and not c.unsub and not r['symbol_verified']
def test_quote_failure_still_waits_unsubscribes():
 from gabfin.providers.futu.equity import inspect_equity
 c=C();c.get_stock_quote=lambda *a:(1,'secret');wait=[]
 r=inspect_equity(c,S,sleep=wait.append);assert c.closed and c.unsub and wait==[61] and 'quote_failed' in r['errors'] and r['last_price'] is None
@pytest.mark.parametrize('v',[float('nan'),float('inf'),True,-1])
def test_provider_bad_number_not_fabricated(v):
 from gabfin.providers.futu.equity import number
 assert number(v) is None
def test_cleanup_failure_is_visible():
 from gabfin.providers.futu.equity import inspect_equity
 c=C();c.unsubscribe=lambda *a:(1,'secret')
 r=inspect_equity(c,S,sleep=lambda n:None);assert c.closed and r['cleanup']=='release_pending' and 'unsubscribe_failed' in r['errors']
def test_valid_smoke_parent_validation():
 from gabfin.providers.futu.equity import inspect_equity,validate_smoke
 from gabfin.providers.futu.runner import _validate
 r=inspect_equity(C(),S,sleep=lambda n:None);assert _validate({'status':'ok','metadata':r},'equity_smoke')['metadata']==r
 for change in [{'account':'secret'},{'bars':[{'time':'secret'}]},{'data_date':'secret'}]:
  with pytest.raises((ValueError,TypeError)):validate_smoke(r|change)
