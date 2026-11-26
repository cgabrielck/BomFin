"""The provider registry routes instruments to sources by declaration.

A registry entry says what a source accepts. It never says what a
source is entitled to, and it never guesses a symbol it does not
recognise. These tests pin both boundaries.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from gabfin.contracts.market import AssetClass, Instrument
from gabfin.contracts.subscriptions import Demand, FeedCapabilities, SubscriptionKey
from gabfin.providers.registry import (
    ALPACA_PROFILE,
    FUTU_PROFILE,
    ProviderRegistry,
    SourceProfile,
    UnknownSource,
    default_registry,
)

NOW = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)
AAPL = UUID('11111111-1111-4111-8111-111111111111')
MSFT = UUID('22222222-2222-4222-8222-222222222222')
CALL = UUID('33333333-3333-4333-8333-333333333333')


def equity(identifier=AAPL, symbols=None):
    return Instrument(schema_version='1.0', instrument_id=identifier, asset_class='equity',
                      vendor_symbols=symbols or {'futu': 'US.AAPL', 'alpaca': 'AAPL'},
                      currency='USD', tick_size='0.01', lot_size='1')


def option(identifier=CALL, symbols=None):
    return Instrument(schema_version='1.0', instrument_id=identifier, asset_class='option',
                      vendor_symbols=symbols or {
                          'futu': 'US.AAPL261218C350000', 'alpaca': 'AAPL261218C00350000'},
                      currency='USD', tick_size='0.01', lot_size='1',
                      option=dict(underlying_id=AAPL, expiry='2026-12-18', right='call',
                                  strike='350', multiplier='100'))


def test_a_source_is_looked_up_by_name_and_unknown_sources_are_refused():
    registry = default_registry()
    assert registry.sources() == ('alpaca', 'futu')
    assert registry.profile('futu').namespace == 'futu'
    with pytest.raises(UnknownSource):
        registry.profile('ibkr')


def test_a_duplicate_registration_is_refused():
    registry = ProviderRegistry([FUTU_PROFILE])
    with pytest.raises(ValueError):
        registry.register(FUTU_PROFILE)


def test_routing_prefers_a_source_whose_namespace_the_instrument_carries():
    registry = default_registry()
    only_alpaca = equity(symbols={'alpaca': 'AAPL'})
    only_futu = equity(symbols={'futu': 'US.AAPL'})
    assert registry.route(only_alpaca).source == 'alpaca'
    assert registry.route(only_futu).source == 'futu'


def test_routing_reports_every_source_that_can_serve_an_instrument():
    registry = default_registry()
    assert {profile.source for profile in registry.routes(equity())} == {'alpaca', 'futu'}


def test_a_missing_namespace_is_not_the_same_as_an_unrecognised_symbol():
    registry = default_registry()
    assert registry.profile('alpaca').validate(equity(symbols={'futu': 'US.AAPL'})) == 'vendor_symbol_missing'
    assert registry.profile('alpaca').validate(equity(symbols={'alpaca': 'not a ticker'})) == 'vendor_symbol_invalid'


def test_a_served_market_that_a_source_does_not_cover_is_unsupported_not_invalid():
    assert FUTU_PROFILE.validate(equity(symbols={'futu': 'HK.00700'})) == 'market_unsupported'


def test_a_dotted_alpaca_ticker_is_a_ticker_not_a_market():
    assert ALPACA_PROFILE.validate(equity(symbols={'alpaca': 'BRK.B'})) is None


def test_a_futu_symbol_that_names_no_known_market_is_invalid():
    assert FUTU_PROFILE.validate(equity(symbols={'futu': 'XX.AAPL'})) == 'vendor_symbol_invalid'


def test_an_option_symbol_must_match_the_option_shape():
    assert FUTU_PROFILE.validate(option(symbols={'futu': 'US.AAPL261218C350000'})) is None
    assert FUTU_PROFILE.validate(option(symbols={'futu': 'US.AAPL'})) == 'vendor_symbol_invalid'


def test_a_profile_needs_a_market_a_pool_and_a_distinct_pool_per_asset_class():
    with pytest.raises(ValueError):
        SourceProfile(source='', namespace='x', markets=('US',), known_market_prefixes=('US.',),
                      symbol_carries_market=True, accepts_equity=lambda s: True,
                      accepts_option=lambda s: True, pools={AssetClass.EQUITY: 'one'})
    with pytest.raises(ValueError):
        SourceProfile(source='x', namespace='x', markets=('US',), known_market_prefixes=('US.',),
                      symbol_carries_market=True, accepts_equity=lambda s: True,
                      accepts_option=lambda s: True,
                      pools={AssetClass.EQUITY: 'one', AssetClass.OPTION: 'one'})


def test_a_maximum_pool_must_be_a_pool_the_source_uses():
    with pytest.raises(ValueError):
        SourceProfile(source='x', namespace='x', markets=('US',), known_market_prefixes=('US.',),
                      symbol_carries_market=True, accepts_equity=lambda s: True,
                      accepts_option=lambda s: True, pools={AssetClass.EQUITY: 'one'},
                      maximum_pools=('other',))


def test_the_planner_refuses_an_unregistered_source_instead_of_planning_on_a_guess():
    from gabfin.market.subscriptions import ChannelSupport, QuotaBudget, plan_subscriptions
    from gabfin.providers.futu.symbols import InstrumentCatalog

    capability = FeedCapabilities(schema_version='1.0', source='ibkr', asset_classes=['equity'],
                                   sessions=['regular'], latency_label='unknown',
                                   max_subscriptions=10, history_limits=[], checked_at=NOW,
                                   permission_errors=[])
    with pytest.raises(ValueError):
        plan_subscriptions(
            [Demand(schema_version='1.0', demand_id=uuid4(),
                    key=SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None),
                    priority='chart', owner=uuid4(), expires_at=NOW + timedelta(minutes=5))],
            capability, InstrumentCatalog([equity()]), registry=default_registry(),
            as_of=NOW, session='regular', max_snapshot_age=timedelta(minutes=3),
            budget=QuotaBudget({'equity': 1}, NOW),
            supported=[ChannelSupport('quote', asset_class='equity', session='regular')])


def test_the_planner_routes_an_alpaca_capability_to_an_alpaca_named_instrument():
    from gabfin.market.subscriptions import ChannelSupport, QuotaBudget, plan_subscriptions
    from gabfin.providers.futu.symbols import InstrumentCatalog

    capability = FeedCapabilities(schema_version='1.0', source='alpaca', asset_classes=['equity'],
                                   sessions=['regular'], latency_label='delayed',
                                   max_subscriptions=10, history_limits=[], checked_at=NOW,
                                   permission_errors=[])
    record = equity(symbols={'alpaca': 'AAPL'})
    demand = Demand(schema_version='1.0', demand_id=uuid4(),
                    key=SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None),
                    priority='chart', owner=uuid4(), expires_at=NOW + timedelta(minutes=5))
    result = plan_subscriptions(
        [demand], capability, InstrumentCatalog([record]), registry=default_registry(),
        as_of=NOW, session='regular', max_snapshot_age=timedelta(minutes=3),
        budget=QuotaBudget({'equity': 1}, NOW),
        supported=[ChannelSupport('quote', asset_class='equity', session='regular')])
    assert result.apply_allowed and result.plan.accepted == (demand.key,)


def test_a_symbol_the_source_does_not_name_is_rejected_with_a_reason():
    from gabfin.market.subscriptions import ChannelSupport, QuotaBudget, plan_subscriptions
    from gabfin.providers.futu.symbols import InstrumentCatalog

    capability = FeedCapabilities(schema_version='1.0', source='alpaca', asset_classes=['equity'],
                                   sessions=['regular'], latency_label='delayed',
                                   max_subscriptions=10, history_limits=[], checked_at=NOW,
                                   permission_errors=[])
    record = equity(symbols={'futu': 'US.AAPL'})
    demand = Demand(schema_version='1.0', demand_id=uuid4(),
                    key=SubscriptionKey(instrument_id=AAPL, channel='quote', timeframe=None),
                    priority='chart', owner=uuid4(), expires_at=NOW + timedelta(minutes=5))
    result = plan_subscriptions(
        [demand], capability, InstrumentCatalog([record]), registry=default_registry(),
        as_of=NOW, session='regular', max_snapshot_age=timedelta(minutes=3),
        budget=QuotaBudget({'equity': 1}, NOW),
        supported=[ChannelSupport('quote', asset_class='equity', session='regular')])
    assert result.plan.rejected[0].reason_codes == ('vendor_symbol_missing',)
