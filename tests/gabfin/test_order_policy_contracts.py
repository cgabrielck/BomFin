"""Contract failure cases before implementation, no live broker or risk settings."""
import json
from copy import deepcopy
import pytest
from pydantic import ValidationError
U=[f'{i:08}-1111-4111-8111-111111111111' for i in range(1,8)]
T='2026-11-25T12:00:00Z'
def policy():
 return dict(schema_version='1.0',version='fixture-only',allowed_strategies=['fixture'],allowed_sessions=['regular'],allowed_assets=['equity'],risk_bounds=dict(per_trade_risk=None,daily_loss=None,runtime_drawdown=None,gross_exposure_leverage=None,missing_data_policy=None),approval_hash=None,approved_at=None,status='draft')
def approved_policy():
 p=policy();p.update(status='approved',approval_hash='a'*64,approved_at=T);p['risk_bounds']=dict(per_trade_risk='0.01',daily_loss='0.02',runtime_drawdown='0.1',gross_exposure_leverage='1',missing_data_policy='halt_entries');return p
def decision():
 return dict(schema_version='1.0',decision_id=U[0],intent_id=U[1],approved=True,reason_codes=['fixture_pass'],quantity='2',risk_amount={'amount':'1.00','currency':'USD'},checks=[{'code':'fixture_check','passed':True}],policy_version='fixture-only',expires_at=T)
def command():
 return dict(schema_version='1.0',client_order_id=U[0],intent_id=U[1],instrument=U[2],risk_decision_id=U[3],side='sell',qty='2',type='limit',limit_price='100.10',tif='day',session='regular')
def event():
 return dict(schema_version='1.0',event_id=U[0],broker_id=None,client_order_id=U[1],status='unknown',cum_fill_qty='0',fill_price=None,fill_evidence='unavailable',evidence_id=None,event_at=T,received_at=T,available_at=T,dedup_key='source:opaque')
def parse(name,p):
 from gabfin.contracts import policy as pol, order
 cls=getattr(pol,name,None) or getattr(order,name)
 return cls.model_validate_json(json.dumps(p))
@pytest.mark.parametrize('name,make',[('PolicyVersion',policy),('PolicyVersion',approved_policy),('RiskDecision',decision),('OrderCommand',command),('OrderEvent',event)])
def test_roundtrip(name,make):
 r=parse(name,make());assert type(r).model_validate_json(r.model_dump_json())==r
@pytest.mark.parametrize('key',['per_trade_risk','daily_loss','runtime_drawdown','gross_exposure_leverage','missing_data_policy'])
def test_missing_policy_bound_never_approved(key):
 p=approved_policy();p['risk_bounds'][key]=None
 with pytest.raises(ValidationError):parse('PolicyVersion',p)
@pytest.mark.parametrize('change',[{'approval_hash':'a'*64},{'approved_at':T},{'allowed_sessions':['overnight']},{'allowed_assets':['option']},{'allowed_strategies':['a','a']}])
def test_invalid_draft(change):
 with pytest.raises(ValidationError):parse('PolicyVersion',policy()|change)
@pytest.mark.parametrize('change',[{'approval_hash':None},{'approved_at':None},{'allowed_strategies':[]},{'approval_hash':'bad'},{'approved_at':'2026-01-01T00:00:00'}])
def test_invalid_approval(change):
 with pytest.raises(ValidationError):parse('PolicyVersion',approved_policy()|change)
@pytest.mark.parametrize('key,value',[('per_trade_risk','1.1'),('daily_loss','-1'),('gross_exposure_leverage','0'),('per_trade_risk',0.01),('runtime_drawdown',True)])
def test_invalid_bound(key,value):
 p=approved_policy();p['risk_bounds'][key]=value
 with pytest.raises(ValidationError):parse('PolicyVersion',p)
