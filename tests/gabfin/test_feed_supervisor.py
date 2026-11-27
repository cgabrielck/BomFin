import asyncio
import pytest
from datetime import timedelta

from gabfin.contracts.feed import FeedHealth, FeedCleanup, RecoveryBatch
from gabfin.contracts.subscriptions import SubscriptionKey, FeedCapabilities
from gabfin.market.supervisor import FeedSupervisor
from test_market_coordinator import coordinator
from test_quote_stream import observation, ID, NOW


class ExternalFeed:
    """Fake provider at the approved FeedAdapter seam; not a mock of our SDK adapter."""
    def __init__(self, number):
        self.number = number
        self.result = None
        self.health = FeedHealth(schema_version='1.0', source='test-feed', connected=True,
                                 heartbeat_at=NOW, gap_pending=True)
        self.closed = False
        self.requested_keys = ()

    async def capabilities(self):
        return FeedCapabilities(schema_version='1.0', source=self.health.source,
            asset_classes=('equity',), sessions=('regular',), latency_label='unknown',
            max_subscriptions=1, history_limits=(), checked_at=NOW, permission_errors=('fixture_only',))

    async def subscribe(self, keys):
        assert keys[0].instrument_id == ID and keys[0].channel == 'quote'
        self.requested_keys = tuple(keys)

    async def unsubscribe(self, keys):
        await self.close()

    @property
    def cleanup(self):
        if self.result is None: return None
        return FeedCleanup(schema_version='1.0', source=self.health.source,
            context_closed=self.result['closed'], release_confirmed=self.result['cleanup']=='unsubscribed',
            requested_keys=self.requested_keys, reason_codes=tuple(self.result['errors']))

    async def events(self):
        yield observation(str(100 + self.number))
        await asyncio.sleep(.02)

    async def close(self):
        self.closed = True
        self.result = dict(cleanup='unsubscribed', closed=True, errors=[])


