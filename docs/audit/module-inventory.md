# GabFin 舊專案結構及命令盤點

本文件記錄 S01/01a–01b 的結構與功能路徑；固定版本及實際檢查結果由 [baseline](baseline-2026-11-25.md) 擁有。以下路徑均相對於該 checkout，並非新的目標架構。**檔案存在或可追蹤呼叫，不代表功能已通過 runtime 驗收。**

## 結構與入口

| 路徑 | 靜態確認的用途／連接 | 驗證邊界 |
|---|---|---|
| `backend/api/app.py` | FastAPI Desk；註冊 intents、zones、mobile、observe router，以及研究、帳戶、委託等 endpoints | 未啟動／未驗證權限與 HTTP 行為 |
| `web/static/` | FastAPI `/` 直接回傳 `index.html`；`/m` 回傳 `mobile.html`；包含 vendored chart JS | 是目前 API 實際服務的介面；未做瀏覽器 QA |
| `web/src/`、`web/package.json` | 另一套 React 19／TypeScript／Vite 6 原始碼；Vite dev proxy `/api` 到 `127.0.0.1:8000` | 01b build 成功，但 typecheck 失敗；產物不是上述 static shell |
| `backend/app.py`、`backend/static/`、`run.py` | Streamlit lab／legacy；`run.py` 啟動 Streamlit 並提供舊 PWA proxy | 與 FastAPI Desk 不同入口；未執行 |
| `backend/api/research_jobs.py`、`backend/agents/`、`backend/research/` | Scan、deep research、評分、基本面、技術面、新聞、LLM、SEC、研究工具 | jobs 使用 thread 與 JSON 結果快取；完整服務追蹤留待 01b |
| `backend/observe/`、`backend/api/desk_observe.py` | observe router → `FutuObserveAdapter`／gateway → 本機 OpenD | API／WebSocket 路由存在；尚未驗證 feed、推送或權益 |
| `backend/trading/engine/` | worker、OrderManager、SignalProcessor、shadow、sticky idempotency、cadence | 未啟動，未作下單或恢復測試 |
| `backend/trading/risk/`、`safety/`、`reconciliation/`、`strategies/` | 風控、mandate／kill、對帳、策略；由 worker／order 路徑使用 | 不把舊數值視作新版本已批准政策 |
| `backend/trading/storage.py`、`intents/` | `create_order_store()` 預設 SQLite，可選 JSON／Postgres；另有 intent models／store | 尚未驗證交易邊界、並發或持久化正確性 |
| `backend/accounts/`、`backend/persistence/migrations/` | 可選 Supabase 帳戶 repository；7 份 SQL migrations | 未連線／未套用 migration |
| `backend/backtesting/`、`backend/lab/`、`scripts/` | 回測、評估、研究與實驗工具 | 沒有執行；不引用歷史績效或 pass 數為本次結果 |
| `tests/`、`pytest.ini` | pytest 搜尋 `tests`，加入 `backend` 到 pythonpath；含 API／observe／trading／research 等子目錄 | 01b 已跑完整 suite；實際 pass／skip 及限制見 baseline |
| `deploy/`、`railway.toml`、`config/`、`data/`、`backend/data/` | systemd worker 配置、Railway alert worker、設定及資料／舊產物 | 沒有部署或載入運行狀態 |

## 01b 功能矩陣：入口 → service → provider → store

「部分」只表示已有實作／部分工程證據；「未知」表示真實外部整合未驗證；「實驗」表示 lab 路徑；「可用」只用於明確列出的已執行檢查。本次沒有可宣稱整套產品可用的證據。64 個 API／WebSocket decorator、5 個 API modules 的靜態索引見 [route-index.json](artifacts/s01-01b/route-index.json)，不是運行時 OpenAPI 驗證。

