"""Research documents preserve provenance, uncertainty and reference integrity."""
from copy import deepcopy
import json
import pytest
from pydantic import ValidationError, TypeAdapter

U = [f'{i:08}-1111-4111-8111-111111111111' for i in range(1,12)]
T = '2026-11-25T12:00:00Z'

def payload():
    return dict(schema_version='1.0',report_id=U[0],request_id=U[1],snapshot_id=U[2],horizon={'kind':'duration','count':10,'unit':'trading_day'},evidence=[dict(schema_version='1.0',evidence_id=U[3],url='https://example.com/filing',artifact_id=None,publisher='Issuer',original_firm=None,published_at=None,first_seen_at=T,available_at=T,content_hash='a'*64,license_tag='unknown')],citations=[dict(citation_id=U[4],evidence_id=U[3],locator='page 2')],facts=[dict(fact_id=U[5],text='Revenue reported',citation_ids=[U[4]])],inferences=[dict(inference_id=U[6],text='Demand may improve',fact_ids=[U[5]],citation_ids=[],assumptions=['Stable currency'],counterevidence=[])],missing_data=[],summary=dict(why_now='New filing',disposition='watch',conditions=['Compare next quarter'],invalidation=['Demand reverses']),completeness='complete',as_of=T,generated_at=T,model_version='fake-v1',prompt_version='v1',usage=dict(input_tokens=None,output_tokens=None,cost=None,cost_state='unknown'))

def parse(data):
    from gabfin.contracts.research import ResearchReport
    return ResearchReport.model_validate_json(json.dumps(data))

def test_report_roundtrip_and_shared_evidence():
    p=payload();p['facts'].append(dict(fact_id=U[7],text='Another fact',citation_ids=[U[4]]))
    r=parse(p);assert len(r.evidence)==1
    assert type(r).model_validate_json(r.model_dump_json())==r
    assert r.evidence[0].published_at is None

@pytest.mark.parametrize('h',[{'kind':'duration','count':3,'unit':u} for u in ['minute','hour','calendar_day','trading_day','week','month','year']]+[{'kind':'event','name':'Earnings','expected_at':None,'window':None},{'kind':'unspecified','reason':'Question needs clarification'}])
def test_horizon_variants(h):
    p=payload();p['horizon']=h;assert parse(p).horizon.kind==h['kind']

@pytest.mark.parametrize('count',[0,-1,True,1.5,'3',9007199254740992])
def test_invalid_duration(count):
    p=payload();p['horizon']['count']=count
    with pytest.raises(ValidationError):parse(p)

@pytest.mark.parametrize('collection',['evidence','citations','facts','inferences'])
def test_duplicate_ids(collection):
    p=payload();p[collection].append(deepcopy(p[collection][0]))
    with pytest.raises(ValidationError):parse(p)

@pytest.mark.parametrize('where',['evidence','fact','inference','counter','duplicate_ref'])
def test_bad_references(where):
    p=payload()
    if where=='evidence':p['citations'][0]['evidence_id']=U[10]
    if where=='fact':p['facts'][0]['citation_ids']=[U[10]]
    if where=='inference':p['inferences'][0]['fact_ids']=[U[10]]
    if where=='counter':p['inferences'][0]['counterevidence']=[U[10]]
    if where=='duplicate_ref':p['facts'][0]['citation_ids']*=2
    with pytest.raises(ValidationError):parse(p)

@pytest.mark.parametrize('mutation',['future','capture','naive','hash','source','extra','unsupported','empty','partial','complete_missing','cost','known','negative','bool_tokens'])
def test_invalid_report(mutation):
    p=payload();e=p['evidence'][0]
    if mutation=='future':e['available_at']='2026-11-26T12:00:00Z'
    if mutation=='capture':e['first_seen_at']='2026-11-26T12:00:00Z'
    if mutation=='naive':p['as_of']='2026-11-25T12:00:00'
    if mutation=='hash':e['content_hash']='xyz'
    if mutation=='source':e['url']=None
    if mutation=='extra':p['submit_order']=True
    if mutation=='unsupported':p['facts'][0]['citation_ids']=[]
    if mutation=='empty':p['facts']=[];p['inferences']=[]
    if mutation=='partial':p['completeness']='partial'
    if mutation=='complete_missing':p['missing_data']=[dict(code='missing',description='No estimate',affected_conclusions=['Valuation'])]
    if mutation=='cost':p['usage']['cost']={'amount':'0.1','currency':'USD'}
    if mutation=='known':p['usage']['cost_state']='known'
    if mutation=='negative':p['usage']['input_tokens']=-1
    if mutation=='bool_tokens':p['usage']['input_tokens']=True
    with pytest.raises(ValidationError):parse(p)

def test_honest_partial_empty_report():
    p=payload();p.update(evidence=[],facts=[],inferences=[],citations=[],completeness='partial',missing_data=[dict(code='unavailable',description='Source missing',affected_conclusions=['No thesis possible'])]);p['summary']['disposition']='insufficient_evidence'
    assert parse(p).completeness=='partial'

def test_known_cost_exact():
    p=payload();p['usage'].update(cost_state='known',cost={'amount':'0.10','currency':'USD'})
    assert json.loads(parse(p).model_dump_json())['usage']['cost']['amount']=='0.10'

def test_request_identity_and_deadline():
    from gabfin.contracts.research import ResearchRequest
    p=dict(schema_version='1.0',request_id=U[0],instruments=[U[1]],question='Compare catalysts',horizon={'kind':'unspecified','reason':'Unknown'},actor_id=U[2],capability_scope=['research:read'],snapshot_id=U[3],budget_id=U[4],as_of=T,deadline='2026-11-25T12:01:00Z')
    assert ResearchRequest.model_validate(p).question=='Compare catalysts'
    for change in [dict(instruments=[]),dict(instruments=[U[1],U[1]]),dict(deadline=T),dict(capability_scope=[])]:
        with pytest.raises(ValidationError):ResearchRequest.model_validate(p|change)

def test_schema_generation():
    from gabfin.contracts.research import ResearchReport, ResearchRequest, EvidenceItem
    for cls in (ResearchReport,ResearchRequest,EvidenceItem):
        schema=cls.model_json_schema(mode='serialization');assert schema['additionalProperties'] is False

@pytest.mark.parametrize('mutation',['credentials','generation','insufficient','inference','cost_negative','cost_float','naive_event','unknown_extra'])
def test_review_boundaries(mutation):
    p=payload()
    if mutation=='credentials':p['evidence'][0]['url']='https://user:secret@example.com/a'
    if mutation=='generation':p['generated_at']='2026-11-24T12:00:00Z'
    if mutation=='insufficient':p['summary']['disposition']='insufficient_evidence'
    if mutation=='inference':p['inferences'][0]['fact_ids']=[]
    if mutation=='cost_negative':p['usage'].update(cost_state='known',cost={'amount':'-1','currency':'USD'})
    if mutation=='cost_float':p['usage'].update(cost_state='known',cost={'amount':0.1,'currency':'USD'})
    if mutation=='naive_event':p['horizon']={'kind':'event','name':'Earnings','expected_at':'2026-12-01T12:00:00'}
    if mutation=='unknown_extra':p['horizon']={'kind':'unspecified','reason':'Unknown','count':3}
    with pytest.raises(ValidationError):parse(p)