def test_two_feed_lifecycles_recover_without_mixing_sessions_or_losing_cleanup():
    async def scenario():
        market = coordinator()
        feeds = []
        def factory():
            feed = ExternalFeed(len(feeds))
            feeds.append(feed)
            return feed
        async def backfill(gap):
            return RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source=gap.source,
                                 start=gap.start, end=gap.end, complete=True, evidence='fixture', events=())
        supervisor = FeedSupervisor(market, factory, [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
                                    heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2)
        await supervisor.run(asyncio.Event(), max_attempts=2, backfill=backfill)
        assert len(feeds) == 2 and all(feed.closed for feed in feeds)
        assert market.snapshot().quotes[0].payload.last.price == 101
        assert not market.snapshot().health.connected
        assert market.snapshot().health.gap_pending  # stopped services cannot permit entries
    asyncio.run(scenario())


def test_stop_during_subscribe_cancels_before_more_provider_work():
    async def scenario():
        entered = asyncio.Event()
        class Starting(ExternalFeed):
            async def subscribe(self, keys):
                self.requested_keys = tuple(keys)
                entered.set()
                await asyncio.Event().wait()
        feed = Starting(0)
        stop = asyncio.Event()
        supervisor = FeedSupervisor(coordinator(), lambda: feed,
            [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
            heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2)
        task = asyncio.create_task(supervisor.run(stop))
        await entered.wait()
        stop.set()
        await asyncio.wait_for(task, .5)
        assert feed.closed
    asyncio.run(scenario())


def test_unverified_cleanup_prevents_starting_a_second_context():
    async def scenario():
        feeds = []
        class Unreleased(ExternalFeed):
            async def close(self):
                self.result = dict(cleanup='release_pending', closed=True, errors=['unsubscribe_failed'])
        def factory():
            feed = Unreleased(len(feeds)); feeds.append(feed); return feed
        market = coordinator()
        supervisor = FeedSupervisor(market, factory,
            [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
            heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2)
        with pytest.raises(RuntimeError, match='cleanup'):
            await supervisor.run(asyncio.Event(), max_attempts=2)
        assert len(feeds) == 1 and market.snapshot().health.gap_pending
        with pytest.raises(RuntimeError, match='cleanup'):
            await supervisor.run(asyncio.Event(), max_attempts=1)
        assert len(feeds) == 1
    asyncio.run(scenario())


def test_frozen_or_existing_context_plan_does_not_open_a_provider():
    from test_subscription_planner import plan, demand, key, AAPL
    from gabfin.market.coordinator import MarketCoordinator
    async def scenario():
        created = []
        def factory(): created.append(True); return ExternalFeed(0)
        market = MarketCoordinator([AAPL], source='futu', replay_capacity=3, max_bars=3, clock=lambda: NOW)
        supervisor = FeedSupervisor(market, factory, [key(AAPL)], heartbeat_timeout=120,
                                    retry_delay=.01, backfill_timeout=2)
        frozen = plan([demand(AAPL)], equity_slots=None)
        with pytest.raises(ValueError, match='frozen'):
            await supervisor.run_plan(frozen, asyncio.Event(), max_attempts=1)
        claimed_existing = plan([demand(AAPL)], current=[key(AAPL)])
        with pytest.raises(ValueError, match='configured'):
            await supervisor.run_plan(claimed_existing, asyncio.Event(), max_attempts=1)
        assert created == []
    asyncio.run(scenario())


def test_transient_factory_failure_before_acquisition_can_retry():
    async def scenario():
        attempts = []
        feed = ExternalFeed(0)
        market = coordinator()
        feed.health = feed.health.model_copy(update={'heartbeat_at': market.now()})
        def factory():
            attempts.append(True)
            if len(attempts) == 1: raise ValueError('temporary constructor failure')
            return feed
        supervisor = FeedSupervisor(market, factory,
            [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
            heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2)
        await supervisor.run(asyncio.Event(), max_attempts=2)
        assert len(attempts) == 2 and feed.closed
    asyncio.run(scenario())


def test_plain_adapter_is_rejected_before_resource_acquisition_with_clear_contract():
    class PlainFeed:
        async def capabilities(self): pass
        async def subscribe(self, keys): raise AssertionError('must not acquire')
        async def unsubscribe(self, keys): pass
        async def events(self):
            if False: yield
    async def scenario():
        supervisor = FeedSupervisor(coordinator(), PlainFeed,
            [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
            heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2)
        with pytest.raises(TypeError, match='ManagedFeedAdapter'):
            await supervisor.run(asyncio.Event(), max_attempts=1)
    asyncio.run(scenario())


def test_hung_event_stream_without_verified_heartbeat_is_closed_before_retry():
    async def scenario():
        feeds = []
        class Silent(ExternalFeed):
            def __init__(self, number):
                super().__init__(number)
                self.health = self.health.model_copy(update={'connected': False, 'heartbeat_at': None})
            async def events(self):
                await asyncio.Event().wait()
                if False: yield
        def factory():
            assert all(feed.closed for feed in feeds)
            feed = Silent(len(feeds)); feeds.append(feed); return feed
        market = coordinator()
        supervisor = FeedSupervisor(market, factory,
            [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
            heartbeat_timeout=.03, retry_delay=.01, backfill_timeout=2)
        with pytest.raises(RuntimeError, match='attempts exhausted'):
            await asyncio.wait_for(supervisor.run(asyncio.Event(), max_attempts=2), .5)
        assert len(feeds) == 2 and all(feed.closed for feed in feeds)
        assert market.snapshot().health.gap_pending and not market.snapshot().health.connected
    asyncio.run(scenario())


def test_successful_subscribe_requires_cleanup_receipt_covering_all_requested_keys():
    async def scenario():
        feeds = []
        class EmptyReceipt(ExternalFeed):
            @property
            def cleanup(self):
                receipt = super().cleanup
                return receipt.model_copy(update={'requested_keys': ()}) if receipt else None
        def factory():
            feed = EmptyReceipt(len(feeds)); feeds.append(feed); return feed
        supervisor = FeedSupervisor(coordinator(), factory,
            [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
            heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2)
        with pytest.raises(RuntimeError, match='cleanup'):
            await supervisor.run(asyncio.Event(), max_attempts=2)
        assert len(feeds) == 1
    asyncio.run(scenario())
