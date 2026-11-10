# Architecture Decisions

**Current decision: ADR-003 + Addendum A (Accepted, 2026-10-21).**  
**ADR-002 is VOID.** ADR-001 remains history only.

This file is the **index**. Canonical ADR-003 text lives in its own file. This file does **not** change live RiskEngine / Kelly / mandate / kill settings or trading runtime code.

---

## Index (binding order, highest first)

1. **[`ADR-003-live-ai-trading-desk.md`](ADR-003-live-ai-trading-desk.md)** — **Accepted** by Gabriel (chat) 2026-10-21, including **Addendum A** (Proposal-governed self-upgrade: Learn → Proposal → Approve → Merge; L1 may auto; L2 only after Approve).
2. **[`MODULAR_ARCHITECTURE.md`](MODULAR_ARCHITECTURE.md)** — M1–M13, dual-clock H1–H3, L1/L2, `HarnessProposal`, Intent v0.
3. **[`AUDIT_REMEDIATION_PLAN_2026-10-21.md`](AUDIT_REMEDIATION_PLAN_2026-10-21.md)** — **Confirmed by Gabriel 2026-10-21** (Hong Kong time). Next-doc work under ADR-003. **Confirmed P0 order:** user-visible journal / provenance first; IntentStore (H1/H3 split) after.
   - **Draft** (pending Owner/PM; not yet Accepted): [`BOUNDED_INTELLIGENCE_ACCEPTANCE.md`](BOUNDED_INTELLIGENCE_ACCEPTANCE.md) — AUDIT item 5 / plan-14 bounded-intelligence acceptance one-pager.
   - **Draft** (pending Owner/PM; not yet Accepted; does not expand 2026-10-21 Confirmed scope): [`ACCOUNT_MANAGEMENT_DESIGN.md`](ACCOUNT_MANAGEMENT_DESIGN.md) — plan-15 account-management design page (Desk vs worker). Issue #10 stays OPEN.
   - **Draft** (pending Owner/PM; not yet Accepted; does not expand 2026-10-21 Confirmed scope): [`LAB_PRODUCT_M7_BINDING.md`](LAB_PRODUCT_M7_BINDING.md) — plan-16 lab≠product M7 binding (`lab/advisory_debate` must not wire to `OrderManager`). Issue #10 stays OPEN.
   - **Draft** (pending Owner/PM; not yet Accepted; does not expand 2026-10-21 Confirmed scope): [`CHARTS_INDICATORS_DESIGN.md`](CHARTS_INDICATORS_DESIGN.md) — ns-1 TradingView-style charts/indicators design page (Desk product vs Streamlit lab). Issue #10 stays OPEN.
   - **Draft** (pending Owner/PM; not yet Accepted; does not expand 2026-10-21 Confirmed scope): [`REFERENCE_SIGNALS_DESIGN.md`](REFERENCE_SIGNALS_DESIGN.md) — ns-2 reference/advisory signals design page (Desk product vs Scan/worker/lab). Issue #10 stays OPEN.
   - **Accepted** (Gabriel 2026-10-30 Asia/Hong_Kong / HKT; previously Owner-approved 2026-10-27; does not expand 2026-10-21 Confirmed 1–5). **Merge ≠ Accepted ≠ runtime** (historical merges #50 ADR land and #53 Zone/P1 evidence docs sync do not change runtime by themselves; Accepted is the decision status, not a runtime flip): [`ADR-004-chart-engine.md`](ADR-004-chart-engine.md) — chart engine + Zone P0.5 + P1 zone evidence docs path (lightweight-charts v4.2.3 / PR #36) + drawing boundaries; Fib/measure in P0 as self-built overlay; Zone（價區／矩形價帶）P0.5 shipped (PR #52 @ `0f8f5d50be68a405cfb954edcdbbddefdaca8a78`; self-built overlay `kind: zone`; not an LC built-in rectangle; not the TV full drawing library; shipping did not itself Accept ADR-004); P1 chat→chart still deferred; zero order tools + Desk-only drawings per Option C. This status edit is docs-only. Issue #10 stays OPEN. ADR-002 is VOID. Binding order unchanged: ADR-003 > MODULAR > AUDIT > ADR-004.
   - **Draft** (pending Owner/PM Accepted; not yet Accepted; docs-only; **Merge ≠ Accepted ≠ runtime**; **no live**; HOLD for triple gate). Does not expand 2026-10-21 Confirmed 1–5: [`ADR-005-mobile-desk-readonly.md`](ADR-005-mobile-desk-readonly.md) — mobile Desk read-only Path A. Option C dual shell. Path A = Tailscale Serve (private HTTPS mesh) + read-only responsive Desk + Safari Add to Home Screen. Capacitor = P1 later (not a delivery of this ADR). IA: 晨報｜狀態｜活動. Three locks are **resolved** in spec 定稿 v1.1 (2026-11-04), which does **not** Accept this ADR: (1) Continue/Pause P0 may POST, paper worker only, button copy must include **paper**; (2) equity-curve event pins **deferred** (not this PR, not P0); (3) Ask Cgab FAB **not in P0**. Zero-order hard bars embedded (DOM must not expose order / Approve live / edit live rules / Scan·Deep execute; no confetti / Nx / FOMO / verified·live stamps; unreachable =「請開啟 Tailscale」, do not guide Funnel/ngrok). Streamlit ≠ mobile main surface. Base tip quieter #56 @ `d67b94ce`. Issue #10 stays OPEN. ADR-002 is VOID. Binding order unchanged: ADR-003 > MODULAR > AUDIT > ADR-004 > this draft. **Draft ≠ Accepted** until Owner Accepted after gates.
   - **Accepted** (Gabriel 2026-11-10 Asia/Hong_Kong / HKT). **Merge ≠ Accepted ≠ runtime**. **no live**. Docs-only; the observe adapter is a later PR and is not shipped here. Does not expand 2026-10-21 Confirmed 1–5, and does not elevate ADR-005 (that file stays Draft; different subject — mobile RO — and must not be written as outranking this Accepted decision). ADR-006 Accepted binds the OpenD observe path only and does not override ADR-003 / MODULAR / AUDIT / ADR-004: [`ADR-006-futu-opend-desk-observe.md`](ADR-006-futu-opend-desk-observe.md) — Futu OpenD → Desk observe layer (`FUTU_OPEND_DESK_OBSERVE`). OpenD is an Owner-operated local daemon (checked build **10.12.7208**, 2026-11-10; API port **11111**, listen local; not a public endpoint; no Funnel/ngrok). Desk talks only through an observe adapter. Quota-safe locks: on-demand only for the current chart symbol, paper/positions, or a small owner-defined watchlist; unsubscribe on leave; cache historical bars; no scanners, no all-stock pools, no universe pre-warm; OpenD is not the Harness research tape. Timeframes: official Futu OpenAPI v10.12 native KLType `K_1M` `K_3M` `K_5M` `K_10M` `K_15M` `K_30M` `K_60M` `K_120M` `K_180M` `K_240M` `K_DAY` `K_WEEK` `K_MON` `K_QUARTER` `K_YEAR` ([quote/KLType](https://openapi.futunn.com/futu-api-doc/hk/quote/quote.html)); **5h / 3d / 5d are synthesized** (5h from 60m bars; 3d and 5d from daily bars as 3 / 5 trading days) and must be labeled synthesized, never as a native KLType. Lowest tier checked 2026-11-10: subscribe **100**, hist K **100 symbols / 7 days** (options **20 / 20** recorded only — no options observe or order path); same symbol, different periods = 1 hist K slot; repeats within 7 days do not recount; hist-kline first page **≤60 / 30s**; depth ~**8 years** minute / ~**20 years** daily. Permissions: US stocks **LV3**, US indices **no permission**, HK stocks **LV1**; symbol map stays US-only (`AAPL` ↔ `US.AAPL`); HK LV1 does not expand mapping. Trading stays locked (no unlock steps, no `OpenSecTradeContext`, no place/modify/cancel). Source `futu_opend`; `verified` / `live` stay false. Honest degrade includes `quota_exhausted`, `opend_unreachable`, `permission_denied`, `empty`, `unmapped_symbol`. No fake close; no silent Yahoo-as-Futu. Alpaca paper remains the only order path. Zero Futu order tools. Option C: Desk = product; Streamlit ≠ this path's main surface. Does not replace the Massive Stocks Starter buy-later recommendation; OpenD is not a purchase SKU. No account identifiers. No prices recorded. Accepted revision base `main` @ `75ef6728` (#60). Issue #10 stays OPEN. ADR-002 is VOID. Binding order: ADR-003 > MODULAR > AUDIT > ADR-004 > this Accepted (OpenD observe only).
   - **Accepted** by Gabriel 2026-10-26 (Asia/Hong_Kong). **Merge ≠ runtime** (method doc only; does not enable live or change risk / kill): [`AI_SMART_TRADER_METHOD.md`](AI_SMART_TRADER_METHOD.md) — 24/7 smart-trader method. Phase 1 is a paper closed loop on the full `STOCK_UNIVERSE`. Phase 1.5 is a bi-daily scout (candidates are not orders). Judge defaults off. Ask Cgab never orders.
   - **Recommendation, not a purchase** (Owner budget 2026-10-26 ≈ HK$400 / ~US$51; does not buy a feed or change runtime): [`DATA_FEED_AND_SUBSCRIPTIONS.md`](DATA_FEED_AND_SUBSCRIPTIONS.md) — Massive Stocks Starter (~$29) is buy-later. Benzinga Earnings (~$99) is over budget. Free earnings calendars first. Alpaca paper stays. No Bloomberg, no IBKR, no Tradier research-tape migration. Options stay ns-4.
4. Older roadmaps — **frozen / superseded**, not authority:
   `AUTO_TRADING_ROADMAP`, `NEXT_PHASE_PLAN`, `QUALITY_ROADMAP`, `PAPER_VALIDATION_RUNBOOK`, `PROGRESS_LOG`, `CGAB_WORLD_CLASS_UPGRADE`.

Visual map: [`boomboom-modular-architecture.html`](boomboom-modular-architecture.html)

**ADR-002 is VOID** (owner decision 2026-10-21). Do not cite it as authoritative. Overlap with ADR-003 engineering preference (evolve `backend/trading/`, Desk = product) is coincidence, not inheritance.

Product surface under ADR-003: **Desk** = FastAPI + `web/static`. **Streamlit** = lab / legacy. Product **M7** is AI advisory in the modular map; `backend/lab/advisory_debate.py` is **not** M7 and must not wire to `OrderManager`.

---

## ADR-002 — Two SKUs, FastAPI desk as product, keep the risk kernel (VOID)

**Status:** VOID (2026-10-21). Replaced by ADR-003. Kept for audit; do not cite as binding.  
**Date:** 2026-09-12  
**Decision ID:** ADR-002  
**Supersedes:** ADR-001  
**Operating plan at the time:** [`CGAB_WORLD_CLASS_UPGRADE.md`](CGAB_WORLD_CLASS_UPGRADE.md) (that plan is now frozen)

### Context

The product goal is a **sellable** top-tier AI system with two functions: (1) world-class stock analysis, (2) paper-proven auto-trading that can go live after evidence. Famous GitHub projects (TradingAgents, Qlib, OpenBB, Nautilus, Freqtrade) were graded against Cgab. ADR-001’s “keep Streamlit as the product UI” no longer matches where Scan/Deep/Auto actually live (FastAPI desk) or what we will sell.

### Decision (historical — VOID)

1. **Do not greenfield-rewrite the repo.** Keep RiskEngine, mandate, kill switch, Kelly, Alpaca `BrokerAdapter`, scoring DNA, and the rule that LLMs/Telegram cannot place orders.
2. **Product UI is the FastAPI desk** (`web/static`, `backend/api/app.py`). Streamlit (`backend/app.py`) is **lab / legacy** until feature parity, then optional retire — not the commercial surface.
3. **Two SKUs, one kernel:** Research (analysis) and Paper Auto. Live is a gated add-on, not unsupervised.
4. **Steal mechanisms, not repos.** Qlib-shaped factor lab in our code; TradingAgents debate is advisory only; Nautilus/Lean may later sidecar simulation; never become a crypto/vnpy bot.
5. **Sequence truth before theatre:** worker universe + why-no-trade + scan freshness + optional research-list strategy **before** FinBERT, committee UI, or QuantStats PDF factories.
6. Paid bars (Polygon) on the seal/paper path; Yahoo is labeled fallback.

### Consequences (historical)

- Dual UI is a tax; new features land on the desk first.
- Stable mean-reversion stays a named strategy. “Buy the Scan list” is a **separate** strategy flag, not a silent replacement.
- Expanding the worker universe requires batching and rate limits (not a naive 74-ticker Yahoo burst).
- Customer live still requires Stage-2 seal + paper runbook. 24/5 paper may be demoed now.

What no longer holds: using this ADR as the constitution.

---

## ADR-001 — Keep Research UI, Upgrade Execution & Data (history)

**Status:** Superseded (history). Do not cite. ADR-002 is also VOID; current authority is ADR-003.  
**Date:** 2026-09-10  
**Decision ID:** ADR-001

Kept for audit. Original intent: do not rebuild from scratch; keep scoring, RiskEngine, Kelly, mandate, kill switch, Alpaca; upgrade PIT/data and seal evidence; optional Lean sidecar.

What no longer binds: **Streamlit as the primary product UI.**
