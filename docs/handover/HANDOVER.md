# GabFin 前後端交接

同一個 worktree、同一個分支，由不同的模型輪流工作。本檔是唯一的交接點。

## 分工邊界

| 角色 | 模型 | 可動範圍 |
|---|---|---|
| 後端 | GPT-6.1 Sol High（本機） | `services/**`、`schemas/gabfin-1.0.json`、`scripts/generate-web-contracts.mjs`、`tests/**`、`docs/**` |
| 前端 | Gemini 4 Carbon（使用者手動切換） | `apps/desk-web/src/**`（`shared/contracts/generated.ts` 唯讀） |

### 前端不可修改

- `services/**` 全部 Python
- `schemas/gabfin-1.0.json`
- `apps/desk-web/src/shared/contracts/generated.ts` — 只能由 `npm run contracts` 產生
- `scripts/generate-web-contracts.mjs`
- `tests/e2e/**` 的既有斷言（可以新增檔案，不可改既有斷言）

前端若需要新的後端欄位，**不要自行加**。在下方 Backlog 段落登記一條，交回後端補合約。

## 交接循環

1. 後端完成一個單位：合約 + 實作 + 測試 + 重建 schema + commit。
2. 後端寫 `ui-tasks/WU-<n>-ui.md` 任務卡，並把本檔 `stage` 改成 `ready-for-ui`，填上 base SHA。
3. 使用者切到 Gemini 4 Carbon。Carbon 只讀：本檔、該任務卡、`apps/desk-web/src/shared/contracts/generated.ts`。
4. Carbon 完成 UI 後，把本檔 `stage` 改成 `ui-done`，在「UI 變更清單」填入實際改動的檔案，並跑 `npm run typecheck`。
5. 使用者切回後端。後端做 diff 審查、整合、跑 pytest 與 Playwright、commit。

一次只有一個模型工作。前端單位進行中時，後端不要動 `apps/desk-web/src/**`。

## 固定段落（每次交接必填）

### Stage

<!-- 每次交接更新這一行為主 -->

stage: `ui-done`

### Base

- 前端 commit：`faea2ba4`（指標疊圖、宏觀面板、來源能力標示）、
  `1ccce0a0`（瀏覽器 e2e 覆蓋）
- 後端 commit：`71928c13`（tape 多月寫入不再遺失先前的月份）、
  `a9aecd2d`（交接卡）
- 再前一階段：`cd59fca1`（分析平面的生產接線 + e2e 覆蓋）、
  `5c49495a`（WU-7 provider routing + WU-9 analysis planes）、
  `9e7d109b`（交接卡）
- 分支：`codex/s01-source-baseline`
- Checkout：`C:/Users/001/Downloads/GabFin-ai-trade`

### Contract delta

本次交接新增或變更的合約。格式：`合約名稱` → 欄位變化 → 生成的 TS 型別位置。

- `IndicatorResponse` → 新增（回應包裝，含 `series` 與 `statuses`）→ `generated.ts` 的 `IndicatorResponse`
- `MacroResponse` → 新增（回應包裝，含 `points`）→ `generated.ts` 的 `MacroResponse`
- `CapabilitiesResponse` → 新增（回應包裝，含 `sources`）→ `generated.ts` 的 `CapabilitiesResponse`
- `IndicatorStatus` → 新增（WU-2 已有，本輪開始提供給前端）→ `generated.ts` 的 `IndicatorStatus`
- `MacroPoint` → 新增（WU-3 已有）→ `generated.ts` 的 `MacroPoint`
- `FeedCapabilities` → 新增能力欄位：`venue_coverage`、`realtime`、`delay_minutes`、`tradable_for_entry`、`depth_levels`、`fee_class`、`unavailable_reason` → `generated.ts` 的 `FeedCapabilities`

**本輪補充沒有改動任何合約**，因此 `schemas/gabfin-1.0.json` 與
`generated.ts` 都沒有變動，Carbon 不需要重新產生契約。

### UI task

- `ui-tasks/WU-9-ui.md`：指標疊圖、宏觀面板、來源能力標示。Carbon 可開始。
- 該任務卡已補上：錯誤形狀對照表、宏觀序列 id 白名單、`Origin` 標頭要求、
  已知後端限制。前端實作前請讀。

### Forbidden edits

見上方「前端不可修改」。

### Open risks

