> LEGACY / SUPERSEDED — describes the previous implementation; not instructions for the new GabFin architecture.
> See [current architecture authority](ARCHITECTURE_DECISION.md). Historical rules below do not govern the redesign.

# AI Smart Trader Method — Harness 全日智能交易員

**Status:** **Accepted** — Owner Approved by Gabriel 2026-10-26（Asia/Hong_Kong）。**Merge ≠ runtime。** 本頁獲准的是方法文件，不是開 live、不是購買資料、不是改 RiskEngine／mandate／kill。  
**Date:** 2026-10-26  
**Binds under:** [ADR-003 + Addendum A](ARCHITECTURE_DECISION.md)（Accepted）> [MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md) > 本頁。衝突時 ADR-003 D1／Addendum A 勝出。\
**Does not:** 改 RiskEngine／Kelly／mandate／kill 語意、開 live、接 `OrderManager` 到 Ask Cgab 或 `lab/advisory_debate`、把本頁升格為已驗證 alpha。  
**Index:** [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md)。**ADR-002 is VOID**，不引用作約束。  
**Starting point improved:** PM brief v1（2026-10-26，Gabriel／BoomBoom Desk）。差異見 §11。  
**Owner direction (2026-10-26):** 產品不是「約 12 檔交易員」。預設跑完整 `STOCK_UNIVERSE`。約每兩日的偵察只擴大候選池；候選不是訂單。每月資料預算約 **HK$400（約 US$51）**。本文件獲准之後仍不在這次 PR 購買或寫入金鑰。

---

## 0. 給主人的摘要

Harness 要變成一個**整天開著的紙上交易員**：看著持倉與行情、在規則說「可以考慮」之後做判斷、然後在風控允許時行動，並把每一步寫進日誌。它不是只會事後寫升級建議的學習器，也不是一個可以自己對券商下單的聊天機器人。

請這樣理解角色。**哨兵**負責盯盤、心跳、止蝕與殺開關，全程不請教模型。**劇本**（現有具名策略）先說某個買入設算不算成立。**判斷員**只能否決或降低信心，不能決定買多少，也不能因為一則新聞就開倉。**執行員**才計算張數並送出紙上單。**偵察**約每兩日從市場上收集可能值得看的名字，寫下出處，放進候選池。候選只是劇本下次可以檢查的範圍，不是買入指令。改止蝕憲法、風險上限、真倉開關這類大事，仍要另出一份提案，等您明確批准。

這不是一套只做大約 12 檔的產品。先前提到約 12 檔，只是在警告「池子太小會封住上行」，從來不是上限。公平回測用的是大約 74 檔。平常運行時，若沒有另外設定抓取上限，就看完整個現有股票池。為了避免一次抓太快而暫時縮小抓取，那是運維旋鈕，不是策略，而且畫面上要寫明實際看了多少檔。

第一階段只證明**紙上閉環**跑得完、停得住、查得到，而且用的是完整股票池，不依賴外部偵察。模型預設關閉。這一階段**不要求**賺過大市，也不把現有策略說成已經勝過 SPY。公平回測裡，穩定策略虧損、進取策略的落後多半是牛市裡現金太多，這些都還沒有被新實驗推翻。美股收市後程式可以醒著並核對委託，但**不會通宵買賣**；現有策略是日線波段，收市後也沒有可以成交的止蝕。偵察排在第一階段完成之後（第 1.5 階段）再做程式；方法上現在就定為產品的一部分，避免以後又縮回一小份名單。

資料預算約 HK$400（約 US$51）一個月。這次不買任何訂閱、不寫金鑰。日 K 的 Massive Stocks Starter（約 $29／月）留到之後再買。Benzinga 財報（約 $99／月）超出預算，現在不買；財報日曆先用免費來源。紙上券商仍是 Alpaca，不改去 Tradier 當研究行情，現在也不買 Bloomberg、不開 IBKR。期權仍是後續能力（ns-4），不是這一階段的下單項目。

Ask Cgab 只負責講解畫面，永遠不落單。

| 階段 | 您會看到什麼 | 還沒有什麼 |
|------|----------------|------------|
| **1 紙上閉環** | 程式在交易時段看盤、按現有策略考慮買賣、風控可拒絕、日誌對得上；殺開關能擋住新買入。模型預設關。看的是完整股票池。 | 不宣稱賺錢、不上真倉、不自動改規則、此階段尚未外出找新股票 |
| **1.5 兩日偵察** | 大約每兩日交出一份候選名單，每名都有出處與日期。名單併進「可以檢查」的範圍。持倉與原有股票池仍保留。 | 候選不會自動變成買入；沒有出處的名字不進名單 |
| **2 時鐘拆開** | 看盤與出場比現時約 60 秒一輪更緊；收市後仍做持倉核對與警報。買入改走意圖帳之前，先證明不會下一兩次、張數不會偷偷變。 | 仍是紙上或影子，模型仍未獲准升級 |
| **3 判斷員要拿出成績** | 同一股票池，比較「有判斷員」與「純規則」。期望值不大於零或不優於純規則，判斷員就保持關閉。 | 真倉仍不開 |
| **4 規則變更要您點頭** | 系統可交出一份完整提案（改了什麼、依據、如何退回）。您拒絕，運行中的規則不變。 | 不是每筆交易都來問您 |
| **5 真倉** | 只在既有證據閘（只計已成交、封印、風控演練、您簽字、小倉）之後另案討論。 | **本文件不批准真倉** |

---

## 1. Product definition

A **smart trader** in this repo is a single paper (later, gated live) process that:

1. **Monitors** account, open orders, positions, kill state, and data freshness whenever the process is up.
2. **Judges** only after a named playbook has already marked a setup `VALID`.
3. **Acts** by submitting through the existing mandate → `RiskEngine` → `OrderManager` path, paper or shadow only.
4. **Records** the chain in the trade journal and risk audit.
5. **Proposes** constitution changes on a separate, slow path that cannot place orders.
6. **Scouts** the wider market about every two calendar days and adds sourced candidates to the names the playbook may inspect. A candidate is not a buy. The default book stays the full `STOCK_UNIVERSE`. A dozen names is not a product ceiling.

That is a different product from today's Harness, which is a ~60s `TradingWorker` plus a thin intent consumer and a **document-only** `HarnessProposal` schema.

