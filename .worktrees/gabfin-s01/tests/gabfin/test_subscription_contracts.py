"""Feed metadata does not enable trading or allocate subscriptions."""
import json
import pytest
from pydantic import ValidationError
U='11111111-1111-4111-8111-111111111111'
T='2026-11-25T12:00:00Z'
def key(channel='quote',tf=None):return dict(instrument_id=U,channel=channel,timeframe=tf)
def cap():return dict(schema_version='1.0',source='test',asset_classes=['equity'],sessions=['regular'],latency_label='unknown',max_subscriptions=None,history_limits=[],checked_at=T,permission_errors=[])
def plan():return dict(schema_version='1.0',source='test',as_of=T,accepted=[key()],rejected=[dict(key=key('trade'),reason_codes=['quota'])])
def parse(name,p):
 from gabfin.contracts import subscriptions
 return getattr(subscriptions,name).model_validate_json(json.dumps(p))
@pytest.mark.parametrize('name,p',[('SubscriptionKey',key()),('SubscriptionKey',key('bar',{'count':1,'unit':'trading_day'})),('FeedCapabilities',cap()),('SubscriptionPlan',plan()),('Demand',dict(schema_version='1.0',demand_id=U,key=key(),priority='holding',owner=U,expires_at=T))])
def test_roundtrip(name,p):
 r=parse(name,p);assert type(r).model_validate_json(r.model_dump_json())==r
@pytest.mark.parametrize('p',[key('bar'),key('quote',{'count':1,'unit':'minute'}),key('trade',{'count':1,'unit':'minute'}),key('option_chain'),key('bar',{'count':0,'unit':'minute'})])
def test_invalid_key(p):
 with pytest.raises(ValidationError):parse('SubscriptionKey',p)
@pytest.mark.parametrize('value',[0,None,100])
def test_quota_unknown_zero_distinct(value):assert parse('FeedCapabilities',cap()|{'max_subscriptions':value}).max_subscriptions==value
@pytest.mark.parametrize('value',[-1,True,1.5,'100',9007199254740992])
def test_bad_quota(value):
 with pytest.raises(ValidationError):parse('FeedCapabilities',cap()|{'max_subscriptions':value})
@pytest.mark.parametrize('change',[{'asset_classes':['equity','equity']},{'sessions':['regular','regular']},{'permission_errors':['denied','denied']},{'checked_at':'2026-01-01T00:00:00'},{'latency_label':'live'},{'source':' test'},{'enabled':True}])
def test_bad_capabilities(change):
 with pytest.raises(ValidationError):parse('FeedCapabilities',cap()|change)
@pytest.mark.parametrize('change',[{'accepted':[key(),key()]},{'rejected':[dict(key=key('trade'),reason_codes=['quota'])]*2},{'rejected':[dict(key=key(),reason_codes=['quota'])]},{'rejected':[dict(key=key('trade'),reason_codes=[])]},{'rejected':[dict(key=key('trade'),reason_codes=['x','x'])]}])
def test_plan_identity_consistency(change):
 with pytest.raises(ValidationError):parse('SubscriptionPlan',plan()|change)
def test_distinct_bar_timeframes_and_empty_plan():
 p=plan()|{'accepted':[key('bar',{'count':1,'unit':'minute'}),key('bar',{'count':5,'unit':'minute'})]}
 assert len(parse('SubscriptionPlan',p).accepted)==2
 assert not parse('SubscriptionPlan',plan()|{'accepted':[],'rejected':[]}).accepted
@pytest.mark.parametrize('count',[None,0,10])
def test_history_limits(count):
 p=cap()|{'history_limits':[dict(channel='bar',timeframe={'count':1,'unit':'minute'},max_records=count)]}
 assert parse('FeedCapabilities',p).history_limits[0].max_records==count
 p['history_limits']*=2
 with pytest.raises(ValidationError):parse('FeedCapabilities',p)
@pytest.mark.parametrize('change',[{'priority':1},{'priority':'urgent'},{'owner':'bad'},{'expires_at':'2026-01-01T00:00:00'}])
def test_demand_metadata_validation(change):
 p=dict(schema_version='1.0',demand_id=U,key=key(),priority='holding',owner=U,expires_at=T)
 with pytest.raises(ValidationError):parse('Demand',p|change)

def test_normalized_uuid_overlap_rejected():
 p=plan();p['rejected']=[dict(key=key()|{'instrument_id':U.replace('-','')},reason_codes=['denied'])]
 with pytest.raises(ValidationError):parse('SubscriptionPlan',p)
def test_same_channel_different_instrument_is_distinct():
 p=plan()|{'accepted':[key(),key()|{'instrument_id':'22222222-2222-4222-8222-222222222222'}]}
 assert len(parse('SubscriptionPlan',p).accepted)==2
@pytest.mark.parametrize('p',[dict(channel='quote',timeframe={'count':1,'unit':'minute'},max_records=10),dict(channel='bar',timeframe=None,max_records=10),dict(channel='trade',timeframe=None,max_records=True)])
def test_bad_history_shape(p):
 with pytest.raises(ValidationError):parse('FeedCapabilities',cap()|{'history_limits':[p]})
def test_observed_overnight_is_not_trading_permission():
 r=parse('FeedCapabilities',cap()|{'sessions':['overnight'],'permission_errors':['denied']})
 assert r.sessions[0]=='overnight' and r.permission_errors==('denied',)
def test_schemas_and_no_computed_identity_on_wire():
 for name,p in [('FeedCapabilities',cap()),('SubscriptionPlan',plan()),('SubscriptionKey',key())]:
  r=parse(name,p);assert type(r).model_json_schema(mode='serialization')['additionalProperties'] is False
  assert 'identity' not in json.loads(r.model_dump_json())