- **生產端點的 tape 尚未寫入**：`/v1/indicators` 已在生產路徑接上 tape，但 tape 內
  尚無實際寫入的序列，因此真實環境會回 **404**（不是空序列）。這是資料狀態，
  不是接線缺陷。前端已把 404 呈現為「此標的尚無可計算的歷史序列」並保留既有 K 線。
- **分析端點目前瀏覽器不可達**：見 Backlog 第一條。前端已防守，不會誤登出。
- **Futu BBO 暫緩**：使用者於 2026-11-27 決定暫不做 bid/ask。SDK 原始碼證實 QUOTE 推送本身不含 bid/ask（`parse_pb_BasicQot` 只回傳 `last_price` 等），`get_market_snapshot` 才有 `ask_price/bid_price`，擺盤則是另一種 frame。前端**不可**假造 bid/ask 顯示。
- **期權 OPRA 缺權限**：Futu 免費層無 OPRA 期權 LV1 權限，期權報價應顯示為「無即時期權權限」，不可顯示假價。前端已在 `unavailable_reason` 非空時顯示原因原文。
- **indicative 報價**：Alpaca indicative 報價必須標示為不可作為進場依據。前端在 `tradable_for_entry === false` 時於來源名稱旁顯示明確警示。
- **G2 仍未放行**：缺 channel／權益證據，維持拒絕新入場。前端不得顯示「可下單」。
- **指標口徑不可混用**：`venue_coverage`（來源口徑）與 `source_coverage`（指標口徑）不同時，量能指標不可並列比較。前端在能力面板底部保留此提示。
- **本輪已知缺陷（既有，非本單位引入）**：`tests/api/test_desk_zone.py::test_zone_sanitize_fail_closed_and_color_only_edits`、
  `tests/api/test_desk_zone_evidence.py` 兩個用例、`tests/trading/engine/test_worker_integration.py::test_shadow_mode_buy_signal_to_fill`
  在本輪之前即失敗（Windows console 編碼與既有邏輯），已用 `git stash` 確認與本輪變更無關。本輪前端也重跑了 `tests/api`，結果相同（244 passed, 3 failed）。

### Backlog

前端登報的後端需求。格式：需求 → 為何需要 → 影響。

- **分析端點無法從瀏覽器呼叫（阻塞 WU-9-ui 的實機驗收）**
  → 為何需要：`services/gabfin/api/auth.py` 的 `validate_request` 要求
    `origin == allowed_origin` 精確相等。瀏覽器的同源 GET **不帶** `Origin`
    標頭，而 `Origin` 是 script 不可設定的 forbidden header，所以
    `fetch('/v1/indicators')` 永遠拿不到 `Origin`，必定回 **401**。
    已用 e2e 量測確認：瀏覽器內 `fetch` → 401；同一 URL 由
    `page.request.get` 帶 `Origin` → 200。
  → 影響：後端既有的 `analysis.spec.ts`（用 `page.request.get` + 手動
    `Origin` 標頭）全過，但**瀏覽器實機**呼叫不通。三個分析端點
    （`/v1/indicators`、`/v1/macro`、`/v1/capabilities`）在真實前端
    目前一律 401，UI 只能顯示「分析請求被拒絕」。
  → 前端已做的防守：把 401 視為「請求被拒絕」而非「登入失效」，
    **不會**把整個工作台登出，行情與 K 線照常運作。已用
    `tests/e2e/analysis-ui.spec.ts` 釘住這個行為。
  → 建議修法（後端擇一）：分析端點改用與 `/market/snapshot` 相同
    的守衛方式——`origin` 為空時以 `allowed_origin` 補足，只在
    `origin` **有值且不等於** `allowed_origin` 時才拒絕；或在
    `ExactTlsOrigin` 中為 `/v1/` 補上 `Origin` 標頭。
  → 註：`services/gabfin/api/app.py` 的 `ExactTlsOrigin` 已確認會
    轉發 `Host`／`scheme` 檢查，問題只在 `Origin` 標頭的產生。

### Next

- 後端：審查本輪前端 diff（見「UI 變更清單」），處理 Backlog 第一條，
  整合、跑 pytest 與 Playwright、commit。
- 前端（Carbon）：`stage: ui-done`，本單位已完成，無待辦。

## UI 變更清單

<!-- Carbon 完成後填入；格式：檔案 → 改動摘要 -->

### 新增

- `apps/desk-web/src/shared/transport/analysis.ts` → 三個分析端點的傳輸層。
  負責 `credentials: 'same-origin'`、`cache: 'no-store'`，並把 400／401／403／
  404／503 分成 `AnalysisInvalid`／`AnalysisRefused`／`AnalysisUnavailable`／
  `AnalysisMissing` 四種可分辨的錯誤。元件不得自行 `fetch`。
