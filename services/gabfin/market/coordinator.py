"""Single-loop market owner: bounded latest state, cursors and explicit gaps."""
from collections import OrderedDict, deque
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from pydantic import TypeAdapter

from gabfin.contracts.common import UtcTimestamp
from gabfin.contracts.events import MarketEvent, BarMarketEvent, QuoteMarketEvent
from gabfin.contracts.feed import FeedHealth, MarketUpdate, MarketSnapshot, RecoveryGap, RecoveryBatch, MarketCursor
from gabfin.contracts.market import PositiveCounter, NonNegativeCounter
from gabfin.contracts.subscriptions import SubscriptionKey, SequenceRule
from gabfin.market.sequences import SequenceTracker
from gabfin.market.stream import QuoteStream


class SnapshotRequired(ValueError):
    """Epoch/cursor retention mismatch; resume only from a new full snapshot."""


def _market_facts(event):
    """Capture clocks may differ for the same fact; source facts may not."""
    local = {'event_id', 'as_of', 'received_at', 'available_at', 'age_ms', 'checked_at'}
    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if key not in local}
        if isinstance(value, (list, tuple)):
            return tuple(strip(item) for item in value)
        return value
    return strip(event.model_dump(mode='python'))


class MarketCoordinator:
    def __init__(self, instrument_ids, *, source, replay_capacity, max_bars, builders=None,
                 required_channels=('quote',), required_keys=None, sequence_rules=(),
                 clock=lambda: datetime.now(timezone.utc)):
        ids = tuple(TypeAdapter(UUID).validate_python(value) for value in instrument_ids)
        if not ids or len(ids) > 1000 or len(set(ids)) != len(ids):
            raise ValueError('A finite, unique instrument set is required')
        counter = TypeAdapter(PositiveCounter)
        self._capacity = counter.validate_python(replay_capacity)
        self._max_bars = counter.validate_python(max_bars)
        self._source, self._clock = source, clock
        if required_keys is not None:
            required_keys = tuple(required_keys)
        self._required_channels = frozenset(required_channels if required_keys is None else
                                            (key.channel for key in required_keys))
        if not self._required_channels or not self._required_channels <= {'quote', 'trade', 'bar'}:
            raise ValueError('Explicit market channels required')
        self._streams = {identifier: QuoteStream(identifier) for identifier in ids}
        self._builders = dict(builders or {})
        if not set(self._builders) <= set(ids):
            raise ValueError('Unregistered bar builder')
        if required_keys is None:
            if 'bar' in self._required_channels:
                raise ValueError('Native bar coverage requires explicit timeframe keys')
            required_keys = [SubscriptionKey(instrument_id=identifier, channel=channel, timeframe=None)
                             for identifier in ids for channel in self._required_channels]
        self._required_keys = {key.identity: SubscriptionKey.model_validate(key.model_dump())
                               for key in required_keys}
        if (not self._required_keys or len(self._required_keys) > 3000
                or any(key.instrument_id not in ids for key in self._required_keys.values())
                or any((identifier, 'trade', None) not in self._required_keys for identifier in self._builders)):
            raise ValueError('Invalid required subscription coverage')
        self._position = MarketCursor(epoch=uuid4(), sequence=0)
        self._history = deque(maxlen=self._capacity)
        self._changed = asyncio.Event()
        self._seen = OrderedDict()
        self._sequence_rules = {}
        self._sequences = SequenceTracker(self._capacity)
        self._sequence_fault = False
        self.declare_sequence_rules(sequence_rules)
        self._bars = {}
        self._health = FeedHealth(schema_version='1.0', source=source, connected=False,
                                  heartbeat_at=None, gap_pending=True)
        self._gap = RecoveryGap(schema_version='1.0', gap_id=uuid4(), source=source,
                                start=self.now(), reason='bootstrap_unverified')

    def now(self):
        return TypeAdapter(UtcTimestamp).validate_python(self._clock())

    def declare_sequence_rules(self, rules):
        declarations = tuple(SequenceRule.model_validate(rule.model_dump()) for rule in rules)
        values = {rule.channel_identity: rule.semantics for rule in declarations}
        if len(values) != len(declarations):
            raise ValueError('Duplicate sequence rule')
        if self._sequence_rules and values != self._sequence_rules:
            raise ValueError('Sequence semantics require a new market epoch')
        if self._seen and values != self._sequence_rules:
            raise ValueError('Cannot change sequence semantics after ingesting events')
        self._sequence_rules = values

    def _publish(self, event=None):
        self._position = self._position.model_copy(update={'sequence': self._position.sequence + 1})
        update = MarketUpdate(schema_version='1.0', epoch=self._position.epoch, sequence=self._position.sequence,
                              processed_at=self.now(), event=event, health=self._health, gap=self._gap)
        self._history.append(update)
        self._changed.set()
        return update.model_copy(deep=True)

    def apply(self, event) -> list[MarketUpdate]:
        event = TypeAdapter(MarketEvent).validate_python(event.model_dump(mode='python'))
        if event.instrument_id not in self._streams or event.source != self._source:
            raise ValueError('Unregistered source/instrument')
        if self._event_key(event) not in self._required_keys:
            raise ValueError('Unregistered channel/timeframe')
        if event.available_at > self.now():
            raise ValueError('event_not_yet_available')
        if not self._valid_source_clock(event):
            return []  # Never enter dedup/sequence evidence for a skewed observation.
        identity = (event.instrument_id, event.kind, event.dedup_key)
        facts = _market_facts(event)
        if identity in self._seen:
            if self._seen[identity] != facts:
                self.disconnected('event_identity_conflict')
                raise ValueError('event_identity_conflict')
            return []
        prepared = None
        if self._sequence_rules.get(self._event_key(event)[1:]) == 'contiguous':
            try:
                prepared = self._sequences.prepare(self._event_key(event), event.source_seq, facts)
            except ValueError:
                self._sequence_fault = True
                self.disconnected('source_sequence_unverified')
                raise
            if prepared.pending and not self._sequences.has_gaps:
                self.disconnected('source_sequence_gap')
        updates = []
        if event.kind == 'quote':
            if self._streams[event.instrument_id].apply(event):
                updates.append(self._publish(event))
        elif event.kind == 'trade':
            builder = self._builders.get(event.instrument_id)
            if builder is None:
                raise ValueError('Trade bar builder not configured')
            try:
                bars = builder.apply(event)
            except ValueError:
                self.disconnected('trade_state_incomplete')
                raise
            updates.extend(self._publish_bars(bars))
        else:
            if event.instrument_id in self._builders:
                raise ValueError('Cannot mix provider bars and trade-built bars')
            if self._cache_bar(event):
                updates.append(self._publish(event))
        self._seen[identity] = facts
        if prepared is not None:
            self._sequences.commit(prepared)
        if len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return updates

    def _publish_bars(self, bars):
        updates = []
        for bar in bars:
            digest = sha256(bar.model_dump_json().encode()).hexdigest()
            derived = BarMarketEvent(schema_version='1.0', kind='bar',
                event_id=uuid5(NAMESPACE_URL, digest), instrument_id=bar.instrument_id,
                event_at=bar.event_at, received_at=bar.received_at, available_at=bar.available_at,
                source=bar.source, source_seq=None, dedup_key='bar:' + digest, payload=bar)
            if self._cache_bar(derived):
                updates.append(self._publish(derived))
        return updates

    def advance(self, at):
        at = TypeAdapter(UtcTimestamp).validate_python(at)
        if at > self.now():
            raise ValueError('Cannot finalize bars in the future')
        updates = []
        for builder in self._builders.values():
            updates.extend(self._publish_bars(builder.advance(at)))
        return updates

    def _cache_bar(self, event):
        bar = event.payload
        key = (event.instrument_id, bar.timeframe.count, bar.timeframe.unit, bar.session, bar.start)
        previous = self._bars.get(key)
        if previous is not None:
            old = previous.payload
            if (bar.available_at < old.available_at or bar.revision < old.revision
                    or (old.status != 'forming' and bar.status == 'forming')):
                return False
            if old.status != 'forming' and bar.revision == old.revision:
                values = lambda value: (value.open, value.high, value.low, value.close, value.volume, value.status)
                if values(old) != values(bar):
                    raise ValueError('conflicting_final_bar_revision')
                return False
        elif len(self._bars) >= self._max_bars:
            oldest = min(self._bars, key=lambda item: item[-1])
            if bar.start <= oldest[-1]:
                return False
            del self._bars[oldest]
        self._bars[key] = event.model_copy(deep=True)
        return True

    @property
    def recovery_gap(self):
        return self._gap.model_copy(deep=True) if self._gap is not None else None

    def heartbeat(self, at, *, cutover=None):
        at = TypeAdapter(UtcTimestamp).validate_python(at)
        if at > self.now() or (self._health.heartbeat_at is not None and at < self._health.heartbeat_at):
            raise ValueError('Invalid heartbeat time')
        next_gap = self._gap
        if self._gap is not None and self._gap.end is None:
            end = at if cutover is None else TypeAdapter(UtcTimestamp).validate_python(cutover)
            if end > at:
                raise ValueError('Connection cannot start after its heartbeat')
            start = self._gap.start
            if self._gap.reason == 'bootstrap_unverified':
                start = min(start, end)
            elif end < start:
                end = at  # A reused worker's original start is not this reconnect.
            if end < start:
                raise ValueError('Heartbeat cannot precede the disconnect window')
            next_gap = self._gap.model_copy(update={'start': start, 'end': end})
        self._health = self._health.model_copy(update={'connected': True, 'heartbeat_at': at})
        self._gap = next_gap
        return self._publish()

    def disconnected(self, reason):
        start = self._health.heartbeat_at or self.now()
        if self._gap is not None:
            start = min(start, self._gap.start)
        self._gap = RecoveryGap(schema_version='1.0', gap_id=uuid4(), source=self._source,
                                start=start, reason=reason)
        self._health = self._health.model_copy(update={'connected': False, 'gap_pending': True})
        return self._publish()

    def recover(self, batch: RecoveryBatch) -> bool:
        batch = RecoveryBatch.model_validate(batch.model_dump(mode='python'))
        gap = self._gap
        if (gap is None or batch.gap_id != gap.gap_id or batch.source != self._source
                or batch.start > gap.start or gap.end is None or batch.end < gap.end
                or batch.end > self.now() or batch.start > batch.end):
            raise ValueError('Recovery does not cover the current gap/cutover')
        for event in batch.events:
            if (event.source != self._source or event.instrument_id not in self._streams
                    or event.available_at > self.now()):
                raise ValueError('Invalid recovery event')
            if batch.mode == 'history' and not self._in_window(event, batch.start, batch.end):
                raise ValueError('History event outside recovery window')
        if batch.mode == 'history' and not self._valid_history_rows(batch.events):
            return False
        for event in sorted(batch.events, key=lambda value: value.available_at):
            self.apply(event)
        if batch.mode == 'quote_snapshot' and self._validated_quote_resync(batch.events, gap) is None:
            return False
        if batch.mode == 'history' and not self._verified_history(batch, gap):
            return False
        if (not batch.complete or not self._health.connected
                or self._sequences.has_gaps or self._sequence_fault):
            return False
        self._gap = None
        self._health = self._health.model_copy(update={'gap_pending': False})
        self._publish()
        return True

    @staticmethod
    def _event_key(event):
        timeframe = ((event.payload.timeframe.count, event.payload.timeframe.unit)
                     if event.kind == 'bar' else None)
        return (event.instrument_id, event.kind, timeframe)

    @staticmethod
    def _valid_source_clock(event):
        if event.event_at > event.received_at:
            return False
        if event.kind == 'quote':
            return all(point is None or point.event_at is None or point.event_at <= point.received_at
                       for point in (event.payload.bid, event.payload.ask, event.payload.last))
        return True

    def _valid_history_rows(self, events):
        identities, trade_ids, bars = set(), set(), set()
        for event in events:
            identity = (self._event_key(event), event.dedup_key)
            if not self._valid_source_clock(event) or identity in identities:
                return False
            identities.add(identity)
            if event.kind == 'trade' and event.payload.trade_id is not None:
                trade_id = (event.instrument_id, event.payload.trade_id)
                if trade_id in trade_ids:
                    return False
                trade_ids.add(trade_id)
            if event.kind == 'bar':
                bar = (self._event_key(event), event.payload.session, event.payload.start, event.payload.revision)
                if bar in bars:
                    return False
                bars.add(bar)
        return True

    @staticmethod
    def _in_window(event, start, end):
        if event.kind == 'bar':
            return event.payload.start <= end and event.payload.end > start
        return start <= event.event_at <= end

    def _verified_history(self, batch, gap):
        receipts = {item.key.identity: item for item in batch.coverage}
        if len(receipts) != len(batch.coverage) or receipts.keys() != self._required_keys.keys():
            return False
        by_key = {}
        for event in batch.events:
            by_key.setdefault(self._event_key(event), []).append(event)
        for identity, receipt in receipts.items():
            if (not receipt.complete or receipt.has_more or receipt.start > gap.start
                    or receipt.end < gap.end or receipt.start < batch.start or receipt.end > batch.end):
                return False
            events = by_key.get(identity, ())
            if (len(events) != receipt.record_count
                    or any(not self._in_window(event, receipt.start, receipt.end) for event in events)):
                return False
        return True

    def recover_latest_quotes(self, snapshots=None):
        """Full snapshots can resync coalescible quotes, never missing prints/bars."""
        gap = self._gap
        quotes = self._validated_quote_resync(snapshots, gap)
        if quotes is None:
            return False
        return self.recover(RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id,
            source=self._source, start=gap.start, end=gap.end, complete=True,
            evidence='full_quote_snapshot_on_new_connection', mode='quote_snapshot', events=quotes))

    def _validated_quote_resync(self, events, gap):
        """Return accepted post-cutover facts; rejected quotes are never proof."""
        if (gap is None or gap.end is None or self._required_channels != {'quote'}
                or self._builders or self._bars):
            return None
        values = tuple(stream.snapshot() for stream in self._streams.values()) if events is None else tuple(events)
        if len(values) != len(self._streams) or any(value is None for value in values):
            return None
        try:
            quotes = tuple(QuoteMarketEvent.model_validate(value.model_dump()) for value in values)
        except (AttributeError, TypeError, ValueError):
            return None
        if {quote.instrument_id for quote in quotes} != set(self._streams):
            return None
        for quote in quotes:
            latest = self._streams[quote.instrument_id].snapshot()
            if (quote.source != self._source or quote.payload.as_of < gap.end
                    or quote.received_at < gap.end or quote.available_at > self.now()
                    or quote.event_at > quote.received_at or latest is None
                    or _market_facts(quote) != _market_facts(latest)):
                return None
            for point in (quote.payload.bid, quote.payload.ask, quote.payload.last):
                if point is not None and point.event_at is not None and point.event_at > point.received_at:
                    return None
        return quotes

    def snapshot(self, instrument_ids=None) -> MarketSnapshot:
        ids = set(self._streams) if instrument_ids is None else set(instrument_ids)
        if not ids <= self._streams.keys():
            raise ValueError('Unregistered snapshot instruments')
        quotes = tuple(event for identifier in sorted(ids, key=str)
                       if (event := self._streams[identifier].snapshot()) is not None)
        bars = tuple(event.model_copy(deep=True) for event in self._bars.values() if event.instrument_id in ids)
        return MarketSnapshot(schema_version='1.0', epoch=self._position.epoch, cursor=self._position.sequence,
                              as_of=self.now(), quotes=quotes, bars=bars, health=self._health, gap=self._gap)

    def replay(self, epoch, cursor=None):
        position = epoch if isinstance(epoch, MarketCursor) else MarketCursor(epoch=epoch, sequence=cursor)
        epoch, cursor = position.epoch, position.sequence
        oldest = self._history[0].sequence if self._history else self._position.sequence + 1
        if epoch != self._position.epoch or cursor > self._position.sequence or cursor < oldest - 1:
            raise SnapshotRequired('snapshot_required')
        return tuple(update.model_copy(deep=True) for update in self._history if update.sequence > cursor)

    async def wait_for_update(self, epoch, cursor=None, *, timeout):
        pending = self.replay(epoch, cursor)
        if pending:
            return pending
        self._changed.clear()
        pending = self.replay(epoch, cursor)
        if pending:
            return pending
        try:
            await asyncio.wait_for(self._changed.wait(), timeout)
        except TimeoutError:
            return ()
        return self.replay(epoch, cursor)
