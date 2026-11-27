# Recent progress

## 2026-11-27 — 分析平面的生產接線完成（提交 `cd59fca1`）

- **發現的實際阻塞**：`create_market_app(analysis=None)` 預設不掛載分析路由，
  且沒有任何生產路徑傳入它；三個端點在真實服務上會是 404。
  `IndicatorPlane` 也只吃抽象 `BarSource`，沒有任何實作。
  也就是說前端若直接開工，第一條 e2e 就會撞上「端點不存在」。
- 新增 `services/gabfin/analysis/sources.py`：tape 支撐的 bar source、
  FRED macro source、已量測能力的 capability source。
- 新增 `services/gabfin/analysis/runtime.py`：唯一決定「哪個來源是哪個」的地方，
  含 symbol resolver（tape 以 symbol 為鍵，不是 canonical uuid）。
- 指標平面改為接受 resolved coverage；stored venue 不在合約接受清單就拒絕計算
  （404）。沒有 venue 的指標不可比較。
- `services/gabfin/storage/tape.py` 新增 `read_rows`：回傳實際行，不只回傳行數。
- e2e fixture 掛載確定性的分析平面，前端因此有真實 server 可對接。
- 驗證：**2388 pytest passed / 4 skipped**（同 `issues.md` 記錄的 4 個既有失敗）、
  **39 Playwright passed**（含新增 6 項分析端點測試）、tsc --noEmit 乾淨。
  **合約未變動**，schema 與 `generated.ts` 未重建。
- 交接卡補上錯誤形狀對照表、宏觀序列白名單、`Origin` 標頭要求、已知後端限制。

## 2026-11-27 — WU-7 provider routing 與 WU-9 分析平面完成並交接前端

- 兩個工作單元已提交（branch `codex/s01-source-baseline`）：
  WU-7+WU-9 `5c49495a`、交接卡 `9e7d109b`。
- WU-7：`services/gabfin/providers/registry.py` 以 `SourceProfile` 描述來源的
  namespace／市場／可接受的 symbol 形狀／配額池，`ProviderRegistry` 依能力路由。
  `market/subscriptions.py` 不再 import Futu，也不再有 `caps.source != 'futu'`。
  無來源接受的 symbol 以明確理由拒收，不改寫成別家的 symbol。
- WU-9：`FeedCapabilities` 新增 `venue_coverage`／`realtime`／`delay_minutes`／
  `tradable_for_entry`／`depth_levels`／`fee_class`／`unavailable_reason`，
  驗證器禁止延遲或 indicative 報價宣稱 `tradable_for_entry=True`。
- WU-9：新增 `services/gabfin/analysis/plane.py`（指標／宏觀／能力三個平面）、
  `services/gabfin/contracts/analysis.py`（三個回應合約）、
  `services/gabfin/api/analysis.py`（`/v1/indicators`、`/v1/macro`、`/v1/capabilities`）。
  宏觀平面只回傳 `as_of` 當時**已發布**的觀測值。
- WU-9 修正三個真實缺陷：`_timeframe` 的 `rstrip` 讓 `1day` 完全無法解析；
  `_date` 被包在 macro 的 `try` 內使格式錯誤變成 503；`PermissionError`
  未被捕捉使能力不足變成 500。
- 新增測試：`tests/providers/test_registry.py`、`tests/gabfin/test_analysis_planes.py`（17）、
  `tests/api/test_analysis_api.py`（24）。
- 驗證：**2375 pytest passed / 4 skipped**、tsc --noEmit 乾淨、
  `schemas/gabfin-1.0.json` 與 `generated.ts` 已重建。
- 前端交接：`docs/handover/HANDOVER.md` `stage: ready-for-ui`，
  `docs/handover/ui-tasks/WU-9-ui.md` 為 Carbon 的任務卡。

## 2026-11-27 — Part 1 完成：tape 基礎、Alpaca adapter、增量指標引擎；FRED 宏觀完成

- 四個工作單元已提交：WU-0 `c870c16b` tape storage、WU-1 `278daf4f` Alpaca adapter、
  WU-2 `b20a5d93` 增量指標引擎、WU-3 `1cbee09e` FRED 宏觀平面。
- WU-1 修正：token bucket 在 sleep 後重算等待量，浮點誤差使它永不收斂，
  單條測試跑了 8 分鐘後 MemoryError。改為低於容差時直接發放並記錄等待次數。
