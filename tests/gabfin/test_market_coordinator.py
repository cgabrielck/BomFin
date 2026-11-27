from datetime import timedelta
from uuid import uuid4

import pytest

from gabfin.contracts.feed import RecoveryBatch
from gabfin.market.coordinator import MarketCoordinator, SnapshotRequired
from test_quote_stream import observation, ID, NOW
from gabfin.market.replay import replay_events


def coordinator(**kwargs):
    return MarketCoordinator([ID], source='test-feed', replay_capacity=3, max_bars=3,
                             clock=lambda: NOW + timedelta(minutes=1), **kwargs)


def test_snapshot_and_bounded_replay_require_reset_for_old_or_foreign_cursor():
    market = coordinator()
    initial = market.snapshot()
    for i in range(5):
        market.apply(observation(str(100 + i)))
    snapshot = market.snapshot()
    assert snapshot.cursor == 5 and snapshot.quotes[0].payload.last.price == 104
    assert [update.sequence for update in market.replay(snapshot.epoch, 2)] == [3, 4, 5]
    with pytest.raises(SnapshotRequired): market.replay(snapshot.epoch, 1)
    with pytest.raises(SnapshotRequired): market.replay(uuid4(), 5)
    assert initial.cursor == 0 and initial.quotes == ()


def test_heartbeat_or_bare_complete_flag_cannot_clear_a_gap():
    market = coordinator()
    market.heartbeat(NOW)
    market.disconnected('network_lost')
    gap = market.snapshot().gap
    market.heartbeat(NOW + timedelta(seconds=30))
    assert market.snapshot().health.connected and market.snapshot().health.gap_pending
    batch = RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source='test-feed',
                          start=gap.start, end=NOW + timedelta(minutes=1), complete=False,
                          evidence='fixture', events=())
    assert not market.recover(batch)
    assert market.snapshot().health.gap_pending
    assert not market.recover(batch.model_copy(update={'complete': True}))
    assert market.snapshot().health.gap_pending


def test_recovery_cannot_close_a_new_gap_or_hide_foreign_or_future_events():
    market = coordinator()
    market.heartbeat(NOW)
    gap = market.snapshot().gap
    batch = RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source='test-feed',
                          start=gap.start, end=NOW, complete=True, evidence='fixture', events=())
    market.disconnected('another_disconnect')
    market.heartbeat(NOW + timedelta(seconds=1))
    with pytest.raises(ValueError): market.recover(batch)
    assert market.snapshot().gap.gap_id != gap.gap_id
    with pytest.raises(ValueError):
        market.recover(batch.model_copy(update={'gap_id': market.snapshot().gap.gap_id,
                                                'end': NOW + timedelta(seconds=120)}))
    assert market.snapshot().health.gap_pending


def test_duplicate_and_old_quotes_do_not_generate_new_state_or_volume():
    market = coordinator()
    first = observation()
    assert len(market.apply(first)) == 1
    assert market.apply(first) == []
    assert market.apply(observation('50', source='2026-11-25T14:00:00Z', age=3600000)) == []
    assert market.snapshot().cursor == 1
    assert market.snapshot().bars == ()


def test_replay_never_consumes_a_future_available_event():
    market = MarketCoordinator([ID], source='test-feed', replay_capacity=3, max_bars=3, clock=lambda: NOW)
    future = observation('200').model_copy(update={'available_at': NOW + timedelta(minutes=1)})
    updates = tuple(replay_events([observation('100'), future], market, as_of=NOW))
    assert len(updates) == 1 and market.snapshot().quotes[0].payload.last.price == 100
    with pytest.raises(ValueError, match='not_yet'):
        market.apply(future)


def test_unknown_instrument_and_backward_replay_are_explicit_failures():
    market = coordinator()
    with pytest.raises(ValueError): market.snapshot([uuid4()])
    future = observation('200').model_copy(update={'available_at': NOW + timedelta(seconds=10)})
    with pytest.raises(ValueError, match='available-time'):
        tuple(replay_events([future, observation('100')], market, as_of=NOW + timedelta(seconds=10)))


