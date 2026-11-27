"""SDK boundary fakes exercise the real callback-to-worker lifecycle."""
from datetime import datetime, timezone
from types import SimpleNamespace
import threading

from gabfin.providers.futu.quote_push import run_quote_context
import pytest


class HandlerBase:
    def on_recv_rsp(self, message):
        return 0, message


class Frame:
    def to_dict(self, orient):
        return [dict(code='US.AAPL', last_price=100.25,
                     data_date='2026-11-25', data_time='09:59:58')]


class Context:
    def __init__(self, stop):
        self.stop = stop
        self.closed = False
        self.owned = 0
        self.unsubscribed = False

    def set_handler(self, handler):
        self.handler = handler
        return 0

    def subscribe(self, codes, types, **kwargs):
        assert codes == ['US.AAPL'] and types == ['QUOTE']
        assert kwargs['subscribe_push'] is True
        assert kwargs['is_first_push'] is True
        self.owned = 1
        self.handler.on_recv_rsp(Frame())
        self.stop.set()
        return 0, None

    def unsubscribe(self, codes, types):
        assert codes == ['US.AAPL'] and types == ['QUOTE']
        self.owned = 0
        self.unsubscribed = True
        return 0, None

    def query_subscription(self, **kwargs):
        return 0, {'own_used': self.owned}

    def close(self):
        self.closed = True


class Clock:
    value = 0.0

    def __call__(self):
        return self.value

    def sleep(self, duration):
        self.value += duration


def test_real_callback_path_emits_sanitized_quote_and_releases_only_own_subscription():
    clock = Clock()
    stop = threading.Event()
    context = Context(stop)
    messages = []
    run_quote_context(context, SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=messages.append, stop=stop, deadline=110,
                      clock=clock, sleep=clock.sleep,
                      now=lambda: datetime(2026, 11, 25, 15, tzinfo=timezone.utc))
    quote = next(message for message in messages if message['kind'] == 'quote')
    assert quote == dict(version=1, kind='quote', code='US.AAPL', price='100.25',
                         event_at='2026-11-25T14:59:58Z', received_at='2026-11-25T15:00:00Z')
    assert messages[-1]['cleanup'] == 'unsubscribed'
    assert messages[-1]['closed'] is True
    assert clock.value >= 61
    assert context.closed and context.unsubscribed


def test_worker_mailbox_coalesces_without_losing_a_newer_source_observation():
    class Burst(Context):
        def subscribe(self, *args, **kwargs):
            self.owned = 1
            class Records:
                def __init__(self, row): self.row = row
                def to_dict(self, orient): return [self.row]
            fresh = Frame().to_dict('records')[0]
            for price in range(1, 1001):
                self.handler.on_recv_rsp(Records(fresh | {'last_price': price}))
            self.handler.on_recv_rsp(Records(fresh | {'data_time': '09:59:00', 'last_price': 99}))
            self.stop.set()
            return 0, None
    stop = threading.Event()
    clock = Clock()
    messages = []
    run_quote_context(Burst(stop), SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=messages.append, stop=stop, deadline=110,
                      clock=clock, sleep=clock.sleep,
                      now=lambda: datetime(2026, 11, 25, 15, tzinfo=timezone.utc))
    assert [m['price'] for m in messages if m['kind'] == 'quote'] == ['1000']
    assert messages[-1]['rejected'] == 1
    assert messages[-1]['coalesced'] == 999


@pytest.mark.parametrize('day,clock', [
    ('2026-11-01', '01:30:00'), ('2026-03-08', '02:30:00'),
    ('2026-11-25', ''), ('2026-11-25', '10:00:00+00:00'),
])
def test_ambiguous_nonexistent_or_missing_source_time_is_not_guessed(day, clock):
    class InvalidFrame:
        def to_dict(self, orient):
            return [dict(code='US.AAPL', last_price=1, data_date=day, data_time=clock)]
    class InvalidQuote(Context):
        def subscribe(self, *args, **kwargs):
            self.owned = 1
            self.handler.on_recv_rsp(InvalidFrame())
            self.stop.set()
            return 0, None
    stop = threading.Event()
    timer = Clock()
    messages = []
    run_quote_context(InvalidQuote(stop), SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=messages.append, stop=stop, deadline=110,
                      clock=timer, sleep=timer.sleep,
                      now=lambda: datetime(2026, 11, 25, 15, tzinfo=timezone.utc))
    assert not any(m['kind'] == 'quote' for m in messages)
    assert messages[-1]['rejected'] == 1


