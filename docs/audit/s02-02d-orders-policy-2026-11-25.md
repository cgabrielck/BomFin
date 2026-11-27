# S02/02d — Order and policy contracts

## Scope

- Base `44aa66d63fc35e859b64b82f290ffb3a598d872b`; checkout `.worktrees/gabfin-s01`, branch `codex/s01-source-baseline`.
- Added `services/gabfin/contracts/policy.py`, `order.py` and `tests/gabfin/test_order_policy_contracts.py` only. Local commit `709652de8b0a4661b8087ebd6ca31f051d8701f1`, not pushed.
- PolicyVersion separates draft declarations from approval metadata and complete risk bounds. No numeric defaults or actual settings installed; test values are fixture-only.
- RiskDecision checks strict booleans, positive sizing, passing/unique checks and explicit reason codes. Denials carry no approved sizing.
- OrderCommand distinguishes buy/sell from strategy direction and validates price/type/session shape. It does not convert short/close into broker buy without position context.
- OrderEvent retains UNKNOWN, canceled partial quantities and unavailable execution prices. Known cumulative-average fill prices require broker evidence references; no order limit price is substituted.

## Verification

- RED: 58 failures from absent policy/order modules after collection; [log](artifacts/s02-02d/red.log).
- Initial GREEN: 313 contract tests. Author self-review added 10 boundary cases; final **323 passed**, including **68 new** cases; [log](artifacts/s02-02d/contracts-final.log).
- Full sanitized regression: **1531 passed / 4 skipped / 1 existing warning**, exit 0, 66.44s; [full log](artifacts/s02-02d/full.log); this run includes all final cases.
- Four serialization schemas passed Draft202012 schema checks; isolated imports did not load backend; [schema log](artifacts/s02-02d/schema.log).
- Four skips are optional Postgres cases missing psycopg; the warning remains Pandas4Warning in backend/research/comps.py:26. The newly generated legacy mock journal was archived outside source after checking it was absent at unit start.
- pip check passed; wheel built and package bytes match source. [Build](artifacts/s02-02d/wheel.log), [pip check](artifacts/s02-02d/pip-check.log), [preservation results](artifacts/s02-02d/verification.json).
- All 490 original tracked files and existing untracked web/package-lock.json hashes preserved. No original source change, dependency change, application/worker launch, provider calls, push or trading.
- Single-agent author self-review; no independent reviewer. No actual approval, principal authorization, broker entitlement or runtime risk performance was verified.

## Engineering rulings / limitations

- Policy declarations and approval hashes are untrusted data until a service verifies the trusted registry, approval content and principal. An approved document shape is not permission to trade. Later Task 3/11/15 checks are mandatory.
- RiskBounds is an initial subset, not the complete deployment policy: per-trade/daily-loss/runtime-drawdown ratios, gross exposure leverage and halt_entries missing-data behavior. Single-instrument limits, liquidity/borrow checks and additional approved runtime settings remain later. Parsing the model is never an activation gate by itself.
- Extended sessions use a conservative limit/day shape restriction. Actual broker capabilities and entitlement must still be checked; no compatibility with a live API is claimed.
- Cumulative quantity may be positive with unavailable price. Consumers must reconcile the missing evidence and cannot derive valuations using an order limit. Fill evidence IDs record provenance, not proof the artifact exists or supports the observation.
- Source clock skew is retained; only local available/received causality is enforced. Historical expired risk decisions remain readable; runtime services enforce expiry.
- Cross-event quantity monotonicity, order transitions, idempotent intent consumption/outbox and cumulative quantity vs original order size are OMS responsibilities, not implemented here.
- HarnessProposal, bracket/stop orders, expanded lifecycle event mappings and remaining support contracts remain subsequent slices. U12's 40% acceptance ceiling is not installed as a runtime risk setting.
- [Implementation brief](../superpowers/plans/2026-11-25-gabfin-s02-02d-orders-policy.md). Next: bounded S02/02e support-contract slice; migrations, aggregate schema and authorization still pending. Entire Task 2 remains incomplete.