| 功能／入口 | Service → provider → store | 狀態及邊界 |
|---|---|---|
| Desk `/`、手機 `/m` | `api/app.py` → `web/static/index.html`／`mobile.html`；無 build dist 接線 | 部分：檔案與 routes 存在；瀏覽器／手機未驗證 |
| React dev／build | `web/src/App.tsx`／`api.ts` → Vite proxy → `/api`；`web/dist/` | 部分：build 成功，但獨立 TypeScript 檢查失敗；並非 `/` 正在服務的 static shell |
| Streamlit lab／舊 PWA | `backend/app.py`；`run.py` → Streamlit subprocess／static proxy | 實驗：保留舊入口，未啟動 |
| Scan `/api/scan`、狀態／latest | `research_jobs.start_scan` → `_run_scan_job` → `agents.recommender.run_full_analysis` → data/fundamental/technical/news/LLM helpers → cache／`last_scan.json`；進度在 memory thread job | 未知：未使用外部行情／模型跑完整研究；不等於 durable job |
| Deep `/api/deep`、`/api/research/{symbol}` | `research_jobs` → `agents.deep_research.analyze_tickers`／`research_bundle` → Yahoo／SEC／LLM／研究模組 → `last_deep.json`／cache | 未知：provider 與完整研究耗時未測 |
| Quotes `/api/quotes` | `app.py` → `yfinance.download` → Yahoo；response rows | 未知：未呼叫行情；不是 OpenD 路徑 |
| Chart `/api/chart/{symbol}` | `desk_chart.chart_payload` → `utils/equity_ohlcv.fetch_daily_ohlcv` → 有配置時 Polygon，否則／失敗時 Yahoo fallback → frame／indicators response | 未知：真實資料授權與新鮮度未測 |
| Observe quote／bars／stream | `api/desk_observe.py` → `FutuObserveAdapter` → `futu_gateway` → 本機 OpenD；adapter subscription／history cache | 未知：測試替身不代表主機 feed 權益／推送驗收 |
| Desk options `/api/options/{symbol}` | `app.py` → `yfinance.Ticker.options`／`option_chain` → Yahoo → response | 未知：此 endpoint 直接用 Yahoo，不能宣稱已接所有 fallback |
| 研究期權與 alerts | `agents/data_fetcher.fetch_options_chain` → Yahoo → Tradier → Polygon → Cboe delayed fallback；`options_quote_adapter`／`options_risk_agent` 處理研究與品質 | 部分：程式有 fallback，真實 chain／Greeks／alerts 未驗證 |
| Intent `/api/intents*` | `api/intents.py` → `intents.writer`／models → `JSONIntentStore` → `trading_intents.json`＋process lock | 部分：與 L2 order ledger 分開；完整恢復與並發證據仍須查測試結果 |
| 委託／cancel／account／positions | `app.py` → `engine/desk_orders.place_desk_order`／`AlpacaBroker` → Alpaca SDK；`create_order_store` → SQLite（預設）／JSON／Postgres | 未知：沒有連接 broker 或啟動交易；測試使用替身 |
| Worker、風控、對帳、kill | `worker_ctl`／worker CLI → `TradingWorker`、`SignalProcessor`、risk gates、mandate、kill、`OrderManager`、`ReconciliationService` → broker／ledger／heartbeat／audit | 未知：未啟動程序、未跑 paper／shadow 運行窗口；舊數值未獲新版本批准 |
| Journal／digest／performance | `api/trade_journal` → `utils/provenance/journal_store`＋order store／audit；`paper_performance` → fills／benchmark helpers → JSON reports，部分分支可讀 broker | 部分：本地路徑存在；不據舊 cache 宣稱最新績效 |
| Drawing zones | `/api/desk/zones*` → `desk_zones` sanitize／snapshot／meta → `desk_zones.json`；前端 drawing block 可由 Node 測試 | 部分：來源證據與下單分離；瀏覽器互動未測 |
| Help chat | `/api/help-chat` → `help_chat.answer_help_chat` → 本地 guide whitelist／固定拒答；無 conversation store／order provider | 部分：是教學路徑，不是新版本帳戶／研究聊天實作 |
| 身份與手機控制 | `desk_auth` → loopback／operator/read token；`mobile_desk` snapshot → worker／scan／journal，continue/pause → operator guard／paper control | 未知：真實代理身份／私人 HTTPS／手機未測；不是新身份設計已完成 |
| 帳戶／收藏／saved plans／通知 | Streamlit `account_ui`／`saved_plan_ui` → `accounts.factory.get_account_repository` → `SupabaseAccountRepository`；`alert_worker` → `alert_monitor`／Telegram → Supabase alert rows | 未知：未連線 Supabase／Telegram，未套用 migrations；非完整 FastAPI account auth |
| 回測／研究 lab | `backtesting/strategy_backtest.py`／scripts → strategy／risk／行情資料；`/api/lab/*` → advisory／schema／sentiment／tear helpers → lab reports | 實驗：可選 lab extras 未安裝，未重跑策略績效或驗證無前視 |

