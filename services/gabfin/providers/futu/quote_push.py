"""Stdlib-only SDK boundary: callback → one-slot mailbox → private IPC.

No contracts/Pandas dependency here: this module also runs in the SDK venv.
The caller owns the hard process deadline; cleanup reserves ten seconds.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
import threading
import time
from zoneinfo import ZoneInfo

from gabfin.providers.futu.symbols_wire import us_equity_symbol

ERRORS = {'deadline_insufficient', 'existing_subscription', 'subscribe_failed',
          'callback_setup_failed', 'stream_failed', 'unsubscribe_failed',
          'cleanup_verify_failed', 'close_failed'}


def _ok(response):
    return isinstance(response, tuple) and len(response) == 2 and type(response[0]) is int and response[0] == 0


def _no_owned_subscription(response):
    return (_ok(response) and isinstance(response[1], dict)
            and type(response[1].get('own_used')) is int and response[1]['own_used'] == 0)


def closed_message(cleanup, closed, errors, *, callbacks=0, coalesced=0, rejected=0):
    """One stdlib wire constructor; the parent independently validates it."""
    return dict(version=1, kind='closed', cleanup=cleanup, closed=closed, errors=errors,
                callbacks=callbacks, coalesced=coalesced, rejected=rejected)


def _source_time(day, clock):
    if not isinstance(day, str) or not isinstance(clock, str):
        raise ValueError('missing_source_time')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or not re.fullmatch(r'\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?', clock):
        raise ValueError('invalid_source_time')
    local = datetime.fromisoformat(day + 'T' + clock)
    zone = ZoneInfo('America/New_York')
    candidates = {local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
                  for fold in (0, 1)
                  if local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == local}
    if len(candidates) != 1:
        raise ValueError('ambiguous_or_nonexistent_source_time')
    return candidates.pop().isoformat().replace('+00:00', 'Z')


class QuoteMailbox:
    """Thread-safe one-slot quote coalescer. It does not retain raw SDK data."""
    def __init__(self, code):
        if not us_equity_symbol(code):
            raise ValueError('unsupported_symbol')
        self.code = code
        self._lock = threading.Lock()
        self._pending = None
        self._closed = False
        self._latest = None
        self.callbacks = 0
        self.coalesced = 0
        self.rejected = 0

    def offer(self, records, *, received_at):
        with self._lock:
            if self._closed:
                return
            self.callbacks += 1
            try:
                if not isinstance(records, list) or len(records) != 1:
                    raise ValueError('not_one_equity')
                row = records[0]
                if row.get('code') != self.code or isinstance(row.get('last_price'), bool):
                    raise ValueError('foreign_or_invalid_quote')
                price = Decimal(str(row.get('last_price')))
                if not price.is_finite() or price < 0 or len(str(price)) > 100:
                    raise ValueError('invalid_price')
                source = _source_time(row.get('data_date'), row.get('data_time'))
                source_at = datetime.fromisoformat(source)
                if source_at > received_at:
                    raise ValueError('source_clock_ahead')
                if self._latest is not None and (source_at < self._latest[0]
                                                or (source_at, price) == self._latest):
                    raise ValueError('late_or_duplicate')
                message = dict(version=1, kind='quote', code=self.code, price=str(price),
                               event_at=source, received_at=received_at.isoformat().replace('+00:00', 'Z'))
            except (ValueError, TypeError, AttributeError, InvalidOperation, OverflowError):
                self.rejected += 1
                return
            if self._pending is not None:
                self.coalesced += 1
            self._pending = message
            self._latest = (source_at, price)

    def take(self):
        with self._lock:
            message, self._pending = self._pending, None
            return message

    def close(self):
        with self._lock:
            self._closed = True


def run_quote_context(context, sdk, handler_base, *, code, emit, stop, deadline,
                      clock=time.monotonic, sleep=time.sleep,
                      now=lambda: datetime.now(timezone.utc)):
    """Own one fresh quote context; never unsubscribe any other connection.

    Failed subscribe can partially allocate: wait the same 61 seconds before
    cleanup. Callback exceptions are sanitized; no raw messages cross IPC.
    """
    mailbox = QuoteMailbox(code)
    attempted_at = None
    errors = []
    cleanup = 'not_subscribed'
    closed = False

    class Handler(handler_base):
        def on_recv_rsp(self, message):
            received_at = now()
            try:
                ret, data = super().on_recv_rsp(message)
                mailbox.offer(data.to_dict(orient='records') if ret == 0 else None,
                              received_at=received_at)
            except Exception:
                mailbox.offer(None, received_at=received_at)
            return 0, None

    try:
        if stop.is_set():
            return
        if deadline - clock() < 75:
            errors.append('deadline_insufficient')
            return
        ownership = context.query_subscription(is_all_conn=False)
        if not _no_owned_subscription(ownership):
            errors.append('existing_subscription')
            return
        if context.set_handler(Handler()) != 0:
            errors.append('callback_setup_failed')
            return
        if stop.is_set():
            return
        if deadline - clock() < 75:
            errors.append('deadline_insufficient')
            return
        attempted_at = clock()
        if not _ok(context.subscribe([code], [sdk.QUOTE], is_first_push=True,
                                     subscribe_push=True, extended_time=False, session=sdk.RTH)):
            errors.append('subscribe_failed')
            return
        emit(dict(version=1, kind='ready'))
        while True:
            message = mailbox.take()
            if message is not None:
                emit(message)
            if stop.is_set() or clock() >= deadline - 10:
                break
            sleep(.02)
    except Exception:
        errors.append('stream_failed')
    finally:
        mailbox.close()
        if attempted_at is not None:
            cleanup = 'release_pending'
            while clock() - attempted_at < 61:
                sleep(min(.1, 61 - (clock() - attempted_at)))
            try:
                if not _ok(context.unsubscribe([code], [sdk.QUOTE])):
                    errors.append('unsubscribe_failed')
                else:
                    quota = context.query_subscription(is_all_conn=False)
                    if _no_owned_subscription(quota):
                        cleanup = 'unsubscribed'
                    else:
                        errors.append('cleanup_verify_failed')
            except Exception:
                errors.append('unsubscribe_failed')
        try:
            context.close()
            closed = True
        except Exception:
            errors.append('close_failed')
        emit(closed_message(cleanup, closed, errors, callbacks=mailbox.callbacks,
                            coalesced=mailbox.coalesced, rejected=mailbox.rejected))