def test_new_connection_full_snapshot_resyncs_duplicate_quote_without_refreshing_source_price():
    market = coordinator()
    market.heartbeat(NOW)
    event = observation()
    market.apply(event)
    assert market.recover_latest_quotes()
    market.disconnected('reconnect')
    market.heartbeat(NOW + timedelta(seconds=30), cutover=NOW + timedelta(seconds=20))
    assert not market.recover_latest_quotes()
    point = event.payload.last.model_copy(update=dict(received_at=NOW + timedelta(seconds=30),
        available_at=NOW + timedelta(seconds=30), age_ms=32000))
    current = event.model_copy(update=dict(received_at=NOW + timedelta(seconds=30),
        available_at=NOW + timedelta(seconds=30), payload=event.payload.model_copy(update={
            'as_of': NOW + timedelta(seconds=30), 'last': point})))
    assert market.apply(current) == []
    assert market.recover_latest_quotes([current])
    assert market.snapshot().quotes[0].event_at == event.event_at
    assert market.snapshot().quotes[0].payload.last.age_ms == 2000


def test_quote_snapshot_recovery_cannot_repair_missing_bar_or_trade_history():
    from gabfin.contracts.subscriptions import SubscriptionKey
    market = MarketCoordinator([ID], source='test-feed', replay_capacity=3, max_bars=3,
        required_keys=(SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None),
                       SubscriptionKey(instrument_id=ID, channel='bar', timeframe=dict(count=1, unit='minute'))),
        clock=lambda: NOW)
    market.heartbeat(NOW)
    market.apply(observation())
    assert not market.recover_latest_quotes()
    assert market.snapshot().health.gap_pending


def test_same_dedup_key_with_changed_market_fact_is_a_conflict_not_a_duplicate():
    market = coordinator()
    event = observation('100')
    market.apply(event)
    conflict = observation('101').model_copy(update={'dedup_key': event.dedup_key})
    with pytest.raises(ValueError, match='conflict'):
        market.apply(conflict)
    assert market.snapshot().quotes[0].payload.last.price == 100


def test_healthy_clock_can_finalize_a_bar_without_another_trade():
    from test_bar_builder import builder, trade, ID as trade_id, START
    market = MarketCoordinator([trade_id], source='fixture', replay_capacity=10, max_bars=3,
                               builders={trade_id: builder()}, required_channels=('trade',),
                               clock=lambda: START + timedelta(seconds=70))
    market.apply(trade(1, 10, '100'))
    updates = market.advance(START + timedelta(seconds=70))
    assert len(updates) == 1
    assert updates[0].event.payload.status == 'final'
    assert updates[0].event.payload.volume == 2


def test_rejected_skewed_or_older_quote_cannot_prove_resync():
    market = coordinator()
    market.heartbeat(NOW)
    skew = observation().model_copy(update={'event_at': NOW + timedelta(seconds=1)})
    assert market.apply(skew) == []
    assert not market.recover_latest_quotes([skew])
    assert market.snapshot().health.gap_pending
    newest = observation('105')
    market.apply(newest)
    older = observation('99', source='2026-11-25T14:00:00Z', age=3600000)
    assert market.apply(older) == []
    assert not market.recover_latest_quotes([older])
    assert market.snapshot().health.gap_pending


def test_old_worker_cutover_cannot_shrink_a_later_disconnect_window():
    now = [NOW]
    market = MarketCoordinator([ID], source='test-feed', replay_capacity=10, max_bars=3,
                               clock=lambda: now[0])
    market.heartbeat(NOW)
    market.apply(observation())
    assert market.recover_latest_quotes()
    now[0] = NOW + timedelta(seconds=10)
    market.heartbeat(now[0])
    market.disconnected('network_lost')
    start = market.recovery_gap.start
    now[0] = NOW + timedelta(seconds=30)
    market.heartbeat(now[0], cutover=NOW)
    gap = market.recovery_gap
    assert gap.start == start and gap.end == now[0]
    assert not market.recover_latest_quotes([observation()])