這是按功能分組的 source 路徑盤點；完整端到端、故障恢復、外部 provider 權益、效能與 UI 驗收仍屬後續關卡。測試結果的覆蓋範圍與失敗分類以 baseline 為準。

## 開發命令

在 checkout root 使用隔離 Python 3.12 環境。下表的 Python 命令使用該 venv 的 executable；01b 使用的實際版本、已執行命令及結果見 baseline，啟動類命令仍只作入口辨識。

| 用途 | Windows PowerShell 命令／位置 | 來源及限制 |
|---|---|---|
| 安裝 Python 依賴 | `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` | 主 manifest；沒有 lockfile；不必為基線安裝 lab extras |
| pytest 基線 | `.\.venv\Scripts\python.exe -m pytest` | Task 1、`pytest.ini`；必須記錄 pass/fail/skip |
| 語法編譯 | `.\.venv\Scripts\python.exe -m compileall -q backend tests` | README；不是功能測試 |
| React 依賴 | `npm install`，工作目錄 `web/` | 無 lockfile，不能直接使用 `npm ci`；應記錄解析結果及生成檔案 |
| React build／typecheck | `npm run build`／`npm exec -- tsc --noEmit`，工作目錄 `web/` | build → `web/dist/`；兩者必須分開記錄，Vite script 不執行 typecheck |
| React dev／preview | `npm run dev`／`npm run preview`，工作目錄 `web/` | manifest scripts；dev port 5173；未啟動 |
| Desk | `.\.venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000` | README；有 broker/store 初始化與 lifespan 行為，非本次驗證命令 |
| Streamlit lab | `.\.venv\Scripts\python.exe -m streamlit run backend/app.py` | README；舊介面，非 Desk |
| Worker／alerts（僅辨識入口） | `python -m backend.trading.engine.worker`；`python backend/alert_worker.py` | deploy runbook／Railway；本次不執行 |

## 已辨識的外部依賴

- 行情及資料：Yahoo／`yfinance`、Polygon、Alpha Vantage、AkShare；OpenD／`futu-api` 為主機可選安裝。期權另有 Tradier、Cboe 等 provider 模組。來源：`backend/agents/`、`backend/observe/`、README。
- 帳戶及執行：Alpaca SDK／broker；本地 SQLite／JSON，Postgres 為可選 ledger；Supabase 為帳戶及 alerts 持久化。來源：`storage.py`、`accounts/factory.py`、migrations。
- 模型及通知：OpenAI-compatible client、Telegram inbox／通知／alert worker。`requirements-lab.txt` 的 Instructor、QuantStats、Transformers／Torch、LangGraph 為可選實驗依賴。
- 本次實際呼叫的是 Python／npm 套件下載來源；應用服務的真實整合、授權、新鮮度、成本與 credentials 未驗證。功能矩陣標示 provider 路徑，實測失敗與 skip 分類由 baseline 擁有。
