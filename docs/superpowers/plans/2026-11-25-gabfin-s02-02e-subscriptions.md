# S02/02e feed and subscription support contracts

Execute single-agent with TDD. Spec: [main plan §2.1 and Tasks 4/5](2026-11-25-gabfin-upgrade-plan.md). Scope is declarations, not subscription planning algorithm or provider integration.

## Interfaces / engineering decisions

- Create `services/gabfin/contracts/subscriptions.py` and `tests/gabfin/test_subscription_contracts.py`; reuse market AssetClass/MarketSession/Timeframe/counters and common UTC/opaque keys.
- SubscriptionKey: instrument_id UUID, channel quote/trade/bar, timeframe nullable Timeframe; bar requires timeframe, others forbid it. Identity uses complete normalized key, not ticker alone.
- HistoryLimit: channel, timeframe nullable with same rules, max_records nullable strict nonnegative JS-safe counter. Unknown stays null; zero is distinct and allowed.
- FeedCapabilities: version, source opaque, asset_classes/sessions tuples, latency_label unknown/realtime/delayed/indicative, max_subscriptions nullable counter, history_limits tuple, checked_at aware UTC, permission_errors tuple opaque codes. Reject duplicate assets/sessions/history keys/errors. This is observed capability metadata, not trading permission; no implicit realtime inference or actual quota allocation.
- Demand: version, demand_id UUID, key, priority holding/chart/strategy/watchlist/candidate, owner UUID, expires_at UTC. Priorities are categories, not user-facing numeric scores; historical expired demands remain readable. No selection algorithm or priority ordering is executed here.
- SubscriptionRejection: key, nonempty unique reason codes. SubscriptionPlan: version, source, as_of UTC, accepted tuple keys, rejected tuple rejections. No duplicates within either side or overlap across sides; empty plan allowed. Identical instrument/channel with different timeframe is a distinct subscription.
- Cross-checking capability snapshots, demand ownership/expiry, quota units, broker/provider entitlement and fairness belongs to later planner/service. No global fixed subscription count or new budget settings.

## Steps / verification

- [x] Preserve tracked hashes/lockfile and record source base.
- [x] Write tests and run RED from absent module; cover roundtrip, channel/timeframe, unknown vs zero quota, duplicate/overlapping decisions and identity distinctions.
- [x] Implement contracts; self-review edge cases then run all gabfin tests and full sanitized pytest.
- [x] Check schemas, isolated imports, wheel/source, pip check and preservation; archive only generated mock journal.
- [x] Commit explicit two paths; update audit and checkpoint. CandidateObservation, governance/jobs/context support, aggregate schema, migrations/auth remain later units.
