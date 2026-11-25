"""Local-only readiness CLI. No SDK import, authentication or entitlement claim."""
import importlib.util
import socket

def _sdk_present():return importlib.util.find_spec('futu') is not None

def _listener():
    try:
        with socket.create_connection(('127.0.0.1',11111),timeout=0.5):return True
    except OSError:return False

def readiness(*,sdk_check=_sdk_present,tcp_check=_listener,check_tcp=False):
    gates=[]
    try:sdk_present=sdk_check() is True
    except Exception:sdk_present=False;gates.append('sdk_check_failed')
    if not sdk_present:gates.append('sdk_unavailable')
    reachable=None
    if check_tcp:
        try:reachable=tcp_check() is True
        except Exception:reachable=False
        if not reachable:gates.append('opend_unreachable')
    else:gates.append('opend_not_checked')
    return {'sdk_present':sdk_present,'listener_reachable':reachable,'gates':gates,'features':{feature:'unverified' for feature in ('equity_quote','bar','option_chain','option_quote','pre_market','post_market')}}

def main():
    import argparse,json
    parser=argparse.ArgumentParser(description='Read-only local OpenD readiness; no entitlement verification')
    parser.add_argument('--check-tcp',action='store_true',help='Check only 127.0.0.1:11111, timeout 0.5s')
    args=parser.parse_args();result=readiness(check_tcp=args.check_tcp)
    print(json.dumps(result,indent=2))
    return 2 if result['gates'] else 0

if __name__=='__main__':raise SystemExit(main())