| | Smart trader (this method) | What the code does today |
|--|----------------------------|--------------------------|
| Always-on process | Yes, Phase 1: process may stay up; order sync already runs outside the cash session | `TradingWorker._run_loop`: `_sync_orders()` always; strategy, exits, and intent consume only inside `_is_market_hours` |
| Entry decision | Playbook `VALID` → optional judge → **one** submitter | Buys call `SignalProcessor.process_signal` directly (`worker.py`). `upsert_active_intent` is **not** called by the worker |
| Second entry path | Must not double-submit | `_consume_intents` → `consume_active_intents` runs on the same market-hours tick and will also submit any `active` intent |
| Sizing | Only M8. Judge never emits quantity | Worker sizes **before** `process_signal`. `size_intent_qty` sizes again at consume time from `conviction_tier` × `RiskLimits`. The two formulas are not the same |
| Exit / kill | Deterministic, never waits on a model | Exits and kill checks live inside the strategy pass; kill blocks new buys and still allows the exit sell path |
| Universe | Full `STOCK_UNIVERSE` when `WORKER_UNIVERSE_CAP` is empty (`fetch_policy.py`). Scout later **adds** names; it does not replace the book with a short list | Fair backtest on main used 74/74. A ~12-name figure in the PM brief was a warning that a capped pool hurts upside, not an operating limit |
| LLM | Optional, budgeted, default off, entry veto/tier only | No product M7 package. `backend/trading/advisory/` does not exist. Lab debate and Ask Cgab are not on the order path |
| Self-upgrade | Proposal → owner Approve → merge. No runtime writer yet | Schema only: `MODULAR_ARCHITECTURE.md` §5.5. No `HarnessProposal` store |

**Definition used in acceptance tests:** Phase 1 is done when one paper-or-shadow cycle can show monitor → playbook → (judge off or veto) → risk decision → journal, with kill blocking buys, **without** a second order from `IntentStore`, and without a live broker.

---

## 2. Non-goals

The LLM, the judge, Ask Cgab, lab debate, and any proposal draft **must never**:

- Call `OrderManager`, `place_desk_order`, Alpaca, or a broker MCP tool.
- Emit `quantity` / `qty` / `notional` / raw size as the order size. Intent v0 already rejects those fields (`backend/trading/intents/writer.py`, `parse_intent`).
- Bypass or clear `kill_switch`, rewrite `TradingMandate`, or relax `RiskLimits`.
- Open a buy from a headline, a scout candidate, or a research tip sheet (ADR-003 D1: news vetoes, it does not trigger).
- Shrink the default book to about 12 names, or treat `WORKER_UNIVERSE_CAP` as a strategy. Empty cap means the full `STOCK_UNIVERSE`. A temporary cap is an ops knob for rate limits and must be printed on the session card.
- Issue an open-ended veto. Unknown veto codes do not block (ADR-003 D3).
- Turn a `consumed` intent into a claimed fill. `consumed` means handed to `process_signal` (`harness_realtime.py`).
- Trade the cash session overnight by setting `IGNORE_MARKET_HOURS`.
- Self-tune thresholds, prompts, or risk percents (no Oracle-style `TUNE` on the hot path).
- Claim the book beats SPY, or treat an unfilled limit as evidence (ADR-003 D4).
- Replace playbooks with a multi-agent debate (ADR-003 §5; `docs/LAB_PRODUCT_M7_BINDING.md`).

Out of scope for Phase 1 and Phase 1.5 of this method: options **orders**, gold, a greenfield port to Nautilus / Freqtrade / Temporal, and any live flag. Options remain a later capability (the owner called that north star **ns-4** on 2026-10-26). This repo has design pages for ns-1 (charts) and ns-2 (reference signals) only; there is no ns-4 spec. Account design already keeps options as research until a separate evidence gate ([ACCOUNT_MANAGEMENT_DESIGN.md](ACCOUNT_MANAGEMENT_DESIGN.md) §8.1). The feed note must not force a stocks-only vendor, and it still does not put an options order on this method's acceptance list.

Desk manual orders stay on `place_desk_order` (operator quantity, mandate + risk, journal stamp). They are not rewritten into IntentStore (MODULAR §4.4 R1-PATH).

---

## 3. Architecture

Roles below. Only the sentinel's exit path and the executor submit orders. The scout never does.

```
                 ┌───────────── process up (24/7) ─────────────┐
                 │                                             │
   quotes/account│   SENTINEL (no LLM)                         │
   ─────────────►│   heartbeat, kill, order sync, exits,       │
                 │   reconcile, stale-data, session clock      │
                 │            │                                │
                 │            │ exits / sells go straight to   │
                 │            ▼                                │
                 │        EXECUTOR                            │
                 │   MandateGate → RiskEngine → OrderManager  │
                 │            │                                │
                 │            ▼                                │
                 │     journal + audit (M10)                   │
                 └─────────────────────────────────────────────┘

   About every 2 calendar days (not on the tick):

   SCOUT → candidate file (symbol, theme, sources, asof, expiry)
        │ no source / not allowlisted / too old / not listable → drop
        ▼
   watch set = STOCK_UNIVERSE ∪ unexpired candidates ∪ open holdings
        │ this set is playbook input only
        ▼
   During cash session only, new buys:

   PLAYBOOK (M6 strategy)  VALID?
        │ no → why_no_trade, stop
        ▼ yes
   JUDGE (M7, default OFF)  closed veto or tier downgrade
        │ timeout / error / budget exceeded → no buy (silence)
        ▼ allowed
   ONE SUBMITTER (Phase 1 = existing process_signal)
        │
        ▼
   EXECUTOR (same as above)

   Slow path, never on the tick:

   journal digest → HarnessProposal → Desk presents → owner Approve
        → only then may L2 change. Reject leaves the running rules untouched.
   There is no apply-merge code yet. Phase 4 builds it. Phase 1 must not invent a writer.

   Never on either path:

   Ask Cgab (backend/api/help_chat.py) and lab/advisory_debate.py
```

| Role | May do | Must not | Real module now |
|------|--------|----------|-----------------|
| **Sentinel** | Heartbeat, kill check, `_sync_orders`, exit sells, daily reconcile, stale / skip codes | Wait on an LLM; open a buy because the model is worried or excited | `TradingWorker._run_loop`, `kill_switch.py`, `reconciliation/service.py`, `ops` heartbeat |
| **Playbook** | Emit `VALID` or a skip code from named strategies | Size the order; call the broker; change its own default parameters at runtime | `backend/trading/strategies/` (`stable`, `aggressive`, `trend`, `adaptive`, …) |
| **Judge** | Closed `veto_codes` from the v0 list, or a lower `conviction_tier`; notes with sources | Approve a setup the playbook called invalid; raise size; talk to the broker; block on the exit path | **Missing.** Target package: `backend/trading/advisory/` (M7). Not `backend/lab/advisory_debate.py` |
| **Executor** | Fail-closed mandate, risk, Kelly/sizer, idempotent submit, paper/shadow | Read the LLM to override a reject; accept raw model size | `safety/mandate.py`, `risk/gates.py`, `risk/position_sizer.py`, `engine/signal_processor.py`, `engine/order_manager.py`, `alpaca_broker.py` |
| **Governor** | Draft a proposal from journal evidence | Merge L2; place an order; hide a diff | Schema in MODULAR §5.5 only. Desk Approve UI not built |
| **Teacher** | Explain the UI | Orders, worker start/stop, rule edits | `backend/api/help_chat.py` |
| **Scout** | Every ~2 calendar days, write candidates with provenance into a watch file | Place or suggest a sized order; delete `STOCK_UNIVERSE`; treat a headline as `VALID`; run on the H1 tick | **Not built.** Phase 1.5. Nearby readers that are not a scout: `data_fetcher.fetch_news`, `fetch_next_earnings`, `picks_news.py`, `polygon_equity.py`, `scan_scheduler.py` |

