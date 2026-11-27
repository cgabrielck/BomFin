import json
from datetime import datetime,timezone
import pytest
T=datetime(2026,11,25,tzinfo=timezone.utc)
class Context:
 def __init__(self,state=None,quota=None,fail=None):self.state=state if state is not None else (0,{'qot_logined':True,'account':'PRIVATE'});self.quota=quota if quota is not None else (0,{'total_used':2,'remain':0,'sub_list':{'PRIVATE':['PRIVATE']}});self.fail=fail;self.closed=False
 def get_global_state(self):
  if self.fail=='state':raise RuntimeError('PRIVATE')
  return self.state
 def query_subscription(self,*,is_all_conn):
  assert is_all_conn is True
  if self.fail=='quota':raise RuntimeError('PRIVATE')
  return self.quota
 def close(self):
  self.closed=True
  if self.fail=='close':raise RuntimeError('PRIVATE')
def inspect(c):
 from gabfin.providers.futu.capabilities import inspect_quote_context
 return inspect_quote_context(c,checked_at=T)
def test_safe_known_zero_metadata():
 c=Context();r=inspect(c);assert c.closed and r['remaining_quota']==0 and r['status']=='metadata_available';assert 'PRIVATE' not in json.dumps(r)
@pytest.mark.parametrize('value',[None,-1,True,1.5,'3',9007199254740992])
def test_invalid_quota_is_unknown(value):
 c=Context(quota=(0,{'total_used':2,'remain':value}));r=inspect(c);assert r['remaining_quota'] is None and r['status']=='metadata_incomplete' and c.closed
@pytest.mark.parametrize('failure',['state','quota','close'])
def test_errors_are_sanitized_and_closed(failure):
 c=Context(fail=failure);r=inspect(c);assert c.closed and r['errors'] and 'PRIVATE' not in json.dumps(r)
@pytest.mark.parametrize('state',[(0,{'qot_logined':False}),(0,{'qot_logined':'true'}),(1,'PRIVATE'),(0,{'trd_logined':True})])
def test_no_implicit_quote_permission(state):
 r=inspect(Context(state=state));assert r['status']!='metadata_available' and 'PRIVATE' not in json.dumps(r)
def test_naive_time_closes_without_call():
 from gabfin.providers.futu.capabilities import inspect_quote_context
 c=Context()
 with pytest.raises(ValueError):inspect_quote_context(c,checked_at=datetime(2026,1,1))
 assert c.closed
def test_preflight_default_does_not_connect():
 from gabfin.providers.futu.preflight import readiness
 calls=[]
 r=readiness(sdk_check=lambda:False,tcp_check=lambda:calls.append(True))
 assert not calls and r['listener_reachable'] is None and r['gates']==['sdk_unavailable','opend_not_checked']
def test_preflight_listener_not_entitlement():
 from gabfin.providers.futu.preflight import readiness
 r=readiness(sdk_check=lambda:True,tcp_check=lambda:True,check_tcp=True)
 assert r['listener_reachable'] is True and all(v=='unverified' for v in r['features'].values())
@pytest.mark.parametrize('quota',[(False,{'total_used':0,'remain':5}),(0,'PRIVATE'),(0,{'total_used':True,'remain':5}),(0,{'total_used':0,'remain':5},'PRIVATE')])
def test_malformed_provider_responses(quota):
 r=inspect(Context(quota=quota));assert r['status']=='metadata_incomplete' and r['errors'] and 'PRIVATE' not in json.dumps(r)
def test_partial_failure_keeps_safe_login():
 r=inspect(Context(fail='quota'));assert r['quote_logged_in'] is True and r['remaining_quota'] is None
 assert r['errors']==['subscription_metadata_failed']
def test_preflight_tcp_exception_is_fixed_gate():
 from gabfin.providers.futu.preflight import readiness
 def fail():raise RuntimeError('PRIVATE')
 r=readiness(sdk_check=lambda:True,tcp_check=fail,check_tcp=True)
 assert r['gates']==['opend_unreachable'] and 'PRIVATE' not in json.dumps(r)
def test_preflight_import_does_not_load_sdk():
 import subprocess,sys
 result=subprocess.run([sys.executable,'-I','-c',"import sys; import gabfin.providers.futu.preflight; import gabfin.providers.futu.capabilities; assert 'futu' not in sys.modules; assert 'backend' not in sys.modules"],capture_output=True,timeout=10)
 assert result.returncode==0
