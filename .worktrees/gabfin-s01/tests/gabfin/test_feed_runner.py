import json,sys,time
from pathlib import Path
import pytest

def worker(tmp_path,body):
 p=tmp_path/'fake.py';p.write_text('import sys,json,time,os\nfrom pathlib import Path\n'+body,encoding='utf-8');return p

def invoke(script,**kw):
 from gabfin.providers.futu.runner import run_probe
 return run_probe(Path(sys.executable),host='127.0.0.1',port=11111,timeout=3,_worker=script,**kw)

def test_timeout_kills_and_reaps(tmp_path):
 s=worker(tmp_path,"print('PRIVATE',flush=True)\ntime.sleep(30)\n")
 from gabfin.providers.futu.runner import run_probe
 start=time.monotonic();r=run_probe(Path(sys.executable),host='127.0.0.1',port=11111,timeout=.2,_worker=s)
 assert r=={'status':'timeout','metadata':None} and time.monotonic()-start<10

@pytest.mark.parametrize('body',["raise RuntimeError('PRIVATE')", "Path(sys.argv[1]).write_text('PRIVATE')", "Path(sys.argv[1]).write_text('x'*20000)"])
def test_failure_never_echoes_raw(tmp_path,body):
 r=invoke(worker(tmp_path,body));assert r['status'] in ('worker_failed','invalid_result') and 'PRIVATE' not in json.dumps(r)

def metadata():return dict(checked_at='2026-11-25T12:00:00Z',status='metadata_available',quote_logged_in=True,total_used_quota=1,remaining_quota=0,errors=[])

def test_safe_result_and_stdout_discard(tmp_path,capsys):
 p={'status':'ok','metadata':metadata()};s=worker(tmp_path,"print('PRIVATE')\nprint('PRIVATE',file=sys.stderr)\nPath(sys.argv[1]).write_text("+repr(json.dumps(p))+ ")\n")
 assert invoke(s)==p
 captured=capsys.readouterr();assert 'PRIVATE' not in captured.out+captured.err

@pytest.mark.parametrize('change',[{'account':'PRIVATE'},{'remaining_quota':True},{'errors':['PRIVATE']},{'quote_logged_in':'true'},{'checked_at':'PRIVATE'},{'status':'PRIVATE'}])
def test_untrusted_child_output_revalidated(tmp_path,change):
 p={'status':'ok','metadata':metadata()|change};s=worker(tmp_path,'Path(sys.argv[1]).write_text('+repr(json.dumps(p))+')')
 assert invoke(s)=={'status':'invalid_result','metadata':None}

@pytest.mark.parametrize('host,port,timeout',[('invalid',11111,3),('127.0.0.1',0,3),('127.0.0.1',True,3),('127.0.0.1',11111,0),('127.0.0.1',11111,float('nan')),('192.168.1.2',11111,3)])
def test_invalid_configuration_no_spawn(host,port,timeout):
 from gabfin.providers.futu.runner import run_probe
 assert run_probe(Path(sys.executable),host=host,port=port,timeout=timeout)['status']=='invalid_config'

def test_secret_environment_not_inherited(tmp_path,monkeypatch):
 monkeypatch.setenv('OPENAI_API_KEY','PRIVATE');s=worker(tmp_path,"assert 'OPENAI_API_KEY' not in os.environ\nPath(sys.argv[1]).write_text('{\"status\":\"sdk_unavailable\",\"metadata\":null}')")
 assert invoke(s)['status']=='sdk_unavailable'
def test_timeout_process_is_no_longer_alive(tmp_path):
 import os
 from gabfin.providers.futu.runner import run_probe
 pidfile=tmp_path/'pid'
 s=worker(tmp_path,'Path('+repr(str(pidfile))+').write_text(str(os.getpid()))\ntime.sleep(30)')
 assert run_probe(Path(sys.executable),host='127.0.0.1',port=11111,timeout=2,_worker=s)['status']=='timeout'
 pid=int(pidfile.read_text())
 if os.name=='nt':
  import ctypes
  from ctypes import wintypes
  api=ctypes.WinDLL('kernel32',use_last_error=True)
  api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];api.OpenProcess.restype=wintypes.HANDLE
  handle=api.OpenProcess(0x1000,False,pid)
  if handle:
   code=wintypes.DWORD();assert api.GetExitCodeProcess(handle,ctypes.byref(code))
   api.CloseHandle(handle);assert code.value!=259
 else:
  with pytest.raises(ProcessLookupError):os.kill(pid,0)
@pytest.mark.parametrize('p',[
 {'status':'ok','metadata':metadata()|{'checked_at':'2026-11-25T12:00:00'}},
 {'status':'ok','metadata':metadata()|{'quote_logged_in':False}},
 {'status':'sdk_unavailable','metadata':{'account':'PRIVATE'}},
 {'status':'ok','metadata':metadata(),'account':'PRIVATE'},
])
def test_inconsistent_result_is_not_accepted(tmp_path,p):
 s=worker(tmp_path,'Path(sys.argv[1]).write_text('+repr(json.dumps(p))+')')
 assert invoke(s)['status']=='invalid_result'
def test_main_environment_still_has_no_sdk():
 import importlib.util
 assert importlib.util.find_spec('futu') is None
def test_real_worker_missing_sdk_returns_safe_gate():
 from gabfin.providers.futu.runner import run_probe
 r=run_probe(Path(sys.executable),host='127.0.0.1',port=11111,timeout=5)
 assert r=={'status':'sdk_unavailable','metadata':None}
