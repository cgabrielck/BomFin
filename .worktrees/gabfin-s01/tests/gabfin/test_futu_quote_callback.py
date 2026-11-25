"""SDK boundary fakes exercise the real callback-to-worker lifecycle."""
from datetime import datetime, timezone
from types import SimpleNamespace
import threading

from gabfin.providers.futu.quote_push import run_quote_context, QuoteMailbox
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
    box = QuoteMailbox('US.AAPL')
    now = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)
    fresh = Frame().to_dict('records')
    box.offer(fresh, received_at=now)
    box.offer([fresh[0] | {'data_time': '09:59:00', 'last_price': 99}], received_at=now)
    assert box.take()['price'] == '100.25'
    assert box.rejected == 1
    for price in range(1, 1001):
        box.offer([fresh[0] | {'last_price': price}], received_at=now)
    assert box.take()['price'] == '1000'
    assert box.take() is None
    assert box.coalesced == 999


@pytest.mark.parametrize('day,clock', [
    ('2026-11-01', '01:30:00'), ('2026-03-08', '02:30:00'),
    ('2026-11-25', ''), ('2026-11-25', '10:00:00+00:00'),
])
def test_ambiguous_nonexistent_or_missing_source_time_is_not_guessed(day, clock):
    box = QuoteMailbox('US.AAPL')
    box.offer([dict(code='US.AAPL', last_price=1, data_date=day, data_time=clock)],
              received_at=datetime(2026, 11, 25, 15, tzinfo=timezone.utc))
    assert box.take() is None
    assert box.rejected == 1


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
