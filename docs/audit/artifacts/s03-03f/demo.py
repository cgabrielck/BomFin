"""Synthetic planner demonstration; no provider connection or actual entitlement."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys
from uuid import UUID

from gabfin.contracts.market import Instrument
from gabfin.contracts.subscriptions import FeedCapabilities, Demand, SubscriptionKey
from gabfin.providers.futu.symbols import InstrumentCatalog
from gabfin.market.subscriptions import ChannelSupport, QuotaBudget, plan_subscriptions

now = datetime(2026, 11, 25, 15, tzinfo=timezone.utc)
stock, holding, call, put = [UUID(int=n) for n in range(1, 5)]
def instrument(identifier, symbol, **extra):
    return Instrument(schema_version='1.0', instrument_id=identifier,
                      asset_class='option' if extra else 'equity', vendor_symbols={'futu': symbol},
                      currency='USD', tick_size='0.01', lot_size='1', **extra)
records = [instrument(stock, 'US.AAPL'), instrument(holding, 'US.MSFT')]
for identifier, right, letter in [(call, 'call', 'C'), (put, 'put', 'P')]:
    records.append(instrument(identifier, 'US.AAPL261218' + letter + '350000', option=dict(
        underlying_id=stock, expiry='2026-12-18', right=right, strike='350', multiplier='100')))
catalog = InstrumentCatalog(records)
keys = {i.instrument_id: SubscriptionKey(instrument_id=i.instrument_id, channel='quote', timeframe=None) for i in records}
requests = [Demand(schema_version='1.0', demand_id=UUID(int=100+n), key=keys[identifier], priority=priority,
                   owner=UUID(int=500), expires_at=now+timedelta(minutes=5))
            for n, (identifier, priority) in enumerate([(stock, 'chart'), (holding, 'holding'), (call, 'watchlist'), (put, 'watchlist')])]
caps = FeedCapabilities(schema_version='1.0', source='futu', asset_classes=['equity', 'option'],
                        sessions=['regular'], latency_label='unknown', max_subscriptions=1,
                        history_limits=[], checked_at=now, permission_errors=[])
schedule = plan_subscriptions(requests, caps, catalog, as_of=now, session='regular',
                             max_snapshot_age=timedelta(minutes=3), budget=QuotaBudget(1, 1, now),
                             supported=[ChannelSupport('quote', asset_class=a, session='regular') for a in ('equity','option')],
                             current=[keys[stock]])
assert schedule.apply_allowed and {k.instrument_id for k in schedule.subscribe} == {holding, call, put}
assert schedule.unsubscribe == (keys[stock],)
assert schedule.plan.rejected[0].reason_codes == ('equity_quota_exhausted',)
names = lambda values: [catalog.get(k.instrument_id).vendor_symbols['futu'] for k in values]
result = {'synthetic_only': True, 'accepted_symbols': names(schedule.plan.accepted),
          'subscribe_symbols': names(schedule.subscribe), 'unsubscribe_symbols': names(schedule.unsubscribe),
          'reason': list(schedule.plan.rejected[0].reason_codes), 'apply_allowed': schedule.apply_allowed,
          'latency_label_unchanged': caps.latency_label, 'no_futu_sdk': importlib.util.find_spec('futu') is None,
          'no_pandas': importlib.util.find_spec('pandas') is None}
assert result['no_futu_sdk'] and result['no_pandas']
Path(sys.argv[1]).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result))
