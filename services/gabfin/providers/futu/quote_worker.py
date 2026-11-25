"""Private, bounded SDK entry point. Only sanitized JSON uses the inherited pipe."""
import json
import logging
import math
import os
from pathlib import Path
import sys
import threading
import time


def main():
    # Preserve a private output descriptor, then discard *all* ordinary stdout
    # at OS level before importing the SDK (including its native dependencies).
    channel = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', buffering=1)
    with open(os.devnull, 'w') as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from gabfin.providers.futu.quote_push import run_quote_context, closed_message
    from gabfin.providers.futu.symbols_wire import us_equity_symbol

    def emit(message):
        line = json.dumps(message, allow_nan=False)
        if len(line.encode()) > 4095:
            raise ValueError('oversized_message')
        channel.write(line + '\n')
        channel.flush()

    context = None
    delegated = False
    try:
        # A daemon blocked on BufferedReader.readline can abort Python during
        # interpreter shutdown. Read the private descriptor without that lock;
        # byte-wise config reading also avoids prefetching a following stop.
        config_line = bytearray()
        while len(config_line) < 4096:
            chunk = os.read(sys.stdin.fileno(), 1)
            if not chunk or chunk == b'\n':
                break
            config_line.extend(chunk)
        if len(config_line) >= 4096:
            raise ValueError('oversized_config')
        config = json.loads(config_line)
        if (not isinstance(config, dict)
                or set(config) != {'version', 'code', 'host', 'port', 'deadline'}
                or type(config['version']) is not int or config['version'] != 1
                or config['host'] != '127.0.0.1'
                or type(config['port']) is not int or not 1 <= config['port'] <= 65535
                or not us_equity_symbol(config['code'])
                or type(config['deadline']) not in (int, float)
                or not math.isfinite(config['deadline'])
                or not 0 < config['deadline'] - time.monotonic() <= 120):
            raise ValueError('invalid_config')
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
            try:
                os.read(sys.stdin.fileno(), 1)
            finally:
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
            emit(closed_message('not_subscribed', closed, ['stream_failed']))
    finally:
        channel.close()


if __name__ == '__main__':
    main()
