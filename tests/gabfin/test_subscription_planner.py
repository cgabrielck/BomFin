from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import asyncio
import pytest

from gabfin.contracts.market import MarketSession
from gabfin.contracts.subscriptions import Demand, FeedCapabilities, SubscriptionKey
from gabfin.providers.registry import default_registry
from gabfin.providers.futu.symbols import InstrumentCatalog
from test_symbols import AAPL, MSFT, CALL, PUT, equity, option

NOW = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)
OWNER = UUID('99999999-9999-4999-8999-999999999999')


def key(identifier=AAPL, channel='quote', timeframe=None):
    return SubscriptionKey(instrument_id=identifier, channel=channel, timeframe=timeframe)


def demand(identifier=AAPL, priority='chart', *, owner=OWNER, expires=None, channel='quote', timeframe=None):
    return Demand(schema_version='1.0', demand_id=uuid4(), key=key(identifier, channel, timeframe),
                  priority=priority, owner=owner, expires_at=expires or NOW + timedelta(minutes=5))


def caps(**changes):
    base = FeedCapabilities(schema_version='1.0', source='futu', asset_classes=['equity', 'option'],
                            sessions=['regular'], latency_label='unknown', max_subscriptions=10,
                            history_limits=[], checked_at=NOW, permission_errors=[])
    return FeedCapabilities.model_validate(base.model_dump(mode='python') | changes)


def plan(demands, *, instruments=None, current=(), capability=None, equity_slots=1, option_slots=1,
         support=None, session=MarketSession.REGULAR, ttl=timedelta(minutes=3), budget_checked=NOW,
         registry=None):
    from gabfin.market.subscriptions import plan_subscriptions, QuotaBudget, ChannelSupport

    slots = {'equity': equity_slots, 'option': option_slots}
    return plan_subscriptions(
        demands, capability or caps(), InstrumentCatalog([equity(), equity(MSFT, 'US.MSFT')] if instruments is None else instruments),
        registry=registry or default_registry(),
        as_of=NOW, session=session, max_snapshot_age=ttl,
        budget=QuotaBudget(slots, budget_checked),
        supported=[ChannelSupport('quote', asset_class=a, session='regular') for a in ('equity', 'option')] if support is None else support, current=current)


def test_holding_preempts_chart_with_exact_delta_and_shared_owner_dedup():
    chart = demand(AAPL, 'chart')
    holding = demand(MSFT, 'holding')
    result = plan([chart, demand(AAPL, owner=uuid4()), holding], current=[key(AAPL)])
    assert result.apply_allowed
    assert result.plan.accepted == (key(MSFT),)
    assert result.subscribe == (key(MSFT),) and result.unsubscribe == (key(AAPL),)
    assert result.plan.rejected[0].key == key(AAPL)
    assert result.plan.rejected[0].reason_codes == ('equity_quota_exhausted',)


def test_all_priorities_and_stable_ties_do_not_depend_on_request_order():
    requests = [demand(AAPL, 'candidate'), demand(MSFT, 'watchlist'), demand(AAPL, 'strategy'), demand(MSFT, 'chart')]
    first = plan(requests)
    assert first.plan.accepted == (key(MSFT),)
    assert plan(list(reversed(requests))).plan == first.plan
    ties = [demand(MSFT, 'chart'), demand(AAPL, 'chart')]
    assert plan(ties).plan.accepted == plan(list(reversed(ties))).plan.accepted == (key(AAPL),)


def test_expired_owner_does_not_cancel_another_owner_and_last_owner_releases():
    result = plan([demand(expires=NOW), demand(owner=uuid4())], current=[key()])
    assert result.plan.accepted == (key(),) and not result.plan.rejected
    assert not result.subscribe and not result.unsubscribe
    result = plan([demand(expires=NOW)], current=[key()])
    assert result.plan.rejected[0].reason_codes == ('demand_expired',)
    assert result.unsubscribe == (key(),)


def test_fake_adapter_receives_only_our_released_and_added_logical_keys():
    class FakeFeedAdapter:
        def __init__(self):
            self.own = {key(AAPL).identity}
            self.calls = []
        async def unsubscribe(self, keys):
            self.calls.append(('unsubscribe', tuple(keys)))
            self.own.difference_update(k.identity for k in keys)
        async def subscribe(self, keys):
            self.calls.append(('subscribe', tuple(keys)))
            self.own.update(k.identity for k in keys)
    adapter = FakeFeedAdapter()
    schedule = plan([demand(AAPL), demand(MSFT, 'holding')], current=[key(AAPL)])
    async def apply():
        assert schedule.apply_allowed
        await adapter.unsubscribe(list(schedule.unsubscribe))
        await adapter.subscribe(list(schedule.subscribe))
    asyncio.run(apply())
    assert adapter.own == {key(MSFT).identity}
    assert adapter.calls == [('unsubscribe', (key(AAPL),)), ('subscribe', (key(MSFT),))]


