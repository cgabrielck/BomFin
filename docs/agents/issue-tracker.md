# Issue tracker：本地 Markdown

## 位置及現有工作

規劃與票據儲存在外層 `C:/Users/001/Desktop/GabFin-ai-trade`；
應用程式 checkout 透過其 AGENTS 指向外層指示。
技能提到「publish」時寫本地檔案，無需建立 GitHub issue 或 label。

- 現有總規劃保留於 [upgrade plan](../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md)。
- 當前工作入口為 [tasks](../memory/tasks.md) 與 [execution](../memory/execution.md)。
- 新功能票據：`docs/tickets/<feature-slug>/issues/<NN>-<slug>.md`，一票一檔。
- 新功能規格：`docs/tickets/<feature-slug>/spec.md`；已有規格則直接連結，
  不複製同一份需求。本專案用持久的 `docs/tickets/` 取代技能預設 `.scratch/`。
- 此次只配置路由；未搬動既有計劃，未建立新的產品票據。
- `to-spec` 的「套用 ready-for-agent label」在本地映射為新 spec 的
  `Status: ready-for-agent`；票據仍各自維護狀態，實作依票據驗收及依賴執行。

## 票據內容及狀態

每張票記錄功能交付、規格連結、可核對的驗收條件、`Blocked by:`，
以及 `Status:`。編號在各 feature 內由 01 起，blocker 優先。
取得票據時讀其全文及連結的必要段落；有歧義才詢問。

`Status:` 採 `draft` → `ready-for-agent` → `in-progress` → `in-review` → `done`。
無法繼續時標 `blocked` 並記錄原因及解除條件；恢復後回到適當狀態。
新範圍或拆票獲確認、且前置票完成，才可進入可執行狀態。
`ready-for-agent` 是本地狀態字串，無需外部 label。
完成條件包含驗收證據、適用驗證及工作流要求的審查；未執行的關卡要列明。

討論附在票據 `## Comments`；驗證輸出放 audit artifact，票據只保留結論與連結。
更新票據時同步當前 checkpoint；每項事實保留一個主要來源，其餘連結引用。
目前沒有採用 `triage` 技能，無需另建 triage label 設定或增加外部流程。