- `apps/desk-web/src/features/analysis/useAnalysis.ts` → 共用 hook。把
  分析請求的狀態分成 idle／loading／ready／missing／unavailable／invalid／
  refused 七種，不把它們合併成一個「錯誤」。key 改變時發出中的請求
  會被放棄，不會把上一個問題的答案當成這一個的答案。
- `apps/desk-web/src/features/chart/indicator-lines.ts` → 指標線的模型。
  把後端的 `series` 轉成可畫的線：字串值原樣保留（`raw`）供顯示，
  解析後的數值（`value`）供繪圖。RSI 與 MACD 各自有 pane，
  MACD 柱狀圖以 bar 畫而非線。
- `apps/desk-web/src/features/chart/IndicatorOverlay.tsx` → 指標疊圖元件。
  切換 SMA20／RSI14／MACD／EMA20／BOLL／VWAP／ATR14；`statuses` 裡的
  指標不畫線，改顯示「RSI 需 14 根，現有 5 根」；顯示 `source_coverage`
  並與 K 線口徑並排；404 顯示「此標的尚無可計算的歷史序列」並保留 K 線；
  503 顯示「指標服務暫時不可用」且不顯示舊值。
- `apps/desk-web/src/features/macro/MacroPanel.tsx` → 宏觀面板。每一列同時
  顯示 `observation_date` 與 `release_date`；`value` 為後端原字串並顯示
  `units`；`as_of` 由使用者指定並交給後端過濾，前端不自行放寬。
- `apps/desk-web/src/features/feed/FeedCapabilityBadges.tsx` → 來源能力標示。
  顯示 `venue_coverage`／`realtime` 或 `delay_minutes`／`fee_class`；
  `tradable_for_entry === false` 時顯示「不可作為入場依據」警示；
  `unavailable_reason` 非空時顯示原因原文。
- `tests/e2e/analysis-ui.spec.ts` → 10 項瀏覽器行為測試。
- `tests/e2e/analysis-visual.spec.ts` → 產生三個面板的截圖供人工檢視。

### 修改

- `apps/desk-web/src/features/chart/chart-port.ts` → 新增 `applyIndicators()`。
  指標線以 `LineSeries` 畫在對應 pane；MACD 柱狀圖以 `HistogramSeries` 畫。
  切換時先移除舊的線，避免同時顯示兩個指標。RSI pane 鎖定 0–100。
  空的 RSI／MACD pane 以 `addPane(true)` 保留，避免切換時 pane 編號位移。
- `apps/desk-web/src/features/chart/ChartCanvas.tsx` → 接受 `indicators` prop
  並交給 chart port。指標繪圖失敗不再取代整張圖表，改為獨立的提示。
- `apps/desk-web/src/features/chart/ChartPanel.tsx` → 持有指標線狀態並傳給
  `ChartCanvas`，同時掛上 `IndicatorOverlay`。
- `apps/desk-web/src/features/market/StockDetail.tsx` → 掛上 `MacroPanel`
  與 `FeedCapabilityBadges`。
- `apps/desk-web/src/app/styles.css` → 三個面板與指標圖例的樣式。
- `playwright.config.ts` → `testMatch` 加入兩個新的 spec 檔。

### 驗證

- `npm run typecheck`（工作區根目錄，含 `npm run contracts` 重新產生契約）
  → **通過**。契約重生後 `generated.ts` 無任何 diff。
- `npx playwright test` → **50 passed**（既有 39 + 新增 10 + 視覺 1）。
  第一次全跑時 `secure-market.spec.ts` 有一項失敗：新增的三個
  `role="alert"` 讓既有的 `getByRole('alert')` strict-mode 命中多個元素。
  已把「請求被拒絕」改成非 alert 的說明文字（拒絕是常態而非警報），
  重跑全過。
- `pytest tests/api -q` → 244 passed, 3 failed。三個失敗是本輪之前即存在的
  已知缺陷，與本單位無關。
- `pytest tests/gabfin -q` → **985 passed**（含 `tape.py` 的多月份寫入測試）。

### 沒有動到

- `apps/desk-web/src/shared/contracts/generated.ts`（唯讀，本輪無合約變更）
- `services/**`、`schemas/**`、`scripts/generate-web-contracts.mjs`
- `tests/e2e/**` 的既有斷言（一個字都沒改）
