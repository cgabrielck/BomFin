# Pending tasks

## T019 — S04 新前端殼與圖表（04d 已完成）

- S03 工程已完成；最新提交／驗證由 [execution](execution.md) 與
  [完成報告](../audit/s03-completion-2026-11-26.md) 擁有。
- 執行方式：[精簡工作流](../agents/workflow.md)，優先規劃／小步實作，按風險審查。
- 使用者已同意混合布局及跨 Section 漸進交付；
  [實施計劃](../superpowers/plans/2026-11-26-gabfin-frontend-delivery-plan.md) 擁有檔案、接口、依賴及驗收。
- 04a 線框與 04b 正式 React demo 已交付；[04b 報告](../audit/s04-04b-desk-2026-11-26.md)
  擁有實際驗證／截圖。使用者 remote 不能親試，已授權沿目前方向繼續。
- 04c 安全行情切片已驗證／獨立審查；[04c 報告](../audit/s04-04c-market-2026-11-26.md) 擁有結果與界線。
- 04d 增量圖表已交付；[04d 報告](../audit/s04-04d-chart-2026-11-26.md) 擁有驗證／截圖及一般斷線 expiry 修正。
- 下一步 04e 核心工作台整合／tracing；不等待本機網站視覺確認。
  04e 已於 2026-11-27 完成實作與實測（未提交、未審查）；
  驗收報告見 [s04-core-acceptance](../audit/s04-core-acceptance.md)。
- 真實機會池／研究隨 S05–06，完整聊天／帳戶／期權／PWA 隨 S10 接入；
  不將整個前端集中在 S04，也不為每節另建一套 app。
- [UI 參考](../superpowers/specs/2026-11-26-gabfin-ui-references.md) 初篩已完成，不重複搜尋；
  示範資料必須標明，G2 不阻塞 UI 建置。auth／行情已接通並驗證；長駐入口／遠端部署未交付。

## T021 — 前後端交接的 WU-9-ui 前端單位

- 任務卡：[docs/handover/ui-tasks/WU-9-ui.md](../handover/ui-tasks/WU-9-ui.md)
  （在 app worktree 內）。狀態：`ready-for-ui`，base commit `cd59fca1`。
- 範圍：圖表指標疊圖、宏觀面板、來源能力標示，全部在 `apps/desk-web/src/**`。
- 前端不可改 `services/**`、`schemas/**`、`generated.ts`；需要新欄位就登記在
  HANDOVER 的 Backlog。
- 前端完成後後端做 diff 審查、整合、跑 pytest 與 Playwright（`npm.cmd run build`
  必須在 Playwright 之前）、commit。
- Part 2 剩餘 WU-4 Futu bid/ask 與 WU-5 order book：**BBO 暫緩**（使用者 2026-11-27 決定）。
- 後端已備妥：三個端點在生產路徑可用，e2e fixture 提供確定性分析平面，
  `tests/e2e/analysis.spec.ts` 6 項斷言全過。任務卡含錯誤形狀對照表與已知限制。

## T020 — G2 行情權益／provider channel 證據

- [G2 票](../tickets/s03-stream/issues/03-feed-evidence-g2.md) 未完成；實際證據、
  解除路線與成本候選由 [feed register](../audit/feed-entitlements.md) 擁有。
- 不因 closed-market 舊價、quote login 或 quota 放行自動入場。
- 舊 Windows 間歇性問題及新發現的 shadow 假期 fixture 問題由 [issues](issues.md) 分別追蹤。
- 保留原檔及證據；不購買、不交易、不 push/deploy，不隨意重啟 OpenD。
