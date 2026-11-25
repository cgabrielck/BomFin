"""Internal SDK worker. Raw SDK output never forms the result channel."""
import json,logging,sys
from pathlib import Path
from datetime import datetime,timezone

def main():
    logging.disable(logging.CRITICAL)
    output=Path(sys.argv[1])
    result={'status':'worker_failed','metadata':None}
    try:
        config=json.loads(sys.stdin.buffer.read(8192))
        sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
        from gabfin.providers.futu.capabilities import inspect_quote_context
        try:
            from futu import OpenQuoteContext,SysConfig
        except ImportError:
            result={'status':'sdk_unavailable','metadata':None}
        else:
            SysConfig.enable_console_log(False)
            if config['encrypted']:
                SysConfig.enable_proto_encrypt(True)
                SysConfig.set_init_rsa_file(config['rsa_file'])
            context=OpenQuoteContext(host=config['host'],port=config['port'],is_encrypt=config['encrypted'])
            result={'status':'ok','metadata':inspect_quote_context(context,checked_at=datetime.now(timezone.utc))}
    except Exception:
        result={'status':'worker_failed','metadata':None}
    output.write_text(json.dumps(result),encoding='utf-8')
if __name__=='__main__':main()
