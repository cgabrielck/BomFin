# S02/02e — Feed and subscription support contracts

## Scope and results

- Checkout `.worktrees/gabfin-s01`, branch `codex/s01-source-baseline`; base `709652de8b0a4661b8087ebd6ca31f051d8701f1`. Local commit `16fd6ff10736b186e9e1bf17815582d1a7231714`, not pushed.
- Added only `services/gabfin/contracts/subscriptions.py` and `tests/gabfin/test_subscription_contracts.py`.
- SubscriptionKey, HistoryLimit, FeedCapabilities, Demand, SubscriptionRejection and SubscriptionPlan reuse existing identity/time/market primitives.
- Bar channels require a timeframe; quote/trade channels forbid it. Identity includes normalized instrument UUID, channel and complete timeframe.
- Unknown quota/history limit remains null, zero remains zero. Negative/coerced counters and duplicate capability declarations are rejected.
- Demands have explicit owner, priority category and expiry. Plans reject duplicate keys and accepted/rejected overlap; rejected keys require nonempty unique reason codes. Empty plans are valid.

## Verification actually performed

- RED: 38 collected tests failed because the new module did not exist; [log](artifacts/s02-02e/red.log).
- Initial GREEN: 361 contract tests passed. Author self-review added seven boundary cases without changing production logic; final **368 passed**, including **45 new** cases; [final log](artifacts/s02-02e/contracts-final.log).
- Full sanitized pytest: **1576 passed / 4 skipped / 1 warning**, exit 0, 65.98s; [full log](artifacts/s02-02e/full.log); includes all final cases.
- Six serialization schemas passed Draft202012 schema checks; isolated import did not load backend. [Schema](artifacts/s02-02e/schema.log).
- pip check and wheel build passed. All package Python bytes match wheel contents; original tracked source and pre-existing lockfile hashes preserved. [Build](artifacts/s02-02e/wheel.log), [pip check](artifacts/s02-02e/pip-check.log), [preservation](artifacts/s02-02e/verification.json).
- Single-agent author self-review only; no independent reviewer. Actual entitlement, throughput, allocation fairness, provider latency and live subscription behavior were not tested.

## Engineering choices and limits

- Model observed capability and proposed plan shapes without implementing allocation. Cost if mistaken for an allocator: oversubscription; later service must cross-check actual quota units, capability snapshot, demand validity and ownership.
- Priority values are categories, not a sorting algorithm or numeric investment score. No starvation/fairness policy or fixed subscription count is introduced.
- MarketSession includes observed overnight/closed/unknown labels; these do not modify the order contract's allowed trading sessions or grant execution permissions.
- Historical expired demands remain parseable. Runtime expiry/current capability verification belongs to the subscription planner; unknown entitlement is not silently treated as realtime.
- History limits are channel/timeframe/max-record metadata only. Date coverage, pagination, source-specific quota weights and calendar resolution need actual provider integration later; no defaults invented here.
- No API, DB, callback, subscription loop, broker/model calls, trading, dependency change or push/deploy occurred.

## Remaining Task 2 inventory

- Main-plan feed/subscription group is now represented. Still absent: Principal/Capability/Resource; StrategyContext; BrokerSnapshot/ReconciliationResult; JobLease/Reservation; ModelRequest/Result; ExperimentSpec/Result; HealthReport.
- CandidateObservation, HarnessProposal and further runtime policy/OMS support remain absent. Aggregate schema artifact, SQLite foundation and Task 3 authorization remain pending.
- Next bounded unit: 02f identity/capability/resource declarations, keeping authentication/service enforcement separate. Do not bundle all remaining groups into one session.
- [Brief](../superpowers/plans/2026-11-25-gabfin-s02-02e-subscriptions.md), [main plan](../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).

- Four skips remain optional Postgres cases lacking psycopg; warning remains Pandas4Warning at backend/research/comps.py:26. Unit-generated mock journal was absent at start and archived outside source after testing.