def test_partial_subscription_failure_still_waits_and_cleans_up():
    class Partial(Context):
        def subscribe(self, *args, **kwargs):
            self.owned = 1
            return -1, 'raw SDK failure with private details'
    clock = Clock()
    stop = threading.Event()
    context = Partial(stop)
    messages = []
    run_quote_context(context, SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=messages.append, stop=stop, deadline=110,
                      clock=clock, sleep=clock.sleep)
    assert messages[-1]['errors'] == ['subscribe_failed']
    assert messages[-1]['cleanup'] == 'unsubscribed'
    assert clock.value >= 61
    assert context.closed


@pytest.mark.parametrize('failure', ['unsubscribe', 'verify', 'close', 'setup', 'existing'])
def test_cleanup_and_preflight_failures_are_explicit_and_do_not_unsubscribe_foreign_state(failure):
    class Broken(Context):
        def query_subscription(self, **kwargs):
            if failure == 'existing':
                return 0, {'own_used': 2}
            if failure == 'verify' and self.unsubscribed:
                return 0, {'own_used': 1}
            return super().query_subscription(**kwargs)

        def set_handler(self, handler):
            return -1 if failure == 'setup' else super().set_handler(handler)

        def unsubscribe(self, *args):
            if failure == 'unsubscribe':
                return -1, 'private error'
            return super().unsubscribe(*args)

        def close(self):
            if failure == 'close':
                raise RuntimeError('private close error')
            super().close()
    clock = Clock()
    stop = threading.Event()
    context = Broken(stop)
    messages = []
    run_quote_context(context, SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=messages.append, stop=stop, deadline=110,
                      clock=clock, sleep=clock.sleep)
    final = messages[-1]
    expected = dict(unsubscribe='unsubscribe_failed', verify='cleanup_verify_failed',
                    close='close_failed', setup='callback_setup_failed', existing='existing_subscription')
    assert expected[failure] in final['errors']
    assert 'private' not in str(messages)
    if failure in ('setup', 'existing'):
        assert not context.unsubscribed
        assert final['cleanup'] == 'not_subscribed'
    if failure in ('unsubscribe', 'verify'):
        assert final['cleanup'] == 'release_pending'
    assert final['closed'] is (failure != 'close')


def test_ipc_failure_during_ready_still_releases_subscription_and_closes():
    clock = Clock()
    context = Context(threading.Event())
    messages = []

    def emit(message):
        if message['kind'] == 'ready':
            raise BrokenPipeError('external IPC failure')
        messages.append(message)

    run_quote_context(context, SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=emit, stop=context.stop, deadline=110,
                      clock=clock, sleep=clock.sleep)
    assert messages[-1]['cleanup'] == 'unsubscribed'
    assert messages[-1]['closed'] is True
    assert messages[-1]['errors'] == ['stream_failed']
    assert clock.value >= 61


@pytest.mark.parametrize('when', ['before_preflight', 'after_preflight'])
def test_cancel_before_subscription_never_allocates_or_waits_minimum_hold(when):
    clock = Clock()
    stop = threading.Event()
    class Cancelling(Context):
        def query_subscription(self, **kwargs):
            stop.set()
            return super().query_subscription(**kwargs)
    context = Cancelling(stop)
    if when == 'before_preflight':
        stop.set()
    messages = []
    run_quote_context(context, SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=messages.append, stop=stop, deadline=110,
                      clock=clock, sleep=clock.sleep)
    assert clock.value == 0
    assert context.owned == 0 and not context.unsubscribed
    assert messages[-1]['cleanup'] == 'not_subscribed'
    assert messages[-1]['closed'] is True


def test_provider_heartbeat_is_independent_of_market_events_and_sanitized():
    clock = Clock()
    stop = threading.Event()
    class Quiet(Context):
        def subscribe(self, *args, **kwargs):
            self.owned = 1
            return 0, None
        def get_global_state(self):
            stop.set()
            return 0, {'qot_logined': True, 'private_account_field': 'never_export'}
    messages = []
    run_quote_context(Quiet(stop), SimpleNamespace(QUOTE='QUOTE', RTH='RTH'), HandlerBase,
                      code='US.AAPL', emit=messages.append, stop=stop, deadline=110,
                      clock=clock, sleep=clock.sleep,
                      now=lambda: datetime(2026, 11, 25, 15, tzinfo=timezone.utc))
    beats = [message for message in messages if message['kind'] == 'heartbeat']
    assert beats == [dict(version=1, kind='heartbeat', checked_at='2026-11-25T15:00:00Z', quote_logged_in=True)]
    assert not any(message['kind'] == 'quote' for message in messages)
    assert 'private_account_field' not in str(messages)