def test_evicted_coordinator_dedup_still_cannot_double_count_a_retained_trade():
    from test_bar_builder import builder, trade, ID as trade_id, START
    market = MarketCoordinator([trade_id], source='fixture', replay_capacity=1, max_bars=3,
        builders={trade_id: builder()}, required_channels=('trade',), clock=lambda: START + timedelta(seconds=70))
    first = trade(1, 1, '100')
    market.apply(first); market.apply(trade(2, 2, '101'))
    altered = first.model_copy(update={'payload': first.payload.model_copy(update={'trade_id': 'new-id'})})
    with pytest.raises(ValueError, match='conflict'):
        market.apply(altered)
    assert market.snapshot().bars[0].payload.volume == 4


def test_history_requires_complete_coverage_for_each_instrument_and_channel():
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.contracts.feed import RecoveryCoverage
    second = uuid4()
    market = MarketCoordinator([ID, second], source='test-feed', replay_capacity=10, max_bars=3,
                               clock=lambda: NOW + timedelta(seconds=30))
    market.heartbeat(NOW)
    gap = market.recovery_gap
    coverage = RecoveryCoverage(key=SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None),
        start=gap.start, end=gap.end, record_count=0, complete=True, has_more=False,
        empty_reason='provider_verified_empty')
    batch = RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source=gap.source,
        start=gap.start, end=gap.end, complete=True, evidence='verified_history_fixture', events=(),
        coverage=(coverage,))
    assert not market.recover(batch)
    second_coverage = coverage.model_copy(update={'key': coverage.key.model_copy(update={'instrument_id': second})})
    assert market.recover(batch.model_copy(update={'coverage': (coverage, second_coverage)}))
    assert market.snapshot().gap is None


def test_history_bar_coverage_cannot_substitute_a_different_timeframe_or_unfinished_page():
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.contracts.feed import RecoveryCoverage
    key = SubscriptionKey(instrument_id=ID, channel='bar', timeframe=dict(count=1, unit='minute'))
    market = MarketCoordinator([ID], source='test-feed', replay_capacity=10, max_bars=3,
                               required_keys=(key,), clock=lambda: NOW)
    market.heartbeat(NOW)
    gap = market.recovery_gap
    coverage = RecoveryCoverage(key=key, start=gap.start, end=gap.end, record_count=0,
        complete=True, has_more=False, empty_reason='market_closed')
    batch = RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source=gap.source,
        start=gap.start, end=gap.end, complete=True, evidence='fixture', events=(), coverage=(coverage,))
    other = key.model_copy(update={'timeframe': key.timeframe.model_copy(update={'count': 5})})
    assert not market.recover(batch.model_copy(update={'coverage': (coverage.model_copy(update={'key': other}),)}))
    assert not market.recover(batch.model_copy(update={'coverage': (coverage.model_copy(update={'has_more': True}),)}))
    assert market.recover(batch)


def test_declared_contiguous_sequence_hole_stays_open_until_missing_print_is_recovered():
    from gabfin.contracts.subscriptions import SubscriptionKey, SequenceRule
    from gabfin.contracts.feed import RecoveryCoverage
    from test_bar_builder import builder, trade, ID as trade_id, START
    key = SubscriptionKey(instrument_id=trade_id, channel='trade', timeframe=None)
    market = MarketCoordinator([trade_id], source='fixture', replay_capacity=10, max_bars=3,
        builders={trade_id: builder()}, required_channels=('trade',),
        sequence_rules=(SequenceRule(channel='trade', timeframe=None, semantics='contiguous'),),
        clock=lambda: START + timedelta(seconds=30))
    market.heartbeat(START)
    market.apply(trade(1, 1, '100')); market.apply(trade(3, 3, '103'))
    market.heartbeat(START + timedelta(seconds=10))
    gap = market.recovery_gap
    receipt = RecoveryCoverage(key=key, start=gap.start, end=gap.end, record_count=0,
        complete=True, has_more=False, empty_reason='provider_verified_empty')
    batch = RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source=gap.source,
        start=gap.start, end=gap.end, complete=True, evidence='fixture', events=(), coverage=(receipt,))
    assert not market.recover(batch)
    receipt = receipt.model_copy(update={'record_count': 1, 'empty_reason': None})
    assert market.recover(batch.model_copy(update={'events': (trade(2, 2, '102'),), 'coverage': (receipt,)}))
    assert market.snapshot().bars[0].payload.volume == 6