def test_options_share_expiry_channel_cost_but_not_stock_or_other_expiry_quota():
    records = [equity(), option(), option(PUT, 'put'), option(MSFT, expiry='2026-12-25')]
    requests = [demand(AAPL, 'holding'), demand(CALL, 'holding'), demand(PUT, 'chart'), demand(MSFT, 'candidate')]
    result = plan(requests, instruments=records, equity_slots=1, option_slots=1)
    assert set(k.instrument_id for k in result.plan.accepted) == {AAPL, CALL, PUT}
    assert result.plan.rejected[0].key.instrument_id == MSFT
    assert result.plan.rejected[0].reason_codes == ('option_quota_exhausted',)


def test_option_capacity_is_independent_of_zero_stock_capacity():
    result = plan([demand(CALL)], instruments=[equity(), option()], equity_slots=0,
                  option_slots=1, capability=caps(max_subscriptions=0))
    assert result.plan.accepted == (key(CALL),) and result.apply_allowed


def test_channel_timeframes_are_distinct_and_require_explicit_support():
    from gabfin.market.subscriptions import ChannelSupport
    from gabfin.contracts.market import Timeframe

    one = Timeframe(count=1, unit='minute')
    five = Timeframe(count=5, unit='minute')
    requests = [demand(channel='bar', timeframe=one, priority='holding'), demand(channel='bar', timeframe=five)]
    result = plan(requests, support=[ChannelSupport('bar', one, asset_class='equity', session='regular'),
                                     ChannelSupport('bar', five, asset_class='equity', session='regular')])
    assert result.plan.accepted == (key(channel='bar', timeframe=one),)
    assert result.plan.rejected[0].reason_codes == ('equity_quota_exhausted',)
    unknown = plan([demand(channel='bar', timeframe=one)])
    assert unknown.plan.rejected[0].reason_codes == ('channel_unverified',)


@pytest.mark.parametrize('change, reason', [
    ({'checked_at': NOW - timedelta(minutes=4)}, 'capability_stale'),
    ({'checked_at': NOW + timedelta(seconds=1)}, 'capability_in_future'),
    ({'permission_errors': ('denied',)}, 'permission_error'),
    ({'sessions': ()}, 'session_unverified'),
    ({'max_subscriptions': None}, 'equity_quota_unknown'),
])
def test_uncertain_capabilities_freeze_changes_including_existing_holding(change, reason):
    result = plan([demand(priority='holding')], capability=caps(**change), current=[key()])
    assert not result.apply_allowed and not result.subscribe and not result.unsubscribe
    assert reason in result.plan.rejected[0].reason_codes and not result.plan.accepted


@pytest.mark.parametrize('pool', ['equity', 'option'])
def test_unknown_quota_is_distinct_from_zero(pool):
    records = [equity(), option()]
    identifier = AAPL if pool == 'equity' else CALL
    unknown = plan([demand(identifier)], instruments=records, equity_slots=None if pool == 'equity' else 1,
                   option_slots=None if pool == 'option' else 1, current=[key(identifier)])
    assert not unknown.apply_allowed and not unknown.unsubscribe
    assert unknown.plan.rejected[0].reason_codes == (pool + '_quota_unknown',)
    zero = plan([demand(identifier)], instruments=records, equity_slots=0, option_slots=0)
    assert zero.apply_allowed and not zero.plan.accepted
    assert zero.plan.rejected[0].reason_codes == (('equity' if pool == 'equity' else 'option') + '_quota_exhausted',)


def test_quota_snapshot_must_match_and_not_exceed_declared_stock_maximum():
    result = plan([demand()], budget_checked=NOW - timedelta(seconds=1), current=[key()])
    assert not result.apply_allowed and result.plan.rejected[0].reason_codes == ('quota_snapshot_mismatch',)
    result = plan([demand()], equity_slots=11)
    assert not result.apply_allowed and result.plan.rejected[0].reason_codes == ('quota_snapshot_conflict',)


@pytest.mark.parametrize('kind, reason', [('unknown', 'unknown_instrument'), ('vendor', 'vendor_symbol_missing'),
                                         ('market', 'market_unsupported'), ('asset', 'asset_class_unverified'),
                                         ('expired', 'instrument_expired')])
def test_identity_and_asset_failures_have_explicit_reasons(kind, reason):
    records = [equity()]
    identifier = AAPL
    capability = caps()
    if kind == 'unknown':
        identifier = MSFT
    elif kind == 'vendor':
        records = [equity().model_copy(update={'vendor_symbols': {'other': 'AAPL'}})]
    elif kind == 'market':
        records = [equity().model_copy(update={'vendor_symbols': {'futu': 'HK.00700'}})]
    elif kind == 'asset':
        capability = caps(asset_classes=())
    else:
        identifier = CALL
        records.append(option(expiry='2026-11-24'))
    result = plan([demand(identifier)], instruments=records, capability=capability)
    assert result.plan.rejected[0].reason_codes == (reason,)


