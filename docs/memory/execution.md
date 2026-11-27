# Execution checkpoint

- Section / unit: **Part 2 即時主線進行中**。WU-7（provider routing）與
  WU-9（分析平面 + 三個端點 + 合約擴充）已提交並交接前端。分析平面的生產接線
  已於 `cd59fca1` 補上。G2 仍未放行。
- Checkout: `C:/Users/001/Downloads/GabFin-ai-trade`（repo 根目錄）。
  2026-11-27 起使用者指定只改 Downloads 內；舊 Desktop checkout 不再作工作位置。
  同日起原始碼由 `.worktrees/gabfin-s01` 提升至 repo 根目錄，路徑引用已改為根層相對路徑。
- Branch: `codex/s01-source-baseline`（GitHub 對應 `cgabrielck/BomFin` 的 `gabriel-dev`）。
- Current HEAD: `8cd7449`（`Rebase the repository on the current architecture`）。
  2026-11-27 原始碼由 `.worktrees/gabfin-s01` 提升至 repo 根目錄；legacy
  `backend/`、`web/` 舊前端、30 個 legacy 文件與 139 個 legacy 測試已移除，
  歷史保留在 BomFin 的 `legacy-full` 分支。根層重建後驗證：
  **1099 pytest passed**（tests/gabfin + tests/providers）、`npm run typecheck`
  與 `npm run build` 乾淨、**50 Playwright passed**。
  新增依賴宣告：`pyarrow`（tape）與 `jsonschema`（schema artifact 測試）。
- 前端交接狀態：`docs/handover/HANDOVER.md` 的 `stage: ready-for-ui`，
  任務卡 `docs/handover/ui-tasks/WU-9-ui.md`。Gemini 4 Carbon 可開始。
  **後端此時不可動 `apps/desk-web/src/**`。**
- 驗證：**2388 pytest passed / 4 skipped**（另有 4 個本輪之前即失敗的既有失敗，
  見 [issues](issues.md)）、**39 Playwright passed**、tsc --noEmit 乾淨。
- 詳細見 [progress](progress.md) 與
  [供應商執行計劃](../superpowers/plans/2026-11-27-gabfin-provider-execution-plan.md)。
- WU-9 修正三個真實缺陷：
  1. `_timeframe` 用 `rstrip` 去掉數字、把單位留在 `unit`，導致 `1day` 完全無法解析。
  2. `_date` 在 macro 的 `try` 內被呼叫，日期格式錯誤被吞成 503 而非 400。
  3. `authorize`／`require_scope` 丟出的 `PermissionError` 未被捕捉，會變成 500。
- `cd59fca1` 修正第四個更根本的缺口：三個分析端點沒有任何生產路徑掛載
  （`analysis=None` 預設），且 `IndicatorPlane` 沒有任何 `BarSource` 實作。
  已補 `analysis/sources.py`、`analysis/runtime.py`、`tape.read_rows`，
  並讓指標平面在 venue 未知時拒絕計算。
- 前端交接機制（`docs/handover/`）與多模型分工邊界見 [decisions](decisions.md) D011。
- 04e 交付、量測與界線：[s04-core-acceptance](../audit/s04-core-acceptance.md)；
  evidence 在 [artifacts/s04-04e](../audit/artifacts/s04-04e)。
- 本機實測（04e）：**925 core／33 Playwright passed**。量測分兩個環境：
  API 與 quote trace 量自合成 TLS fixture；首屏與快取切頁量自 Vite dev server。
- 使用者已授權並上傳 source 至 `cgabrielck/BomFin` 的 `gabfin-s04d` 分支；原 main 保留。
- Freshness、trade bars、coordinator/recovery/replay、managed lifecycle、
  authenticated loopback stream 及 quote-only host 已交付。
- [工程票](../tickets/s03-stream/issues/02-market-state-recovery.md) 已完成；
  [G2 票](../tickets/s03-stream/issues/03-feed-evidence-g2.md) 保持未完成。
- 04b／04c／04d 交付報告見 [audit](../audit) 目錄。
- Next exact action: **等待 Carbon 完成 WU-9-ui**，之後後端做 diff 審查、整合、
  跑 pytest 與 Playwright、commit。Part 2 剩餘 WU-4 Futu bid/ask、WU-5 order book
  （**BBO 暫緩**，使用者 2026-11-27 決定）。`npm.cmd run build` 必須在 Playwright 之前。
  長駐 operator 入口與遠端部署仍待交付。
- G2 可以另作有界驗證；缺 channel／權益證據及未批准政策維持拒絕新入場。
- 不購買、不啟動交易、不部署；不重啟既有 OpenD。
- 實作／審查路由：[workflow](../agents/workflow.md)。
