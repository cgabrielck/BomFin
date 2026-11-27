from datetime import datetime,timezone
from uuid import UUID
import pytest
from pydantic import ValidationError
U='11111111-1111-4111-8111-111111111111'
T='2026-11-25T12:00:00Z'
def test_model_unknown_cost_and_failure():
 from gabfin.contracts.support import ModelResult
 p=dict(schema_version='1.0',request_id=U,model='fake',output=None,error='timeout',usage=dict(input_tokens=None,output_tokens=None,cost=None,cost_state='unknown'))
 assert ModelResult.model_validate(p).output is None
 with pytest.raises(ValidationError):ModelResult.model_validate(p|{'error':None})
def test_candidate_expiry():
 from gabfin.contracts.support import CandidateObservation
 p=dict(schema_version='1.0',observation_id=U,instrument=U,reason='event',evidence=[U],horizon={'kind':'unspecified','reason':'unknown'},observed_at=T,expires_at=T,action='include')
 with pytest.raises(ValidationError):CandidateObservation.model_validate(p)
def test_strategy_future_bar_rejected(bar_payload):
 from gabfin.contracts.support import StrategyContext
 from gabfin.contracts.market import Bar
 p=dict(schema_version="1.0",as_of="2026-11-23T12:00:00Z",finalized_bars=[bar_payload],features={},account_snapshot_id=U,strategy_version="v1",policy_version="p1")
 with pytest.raises(ValidationError):StrategyContext.model_validate(p)
def test_reconciliation_cannot_allow_mismatch():
 from gabfin.contracts.support import ReconciliationResult
 with pytest.raises(ValidationError):ReconciliationResult(schema_version='1.0',matched=False,mismatches=['missing'],entry_allowed=True)
def test_proposal_unapproved_by_default():
 from gabfin.contracts.support import HarnessProposal
 assert 'approval' in HarnessProposal.model_fields

@pytest.mark.parametrize('output,error',[(None,None),({},'failed')])
def test_model_outcome_exclusive(output,error):
 from gabfin.contracts.support import ModelResult
 with pytest.raises(ValidationError):ModelResult(schema_version='1.0',request_id=U,model='fake',output=output,error=error,usage=dict(input_tokens=None,output_tokens=None,cost=None,cost_state='unknown'))
def test_proposal_hash_is_digest():
 from gabfin.contracts.support import HarnessProposal
 with pytest.raises(ValidationError):HarnessProposal(schema_version='1.0',proposal_id=U,artifact_hash='not-a-digest',base_version='v1',deploy_version='v2',diff='change',experiment_ids=[U],metrics={},rollback_version='v1',approval=None)
@pytest.mark.parametrize('name,p,change',[
 ('SubmitResult',dict(schema_version='1.0',status='UNKNOWN',client_order_id=U,broker_id=None,reason='timeout'),{'status':'ACKNOWLEDGED'}),
 ('ExperimentSpec',dict(schema_version='1.0',experiment_id=U,strategy_version='v1',dataset_manifest='hash',start=T,end='2026-11-26T12:00:00Z',session_policy=['regular'],execution_assumptions=['spread']),{'end':T}),
 ('HealthReport',dict(schema_version='1.0',component='test',heartbeat_at=T,state='unknown',last_error_code=None,lag_ms=None,dependency_health={}),{'lag_ms':True}),
 ('ReconciliationResult',dict(schema_version='1.0',matched=True,mismatches=[],entry_allowed=False),{'mismatches':['unknown order']}),
 ('ModelRequest',dict(schema_version='1.0',request_id=U,model='fake',output_schema={'type':'object'},messages=[{'role':'user','content':'Research'}],evidence_refs=[U],deadline=T),{'messages':[]})])
def test_support_roundtrip_and_rejection(name,p,change):
 from gabfin.contracts import support
 cls=getattr(support,name);r=cls.model_validate(p);assert cls.model_validate_json(r.model_dump_json())==r
 with pytest.raises(ValidationError):cls.model_validate(p|change)
