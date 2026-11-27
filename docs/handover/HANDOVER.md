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

stage: `ready-for-ui`

### Base

- 後端 commit：`cd59fca1`（分析平面的生產接線 + e2e 覆蓋）
- 前一階段：`5c49495a`（WU-7 provider routing + WU-9 analysis planes）、
  `9e7d109b`（交接卡）
- 分支：`codex/s01-source-baseline`
- Checkout：`C:/Users/001/Downloads/GabFin-ai-trade/.worktrees/gabfin-s01`

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
  不是接線缺陷。Carbon 的 UI 必須把 404 呈現為「尚無可計算的歷史序列」。
- **Futu BBO 暫緩**：使用者於 2026-11-27 決定暫不做 bid/ask。SDK 原始碼證實 QUOTE 推送本身不含 bid/ask（`parse_pb_BasicQot` 只回傳 `last_price` 等），`get_market_snapshot` 才有 `ask_price/bid_price`，擺盤則是另一種 frame。前端**不可**假造 bid/ask 顯示。
- **期權 OPRA 缺權限**：Futu 免費層無 OPRA 期權 LV1 權限，期權報價應顯示為「無即時期權權限」，不可顯示假價。
- **indicative 報價**：Alpaca indicative 報價必須標示為不可作為進場依據。
- **G2 仍未放行**：缺 channel／權益證據，維持拒絕新入場。前端不得顯示「可下單」。
- **指標口徑不可混用**：`venue_coverage`（來源口徑）與 `source_coverage`（指標口徑）不同時，量能指標不可並列比較。
- **本輪已知缺陷（既有，非本單位引入）**：`tests/api/test_desk_zone.py::test_zone_sanitize_fail_closed_and_color_only_edits`、
  `tests/api/test_desk_zone_evidence.py` 兩個用例、`tests/trading/engine/test_worker_integration.py::test_shadow_mode_buy_signal_to_fill`
  在本輪之前即失敗（Windows console 編碼與既有邏輯），已用 `git stash` 確認與本輪變更無關。

### Backlog

前端登報的後端需求。格式：需求 → 為何需要 → 影響。

- （無）


### Next

- 後端：等待 Carbon 完成 WU-9-ui，之後做 diff 審查、整合、跑 pytest 與 Playwright、commit。
- 前端（Carbon）：`stage: ready-for-ui` 且 `ui-tasks/WU-9-ui.md` 存在，**可以開始**。

## UI 變更清單

<!-- Carbon 完成後填入；格式：檔案 → 改動摘要 -->

- （無）
