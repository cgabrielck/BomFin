import pytest
from uuid import UUID
from datetime import datetime,timezone,timedelta
from gabfin.contracts.identity import Principal,Resource,Capability
U=UUID('11111111-1111-4111-8111-111111111111')
def test_role_ceiling_and_ownership():
 from gabfin.api.capabilities import authorize
 p=Principal(schema_version='1.0',actor_id=U,role='chat',scope=['submit_order','read_report'])
 r=Resource(schema_version='1.0',kind='research_report',id=U,owner=U)
 with pytest.raises(PermissionError):authorize(p,Capability.SUBMIT_ORDER,r)
 authorize(p,Capability.READ_REPORT,r)
 with pytest.raises(PermissionError):authorize(p,Capability.READ_REPORT,r.model_copy(update={'owner':UUID(int=2)}))
def test_pairing_single_use_expiry_and_restart(tmp_path):
 from gabfin.api.sessions import SessionStore
 t=[datetime(2026,1,1,tzinfo=timezone.utc)]
 path=tmp_path/'auth.db';s=SessionStore(path,owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=3,clock=lambda:t[0]);code=s.create_pairing();token,csrf=s.issue_session(code)
 with pytest.raises(PermissionError):s.issue_session(code)
 s2=SessionStore(path,owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=3,clock=lambda:t[0]);assert s2.resolve(token).actor_id==U
 t[0]+=timedelta(seconds=61)
 with pytest.raises(PermissionError):s2.resolve(token)
def test_auth_boundary(tmp_path):
 from gabfin.api.sessions import SessionStore
 from gabfin.api.auth import validate_request
 s=SessionStore(tmp_path/'auth.db',owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=3)
 with pytest.raises(PermissionError):validate_request(s,None,origin='https://desk.test',allowed_origin='https://desk.test',write=False,query={'token':'fake'},csrf=None)
 token,csrf=s.issue_session(s.create_pairing())
 with pytest.raises(PermissionError):validate_request(s,token,origin='https://evil.test',allowed_origin='https://desk.test',write=False,query={},csrf=None)
 with pytest.raises(PermissionError):validate_request(s,token,origin='https://desk.test',allowed_origin='https://desk.test',write=True,query={},csrf='bad')
 assert validate_request(s,token,origin='https://desk.test',allowed_origin='https://desk.test',write=True,query={},csrf=csrf).actor_id==U
def test_real_http_and_ws_guards(tmp_path):
 from fastapi.testclient import TestClient
 from gabfin.api.auth import create_app
 from gabfin.api.sessions import SessionStore
 s=SessionStore(tmp_path/'auth.db',owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=3)
 client=TestClient(create_app(s,allowed_origin='https://desk.test'),base_url='https://desk.test')
 assert client.get('/session',headers={'Origin':'https://desk.test','X-Forwarded-For':'127.0.0.1'}).status_code==401
 response=client.post('/pair',json={'code':s.create_pairing()},headers={'Origin':'https://desk.test'})
 assert response.status_code==200
 cookie=response.headers['set-cookie'];assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie
 assert client.get('/session',headers={'Origin':'https://evil.test'}).status_code==401
 assert client.get('/session?token=fake',headers={'Origin':'https://desk.test'}).status_code==401
 assert client.get('/session',headers={'Origin':'https://desk.test'}).status_code==200
 from starlette.websockets import WebSocketDisconnect
 with pytest.raises(WebSocketDisconnect):
  with client.websocket_connect('/ws',headers={'Origin':'https://evil.test'}):pass
 assert client.post('/logout',headers={'Origin':'https://desk.test'}).status_code==401
 assert client.post('/logout',headers={'Origin':'https://desk.test','X-CSRF-Token':response.json()['csrf']}).status_code==200
 assert client.get('/session',headers={'Origin':'https://desk.test'}).status_code==401
def test_pairing_expiry_and_throttle(tmp_path):
 from gabfin.api.sessions import SessionStore
 t=[datetime(2026,1,1,tzinfo=timezone.utc)]
 s=SessionStore(tmp_path/'a.db',owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=2,clock=lambda:t[0])
 code=s.create_pairing();t[0]+=timedelta(seconds=11)
 with pytest.raises(PermissionError):s.issue_session(code)
 with pytest.raises(PermissionError):s.issue_session('invalid')
 with pytest.raises(PermissionError):s.issue_session(s.create_pairing())
def test_service_principal_from_trusted_store(tmp_path):
 from gabfin.api.sessions import SessionStore
 from gabfin.api.capabilities import authorize
 s=SessionStore(tmp_path/'a.db',owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=3)
 token,_=s.issue_service(actor_id=UUID(int=2),role='research',scope=['read_report'])
 p=s.resolve(token);assert p.role=='research'
 r=Resource(schema_version='1.0',kind='research_report',id=U,owner=UUID(int=2))
 authorize(p,Capability.READ_REPORT,r)
 with pytest.raises(PermissionError):authorize(p,Capability.SUBMIT_ORDER,r)
 with pytest.raises(PermissionError):s.issue_service(actor_id=U,role='chat',scope=['submit_order'])
def test_idle_websocket_expiry(tmp_path):
 from gabfin.api.sessions import SessionStore
 from gabfin.api.auth import create_app
 from fastapi.testclient import TestClient
 from starlette.websockets import WebSocketDisconnect
 s=SessionStore(tmp_path/'a.db',owner_id=U,session_seconds=1,pairing_seconds=10,max_failures=3)
 c=TestClient(create_app(s,allowed_origin='https://desk.test'),base_url='https://desk.test')
 c.post('/pair',json={'code':s.create_pairing()},headers={'Origin':'https://desk.test'})
 with c.websocket_connect('wss://desk.test/ws',headers={'Origin':'https://desk.test','Cookie':'gabfin_session='+c.cookies.get('gabfin_session')}) as ws:
  with pytest.raises(WebSocketDisconnect):ws.receive_json()
def test_wrong_resource_kind_rejected():
 from gabfin.api.capabilities import authorize
 p=Principal(schema_version='1.0',actor_id=U,role='chat',scope=['read_report'])
 r=Resource(schema_version='1.0',kind='order',id=U,owner=U)
 with pytest.raises(PermissionError):authorize(p,Capability.READ_REPORT,r)
def test_pairing_concurrent_single_use(tmp_path):
 from concurrent.futures import ThreadPoolExecutor
 from gabfin.api.sessions import SessionStore
 s=SessionStore(tmp_path/'a.db',owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=5)
 code=s.create_pairing()
 def attempt(_):
  try:s.issue_session(code);return True
  except PermissionError:return False
 with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(attempt,range(2)))==1
def test_same_origin_browser_get_without_origin_header(tmp_path):
 from gabfin.api.sessions import SessionStore
 from gabfin.api.auth import create_app
 from fastapi.testclient import TestClient
 s=SessionStore(tmp_path/'auth.db',owner_id=U,session_seconds=60,pairing_seconds=10,max_failures=3)
 c=TestClient(create_app(s,allowed_origin='https://desk.test'),base_url='https://desk.test')
 c.post('/pair',json={'code':s.create_pairing()},headers={'Origin':'https://desk.test'})
 assert c.get('/session').status_code==200
 assert c.post('/logout').status_code==401
