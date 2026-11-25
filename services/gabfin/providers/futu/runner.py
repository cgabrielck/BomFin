"""Time-bounded SDK worker with discarded raw output and strict result parsing."""
from datetime import datetime,timezone
import ipaddress,json,math,os,subprocess,tempfile
from pathlib import Path

ERRORS={'quote_login_unknown','global_state_failed','quota_unknown','subscription_metadata_failed','context_close_failed'}
FIELDS={'checked_at','status','quote_logged_in','total_used_quota','remaining_quota','errors'}

def _validate(result):
    if not isinstance(result,dict) or set(result)!={'status','metadata'}:raise ValueError()
    if result['status'] in ('sdk_unavailable','worker_failed'):
        if result['metadata'] is not None:raise ValueError()
        return result
    if result['status']!='ok':raise ValueError()
    m=result['metadata']
    if not isinstance(m,dict) or set(m)!=FIELDS:raise ValueError()
    if m['status'] not in ('metadata_available','metadata_incomplete','quote_not_logged_in'):raise ValueError()
    if m['quote_logged_in'] is not None and type(m['quote_logged_in']) is not bool:raise ValueError()
    for field in ('total_used_quota','remaining_quota'):
        v=m[field]
        if v is not None and (type(v) is not int or not 0<=v<=9007199254740991):raise ValueError()
    errors=m['errors']
    if not isinstance(errors,list) or any(type(e) is not str or e not in ERRORS for e in errors):raise ValueError()
    t=datetime.fromisoformat(m['checked_at'])
    if t.tzinfo is None:raise ValueError()
    m['checked_at']=t.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    if m['status']=='metadata_available' and (m['quote_logged_in'] is not True or errors or m['total_used_quota'] is None or m['remaining_quota'] is None):raise ValueError()
    if m['status']=='quote_not_logged_in' and m['quote_logged_in'] is not False:raise ValueError()
    return result

def run_probe(python:Path,*,host:str,port:int,timeout:float,encrypted=False,rsa_file=None,_worker=None):
    def failure(status):return {'status':status,'metadata':None}
    try:
        ip=ipaddress.ip_address(host)
        if ip.is_unspecified or ip.is_multicast or type(port) is not int or not 1<=port<=65535:raise ValueError()
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=120:raise ValueError()
        if type(encrypted) is not bool or (not ip.is_loopback and not encrypted):raise ValueError()
        key=str(Path(rsa_file).resolve(strict=True)) if rsa_file is not None else None
        if encrypted and key is None:raise ValueError()
        executable=Path(python).resolve(strict=True)
        worker=Path(_worker).resolve(strict=True) if _worker else Path(__file__).with_name('worker.py').resolve()
    except (ValueError,TypeError,OSError):return failure('invalid_config')
    with tempfile.TemporaryDirectory(prefix='gabfin-quote-') as folder:
        output=Path(folder)/'result.json'
        env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','COMSPEC')}
        env.update(TEMP=folder,TMP=folder,APPDATA=folder,LOCALAPPDATA=folder,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        config={'host':str(ip),'port':port,'encrypted':encrypted,'rsa_file':key}
        try:
            subprocess.run([str(executable),'-I',str(worker),str(output)],input=json.dumps(config).encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,cwd=folder,timeout=timeout,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:return failure('timeout')
        except (OSError,subprocess.CalledProcessError):return failure('worker_failed')
        try:
            if output.stat().st_size>16384:return failure('invalid_result')
            return _validate(json.loads(output.read_text(encoding='utf-8')))
        except (OSError,ValueError,TypeError,KeyError,OverflowError):return failure('invalid_result')

def main():
    import argparse
    p=argparse.ArgumentParser(description='Bounded quote-only OpenD metadata probe')
    p.add_argument('--python',required=True,type=Path);p.add_argument('--host',required=True);p.add_argument('--port',required=True,type=int);p.add_argument('--timeout',type=float,default=10)
    p.add_argument('--encrypted',action='store_true');p.add_argument('--rsa-file',type=Path)
    a=p.parse_args();r=run_probe(a.python,host=a.host,port=a.port,timeout=a.timeout,encrypted=a.encrypted,rsa_file=a.rsa_file)
    print(json.dumps(r,indent=2));return 0 if r['status']=='ok' and r['metadata']['status']=='metadata_available' else 2
if __name__=='__main__':raise SystemExit(main())
