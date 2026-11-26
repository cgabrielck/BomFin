import asyncio
import pytest
from uuid import uuid4

from gabfin.contracts.subscriptions import SubscriptionKey
from gabfin.market.host import serve_market
from gabfin.market.internal_stream import InternalMarketClient
from test_feed_supervisor import ExternalFeed
from test_internal_market_stream import sessions
from test_market_coordinator import coordinator
from test_quote_stream import ID


def test_market_host_owns_listener_and_feed_until_context_closes(tmp_path):
    async def scenario():
        store = sessions(tmp_path)
        token, _ = store.issue_service(actor_id=uuid4(), role='research', scope=['read_market'])
        market = coordinator()
        feed = ExternalFeed(0)
        async with serve_market(market, store, lambda: feed,
            [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
            heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2, max_attempts=1) as address:
            client = await InternalMarketClient.connect(*address, token=token, instrument_ids=[ID])
            try:
                first = await client.receive(timeout=2)
                assert first.kind == 'snapshot'
                assert first.payload.quotes[0].payload.last.price == 100
            finally:
                await client.close()
        assert feed.closed and not market.snapshot().health.connected
    asyncio.run(scenario())


def test_supervisor_failure_closes_listener_and_wakes_foreground_host(tmp_path):
    async def scenario():
        class FailedCleanup(ExternalFeed):
            async def close(self):
                self.result = dict(cleanup='release_pending', closed=True, errors=['fixture'])
        finished = asyncio.Event()
        market = coordinator()
        with pytest.raises(RuntimeError, match='cleanup'):
            async with serve_market(market, sessions(tmp_path), lambda: FailedCleanup(0),
                [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
                heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2,
                max_attempts=1, finished=finished) as address:
                await asyncio.wait_for(finished.wait(), 1)
                with pytest.raises(OSError):
                    await asyncio.open_connection(*address)
                assert not market.snapshot().health.connected
    asyncio.run(scenario())


def test_subscribe_failure_is_propagated_when_diagnostic_attempts_exhausted(tmp_path):
    async def scenario():
        class SubscribeFails(ExternalFeed):
            async def subscribe(self, keys):
                self.requested_keys = tuple(keys)
                raise RuntimeError('provider unavailable')
        finished = asyncio.Event()
        with pytest.raises(RuntimeError, match='attempts exhausted'):
            async with serve_market(coordinator(), sessions(tmp_path), lambda: SubscribeFails(0),
                [SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None)],
                heartbeat_timeout=120, retry_delay=.01, backfill_timeout=2,
                max_attempts=1, finished=finished):
                await asyncio.wait_for(finished.wait(), 1)
    asyncio.run(scenario())
