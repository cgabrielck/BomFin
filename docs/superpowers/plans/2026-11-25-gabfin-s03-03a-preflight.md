# S03/03a quote-only preflight and diagnostics

Single-agent inline TDD slice of [Task 4](2026-11-25-gabfin-upgrade-plan.md). Full S03 is not this unit's completion criterion.

## Scope / decisions

- Create provider package and `providers/futu/capabilities.py`, `preflight.py`; tests `tests/gabfin/test_feed_preflight.py`. Existing code/schema untouched.
- No SDK dependency installation, login, trade context, subscription or broker call. Local CLI checks SDK metadata without importing futu and optionally performs a bounded loopback TCP check. Default endpoint is explicit 127.0.0.1:11111; do not scan network/ports. No endpoint/credentials echoed.
- Preflight JSON reports only sdk_present/listener_reachable (nullable if no TCP check), fixed gate codes and explicit unverified quote/bar/options/PRE/POST capabilities. A listening socket does not prove OpenD or entitlement.
- Read-only `inspect_quote_context(context, checked_at)` accepts an injected already-open quote context. Calls get_global_state and query_subscription(is_all_conn=True), always close in finally. Only copy strict qot_logined bool and strict nonnegative JS-safe total_used/remain counters. Never retain raw global/subscription payload, account IDs, broker names, subscribed symbols or exception strings.
- Metadata diagnostics report metadata_available only if login and both counters known; this is not a live quote entitlement label. Failed status/quota/close calls preserve known safe fields with fixed codes; missing/invalid counters remain unknown, never zero. These primitives do not instantiate/import the SDK; future SDK execution must run in a bounded child process per architecture.
- Official references: [global state](https://openapi.futunn.com/futu-api-doc/en/quote/get-global-state.html), [subscription status](https://openapi.futunn.com/futu-api-doc/en/quote/query-subscription.html), [permissions](https://openapi.futunn.com/futu-api-doc/en/intro/authority.html). API vs App entitlement differs; quota metadata does not prove instrument/session coverage.

## Steps

- [x] Snapshot source/lock; record local process/port/SDK evidence.
- [x] RED tests: strict/sanitized metadata, zero vs unknown, partial errors and guaranteed close; preflight no SDK import or implicit network.
- [x] Implement diagnostic primitives and CLI; GREEN, then full sanitized regression and packaging/preservation.
- [x] Run actual local readiness check; save only safe fields; record missing runtime as external gate, no fake market smoke claim.
- [x] Commit explicit paths; update checkpoint with follow-up real OpenD smoke and remaining Task 4 work.