**One submitter rule (Phase 1).** New auto buys keep using `SignalProcessor.process_signal`, which already has mandate reservation, sticky idempotency (`sticky_idempotency.py`), bracket orders, and shadow `next_bars`. The worker must **not** also `upsert_active_intent(..., status=active)` for that same buy. `consume_active_intents` would submit it again on the same tick.

IntentStore remains the target bus (ADR-003 Addendum A, MODULAR §4.4), but it becomes the **only** auto-entry submitter in Phase 2, after both gates in §6.2 pass. Until then, a judge decision is a journal record on the existing buy, not an `active` intent.

**Silence is the safe action.** No quote, stale research, judge timeout, token budget exceeded, or schema failure → no new buy. Exits still run. This is the opposite of an advisory layer that fails open and lets the order through.

**Desk vs worker.** Option C stands: Streamlit browses; trading actions stay on the Desk. Ask Cgab is the teacher. The scout is not a trading role.

### 3.1 Scout — bi-daily universe refresh

**Product intent (declared now, coded in Phase 1.5).** About every two calendar days the process looks past the fixed list for names worth inspecting. The pool is allowed to grow. It is not capped at a dozen names. Phase 1 still passes on today's full `STOCK_UNIVERSE` with no external discovery API.

**Clock.** `SCOUT_INTERVAL_DAYS` default **2**. `SCOUT_ENABLED` stays **0** until the Phase 1.5 implementation is merged, so a Phase 1 deploy does not call discovery feeds. When that phase is on, a failed or skipped run keeps the previous candidate file until each row expires. Scout failure must not block exits, kill, or the core book.

**Output.** A candidate file, not an intent and not an order. Suggested shape `scout_candidate.v0`:

| Field | Rule |
|-------|------|
| `symbol` | US equity ticker |
| `theme` | Optional label (sector, event, setup family). Not a side and not a size |
| `sources` | At least one `{type, ref, asof, publisher}`. `ref` is a URL or a stable id. Empty `sources` → drop the row |
| `asof` | When this row was written |
| `expires` | Default `asof` + `SCOUT_MAX_AGE_DAYS` (default **4**, two missed cycles) |
| `status` | `candidate` only. No status may mean buy, sell, or sized |

**What the worker reads.** Playbook input = `STOCK_UNIVERSE` ∪ unexpired candidates ∪ open holdings, deduped. Holdings stay even when the scout did not mention them and even when they would fail a new-candidate screen. The core list stays when `WORKER_UNIVERSE_CAP` is empty. Scout widens. It does not replace the book with the latest tip sheet.

**Filters (Phase 1.5 acceptance).** A row that fails any line is omitted from the watch set. None of these lines call `OrderManager`.

| Filter | Rule |
|--------|------|
| Allowlist | `sources[].type` must be one of `core_universe`, `holding`, `operator`, `polygon_grouped_daily`, `polygon_reference`, `yahoo_news_ticker`, `sec_edgar_filing`, `earnings_calendar`. Anything else is dropped |
| Provenance | Missing `ref` or `asof` → drop |
| Age | Older than `SCOUT_MAX_AGE_DAYS` → drop. Holdings and `STOCK_UNIVERSE` are not aged out by this clock |
| Dedupe | One row per symbol. Merge sources. Do not create two candidates that can double-fetch |
| Listability | Paper-broker asset lookup must say the symbol is a tradable US equity. Lookup missing or negative → drop. `alpaca_broker.py` does not expose this filter today; Phase 1.5 adds a read-only lookup |
| Price / liquidity | No min-price or min-dollar-volume gate exists on the worker entry path today. Bars code can already see a non-positive price (`risk/gates.py` `positive_price`) and research rows can carry `dollar_volume_10d_avg` (`technical_analyzer.py`). Phase 1.5 rejects a **new** candidate with no positive last price or with zero volume. A new numeric floor (price or dollar volume) is written in that implementation PR and reviewed like a default change. This method does not invent one |
| Holdings | Always kept on the fetch list (`fetch_policy.symbols_to_fetch` already puts holdings first) |
| Core book | `WORKER_UNIVERSE_CAP` empty → fetch the whole union, in the existing batches. A set cap truncates **after** holdings and must be labeled `ops cap` on the session card. It is not a strategy, and it is not a 12-name product |

**Honest sources.** This page does not turn on a feed.

Already in the repo, and **not** a market-wide scout:

| Piece | What it actually does |
|-------|------------------------|
| `backend/utils/constants.py` `STOCK_UNIVERSE` | Static default book. Tests pin length in 70–80. Fair report loaded 74/74 |
| `engine/fetch_policy.py` | Empty `WORKER_UNIVERSE_CAP` fetches that whole book, holdings first, batched |
| `agents/data_fetcher.py` `fetch_news` | Yahoo news for a ticker **already chosen**. It does not search the market for new tickers |
| `fetch_next_earnings` | Next earnings date for one ticker via yfinance |
| `agents/picks_news.py` | News and earnings write-up for selected names |
| `agents/polygon_equity.py` | Daily bars and `list_date` when `POLYGON_API_KEY` / `MASSIVE_API_KEY` is set. No grouped-daily or gainers call |
| `api/scan_scheduler.py` | Re-scans the current book on a session clock. Not a two-day discovery job |
| `agents/sec_analyzer.py` | Filings for a named company, not a market sweep |

Plausible categories for the Phase 1.5 wiring PR (still not a claim that we subscribe today):

- **Market scanner on a key we may already have:** Polygon grouped daily or movers, only behind `polygon_equity.is_configured()` and only if that PR adds the endpoint. If the key is absent, that source is skipped, not faked.
- **Earnings calendar that emits symbols:** the per-name yfinance helper is not enough. A market-wide calendar is a separate client.
- **News-wire tickers:** an allowlisted publisher API that returns symbols plus a URL. Yahoo-per-ticker news can corroborate a symbol we already have; it cannot be the discovery engine.
- **SEC EDGAR recent filings:** public, no Bloomberg contract required. A later job may list filers. `sec_analyzer` does not do that sweep today.

**Not in this product until a real contract exists, and not implied by this method:** Bloomberg, FactSet, Refinitiv, S&P Capital IQ, or scraped paywalled PDFs. Do not stub those names as if they returned data.

Paid feeds and the owner's monthly cap are in [`DATA_FEED_AND_SUBSCRIPTIONS.md`](DATA_FEED_AND_SUBSCRIPTIONS.md) (prices checked 2026-10-26; budget revised the same day after approval). Owner cap ≈ **HK$400 (~US$51)**. **This acceptance buys nothing and writes no keys.** **Later, not in this PR:** Massive Stocks Starter (~$29/month, same key as today's Polygon client) for daily OHLCV, grouped daily, and news with URLs. **Not now:** Benzinga Earnings (~$99/month) is over that cap. Until a paid calendar fits, symbol-emitting dates come from free **Alpha Vantage `EARNINGS_CALENDAR`**, the **Finnhub** free calendar, and **SEC / XOOMAR** to confirm a result was actually reported. Those rows still only write candidates, under the existing `earnings_calendar` or `sec_edgar_filing` types. Yahoo stays corroboration. Phase 1.5 may add the allowlist type `massive_news` only after Starter exists; until that PR, this closed list is unchanged.

