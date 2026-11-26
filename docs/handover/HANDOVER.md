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

stage: `backend-ready`

### Base

- 後端 commit：`1cbee09e`（WU-3 FRED 宏觀）
- 分支：`codex/s01-source-baseline`
- Checkout：`C:/Users/001/Downloads/GabFin-ai-trade/.worktrees/gabfin-s01`

### Contract delta

本次交接新增或變更的合約。格式：`合約名稱` → 欄位變化 → 生成的 TS 型別位置。

- `IndicatorSeries` / `IndicatorStatus` → 新增（WU-2 已有，本輪開始提供給前端）→ `generated.ts` 的 `IndicatorSeries`、`IndicatorStatus`
- `MacroSnapshot` / `MacroPoint` → 新增（WU-3 已有）→ `generated.ts` 的 `MacroSnapshot`、`MacroPoint`
- `FeedCapabilities` → 新增能力欄位（見下）→ `generated.ts` 的 `FeedCapabilities`

### UI task

- 目前無前端單位。下一個是 `ui-tasks/WU-9-ui.md`（指標疊圖與宏觀面板），待後端 WU-9 就緒。

### Forbidden edits

見上方「前端不可修改」。

### Open risks

- **Futu BBO 暫緩**：使用者於 2026-11-27 決定暫不做 bid/ask。SDK 原始碼證實 QUOTE 推送本身不含 bid/ask（`parse_pb_BasicQot` 只回傳 `last_price` 等），`get_market_snapshot` 才有 `ask_price/bid_price`，擺盤則是另一種 frame。前端**不可**假造 bid/ask 顯示。
- **期權 OPRA 缺權限**：Futu 免費層無 OPRA 期權 LV1 權限，期權報價應顯示為「無即時期權權限」，不可顯示假價。
- **indicative 報價**：Alpaca indicative 報價必須標示為不可作為進場依據。
- **G2 仍未放行**：缺 channel／權益證據，維持拒絕新入場。前端不得顯示「可下單」。

### Backlog

前端登報的後端需求。格式：需求 → 為何需要 → 影響。

- （無）

### Next

- 後端：實作 WU-9 合約擴充與 `/v1/indicators`、`/v1/macro` 端點，重建 schema 後 commit，然後寫 `ui-tasks/WU-9-ui.md`。
- 前端（Carbon）：等待 `stage: ready-for-ui` 且 `ui-tasks/WU-9-ui.md` 存在後再開始。

## UI 變更清單

<!-- Carbon 完成後填入；格式：檔案 → 改動摘要 -->

- （無）
