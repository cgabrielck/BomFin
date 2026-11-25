"""Lease and reservation shape tests; no scheduler or budget mutations."""
import json
import pytest
from pydantic import ValidationError
U='11111111-1111-4111-8111-111111111111'
T='2026-11-25T12:00:00Z'
def lease():return dict(schema_version='1.0',job_id=U,worker_id=U,lease_token=U,acquired_at=T,expires_at='2026-11-25T12:01:00Z',attempt=1)
def reservation():return dict(schema_version='1.0',reservation_id=U,budget_id=U,job_id=U,amount='0.10',currency='USD',status='reserved',actual_amount=None,created_at=T,updated_at=T)
def parse(name,p):
 from gabfin.contracts import jobs
 return getattr(jobs,name).model_validate_json(json.dumps(p))
@pytest.mark.parametrize('name,p',[('JobLease',lease()),('Reservation',reservation())])
def test_roundtrip(name,p):
 r=parse(name,p);assert type(r).model_validate_json(r.model_dump_json())==r
@pytest.mark.parametrize('attempt',[0,-1,True,1.5,'1',9007199254740992])
def test_attempt_strict_positive(attempt):
 with pytest.raises(ValidationError):parse('JobLease',lease()|{'attempt':attempt})
@pytest.mark.parametrize('change',[{'job_id':'job'},{'worker_id':True},{'lease_token':''},{'lease_token':'secret-token'},{'expires_at':T},{'expires_at':'2026-11-24T12:00:00Z'},{'acquired_at':'2026-11-25T12:00:00'},{'expires_at':123},{'owner':'fake'}])
def test_bad_lease(change):
 with pytest.raises(ValidationError):parse('JobLease',lease()|change)
def test_token_not_in_repr_but_internal_wire_contains_it():
 p=lease();p['lease_token']='22222222-2222-4222-8222-222222222222';r=parse('JobLease',p)
 assert p['lease_token'] not in repr(r)
 assert json.loads(r.model_dump_json())['lease_token']==p['lease_token']
def test_historical_lease_is_readable():assert parse('JobLease',lease()|{'acquired_at':'2000-01-01T00:00:00Z','expires_at':'2000-01-01T00:01:00Z'}).attempt==1
@pytest.mark.parametrize('status',['reserved','released','unknown'])
def test_unsettled_cost_stays_unknown(status):
 r=parse('Reservation',reservation()|{'status':status});assert r.actual_amount is None
 assert json.loads(r.model_dump_json())['amount']=='0.10'
@pytest.mark.parametrize('actual',['0','0.10','0.25'])
def test_settlement_zero_exact_and_overrun(actual):
 r=parse('Reservation',reservation()|{'status':'settled','actual_amount':actual})
 assert json.loads(r.model_dump_json())['actual_amount']==actual
@pytest.mark.parametrize('status',['reserved','released','unknown'])
def test_unsettled_cannot_claim_actual(status):
 with pytest.raises(ValidationError):parse('Reservation',reservation()|{'status':status,'actual_amount':'0'})
@pytest.mark.parametrize('change',[{'status':'settled'},{'status':'failed'},{'amount':None},{'amount':'-1'},{'amount':0.1},{'amount':True},{'amount':'NaN'},{'currency':'usd'},{'budget_id':'monthly'},{'actual_amount':'-1','status':'settled'},{'actual_amount':0.1,'status':'settled'},{'updated_at':'2026-11-24T12:00:00Z'},{'created_at':'2026-11-25T12:00:00'},{'approved_cap':'100'}])
def test_bad_reservation(change):
 with pytest.raises(ValidationError):parse('Reservation',reservation()|change)
def test_zero_reservation_is_explicit_and_precision_preserved():
 assert parse('Reservation',reservation()|{'amount':'0'}).amount==0
 assert json.loads(parse('Reservation',reservation()|{'amount':'0.10000000000000000001'}).model_dump_json())['amount']=='0.10000000000000000001'
@pytest.mark.parametrize('name,p,field',[('JobLease',lease(),'lease_token'),('JobLease',lease(),'attempt'),('Reservation',reservation(),'actual_amount'),('Reservation',reservation(),'amount')])
def test_required_fields(name,p,field):
 p=p.copy();p.pop(field)
 with pytest.raises(ValidationError):parse(name,p)
def test_schemas():
 for name,p in [('JobLease',lease()),('Reservation',reservation())]:assert type(parse(name,p)).model_json_schema(mode='serialization')['additionalProperties'] is False

@pytest.mark.parametrize('name,p,field',[('JobLease',lease(),'acquired_at'),('JobLease',lease(),'expires_at'),('Reservation',reservation(),'created_at'),('Reservation',reservation(),'updated_at')])
def test_offset_normalizes_to_utc(name,p,field):
 p=p.copy();p[field]='2026-11-25T20:00:00+08:00'
 if name=='JobLease' and field=='expires_at':p[field]='2026-11-25T20:01:00+08:00'
 r=parse(name,p);assert json.loads(r.model_dump_json())[field].endswith('Z')
@pytest.mark.parametrize('value',['Infinity','NaN',True,'-0.01'])
def test_actual_amount_review(value):
 with pytest.raises(ValidationError):parse('Reservation',reservation()|{'status':'settled','actual_amount':value})