- WU-2 修正 WMA 增量化：視窗滾動時新值誤用滿權重，首個完整視窗與直接計算不符。
- WU-2 引擎不變式「seeded 狀態 == 全量重算」在 7 個 seed 點驗證通過；
  ATR／Bollinger／MACD 以不同路徑重算，避免同源錯誤互相印證。
- WU-3 關鍵：宏觀點**強制保留 `release_date`**，缺 release date 的觀測直接拒收
  （給預設值會把 look-ahead bug 變成靜默 bug）。FRED key 只在 query string，
  錯誤訊息／transport 例外一律 redact。
- 驗證：1116 pytest passed、tsc --noEmit 乾淨。
- 規格見 [provider execution plan](../superpowers/plans/2026-11-27-gabfin-provider-execution-plan.md)。

## 2026-11-27 — S04/04e 核心工作台整合已審查、修正並提交

- 04e 已提交 `73cd12cb`（base `7b22e6f5`）。交付 receive→state→consumer→render
  四層 trace、鍵盤焦點還原、導航／首屏量測。
- 聚焦獨立 review（Standards＋Spec 雙軸）發現 **3 個阻塞缺陷**，全部修正並重新驗證：
  trace 永久遺失（RAF 被 cleanup 取消但 event id 已佔位）、`event_id` 不可靠作 dedup key
  （真實 provider 決定性推導，跨 epoch 可重現）、量測數字與 artifact 不符且環境歸屬錯誤。
- 修正後：**925 core／33 Playwright passed**，typecheck／build exit 0。
  API p95 141.6ms、桌面快取切頁 p95 29.6ms、首屏 p95 122.5ms。
  量測分兩個環境且已在 artifact 標明：API／trace 量自合成 TLS fixture；
  首屏／切頁量自 **Vite dev server**（非 TLS fixture、非 production bundle）。
- 報告：[s04-core-acceptance](../audit/s04-core-acceptance.md)。

## 2026-11-27 — Downloads worktree 環境重建

- 原 `.venv` 的 `pyvenv.cfg` 與 editable `.pth` 均指向 Desktop checkout；已刪除並在
  Downloads 內重建。步驟、驗證與環境事實：[環境搭建記錄](../audit/local-env-setup-2026-11-27.md)。

## 2026-11-26 — S04/04d 增量圖表完成

- 本機提交 f361264；1m K 線／量、增量修訂／reset、縮放／手機及清理已交付。
- 28 項 Playwright／bar patch 通過；初次 expiry 失敗與修正、聚焦審查、截圖及驗證界線：
  [04d report](../audit/s04-04d-chart-2026-11-26.md)。下一步 04e 整合／tracing。

## 2026-11-26 — S04/04c 安全行情切片完成

- 本機提交 a434de2；HTTPS 配對、snapshot／WS bridge、runtime validation、
  到期／重連／清理已交付。925 core／17 browser 通過、一次聚焦獨立審查、
  真實只讀 smoke、完整回歸的一項既有失敗與截圖：
  [04c report](../audit/s04-04c-market-2026-11-26.md)。下一步 04d 圖表。

## 2026-11-26 — S04/04b React 示範工作台完成

- 本機提交 898cc04；首頁／詳情、手機導航、示範資料與型別生成已交付。
- 7 e2e、typecheck／build、production 截圖與保留驗證見 [04b report](../audit/s04-04b-desk-2026-11-26.md)。

## 2026-11-26 — S03 工程收尾完成，G2 未放行

- 已提交 1802198；freshness／bar／recovery／stream／lifecycle 交付。
- 最終回歸、雙軸獨立複查、乾淨 wheel 及真實 consumer 鏈路：
  [S03 report](../audit/s03-completion-2026-11-26.md)。
- 實際是舊收市價，權益 gate 仍 open；沒有交易／部署。

## 2026-11-25 — S03/03c–03g 供應商診斷切片

- 03c 個股 quote／日 K `2607a81`；03d 期權鏈 `953b5d2`；03e 歷史分鐘 K `87e2953`；
  03f symbol／訂閱計劃 `a8d23d5`；03g callback／有界 cache `3073cf3`。
- 各自報告在 [audit](../audit) 目錄（s03-03c…s03-03g）。共同邊界：
  只取得上一交易日觀察，未證明即時；配額回復、無 worker 殘留；未交易。

## 2026-11-25 — Matt Pocock 工作流技能及專案路由

- 安裝與驗證由 [report](../audit/skills-workflow-2026-11-25.md) 記錄。
- 工作流入口、tracker 及領域文件已接入。
