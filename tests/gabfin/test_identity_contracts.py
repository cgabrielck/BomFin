"""Identity declarations are untrusted until resolved by server auth."""
import json
import pytest
from pydantic import ValidationError
U='11111111-1111-4111-8111-111111111111'
CAPS=['read_account','resolve_symbols','start_research','read_report','draft_trade_plan','read_market','manage_watchlist','propose_strategy','strategy:emit','submit_order','cancel_order','start_worker','pause_worker','resume_worker','write_policy','approve_proposal']
def principal():return dict(schema_version='1.0',actor_id=U,role='chat',scope=['read_report'])
def resource():return dict(schema_version='1.0',kind='research_report',id=U,owner=U)
def parse(name,p):
 from gabfin.contracts import identity
 return getattr(identity,name).model_validate_json(json.dumps(p))
@pytest.mark.parametrize('role',['owner','chat','research','strategy','executor'])
def test_role_roundtrip(role):
 r=parse('Principal',principal()|{'role':role,'scope':[]});assert r.scope==()
 assert type(r).model_validate_json(r.model_dump_json())==r
@pytest.mark.parametrize('capability',CAPS)
def test_capability_names(capability):assert parse('Principal',principal()|{'scope':[capability]}).scope[0]==capability
@pytest.mark.parametrize('change',[{'actor_id':'bad'},{'actor_id':True},{'role':'operator'},{'role':'OWNER'},{'scope':['*']},{'scope':['read_report','read_report']},{'scope':['strategy:emit','submit_order','*']},{'scope':None},{'role':None},{'scope':[1]},{'scope':[' read_report']},{'session_token':'fake'},{'source_ip':'127.0.0.1'},{'forwarded_for':'127.0.0.1'}])
def test_bad_principal(change):
 with pytest.raises(ValidationError):parse('Principal',principal()|change)
def test_scope_is_required_and_no_default_grants():
 p=principal();p.pop('scope')
 with pytest.raises(ValidationError):parse('Principal',p)
 assert not parse('Principal',principal()|{'role':'owner','scope':[]}).scope
@pytest.mark.parametrize('kind',['account','instrument','research_job','research_report','watchlist','order','strategy','policy','proposal','artifact'])
def test_resource_kinds(kind):
 r=parse('Resource',resource()|{'kind':kind});assert type(r).model_validate_json(r.model_dump_json())==r
@pytest.mark.parametrize('change',[{'kind':'anything'},{'owner':None},{'owner':'localhost'},{'id':'AAPL'},{'owner':1},{'authenticated':True}])
def test_bad_resource(change):
 with pytest.raises(ValidationError):parse('Resource',resource()|change)
def test_resource_requires_owner():
 p=resource();p.pop('owner')
 with pytest.raises(ValidationError):parse('Resource',p)
def test_metadata_does_not_authenticate():
 r=parse('Principal',principal()|{'scope':['submit_order']})
 assert not hasattr(r,'authorize') and not hasattr(r,'authenticated')
def test_schemas():
 for name,p in [('Principal',principal()),('Resource',resource())]:
  schema=type(parse(name,p)).model_json_schema(mode='serialization')
  assert schema['additionalProperties'] is False and 'schema_version' in schema['required']