@pytest.mark.parametrize('change',[{'approved':1},{'approved':'true'},{'quantity':None},{'quantity':'0'},{'risk_amount':None},{'risk_amount':{'amount':'0','currency':'USD'}},{'checks':[{'code':'fail','passed':False}]},{'checks':[]},{'reason_codes':[]}])
def test_invalid_risk_approval(change):
 with pytest.raises(ValidationError):parse('RiskDecision',decision()|change)
def test_denial_has_no_sizing():
 p=decision();p.update(approved=False,quantity=None,risk_amount=None);assert parse('RiskDecision',p).approved is False
 with pytest.raises(ValidationError):parse('RiskDecision',p|{'quantity':'2'})
@pytest.mark.parametrize('change',[{'qty':'0'},{'qty':2.0},{'side':'short'},{'limit_price':None},{'type':'market'},{'session':'overnight'},{'session':'pre_market','tif':'gtc'},{'session':'post_market','type':'market','limit_price':None}])
def test_invalid_command(change):
 with pytest.raises(ValidationError):parse('OrderCommand',command()|change)
def test_regular_market_and_extended_limit():
 assert parse('OrderCommand',command()|{'type':'market','limit_price':None}).type=='market'
 assert parse('OrderCommand',command()|{'session':'post_market'}).session=='post_market'
@pytest.mark.parametrize('status',['partial','filled','canceled'])
def test_missing_price_does_not_fabricate_fill(status):
 r=parse('OrderEvent',event()|{'status':status,'cum_fill_qty':'1'})
 assert r.fill_price is None
@pytest.mark.parametrize('change',[{'fill_price':'10'},{'status':'filled'},{'status':'partial'},{'cum_fill_qty':'-1'},{'cum_fill_qty':0.0},{'cum_fill_qty':'1','fill_price':'10'},{'fill_evidence':'broker_reported'},{'dedup_key':''},{'available_at':'2026-11-24T12:00:00Z'}])
def test_invalid_fill_observation(change):
 with pytest.raises(ValidationError):parse('OrderEvent',event()|change)
def test_broker_evidence_and_canceled_partial():
 p=event()|{'status':'canceled','cum_fill_qty':'1','fill_price':'100.10','fill_evidence':'broker_reported','evidence_id':U[2],'broker_id':'broker:1'}
 r=parse('OrderEvent',p);assert json.loads(r.model_dump_json())['fill_price']=='100.10'
 assert parse('OrderEvent',event()).status=='unknown'
def test_schemas():
 for name,make in [('PolicyVersion',policy),('RiskDecision',decision),('OrderCommand',command),('OrderEvent',event)]:
  assert type(parse(name,make())).model_json_schema(mode='serialization')['additionalProperties'] is False

@pytest.mark.parametrize('change',[{'checks':[{'code':'check','passed':1}]},{'checks':[{'code':'check','passed':True}]*2},{'reason_codes':['pass','pass']},{'expires_at':'2026-01-01T00:00:00'},{'risk_amount':{'amount':1.0,'currency':'USD'}}])
def test_risk_review_invalid(change):
 with pytest.raises(ValidationError):parse('RiskDecision',decision()|change)
@pytest.mark.parametrize('change',[{'cum_fill_qty':'1','fill_evidence':'broker_reported','evidence_id':U[2]},{'cum_fill_qty':'1','fill_evidence':'broker_reported','broker_id':'broker'},{'evidence_id':U[2]},{'fill_evidence':'broker_reported','broker_id':'broker','evidence_id':U[2]}])
def test_fill_review_invalid(change):
 with pytest.raises(ValidationError):parse('OrderEvent',event()|change)
def test_source_clock_skew_and_history_remain_readable():
 assert parse('OrderEvent',event()|{'event_at':'2026-11-26T12:00:00Z'}).status=='unknown'
 assert parse('PolicyVersion',approved_policy()|{'status':'retired'}).status=='retired'
 assert parse('RiskDecision',decision()).expires_at.year==2026
