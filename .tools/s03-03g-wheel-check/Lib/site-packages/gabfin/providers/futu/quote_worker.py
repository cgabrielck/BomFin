"""Private, bounded SDK entry point. Only sanitized JSON uses the inherited pipe."""
import json
import logging
import os
from pathlib import Path
import sys
import threading


def main():
    # Preserve a private output descriptor, then discard *all* ordinary stdout
    # at OS level before importing the SDK (including its native dependencies).
    channel = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', buffering=1)
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
    logging.disable(logging.CRITICAL)

    def emit(message):
        line = json.dumps(message, allow_nan=False)
        if len(line.encode()) > 4095:
            raise ValueError('oversized_message')
        channel.write(line + '\n')
        channel.flush()

    context = None
    delegated = False
    try:
        config = json.loads(sys.stdin.buffer.readline(4096))
        if config['version'] != 1 or config['host'] != '127.0.0.1':
            raise ValueError('invalid_config')
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from gabfin.providers.futu.quote_push import run_quote_context
        from futu import OpenQuoteContext, SysConfig, StockQuoteHandlerBase, SubType, Session
        from importlib.metadata import version
        from types import SimpleNamespace
        if version('futu-api') != '10.12.7208':
            raise ValueError('unsupported_sdk')
        SysConfig.enable_console_log(False)
        context = OpenQuoteContext(host=config['host'], port=config['port'], is_encrypt=False)
        context.set_sync_query_connect_timeout(3)
        stop = threading.Event()

        def control():
            sys.stdin.buffer.readline(32)
            stop.set()

        threading.Thread(target=control, daemon=True).start()
        delegated = True
        run_quote_context(context, SimpleNamespace(QUOTE=SubType.QUOTE, RTH=Session.RTH),
                          StockQuoteHandlerBase, code=config['code'], emit=emit,
                          stop=stop, deadline=config['deadline'])
    except Exception:
        closed = context is None
        if context is not None and not delegated:
            try:
                context.close()
                closed = True
            except Exception:
                pass
        if not delegated:
            emit(dict(version=1, kind='closed', cleanup='not_subscribed', closed=closed,
                      errors=['stream_failed'], callbacks=0, coalesced=0, rejected=0))
    finally:
        channel.close()


if __name__ == '__main__':
    main()