def test_numeric_opaque_sequences_are_not_assumed_contiguous():
    market = coordinator()
    market.apply(observation('100').model_copy(update={'source_seq': '1'}))
    market.apply(observation('101').model_copy(update={'source_seq': '300'}))
    assert market.snapshot().cursor == 2
    assert market.snapshot().gap.reason == 'bootstrap_unverified'


def test_history_duplicate_rows_do_not_count_as_complete_missing_prints():
    from gabfin.contracts.subscriptions import SubscriptionKey
    from gabfin.contracts.feed import RecoveryCoverage
    from test_bar_builder import builder, trade, ID as trade_id, START
    key = SubscriptionKey(instrument_id=trade_id, channel='trade', timeframe=None)
    market = MarketCoordinator([trade_id], source='fixture', replay_capacity=10, max_bars=3,
        builders={trade_id: builder()}, required_channels=('trade',), clock=lambda: START + timedelta(seconds=30))
    market.heartbeat(START)
    market.disconnected('fixture_gap')
    market.heartbeat(START + timedelta(seconds=20))
    gap = market.recovery_gap
    receipt = RecoveryCoverage(key=key, start=gap.start, end=gap.end, record_count=2,
        complete=True, has_more=False)
    event = trade(1, 1, '100')
    batch = RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source=gap.source,
        start=gap.start, end=gap.end, complete=True, evidence='fixture', events=(event,event), coverage=(receipt,))
    assert not market.recover(batch)
    assert market.snapshot().health.gap_pending


def test_contiguous_sequence_cannot_reset_or_relabel_a_prior_number():
    from gabfin.contracts.subscriptions import SequenceRule
    from test_bar_builder import builder, trade, ID as trade_id, START
    market = MarketCoordinator([trade_id], source='fixture', replay_capacity=2, max_bars=3,
        builders={trade_id: builder()}, required_channels=('trade',),
        sequence_rules=(SequenceRule(channel='trade', timeframe=None, semantics='contiguous'),),
        clock=lambda: START + timedelta(seconds=30))
    market.apply(trade(100, 1, '100'))
    with pytest.raises(ValueError, match='sequence'):
        market.apply(trade(1, 2, '101'))
    assert market.snapshot().bars[0].payload.volume == 2
    assert market.snapshot().health.gap_pending


def test_skewed_quote_cannot_fill_a_contiguous_hole_through_history():
    from gabfin.contracts.subscriptions import SequenceRule, SubscriptionKey
    from gabfin.contracts.feed import RecoveryCoverage
    market = coordinator(sequence_rules=(SequenceRule(channel='quote', timeframe=None, semantics='contiguous'),))
    market.heartbeat(NOW)
    market.apply(observation('100').model_copy(update={'source_seq': '1'}))
    market.apply(observation('103').model_copy(update={'source_seq': '3'}))
    market.heartbeat(NOW + timedelta(seconds=10))
    gap = market.recovery_gap
    skew = observation('102').model_copy(update={'source_seq': '2', 'event_at': NOW + timedelta(seconds=1)})
    receipt = RecoveryCoverage(key=SubscriptionKey(instrument_id=ID, channel='quote', timeframe=None),
        start=gap.start, end=gap.end, record_count=1, complete=True, has_more=False)
    batch = RecoveryBatch(schema_version='1.0', gap_id=gap.gap_id, source=gap.source,
        start=gap.start, end=gap.end, complete=True, evidence='fixture', events=(skew,), coverage=(receipt,))
    assert not market.recover(batch)
    assert market.snapshot().health.gap_pending
    assert market.snapshot().quotes[0].payload.last.price == 103