def test_lost_channel_declaration_does_not_teardown_existing_holding():
    result = plan([demand(priority='holding')], current=[key()], support=[])
    assert not result.apply_allowed and not result.unsubscribe
    assert 'channel_unverified' in result.plan.rejected[0].reason_codes


def test_empty_demand_set_freezes_when_affected_quota_or_capability_is_unknown():
    result = plan([], current=[key()], equity_slots=None, option_slots=None,
                  capability=caps(checked_at=NOW - timedelta(days=1)))
    assert not result.apply_allowed and not result.unsubscribe and not result.subscribe


def test_repeated_demand_id_cannot_change_meaning():
    first = demand()
    assert len(plan([first, first]).plan.accepted) == 1
    with pytest.raises(ValueError):
        plan([first, first.model_copy(update={'priority': 'holding'})])


@pytest.mark.parametrize('value', [True, -1, 1.5, '1'])
def test_invalid_quota_configuration_is_rejected(value):
    from gabfin.market.subscriptions import QuotaBudget
    with pytest.raises(ValueError):
        QuotaBudget({'equity': value, 'option': 1}, NOW)


@pytest.mark.parametrize('session', ['closed', 'unknown', 'pre_market'])
def test_unverified_session_is_not_authorization(session):
    result = plan([demand()], session=session)
    assert not result.apply_allowed and 'session_unverified' in result.plan.rejected[0].reason_codes


def test_foreign_current_key_and_implicit_ttl_are_rejected():
    result = plan([], current=[key(CALL)])
    assert not result.apply_allowed and not result.unsubscribe
    assert 'current_identity_unverified' in result.blocked_reasons
    with pytest.raises(ValueError):
        plan([demand()], ttl=timedelta(0))


def test_planning_leaves_inputs_and_unknown_latency_unchanged():
    capability = caps()
    before = capability.model_dump_json()
    request = demand()
    result = plan([request], capability=capability)
    assert capability.model_dump_json() == before
    assert capability.latency_label == 'unknown' and result.plan.accepted == (request.key,)


@pytest.mark.parametrize('change', [{'checked_at': NOW - timedelta(days=1)},
                                 {'checked_at': NOW + timedelta(seconds=1)}, {'permission_errors': ('denied',)}])
def test_no_live_demands_still_requires_reliable_manifest_for_release(change):
    result = plan([], capability=caps(**change), current=[key()])
    assert not result.apply_allowed and not result.unsubscribe and result.blocked_reasons


def test_current_pool_is_checked_even_if_only_other_asset_is_requested():
    result = plan([demand(CALL)], instruments=[equity(), option()], current=[key(AAPL)], equity_slots=None)
    assert not result.apply_allowed and not result.subscribe and not result.unsubscribe
    assert 'equity_quota_unknown' in result.blocked_reasons


def test_missing_current_catalog_binding_is_frozen_instead_of_dropped():
    result = plan([demand(MSFT)], current=[key(AAPL)], instruments=[equity(MSFT, 'US.MSFT')])
    assert not result.apply_allowed and not result.subscribe and not result.unsubscribe
    assert result.blocked_reasons == ('current_identity_unverified',)


def test_known_empty_target_can_release_owned_keys():
    result = plan([], current=[key()])
    assert result.apply_allowed and result.unsubscribe == (key(),)


def test_empty_vendor_ticker_is_not_allocated():
    result = plan([demand()], instruments=[equity(symbol='US.')])
    assert result.plan.rejected[0].reason_codes == ('vendor_symbol_invalid',)


def test_non_us_option_is_registered_and_rejected_individually():
    hk_stock = equity(MSFT, 'HK.00700')
    hk_option = option(PUT).model_copy(update={
        'vendor_symbols': {'futu': 'HK.TCH261218C350000'},
        'option': option(PUT).option.model_copy(update={'underlying_id': MSFT})})
    result = plan([demand(AAPL), demand(PUT)], instruments=[equity(), hk_stock, hk_option])
    assert result.plan.accepted == (key(AAPL),)
    assert result.plan.rejected[0].reason_codes == ('market_unsupported',)


def test_stock_pre_market_support_does_not_imply_option_pre_market_support():
    from gabfin.market.subscriptions import ChannelSupport
    support = [ChannelSupport('quote', asset_class='equity', session='pre_market'),
               ChannelSupport('quote', asset_class='option', session='regular')]
    result = plan([demand(AAPL), demand(CALL)], instruments=[equity(), option()],
                  capability=caps(sessions=('regular', 'pre_market')), session='pre_market', support=support)
    assert result.plan.accepted == (key(AAPL),)
    assert result.plan.rejected[0].reason_codes == ('channel_unverified',)
