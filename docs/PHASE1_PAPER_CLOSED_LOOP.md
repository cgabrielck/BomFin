# Phase 1 — 紙上閉環（實作筆記）

**狀態：** 程式切片，**未合入 `main`**。方法頁 [`AI_SMART_TRADER_METHOD.md`](AI_SMART_TRADER_METHOD.md) 已獲准；本頁只記錄 Phase 1 碼做了什麼。**Merge ≠ runtime。** 不開 live、不改產品預設、不購買資料。

## 這一刀交付什麼

一個 `--once` 週期可以走完：看盤 → 現有劇本 `VALID` 或跳過 → 判斷員槽（預設關）→ 既有 `process_signal`（mandate → RiskEngine → OrderManager）→ 日誌。沒有單時，寫下 `why_no_trade` 也算成功。

| 項目 | 落點 |
|------|------|
| 唯一買入送單者 | `TradingWorker._run_strategy_signals` 裡的 `SignalProcessor.process_signal`。這條路徑**不**寫 `active` intent |
| 判斷員槽 | `backend/trading/advisory/`（介面 + `AI_JUDGE=0` 的 no-op）。呼叫點在買入 `process_signal` **正前方**。關閉時不打網路、不呼叫 client |
| 判斷失敗 | `AI_JUDGE=1` 且逾時、壞 JSON、空 sources、或帶 `quantity`／`notional` → 不買。出場仍走 `_submit_sell`，不經判斷員 |
| 未知 veto | 不在 `CALENDAR_BLACKOUT`／`STALE_DATA`／`CORR_CAP`／`KILL_ACTIVE`／`EVENT_FREEZE` 的代碼只記 log，不擋 `VALID` |
| Session card | `backend/trading/engine/session_card.py`，寫進 heartbeat 的 `session_card`。核心池大小、cap、抓到幾檔、skip 次數、訂單狀態。空的 `WORKER_UNIVERSE_CAP` = 完整 `STOCK_UNIVERSE`。截斷時標 **ops cap**。不是封印，不寫「贏過 SPY」 |
| 模式 | CLI `--mode` 預設仍是 `shadow`。`paper` 沿用 `AlpacaBroker` 的 paper endpoint。Phase 1 指令不帶 `--allow-live` |
| 偵察 | `SCOUT_ENABLED` 預設 0。沒有 scout client，`candidate_size` 固定 0。環境變數設成 1 也不會去抓新股票 |

## 刻意不做

- 不改 `RiskLimits` 預設（Kelly 0.5、單筆名目上限、日損百分比、集中度、總曝險）。
- 不改 mandate／kill 語意。Kill 仍擋新買、出場仍可賣；resume 仍寫 `kill_switch_resume`。
- 不把 `conviction_tier` 拿去改張數（那是 Phase 2 尺寸對齊之後的事）。
- 不把買入改走 intent bus（`ENTRY_VIA_INTENT` 不在這刀）。`consume_active_intents` 只消費別人寫好的 intent，不是第二個送單者。
- 不接 Ask Cgab、`lab/advisory_debate`、MCP 到 `OrderManager`。`advisory` 套件不准 import `OrderManager`。
- 不開 `IGNORE_MARKET_HOURS`。不實作 Phase 1.5 偵察、Phase 2 時鐘拆分、Phase 3 判斷員對打、Phase 4 提案合併、live。
- 不自調門檻、不寫會自動合併規則的 runtime writer。
- 正報酬、Sharpe、贏過 SPY、已批准提案、live 偵察，都不是驗收。

## 怎麼跑 `--once` 閉環測試

驗收用假券商，不打網路。指令就是 worker CLI 的 `--once`（`main(["--once", ...])`）：

```bash
python -m pytest \
  tests/trading/engine/test_phase1_closed_loop.py \
  tests/trading/advisory/test_judge.py \
  -q
```

對到的案例：

- `test_once_cycle_journals_order_and_does_not_double_submit` — `--once --mode paper`，日誌有 `submitted`／`filled`／`risk_rejected`／`canceled` 之一，而且 `process_signal` 只送一次、intent store 沒有新的 `active`。
- `test_once_quiet_cycle_writes_why_no_trade` — 沒有單，session card 寫下 `no_setup`。沉默但有 skip，算成功。

手動煙霧（要自己的 paper 金鑰，**不要**加 `--allow-live`）：

```bash
python -m backend.trading.engine.worker --once --mode shadow
```

預設已是 `shadow`。紙上帳戶才用 `--mode paper`（`APCA_PAPER=true`）。Heartbeat JSON 裡的 `session_card` 就是這一輪的標籤。

## 經驗與學習

Harness 難控，是因為同一輪裡已經有兩條會碰到 `process_signal` 的路：劇本買入，以及 H1 消費 `active` intent。Phase 1 若兩邊都寫，一筆訊號會買兩次，而且兩套張數公式還不一樣。所以這刀只延長既有的送單者，不新開一條。

另一個容易誤判的地方是「沒有成交＝失敗」。劇本多數日子不給 `VALID`。把 skip 寫進 `why_no_trade` 才是閉環；沒有寫下來的安靜才是故障。

判斷員預設關掉，是為了之後能跟純規則比，而不是為了這一輪就接上模型。失敗要沉默（不買），出場不能等模型。未知 veto 不擋，避免散文式否決把整本書鎖死。

約 12 檔不是產品。空的 `WORKER_UNIVERSE_CAP` 就是全池。有人為了速率把 cap 調小，卡片要寫 **ops cap**，否則會把運維旋鈕說成策略，再拿去跟 74 檔公平回測或滿倉 SPY 比。

匯入失敗時退回 `AAPL MSFT GOOGL AMZN NVDA` 是資料故障，不是績效。卡片要這樣標，不能把它畫成一本書的成績。
