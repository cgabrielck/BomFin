"""One feed owner; lifecycle retries do not erase gaps or fabricate heartbeats."""
import asyncio
import math
from datetime import timedelta

from pydantic import TypeAdapter

from gabfin.contracts.feed import FeedHealth, FeedCleanup
from gabfin.contracts.market import PositiveCounter
from gabfin.protocols import ManagedFeedAdapter


class FeedSupervisor:
    def __init__(self, market, factory, keys, *, heartbeat_timeout, retry_delay, backfill_timeout,
                 cleanup_timeout=130, event_sink=None):
        for value in (heartbeat_timeout, retry_delay, backfill_timeout, cleanup_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError('Finite positive lifecycle limits required')
        self.market, self._factory = market, factory
        self._event_sink = event_sink
        self._keys = tuple(key.model_copy(deep=True) for key in keys)
        if not self._keys:
            raise ValueError('Explicit subscriptions required')
        self._source = market.snapshot().health.source
        self._heartbeat_timeout = timedelta(seconds=heartbeat_timeout)
        self._retry_delay, self._backfill_timeout = retry_delay, backfill_timeout
        self._cleanup_timeout = cleanup_timeout
        self.last_error = None
        self._running = False
        self._cycle_quotes = {}
        self._cleanup_verified = True
        self._subscription_attempted = False

    async def _collect(self, feed):
        async for event in feed.events():
            if self._event_sink is not None:
                await asyncio.to_thread(self._event_sink, event)
            self.market.apply(event)
            if event.kind == 'quote':
                self._cycle_quotes[event.instrument_id] = event.model_copy(deep=True)

    async def _subscribe(self, feed):
        capabilities = await feed.capabilities()
        if capabilities.source != self._source:
            raise ValueError('Provider capability source mismatch')
        self.market.declare_sequence_rules(capabilities.sequence_rules)
        self._subscription_attempted = True
        await feed.subscribe(list(self._keys))

    async def _backfill(self, gap, backfill):
        try:
            batch = await asyncio.wait_for(backfill(gap), self._backfill_timeout)
            if batch is not None:
                self.market.recover(batch)
        except Exception:
            self.last_error = 'backfill_incomplete'

    async def _monitor(self, feed, backfill):
        previous_at = None
        previous_connected = None
        attempted_gap = None
        recovery = None
        loop = asyncio.get_running_loop()
        last_observed = loop.time()
        timeout = self._heartbeat_timeout.total_seconds()
        try:
            while True:
                health = FeedHealth.model_validate(feed.health.model_dump())
                current = self.market.now()
                healthy = (health is not None and health.source == self._source and health.connected
                           and health.heartbeat_at is not None and health.heartbeat_at <= current
                           and current - health.heartbeat_at <= self._heartbeat_timeout)
                if healthy:
                    if previous_at != health.heartbeat_at or previous_connected is not True:
                        last_observed = loop.time()
                        self.market.heartbeat(health.heartbeat_at, cutover=health.connection_started_at)
                        self.market.advance(current)
                        previous_at = health.heartbeat_at
                    if backfill is not None:
                        gap = self.market.recovery_gap
                        if gap is not None and gap.end is not None and gap.gap_id != attempted_gap:
                            if recovery is not None:
                                recovery.cancel()
                                await asyncio.gather(recovery, return_exceptions=True)
                            attempted_gap = gap.gap_id
                            recovery = asyncio.create_task(self._backfill(gap, backfill))
                    elif health.connection_started_at is not None:
                        self.market.recover_latest_quotes(self._cycle_quotes.values())
                else:
                    if previous_connected is not False:
                        self.market.disconnected('provider_heartbeat_unverified')
                    if previous_connected is True:
                        self._cycle_quotes.clear()
                        raise RuntimeError('Verified provider heartbeat lost')
                if loop.time() - last_observed >= timeout:
                    self.market.disconnected('provider_heartbeat_timeout')
                    self._cycle_quotes.clear()
                    raise RuntimeError('Provider heartbeat timed out')
                previous_connected = healthy
                await asyncio.sleep(min(.1, timeout / 2))
        finally:
            if recovery is not None:
                recovery.cancel()
                await asyncio.gather(recovery, return_exceptions=True)

    async def run(self, stop: asyncio.Event, *, max_attempts=None, backfill=None):
        """Trusted host entry point. max_attempts=None is persistent until stopped.

        Backfill is an external history API returning a verified RecoveryBatch;
        None/incomplete data keeps the gap. No task here grants trading authority.
        """
        if self._running:
            raise RuntimeError('One supervisor runner is permitted')
        if not self._cleanup_verified:
            raise RuntimeError('Previous feed cleanup remains unverified')
        if max_attempts is not None:
            max_attempts = TypeAdapter(PositiveCounter).validate_python(max_attempts)
        self._running = True
        attempts = 0
        try:
            while not stop.is_set() and (max_attempts is None or attempts < max_attempts):
                attempts += 1
                self._cycle_quotes = {}
                self._subscription_attempted = False
                self.last_error = None
                try:
                    feed = self._factory()
                except Exception:
                    self.last_error = 'feed_creation_failed'
                    self.market.disconnected('feed_creation_failed')
                    if max_attempts is not None and attempts >= max_attempts:
                        raise RuntimeError('Feed attempts exhausted') from None
                    await self._pause(stop)
                    continue
                if not isinstance(feed, ManagedFeedAdapter):
                    raise TypeError('Supervisor requires ManagedFeedAdapter')
                self._cleanup_verified = False
                tasks = []
                cycle_failed = False
                try:
                    starting = asyncio.create_task(self._subscribe(feed))
                    stopping = asyncio.create_task(stop.wait())
                    tasks = [starting, stopping]
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    if stopping in done:
                        continue
                    await starting
                    collect = asyncio.create_task(self._collect(feed))
                    monitor = asyncio.create_task(self._monitor(feed, backfill))
                    tasks = [collect, monitor, stopping]
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    if collect in done:
                        await collect
                    elif monitor in done:
                        await monitor
                        raise RuntimeError('Health monitoring stopped unexpectedly')
                except Exception:
                    self.last_error = 'feed_cycle_failed'
                    cycle_failed = True
                finally:
                    self.market.disconnected('feed_closing')
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    try:
                        await asyncio.wait_for(feed.close(), self._cleanup_timeout)
                    except Exception:
                        self.last_error = 'cleanup_unverified'
                        raise RuntimeError('Feed cleanup failed') from None
                    cleanup = feed.cleanup
                    expected = {key.identity for key in self._keys}
                    released = {key.identity for key in cleanup.requested_keys} if isinstance(cleanup, FeedCleanup) else set()
                    if (not isinstance(cleanup, FeedCleanup) or not cleanup.context_closed
                            or not cleanup.release_confirmed or cleanup.source != self._source
                            or not released <= expected
                            or (self._subscription_attempted and released != expected)):
                        self.last_error = 'cleanup_unverified'
                        raise RuntimeError('Cannot start another feed without verified cleanup')
                    self._cleanup_verified = True
                    self.market.disconnected('feed_cycle_ended')
                if stop.is_set() or (max_attempts is not None and attempts >= max_attempts):
                    if cycle_failed and not stop.is_set():
                        raise RuntimeError('Feed attempts exhausted')
                    break
                await self._pause(stop)
        finally:
            self._running = False
            self.market.disconnected('feed_stopped')

    async def _pause(self, stop):
        try:
            await asyncio.wait_for(stop.wait(), self._retry_delay)
        except TimeoutError:
            pass

    async def run_plan(self, schedule, stop, *, max_attempts=None, backfill=None):
        """Apply one fresh-context advisory plan through the owned feed lifecycle.

        Caller re-plans after the previous runner has verified release. We do not
        take over an unknown existing context or interpret a target as an ACK.
        """
        if (not schedule.apply_allowed or schedule.unsubscribe
                or schedule.plan.source != self._source):
            raise ValueError('Plan frozen or prior release not verified')
        accepted = tuple(key.identity for key in schedule.plan.accepted)
        if not accepted:
            if self._running:
                raise RuntimeError('Stop and await the current owner before applying another plan')
            return
        if (accepted != tuple(key.identity for key in self._keys)
                or tuple(key.identity for key in schedule.subscribe) != accepted):
            raise ValueError('Plan does not match configured feed keys')
        await self.run(stop, max_attempts=max_attempts, backfill=backfill)
