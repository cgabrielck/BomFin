# Architecture

- Current Massive runtime: `providers/massive/ws.py` owns the sole wire reader and bounded
  frame dispatch; `MassiveQuoteAdapter` implements ManagedFeedAdapter; FeedSupervisor owns
  retry after verified cleanup. `scripts/desk-server.py` and `market/host.py` use Massive.
  REST/history/options use a shared client limiter. Runtime scope and unverified gates:
  [execution checkpoint](execution.md).

- Canonical design: [requirements and architecture](../superpowers/specs/2026-11-25-gabfin-system-design.md).
- Tasks and migration: [upgrade plan](../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).
- Status: new architecture has primitive/intent, market, research and order/policy contracts;
  remaining runtime components beyond S02 are not implemented by those slices.
  Legacy source is isolated locally; location and revision are in [execution.md](execution.md).
- Current source structure and development commands: [module inventory](../audit/module-inventory.md).
  It distinguishes FastAPI-served static UI, React/Vite source and Streamlit lab.
- Direction: new React desktop-web frontend (no iPhone/PWA); isolated market, research and execution
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

- Feed capability/subscription contracts originated in
  [02e report](../audit/s02-02e-subscriptions-2026-11-25.md); allocator/provider
  implementation followed in S03, whose current scope is linked below.

- Identity/capability/resource declarations originated in
  [02f report](../audit/s02-02f-identity-2026-11-25.md); actual session/auth enforcement
  followed in the completed S02 foundation linked below.

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
  initial scope: [03c report](../audit/s03-03c-equity-2026-11-25.md).

- Bounded standard AAPL option chain/quote diagnostic and separate option-quota
  cleanup verified; full catalog/allocator and realtime proof remain later:
  [03d report](../audit/s03-03d-options-2026-11-25.md).

- Bounded historical RTH/ETH diagnostic uses a version-gated single-page quote
  transport/parser to avoid SDK auto-pagination and missing-price inheritance;
  scope, private-hook dependency and live evidence: [03e report](../audit/s03-03e-history-2026-11-25.md).

- Finite namespaced InstrumentCatalog and advisory subscription scheduling now
  use explicit asset/session/channel support and separate Futu quota pools;
  snapshot freeze/deltas and deferred provider integration: [03f report](../audit/s03-03f-planner-2026-11-25.md).

- S03 now owns freshness/calendar checks, trade bars, bounded state/replay,
  verified recovery, managed lifecycle and authenticated internal streaming.
  Futu live producer remains single-equity quote-only; API/UI rendering is S04.
  Commands, interfaces, verified boundaries and G2 hold:
  [S03 report](../audit/s03-completion-2026-11-26.md).

- S04: runtime validation, HTTPS pairing, leased API→S03 bridge and snapshot reset:
  [04c auth/commands](../audit/s04-04c-market-2026-11-26.md).
  Independent quote/bar subscriptions, bounded 1m candle/volume wrapper and
  synthetic fixtures: [04d chart lifecycle/checks/limits](../audit/s04-04d-chart-2026-11-26.md).
- S04/04e core-workbench integration, four-layer quote tracing and applicable
  performance measurements: [core acceptance](../audit/s04-core-acceptance.md).
  Implemented and measured locally, but not yet committed or independently reviewed.

- Part 2 provider layer: `services/gabfin/providers/registry.py` owns
  source-agnostic routing (`SourceProfile`, `ProviderRegistry`); the market
  subscription planner asks the registry and names no vendor.
  `services/gabfin/analysis/plane.py` owns the three read-only analysis
  planes; `services/gabfin/api/analysis.py` exposes them behind the same
  session, origin and capability authority the market routes use.
  `services/gabfin/contracts/analysis.py` owns the three response contracts.
  `services/gabfin/analysis/sources.py` and `analysis/runtime.py` supply the
  concrete sources (tape bars, FRED observations, measured feeds) and the one
  place that decides which source is which; the tape is keyed by vendor symbol,
  so a resolver maps the canonical instrument id onto the stored series.
- S4 research: `research/capture.py` freezes local tape/indicators and explicit released observations;
  `store.py` owns SQLite snapshot/evidence hashes and checks; `tools.py` exposes only frozen read-only data.
  `service.py` wires per-run LangGraph and durable audit-before-return; `model.py` selects an HTTPS
  OpenAI-compatible provider via process `LLM_*` settings. CLI: `python -m gabfin.research --help`.
  Coverage/missing-data/provider verification boundaries: [session09](../superpowers/logs/2026-11-27-session-09.md).
- S5 research API: `api/research.py` exposes the browser's research job routes behind the
  same session/origin/capability authority as the market and analysis routes.
  `research/jobs.py` owns the durable job queue (SQLite `research_jobs` table beside the
  snapshots), the bounded queue, the per-job deadline and the background runner.
  `create_market_app(..., research={'jobs': ...})` mounts it; the app's lifespan cancels
  the background jobs on shutdown. The client never names the snapshot or the cutoff:
  the server injects the capture at its own UTC cutoff. A snapshot is described, never
  quoted, because it may carry an account balance.
  Browser entry: `features/research/ResearchCenter.tsx` plus `useResearchView.ts` and
  `shared/transport/research.ts`; graph results retain a `reports` wrapper.
  Local launcher: `scripts/start-desk.ps1`; `-Offline` avoids a provider connection,
  `-Runtime` isolates sessions/jobs, and `runtime/owner-id` preserves report ownership.
- Frontend/backend handover is file-based: `docs/handover/HANDOVER.md` is the
  only state file, `docs/handover/ui-contract.md` is the API contract the
  browser may rely on, and `docs/handover/ui-tasks/WU-<n>-ui.md` is one task
  card per frontend unit. Boundaries are recorded in [decisions.md](decisions.md) D011.