Alpaca paper stays the broker. Tradier is not the research tape. No Bloomberg and no IBKR in this budget. Options stay deferred (ns-4): the feed note §9 still leaves one later OPRA-class tape and one later order path, and Phase 1 still does not buy an options feed or submit an options order.

**Safety boundary.** Scout output is consumed as the playbook's **input set** only. The buy path is unchanged: playbook `VALID` → optional judge → mandate → `RiskEngine` → one submitter. A candidate with a bullish theme and three headlines is still not an order. Wiring the candidate file to `OrderManager`, `place_desk_order`, or `upsert_active_intent` is a defect.

---

## 4. Clocks and latency

US cash equities are not a 24-hour market. "24/7" means the **process** stays up. It does not mean overnight entries.

Current playbooks are daily-bar swing rules (`stable.py` RSI(2) / SMA, `aggressive` VCP, `trend.py` ATR trail). A one-second loop cannot invent an intraday stop those rules do not have. A daily stop also cannot fill while the primary session is closed. Overnight gap risk is accepted and bounded by size, mandate, and kill — not by an LLM watching futures.

| Clock | Phase 1 budget (honest) | Later budget | LLM allowed? |
|-------|-------------------------|--------------|--------------|
| **H1 protect** | Same tick as today: worker `--interval` default **60s**, and only while `_is_market_hours` is true. Order sync still runs every tick outside the session | Phase 2: exit/kill/sync on their own loop, target one check per **≤5s** while the process is up. Fills still wait for the session | **No.** `harness_realtime.py` already states H1 must not block on an LLM |
| **H2 reconcile** | Once per calendar day inside the session (`_run_reconciliation`) | 5–15s lightweight order-status sync (partially what `_sync_orders` already does every tick) | No |
| **H3 entries** | At most one decision pass per worker tick during the session. Judge call timeout **3s hard**, then silence | Bar-close or ≤5 min. Still not on the exit loop | Yes, entry only, budgeted |
| **Off session** | Process up, `_sync_orders`, heartbeat, kill file still honored. **No** strategy scan, **no** new buys, **no** pretend stops | Heartbeat age alert, intent expiry, next-open gap **report** (not a hidden market order) | No |
| **Governor** | Not built | Daily or weekly batch. Never on the tick | Yes, off the money path |
| **Scout** | Not in Phase 1. Product intent is already this row | Phase 1.5: one pass every `SCOUT_INTERVAL_DAYS` (default 2). Must not delay H1. A late run is fine | Optional, off the money path, and only to extract symbols and themes into the candidate schema. It still cannot emit a side or a size |

Do not set `IGNORE_MARKET_HOURS` to make the demo look 24/7. `cadence.py` already says that switch must not rewrite that flag. Weekly cadence (`WORKER_CADENCE=weekly`) remains an entry filter (Monday, plus panic regime); it is not a substitute for the judge.

**Cost budget (when the judge flag is on).** Hard cap per UTC day: call count and token count, stored beside the decision log. Over budget → judge auto-disables for the rest of the day and the playbook arm continues. A disabled judge is a successful degrade, not an incident.

---

## 5. Where the model sits

```
playbook VALID
    → judge (optional): {veto_codes[], conviction_tier, notes, sources}
    → if veto_codes empty: existing worker sizer (Phase 1) computes qty
    → MandateGate
    → RiskEngine.evaluate_order     # does not read the model
    → OrderManager                  # paper or shadow
```

The model is a **classifier with a closed output**, not an agent with tools.

Allowed judge output:

| Field | Rule |
|-------|------|
| `veto_codes` | Subset of MODULAR §5.3 / bounded-intelligence v0: `CALENDAR_BLACKOUT`, `STALE_DATA`, `CORR_CAP`, `KILL_ACTIVE`, `EVENT_FREEZE`. Empty means "do not veto". Any other code is ignored and logged, and does **not** block |
| `conviction_tier` | `low` / `med` / `high` only. Phase 1 may log it. It must not change quantity until Phase 2 size parity is signed |
| `sources` | At least one `{type, ref, asof}`. Empty sources → treat as judge failure → silence |
| `notes` | Human-readable, not an order |

Forbidden in the same payload: quantity, notional, order type, broker ids, mandate edits, `TUNE` directives.

`KILL_ACTIVE` in a judge payload is redundant. The sentinel already blocks buys when `kill_switch.is_halted()` is true. The judge must not be the component that *clears* a halt.

Lab `advisory_debate.py` may keep stealing TradingAgents **role names** for memos. Product code must not import it into `worker.py`, `harness_realtime.py`, `signal_processor.py`, or `desk_orders.py`.

---

## 6. Phased delivery

Each phase has pass/fail checks. A later phase does not start by relaxing an earlier one.

### 6.1 Phase 1 — Paper closed loop

**Intent.** Prove monitor → judge slot → act → journal on the submitter that already works. Default judge **off**, so the loop is the rule trader. The slot exists so Phase 3 can turn the model on without a second order path.

**In scope**

- `TradingWorker` with `--mode paper` or `--mode shadow`. CLI default stays `shadow`. `--allow-live` stays a separate, unused switch and Phase 1 tests assert the runner under test does not pass it.
- Judge call site **immediately before** the buy `process_signal` in `_run_strategy_signals`, behind `AI_JUDGE=0` (default). `AI_JUDGE=0` performs zero network model calls.
- Exits, kill, and `_sync_orders` unchanged and not routed through the judge.
- Decision row in the existing journal (`backend/utils/provenance/trade_log.py`) for any veto or judge failure.
- Session card: universe requested, cap, fetched count, skip-code counts (`why_no_trade`), order statuses. Label paper vs SPY if `/api/performance` has a book. The card is not a seal.

**Acceptance (all required)**

