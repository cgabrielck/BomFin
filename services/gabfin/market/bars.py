"""Bounded event-time trade bars over an explicit exchange calendar snapshot."""
from datetime import timedelta
from decimal import Decimal, localcontext
from itertools import groupby
from bisect import bisect_right
from uuid import UUID

from pydantic import TypeAdapter

from gabfin.contracts.common import UtcTimestamp
from gabfin.contracts.events import TradeMarketEvent
from gabfin.contracts.feed import CalendarSnapshot
from gabfin.contracts.market import Bar, PositiveCounter, Timeframe
from gabfin.market.sequences import numeric_sequence


class MarketCapacityError(ValueError):
    """The caller must mark a gap; never silently discard an uncounted trade."""


class BarBuilder:
    def __init__(self, instrument_id: UUID, *, source: str, calendar: CalendarSnapshot,
                 timeframe: Timeframe, max_bars: int, max_trades: int,
                 corporate_action_policy: str):
        counter = TypeAdapter(PositiveCounter)
        self._max_bars = counter.validate_python(max_bars)
        self._max_trades = counter.validate_python(max_trades)
        if timeframe.unit not in ('second', 'minute'):
            raise ValueError('Only fixed second/minute trade bars are supported')
        self._duration = timedelta(seconds=timeframe.count * (60 if timeframe.unit == 'minute' else 1))
        self._id, self._source = instrument_id, source
        self._calendar = calendar.model_copy(deep=True)
        self._session_starts = tuple(window.start for window in calendar.windows)
        self._timeframe = timeframe
        self._policy = corporate_action_policy
        self._buckets = {}
        self._identities = {}
        self._dedup_keys = {}
        self._floor = calendar.coverage_start
        self._watermark = calendar.coverage_start

    def _window(self, at):
        if not self._calendar.coverage_start <= at < self._calendar.coverage_end:
            raise ValueError('calendar_unavailable')
        index = bisect_right(self._session_starts, at) - 1
        if index >= 0 and at < self._calendar.windows[index].end:
            return self._calendar.windows[index]
        return None

    @staticmethod
    def _ordered(trades):
        values = sorted(((event, numeric_sequence(event.source_seq)) for event in trades.values()),
                        key=lambda item: item[0].event_at)
        for _, group in groupby(values, key=lambda item: item[0].event_at):
            tied = list(group)
            if len({event.payload.price for event, _ in tied}) > 1:
                sequences = [sequence for _, sequence in tied]
                if None in sequences or len(set(sequences)) != len(tied):
                    raise ValueError('ambiguous_trade_order')
        return [event for event, _ in sorted(values, key=lambda item:
                (item[0].event_at, item[1] if item[1] is not None else 0, item[0].dedup_key))]

    def _render(self, start, bucket, *, status, revision, available_at):
        trades = self._ordered(bucket['trades'])
        quantities = [event.payload.quantity for event in trades]
        precision = max(q.adjusted() for q in quantities) - min(q.as_tuple().exponent for q in quantities) + len(str(len(trades))) + 2
        if precision > 1000:
            raise MarketCapacityError('quantity_precision_capacity')
        with localcontext() as context:
            context.prec = max(precision, 1)
            volume = sum(quantities, Decimal(0))
        return Bar(schema_version='1.0', instrument_id=self._id, source=self._source,
                   timeframe=self._timeframe, session=bucket['session'], start=start, end=bucket['end'],
                   open=trades[0].payload.price, high=max(e.payload.price for e in trades),
                   low=min(e.payload.price for e in trades), close=trades[-1].payload.price,
                   volume=volume, status=status, revision=revision, corporate_action_policy=self._policy,
                   event_at=max(e.event_at for e in trades),
                   received_at=max(e.received_at for e in trades), available_at=available_at)

    def apply(self, event: TradeMarketEvent) -> list[Bar]:
        if (not isinstance(event, TradeMarketEvent) or event.instrument_id != self._id
                or event.source != self._source):
            raise ValueError('Only the configured instrument/source trade is accepted')
        if event.event_at > event.available_at or event.event_at < self._floor:
            raise ValueError('future_or_evicted_trade')
        window = self._window(event.event_at)
        if window is None:
            raise ValueError('market_closed')
        identity = (('trade_id', event.payload.trade_id) if event.payload.trade_id is not None else
                    ('dedup_key', event.dedup_key))
        fingerprint = (event.event_at, event.payload.price, event.payload.quantity, event.source_seq)
        if event.dedup_key in self._dedup_keys and self._dedup_keys[event.dedup_key] != identity:
            raise ValueError('trade_identity_conflict')
        if identity in self._identities:
            if self._identities[identity][1:] != (fingerprint, event.dedup_key):
                raise ValueError('trade_identity_conflict')
            return []
        start = window.start + ((event.event_at - window.start) // self._duration) * self._duration
        old = self._buckets.get(start)
        bucket = dict(trades=dict(old['trades']) if old else {}, session=window.session,
                      end=min(start + self._duration, window.end))
        bucket['trades'][identity] = event.model_copy(deep=True)
        capture = max(event.available_at, self._watermark)
        prior = old['bar'] if old else None
        status = 'corrected' if prior is not None and prior.status != 'forming' else ('final' if bucket['end'] <= capture else 'forming')
        revision = prior.revision + 1 if status == 'corrected' else 0
        bar = self._render(start, bucket, status=status, revision=revision, available_at=capture)
        # Determine evictions without mutating state; a rejected input is atomic.
        evict = []
        retained_trades = len(self._identities)
        retained_bars = len(self._buckets)
        for old_start in sorted(self._buckets):
            if retained_bars + (old is None) <= self._max_bars and retained_trades + 1 <= self._max_trades:
                break
            candidate = self._buckets[old_start]
            if old_start >= start or candidate['end'] > capture:
                break
            evict.append(old_start)
            retained_trades -= len(candidate['trades'])
            retained_bars -= 1
        if retained_bars + (old is None) > self._max_bars or retained_trades + 1 > self._max_trades:
            raise MarketCapacityError('trade_retention_capacity')
        updates = [bar for bar in self.advance(capture) if bar.start != start]
        for old_start in evict:
            removed = self._buckets.pop(old_start)
            self._floor = max(self._floor, removed['end'])
            for key in removed['trades']:
                _, _, dedup_key = self._identities.pop(key)
                del self._dedup_keys[dedup_key]
        bucket['bar'] = bar
        self._buckets[start] = bucket
        self._identities[identity] = (start, fingerprint, event.dedup_key)
        self._dedup_keys[event.dedup_key] = identity
        updates.append(bar.model_copy(deep=True))
        return updates

    def advance(self, watermark) -> list[Bar]:
        watermark = TypeAdapter(UtcTimestamp).validate_python(watermark)
        if watermark < self._watermark:
            raise ValueError('Watermark cannot move backwards')
        updates = []
        for start, bucket in sorted(self._buckets.items()):
            if bucket['end'] <= watermark and bucket['bar'].status == 'forming':
                bar = self._render(start, bucket, status='final', revision=0, available_at=watermark)
                bucket['bar'] = bar
                updates.append(bar.model_copy(deep=True))
        self._watermark = watermark
        return updates

    def snapshot(self) -> tuple[Bar, ...]:
        return tuple(bucket['bar'].model_copy(deep=True) for _, bucket in sorted(self._buckets.items()))
