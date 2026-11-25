# Architecture

- Canonical design: [requirements and architecture](../superpowers/specs/2026-11-25-gabfin-system-design.md).
- Tasks and migration: [upgrade plan](../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).
- Status: new architecture has primitive/intent, market, research and order/policy contracts;
  remaining runtime components beyond S02 are not implemented by those slices.
  Legacy source is isolated locally; location and revision are in [execution.md](execution.md).
- Current source structure and development commands: [module inventory](../audit/module-inventory.md).
  It distinguishes FastAPI-served static UI, React/Vite source and Streamlit lab.
- Direction: new React/PWA frontend; isolated market, research and execution
  processes; explicit contracts; deterministic risk and ledger; bounded research
  harness. Exact provider/engine choices have validation gates in the plan.
- Do not apply old ADRs as product constraints. Do not restore rejected
  requirements from older summaries; the canonical design owns requirements.
- Legacy checkout authority entries have been replaced and old ADRs retired;
  scope and verification are in the [cleanup report](../audit/legacy-authority-cleanup-2026-11-25.md).
- Legacy tests and Vite build have now run; source typecheck has known failures.
  Actual counts, versions and limits: [baseline](../audit/baseline-2026-11-25.md).
  Baseline alone does not establish runtime integration; see S03 evidence below.
- New namespace: `services/gabfin/contracts/`, installed through root pyproject
  discovery. Primitive/intent interfaces: [02a report](../audit/s02-02a-contracts-2026-11-25.md).
  Market/instrument/quote/bar and typed event semantics, tests and limits:
  [02b report](../audit/s02-02b-market-events-2026-11-25.md).

- Discovery/advice/monitoring experience and authorized-intent routing review:
  [research experience plan](../superpowers/plans/2026-11-25-gabfin-research-experience-plan.md).
  These additions are planned, not runtime-verified.

- Research/evidence/request/report contracts and local validation now exist;
  implemented boundaries: [02c report](../audit/s02-02c-research-2026-11-25.md).

- Policy/order declaration validation and evidence-aware event shapes now exist;
  runtime approval/OMS remain later: [02d report](../audit/s02-02d-orders-policy-2026-11-25.md).

- Feed capability/subscription demand and decision contracts now exist; allocator
  and provider checks remain later: [02e report](../audit/s02-02e-subscriptions-2026-11-25.md).

- Explicit identity/capability/resource declarations exist; actual session/auth
  enforcement remains Task 3: [02f report](../audit/s02-02f-identity-2026-11-25.md).

- JobLease/Reservation declarations preserve unknown spend and lease intervals;
  transactional scheduler/budget services remain Task 6: [02g report](../audit/s02-02g-jobs-budget-2026-11-25.md).

- S02 foundation complete: all planned domain/support documents, shared schema,
  SQLite migration and HTTP/WebSocket session/capability services. Interfaces,
  verified scope and deferred integration gates: [S02 report](../audit/s02-completion-2026-11-25.md).

- S03 readiness and injected quote metadata probes originated in
  [03a report](../audit/s03-03a-preflight-2026-11-25.md); later slices own live evidence.

- Quote-only SDK worker has an external timeout and sanitized result channel;
  localhost metadata first verified in [03b report](../audit/s03-03b-runner-2026-11-25.md).

- One-equity quote/D1-bar diagnostic operation verified with explicit cleanup;
  native market event production remains later: [03c report](../audit/s03-03c-equity-2026-11-25.md).

- Bounded standard AAPL option chain/quote diagnostic and separate option-quota
  cleanup verified; full catalog/allocator and realtime proof remain later:
  [03d report](../audit/s03-03d-options-2026-11-25.md).

- Bounded historical RTH/ETH diagnostic uses a version-gated single-page quote
  transport/parser to avoid SDK auto-pagination and missing-price inheritance;
  scope, private-hook dependency and live evidence: [03e report](../audit/s03-03e-history-2026-11-25.md).

- Finite namespaced InstrumentCatalog and advisory subscription scheduling now
  use explicit asset/session/channel support and separate Futu quota pools;
  snapshot freeze/deltas and deferred provider integration: [03f report](../audit/s03-03f-planner-2026-11-25.md).
