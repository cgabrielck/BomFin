"""Internal SDK worker. Raw SDK output never forms the result channel."""
import json,logging,sys
from pathlib import Path
from datetime import datetime,timezone

def main():
    logging.disable(logging.CRITICAL)
    output=Path(sys.argv[1])
    result={'status':'worker_failed','metadata':None}
    context=None
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
            if config.get('operation')=='history_smoke':
                from futu import Session,KLType,AuType,KL_FIELD
                from futu.common.pb.Qot_Common_pb2 import QotMarket_US_Security
                from futu.quote.quote_query import RequestHistoryKlineQuery
                from importlib.metadata import version
                from types import SimpleNamespace
                from gabfin.providers.futu.history import inspect_history
                from gabfin.providers.futu.history_wire import SinglePageHistoryContext
                if version('futu-api')!='10.12.7208':raise ValueError('unsupported_history_sdk')
                context.set_sync_query_connect_timeout(3)
                sdk=SimpleNamespace(RTH=Session.RTH,ETH=Session.ETH,K_1M=KLType.K_1M,NONE=AuType.NONE,
                                    FIELDS=[KL_FIELD.DATE_TIME,KL_FIELD.OPEN,KL_FIELD.HIGH,KL_FIELD.LOW,KL_FIELD.CLOSE])
                history_context=SinglePageHistoryContext(context,pack_request=RequestHistoryKlineQuery.pack_req,us_market=QotMarket_US_Security)
                result={'status':'ok','metadata':inspect_history(history_context,sdk,deadline=config['deadline_monotonic'])}
            elif config.get('operation')=='options_smoke':
                from futu import SubType,Session,OptionType
                from types import SimpleNamespace
                from gabfin.providers.futu.options import inspect_options
                sdk=SimpleNamespace(QUOTE=SubType.QUOTE,RTH=Session.RTH,ALL=OptionType.ALL)
                result={'status':'ok','metadata':inspect_options(context,sdk,deadline=config['deadline_monotonic'])}
            elif config.get('operation')=='equity_smoke':
                from futu import Market,SecurityType,SubType,AuType,Session
                from types import SimpleNamespace
                from gabfin.providers.futu.equity import inspect_equity
                sdk=SimpleNamespace(US=Market.US,STOCK=SecurityType.STOCK,QUOTE=SubType.QUOTE,K_DAY=SubType.K_DAY,NONE=AuType.NONE,RTH=Session.RTH)
                result={'status':'ok','metadata':inspect_equity(context,sdk)}
            else:
                result={'status':'ok','metadata':inspect_quote_context(context,checked_at=datetime.now(timezone.utc))}
    except Exception:
        if context is not None:
            try:context.close()
            except Exception:pass
        result={'status':'worker_failed','metadata':None}
    output.write_text(json.dumps(result),encoding='utf-8')
if __name__=='__main__':main()