1. **Closed loop, rules arm.** One `--once` cycle against a fake or paper broker produces either a journaled order outcome (`submitted`, `filled`, `risk_rejected`, `canceled`) or a `why_no_trade` skip summary. Both count as success. Silence with a written skip is success.
2. **No double submit.** That cycle does not create an `active` intent for the same buy. `consume_active_intents` either sees nothing new or is not a second submitter. A test fails if both `process_signal` and an intent consume submit a buy for one signal.
3. **Kill.** Engaged kill → zero new buys on the next cycle. The existing exit path may still submit a sell. Resume writes `kill_switch_resume` audit.
4. **Judge failure is silence.** With `AI_JUDGE=1` and a stub that times out or returns bad JSON, buy count is zero and the exit function is still invoked in the same cycle.
5. **Schema.** A payload containing `quantity` / `notional` is rejected by intent parsing and is not turned into an order. An unknown veto code does not block a `VALID` setup.
6. **LLM not on H1.** Static check: `harness_realtime.py` and the exit/kill section do not import a chat client. Ask Cgab tests and `tests/lab/test_advisory_debate_isolation.py` stay green.
7. **Live stays off.** The Phase 1 command does not pass `--allow-live`. Paper mode uses the paper Alpaca endpoint already selected by `AlpacaBroker`.
8. **Honest book.** The session card prints core `STOCK_UNIVERSE` size, fetch cap, and names fetched. Empty `WORKER_UNIVERSE_CAP` fetches the full core book (today's `fetch_policy` behavior). The card does not say the book beat SPY. If a cap truncated the fetch, the card says `ops cap`, not that the strategy's universe is the short list. Phase 1 does not set a default cap, and it does not use a 12-name book.
9. **Scout stays out of Phase 1.** `SCOUT_ENABLED` is off. No discovery client is required for the closed loop to pass.

**Not acceptance.** Positive P&L, Sharpe, a green E0 backtest, an approved proposal, or a live scout feed.

### 6.1b Phase 1.5 — Bi-daily scout

**Intent.** After Phase 1's paper loop is real, add the slow refresh so the watch set can grow past the static list. This phase is the first implementation of §3.1. It is not required for Phase 1 to pass, and it is not postponed to live.

**In scope**

- A scheduled job, default every 2 calendar days, writing `scout_candidate.v0` rows.
- Playbook input becomes the union in §3.1. Core names and holdings remain.
- Session card adds `candidate_size` next to core size, cap, and fetched count.
- Read-only paper-broker listability check. No new order type.

**Acceptance (all required)**

1. A fixture scout writes candidates that each have `sources[].ref` and `asof`, and the scout module does not import `OrderManager`, `place_desk_order`, or `upsert_active_intent`.
2. The next playbook pass may **see** a fresh candidate as an input symbol. Seeing it does not submit a buy unless that symbol is independently `VALID` and passes mandate and risk.
3. A fixture that is only a headline or a tip, with no playbook `VALID`, produces zero orders.
4. A candidate older than `SCOUT_MAX_AGE_DAYS` leaves the watch set. An open holding with the same symbol stays on the fetch list. A `STOCK_UNIVERSE` name stays when the cap is empty.
5. A row whose source type is not on the §3.1 allowlist is dropped. A row with empty `sources` is dropped.
6. With `SCOUT_ENABLED=0`, the fetch list matches Phase 1 (full core book, no candidate file required).
7. No Bloomberg, FactSet, Refinitiv, or Capital IQ client appears in the PR.

**Not acceptance.** The candidate list beat SPY, or a tip sheet was auto-traded.

### 6.2 Phase 2 — Split the clock; then consider one intent submitter

1. Move kill check, exit evaluation, and order sync onto a loop that runs while the process is up, including outside the cash session. New buys stay inside the session clock and the cadence filter.
2. Exit latency target: the protect pass starts within **5s** of the previous pass finishing. Do not advertise a 1s stop fill. Daily bars and the cash session still dominate fill time.
3. Off-session pass writes heartbeat and a position snapshot, expires stale intents (`expire_stale_intents`), and does not submit buys.
4. Intent migration is a **separate** flag, default off: `ENTRY_VIA_INTENT=0`. It turns on only after:
   - **Parity note:** a fixture records worker-sizer quantity and `size_intent_qty` for the same account, price, and limits. If they differ, the owner signs which formula is canonical. Phase 2 does not silently switch.
   - **Single submitter test:** when the flag is on, the strategy pass writes one `active` intent and does **not** call `process_signal` for that buy. Sticky idempotency still covers broker retries.
5. `consumed` remains "handed to risk", and the desk copy keeps saying so.

### 6.3 Phase 3 — The judge earns the seat

Same universe, same playbook, same sizer, same costs.

- Arm A: `AI_JUDGE=0`.
- Arm B: `AI_JUDGE=1` with closed veto only.
- Metric: R-expectancy \(E = (win\% \times avg\ win\ R) - (loss\% \times avg\ loss\ R)\) on **filled** round trips, plus trade count and average invested percent.
- Promote the judge on the product path only if Arm B's E is **> 0** and **> Arm A** on that shared universe, with the sample large enough to state (do not treat a handful of fills as a seal). Otherwise the flag returns to 0 and stays there.
- Every veto stores a counterfactual ("would have submitted") for a later shadow read. Missing counterfactual → that veto mode fails acceptance.
- This phase does **not** by itself open live (ADR-003 D2 then D4).

### 6.4 Phase 4 — Governor

Implement `harness_proposal.v0` as a store plus Desk present / approve / reject. One drill: digest → proposal → reject (L2 bytes unchanged) → approve → merge → rollback. Empty `sources` is rejected. Diffs that touch mandate, kill, risk percents, or the live flag are L2 and do not apply before Approve.

No Phase 4 work is required for Phase 1 to be true.

### 6.5 Phase 5 — Live

Not scheduled by this document. Reuse the existing promotion picture (MODULAR §4.3, `docs/STAGE2_SEAL_REPORT.md`, `docs/PAPER_VALIDATION_RUNBOOK.md`): filled-only counts, seal, a risk drill that actually fired, human sign-off, small capital. Unfilled limits do not count. The judge is included only if Phase 3 passed.

---

## 7. Reuse map

Extend these. Do not replace them with an agent framework.

| Need | Use | Leave alone in Phase 1 |
|------|-----|------------------------|
| Entry submit, idempotency, shadow | `engine/signal_processor.py`, `engine/sticky_idempotency.py`, `engine/shadow.py` | Do not add a second broker client |
| Risk reject | `risk/gates.py` `RiskEngine`, `risk/shared_state.py` (cooldown, daily loss) | No new limit numbers |
| Size | `risk/position_sizer.py` via the worker (Phase 1) | Do not let the judge pass shares |
| Mandate / kill / audit | `safety/mandate.py`, `safety/kill_switch.py`, `safety/audit.py` | Kill file format |
| Intent ledger (Phase 2 bus) | `intents/store.py`, `intents/models.py`, `intents/writer.py`, `engine/harness_realtime.py` | Do not write `active` intents from the Phase 1 buy path |
| Playbooks | `strategies/registry.py` and the named modules | Do not retune RSI, ATR, or VCP defaults in the trader PR |
| Why a name was skipped | `strategies/skip_codes.py`, worker `why_no_trade` log | — |
| Universe fetch | `engine/fetch_policy.py` (`WORKER_UNIVERSE_CAP`, batch, pause). Empty cap = full book. Holdings are always fetched | Do not burst the book in one tick. Do not set a default cap of 12 |
| Session filter | `engine/cadence.py` | Do not flip `IGNORE_MARKET_HOURS` |
| Journal the human can open | `utils/provenance/trade_log.py` | Do not mark paper rows as verified or live |
| Paper vs SPY display | `backend/api/paper_performance.py` (consumed by the lab tear sheet) | Do not treat it as a seal |
| Desk kill / resume | `POST /api/ops/kill`, `POST /api/ops/resume` in `backend/api/app.py` | — |
| Manual ticket | `engine/desk_orders.py` `place_desk_order` | Still not an IntentStore write |
| Teaching | `backend/api/help_chat.py` | Never import the executor |
| Research memos | `backend/lab/advisory_debate.py` | Never import from the worker |
| Broker | `alpaca_broker.py` paper endpoint | No live key path in this work |
| Regime context | `backend/agents/market_regime.py` (worker exposure target). Judge may not raise that target | Do not pretend the fair-backtest regime switch is the same classifier (see §9) |
| Scout readers (Phase 1.5, not Phase 1) | Per-name Yahoo news and earnings (`data_fetcher.py`), picks write-up (`picks_news.py`), Polygon bars / `list_date` (`polygon_equity.py`), session rescan of the current book (`scan_scheduler.py`), dollar-volume field (`technical_analyzer.py`) | Do not call these a market scout. Do not add Bloomberg / FactSet. Do not connect their output to `OrderManager` |

`backend/trading/advisory/` is the only new package in Phase 1, and it is a judge **interface** plus a no-op default. It must not import `OrderManager`. The scout package is Phase 1.5 and has the same import ban.

---

## 8. Failure modes

| Failure | What the user would see if we did nothing | Mitigation in this method |
|---------|-------------------------------------------|---------------------------|
| Model invents a buy or a size | A headline becomes a position, or size ignores the 25% / notional caps | Playbook gate first; schema rejects size; `RiskEngine` still evaluates; judge default off |
| Model "vetoes" with prose | Either everything blocks, or nothing does | Closed code list; unknown code does not block |
| Judge timeout or 500 | Tick stalls, stops wait | Judge is not on the exit path; 3s timeout → no new buy |
| Token cost runaway | Bill grows on a quiet day | Daily call/token cap → degrade to rules arm |
| Two submitters | Duplicate paper buys | Phase 1 forbids `active` intents on that path; test in §6.1.2 |
| Stuck worker | Heartbeat ages out, positions unwatched | Existing heartbeat file. Phase 2 adds an age alert. Restart must hit sticky idempotency, not a fresh minute-key, when a submit's acceptance is unknown (`ACCEPTANCE_UNKNOWN`) |
| Overtrading | Stable-like hundreds of round trips | Existing mandate daily cap, cooldown, intent expiry, one active intent per symbol+side (writer already replaces). Judge must not loosen these |
| Regime shift | Adding risk into a spike | `RiskEngine` VIX dampener and worker `target_allocation`. Judge cannot raise exposure |
| Stale or partial book | Decisions on missing bars, or a 5-name fallback looking like a strategy | `fetch_policy` + skip codes. Import fallback `AAPL MSFT GOOGL AMZN NVDA` (`worker.py`) must show up as a data fault on the session card, not as performance |
| Cash drag sold as skill | A 35% invested book "loses to SPY" and someone levers up | Session card and §9 require invested percent. No silent SPY core inside a strategy id |
| Self-tuning | Model widens stops after a loss | Forbidden. That diff is an L2 proposal |
| Proposal confused with an order | An unapproved diff starts trading | Separate stores. Phase 1 has no proposal applier |
| Gap through a daily stop | Open prints through the stop | Say so on the desk. Do not paper over it with an overnight LLM. Size and kill are the bounds |
| Lab or chat wired "just for paper" | Teaching text becomes an order | Existing isolation tests stay in the Phase 1 bar |
| Tip sheet becomes the book | A dozen headlines replace `STOCK_UNIVERSE`, or a scout row is submitted as a buy | Scout only unions candidates onto the full core book. Empty cap stays full-book. Candidate status cannot be an order. Headline without playbook `VALID` submits nothing |
| Ops cap mistaken for strategy | Someone sets a small `WORKER_UNIVERSE_CAP` and compares the card to the 74-name fair report or to fully invested SPY | Session card prints core vs cap vs fetched vs invested %. The cap is labeled `ops cap`. The product default stays empty |

---

## 9. Fair backtest, E0–E1, universe size

This trader does not get to ignore the research record.

**On main today.** [`docs/FAIR_STRATEGY_BACKTEST_REPORT.md`](FAIR_STRATEGY_BACKTEST_REPORT.md) (window `2023-09-28` → `2026-09-26`, universe **74/74**):

| Strategy | Total return | Excess vs SPY | Sharpe | Max DD | Trades | Avg invested |
|----------|--------------|---------------|--------|--------|--------|--------------|
| stable | −25.47% | −112.12 pp | −0.80 | 28.10% | 1440 | 35.71% |
| aggressive | +22.39% | −64.26 pp | 0.68 | 10.01% | 95 | 35.38% |
| hybrid | −4.38% | −91.03 pp | −0.02 | 26.54% | 1115 | 68.42% |
| SPY buy & hold | +86.65% | — | 1.45 | 18.76% | 1 | — |

None of these clear the Stage-2 yardstick (Sharpe ≥ 1 and a cost-aware positive excess; see `docs/STAGE2_SEAL_REPORT.md`). Equal-weight universe +191.88% is a survivorship-biased note, not a pass line.

**Draft, not on main.** [PR #42](https://github.com/cgabrielck/cgabrielck-stock-analyzer/pull/42) (`docs/FAIR_BACKTEST_ROOTCAUSE_AND_LIFT_PLAN.md`, branch `cursor/fair-backtest-rootcause-7986`) is the root-cause note. Use it as the hypothesis list, not as a merged result:

- **E0** is a measurement fix (next-open exits, costs inside profit factor, rank signals instead of ticker sort). It is expected to make published results look **worse**. It must land before anyone cites a "lift" against the 2026-09-28 table. E0 does not change the live worker.
- **E1** (drop RSI(2) take-profit on stable) is the first strategy hypothesis, and it needs a down-market window. It is not a paper-trading default and not a Phase 1 task.
- Aggressive's gap vs SPY is mostly **cash drag** (about 35% invested in a strong bull market). Stable's loss is mostly the positions themselves (RSI(2) take-profit on 889 of 1440 exits). Hybrid was not "mis-routed into mean reversion".
- A named core-satellite (hold SPY, plus a sleeve) must be a **new policy id**. It must not be written back into `aggressive` or `hybrid`, and it must not loosen Kelly, the 25% name cap, mandate, or kill.

**Universe size.** The operating pool is the full `STOCK_UNIVERSE` (tests pin length in 70–80; the fair report loaded **74/74**). `WORKER_UNIVERSE_CAP` empty means fetch that whole book, holdings first, in batches (`fetch_policy.py`). That empty-cap behavior is the product default. Keep it.

The "~12 names" sentence in PM brief v1 was only a warning: a pool that small caps upside. Gabriel restated on 2026-10-26 that it is **not** a ceiling and not the runtime book. This method does not set a 12-name default, and Phase 1.5's scout exists so the watch set can grow wider than any fixed short list.

`WORKER_UNIVERSE_CAP` and `--tickers` remain explicit overrides for rate limits or a one-off debug run. They are ops knobs. The session card must show core size, candidate size (zero until Phase 1.5), cap, and fetched count. If a run was capped, do not compare that card to the 74-name fair report or to fully invested SPY unless average invested percent is on the same card. `RiskLimits.max_open_positions` default 10 limits how many names can be **held**. It does not shrink the research or scout universe, and it is not a reason to fetch only 12 symbols.

**How the phases use this**

| Phase | Relationship to E0 / E1 / universe |
|-------|-------------------------------------|
| 1 | Run the **current** playbook defaults on the **full** core book. Report core size, cap, fetched count, and invested fraction. Do not retune. Do not claim the fair-report gap is closed. Do not wait on the scout |
| 1.5 | Union sourced candidates onto that full book. Still no retune. Candidates are not a backtest lift and are not orders |
| 2 | Still no retune. Clock split does not change signal rules |
| 3 | Judge-vs-rules on one **stated** universe (core plus whatever candidates were actually eligible, counts printed). If E0 has not been re-run, say the backtest yardstick is still the optimistic 2026-09-28 report. Paper E is the promotion metric, not a rewritten backtest |
| Strategy default changes | Separate research PRs under the PR #42 rules (one lever, holdout window). Out of band for the trader loop |

The fair-report regime switch (`classify_spy_regime`) is not the worker's `classify_market_regime` (VIX, `target_allocation`). Do not explain a paper fill by quoting the backtest router.

---

## 10. OSS patterns — adopt or reject

Inspected 2026-10-26. Stars and README claims move; the adopt/reject is about the **mechanism**, not about vendoring code.

### Adopt (mechanism only)

| Source | What we copy | What we do not copy |
|--------|----------------|---------------------|
| [HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) order guard (described in the repo contributor guide and mirrored by [hdworker/bybit-mcp](https://github.com/hdworker/bybit-mcp)): load mandate → expiry → halt before any broker call → parse intent → price the notional or deny → check caps. Structural breaches deny; the agent cannot edit the mandate | Fail-closed order of checks; halt is a file, not a prompt; write-tools and read-tools are different classes | Their later [pre-trade advisory](https://github.com/HKUDS/Vibe-Trading/pull/328) is **fail-open** and "never blocks". Our judge failure mode is silence on **entries**. Do not port their crypto/perp deploy loop |
| [nautechsystems/nautilus_trader](https://nautilustrader.io/docs/latest/concepts/execution/) `RiskEngine` on the submit path: denied orders never reach the venue; reconciliation is a separate component | We already have this shape (`RiskEngine` → `OrderManager` → `ReconciliationService`). Keep it | Do not rewrite the desk onto Nautilus |
| [laukkw/brale-core](https://github.com/laukkw/brale-core): models propose a plan, a deterministic engine checks price, size, stops; default execution is dry-run; cycle is observe → decide → plan → execute → monitor → reconcile | The split and the dry-run default. Our shadow mode is the dry-run | Go + Freqtrade runtime. Freqtrade wants to be the host; our host is `TradingWorker` |
| [CoinRithm/coinrithm-agent-trading](https://github.com/CoinRithm/coinrithm-agent-trading/blob/main/docs/agent-runner.md) `observe → decide → validate → act`, structured decisions, dry-run default, hard caps | Loop names and "validate before act" | Their venues and the idea that a markdown file the agent can edit is the risk constitution. Caps stay in `RiskLimits` / mandate |
| [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) ([paper](https://arxiv.org/html/2412.20138v6)): analyst vs trader vs risk vs portfolio manager, plus a memory of past decisions | **Role names** for memos and for the governor's narrative. Journal is the memory | The portfolio manager is **not** our approver. LLM risk debate is not `RiskEngine`. Their simulated exchange is not Alpaca. ADR-003 already bars a debate committee as the execution engine. Lab code may keep role-play; product must not |
| [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund): paper ledger, an explicit decision shown before the paper fill, kill switch, hash-chained session log. README: educational, not a broker | Paper-first, decision record, kill | Persona swarm as the trader. "Approval every session" would make Phase 1 a copilot; owner Approve is for **rule changes**, not for every paper buy the playbook already authorized |

### Reject

| Source | Why it does not fit |
|--------|---------------------|
| [Hafida3/TRADING-BOT](https://github.com/Hafida3/TRADING-BOT) (Oracle, SOL/USDC) | Useful sentence — "signals propose, the LLM can refuse, the code decides" — and then a design we will not ship. One ReAct call every 300s **before** act, so exits wait on the model. `TUNE` rewrites thresholds from inside the loop. Live path is Jupiter. Single-author sketch, not a dependency. We keep the sentence for **entries only** |
| [sundeep-dayalan/sentient-trader](https://github.com/sundeep-dayalan/sentient-trader) | Headline in, four-model debate, then a trade. That is the ADR-003 failure mode (news must not open a position). Two-star demo with a large open-issue list. Drop |
| [OpenTradeOSS/OpenTrade](https://github.com/OpenTradeOSS/OpenTrade) | macOS harness that gives Claude Code / Codex the Robinhood MCP and lets the agent trade. The model holds the broker tool. Guardrails sit around an agent session, not inside our `RiskEngine`. Wrong broker, wrong trust boundary |
| [useopentrade](https://pypi.org/project/useopentrade/) / opentrade.money | Another TradingAgents-style memo pipeline aimed at crypto deployment. Do not confuse the name with `OpenTradeOSS/OpenTrade`. Neither is our execution layer |
| [Aslan11/crypto-trading-agents](https://github.com/Aslan11/crypto-trading-agents) | Temporal durability and an LLM-as-judge that rewrites prompts from P&L. Durability is attractive; adopting Temporal is a rewrite. Autonomous prompt updates are L2 and belong in a proposal, not in a 24/7 optimizer |
| [Alessandro624/trading-agent-hackathon](https://github.com/Alessandro624/trading-agent-hackathon) | Observe → reason → act on Alpaca paper, but the decision object includes **quantity**, and a second LLM is the risk review. Quantity-from-the-model is forbidden here |
| [Mai0313/TradingAgents](https://github.com/Mai0313/tradingagents) | Fork that still emits a trade recommendation with size, target, and stop from the risk judge. Same rejection as upstream-plus-size |
| Freqtrade `IStrategy` as the new core, Hummingbot controllers, QuantConnect LEAN | Mature hosts for a different product. Hummingbot is a market-making engine. LEAN is a platform commitment. ADR-003 D5 says evolve `backend/trading/` |

**PM v1's loop** was `observe → LLM judge → hard gate → act → log → maybe learn`. The loop we will implement is:

```
observe (sentinel, no LLM)
  → names = full STOCK_UNIVERSE ∪ scout candidates (Phase 1.5; not orders)
  → playbook VALID or skip
  → optional LLM judge (veto / tier only; failure = skip)
  → hard gate (mandate + RiskEngine) 
  → act (one submitter, paper/shadow)
  → log
  → learn only as a proposal, later, with a human Approve
```

The scout is not a step between "headline" and "act". The hard gate is not a courtesy check after the model has already decided to trade. The model never sees a broker tool, and it is not consulted for the exit.

---

## 11. Where this method upgrades PM brief v1

Kept from v1, unchanged: paper before live; hard risk gates; owner Approve for major rule changes; extend Harness rather than rewrite; Ask Cgab stays teaching-only; do not pretend the current strategies beat SPY; dual shell with Desk as the only trading UI.

| # | PM v1 | This method | Why |
|---|--------|-------------|-----|
| 1 | One loop: observe → **LLM judge** → gate → act | Playbook first. LLM only vetoes or downgrades a `VALID` entry. Exits never enter that loop | Otherwise stops wait on a model (Oracle's 300s cycle). ADR-003 H1 already forbids a synchronous LLM on the protect path. News-triggered debate (sentient-trader) violates D1 |
| 2 | "24/7 trader" read as always judging and acting | 24/7 **process**. Buys only in the cash session. Phase 1 exits still sit inside `_is_market_hours`, which the brief did not mention | The worker does not manage exits overnight today. US stocks do not fill a daily stop at midnight. `IGNORE_MARKET_HOURS` is not the fix |
| 3 | Phase 1 = paper closed loop, criteria left open | Phase 1 pass/fail list in §6.1, including double-submit and "skip is success" | Without that, an engineer will wire intents **and** `process_signal` and double-buy, or call a quiet day a failure |
| 4 | Harness already sounded like H1 consumes H3 intents | Phase 1 **keeps** `process_signal` as the buy submitter. Intent consume stays for intents something else wrote. Unification is Phase 2 after a size-parity note | Worker buys never call `upsert_active_intent`. `size_intent_qty` is a different sizer. The thin hook is real and is not the paper auto path |
| 5 | LLM judge is the product | Judge interface exists in Phase 1 and defaults **off**. Promotion is Phase 3 against the rules arm (ADR D2) | A loop that requires a model cannot be compared to pure rules, and it ships cost and hallucination before any edge |
| 6 | TradingAgents-style debate as a pattern to pressure-test | Roles for memos only. Debate is not the engine. Lab file stays unwired | ADR-003 out of scope, plus `LAB_PRODUCT_M7_BINDING.md`. Vibe-Trading's fail-open advisory is the wrong polarity |
| 7 | Self-upgrade implied by the learn step | No hot-path `TUNE`, no prompt optimizer (reject Aslan11 / Oracle). Governor waits until Phase 4 because **no proposal applier exists** | PM v1 could be read as if governance code were already there. It is a schema in MODULAR §5.5 |
| 8 | ~12-name pool "caps upside" as context. The first draft of this file over-read that sentence and treated a short list as the operating case | **Corrected 2026-10-26 by Gabriel.** ~12 was a warning, never a ceiling. Default runtime stays full `STOCK_UNIVERSE` whenever `WORKER_UNIVERSE_CAP` is empty. A cap is an ops knob and must be labeled. If someone still caps small, they must not compare that card to the 74-name fair report or to fully invested SPY without invested % | The fair report's aggressive gap is already mostly cash drag at ~35% invested on a **74-name** book. Shrinking the book is not the remedy, and it is not the product |
| 9 | OSS list treated as peers | Drop sentient-trader, both OpenTrades, Oracle-as-architecture, hackathon quantity-from-LLM. Add Nautilus (pattern we have), Brale (propose/validate/dry-run), Vibe-Trading **guard** not its fail-open advisor, CoinRithm's validate-before-act | Those drops are the designs that put the model on the broker or on the exit |
| 10 | Backtest mentioned as a warning | Phase 3 may not cite a lift until E0 exists. E1 is not a trader default. PR #42 is draft and not on `main` | Otherwise paper P&L gets narrated as if the known measurement bugs were fixed |
| 11 | (not in v1) Living universe | **Scout**, about every 2 calendar days, Phase **1.5** after the paper loop exists. Candidates carry source, ref, asof, and theme, and join the watch set only. Headlines still cannot open a position | Gabriel 2026-10-26: do not keep a short-list mindset. Phase 1 still does not depend on discovery APIs. Bloomberg / FactSet are not pretended |
| 12 | (not in v1) Stocks-only subscription | Feed note §9 compares Bloomberg, IBKR, Massive, Alpaca, Tradier, and tastytrade. Options stay **out of Phase 1 / 1.5 orders**. A later options door remains: one tape and one order path, Alpaca paper options first | Gabriel 2026-10-26: more functions, including options. Personal / non-pro. No Bloomberg, no IBKR, no Tradier migration now |
| 13 | (after approval) Buy Starter and Benzinga together | **Revised the same day.** Monthly data budget ≈ **HK$400 (~US$51)**. Massive Stocks Starter (~$29) is **buy later**, not this PR. Benzinga Earnings (~$99) is **over budget**. Free calendars first: Alpha Vantage `EARNINGS_CALENDAR`, Finnhub free calendar; SEC / XOOMAR confirm reported. This PR purchases nothing and writes no keys | Gabriel 2026-10-26 Asia/Hong_Kong, after the first PR body |

---

## 12. What implementing Phase 1 must not touch

- `RiskLimits` defaults, mandate JSON semantics, kill file semantics.
- Strategy numeric defaults (`RSI2_EXIT`, ATR multiples, VCP rules). Those are E1+ research.
- `--allow-live` behavior, other than tests that the Phase 1 path does not use it.
- `place_desk_order` quantity handling.
- `backend/lab/advisory_debate.py` wiring.
- `backend/api/help_chat.py` tools.
- Default universe size. Do not set `WORKER_UNIVERSE_CAP` to 12 or any other short list in the Phase 1 change.
- Scout clients, candidate files, and any path from a tip sheet to `OrderManager`. That work is Phase 1.5, under §3.1 and §6.1b.

A Phase 1 code PR that needs any of those is out of method and needs its own owner decision.

---

## 13. Related docs

- [ADR-003-live-ai-trading-desk.md](ARCHITECTURE_DECISION.md) — D1–D4, Addendum A clocks and proposals.
- [MODULAR_ARCHITECTURE.md](MODULAR_ARCHITECTURE.md) — §4.4 clocks, §4.5 governance, §5.5 proposal, §5.6 intent.
- [BOUNDED_INTELLIGENCE_ACCEPTANCE.md](BOUNDED_INTELLIGENCE_ACCEPTANCE.md) — Draft acceptance for veto / expectancy. Not Accepted.
- [LAB_PRODUCT_M7_BINDING.md](LAB_PRODUCT_M7_BINDING.md) — Lab debate is not the product path.
- [FAIR_STRATEGY_BACKTEST_REPORT.md](FAIR_STRATEGY_BACKTEST_REPORT.md) — 2026-09-28 numbers on `main`.
- [PR #42](https://github.com/cgabrielck/cgabrielck-stock-analyzer/pull/42) — draft E0–E9 plan, not merged.
- [STAGE2_SEAL_REPORT.md](STAGE2_SEAL_REPORT.md), [PAPER_VALIDATION_RUNBOOK.md](PAPER_VALIDATION_RUNBOOK.md) — frozen promotion references, still the live-gate picture.
- [ACCOUNT_MANAGEMENT_DESIGN.md](ACCOUNT_MANAGEMENT_DESIGN.md) — Desk manual path vs worker path.
- [DATA_FEED_AND_SUBSCRIPTIONS.md](DATA_FEED_AND_SUBSCRIPTIONS.md) — 2026-10-26 prices, revised the same day to ≈ HK$400 (~US$51). Starter is buy-later. Benzinga is over budget. Free calendars first. Not a purchase order. Options orders stay outside Phase 1 and Phase 1.5.
