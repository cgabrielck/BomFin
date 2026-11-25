# GabFin 開發技能流程

## 適用範圍

使用者於 2026-11-25 要求採用 Matt Pocock 的模組化工作流。
本文件供規劃、實作及審查單位使用；安裝來源與驗證由
[安裝報告](../audit/skills-workflow-2026-11-25.md) 擁有。

以此流程串接 GabFin 工作；現有 Superpowers 技能保留作相應工具，
同一單位只採一條主流程。技能的通用範本按本專案指示適配。
工作目錄、分支及下一單位以 [execution](../memory/execution.md) 為準。
本文件的相對文件連結均以所在文件為基準，不以 shell cwd 為基準。

使用者已明確要求採用此流程。進入各分支時，直接讀取
`C:/Users/001/.agents/skills/<skill-name>/SKILL.md` 及其必要參考再執行；
不要只靠技能名稱的隱式匹配。`grill-me`、`to-spec`、`to-tickets`、
`implement` 等需明確呼叫的技能也按此授權載入，保留上游檔案原樣。

## 從需求到實作

1. **grill-me／grilling**：只釐清新的需求、重要取捨或真正 blocker。
   先查既有文件及程式可回答的內容；沿用已確認的產品需求。
2. **to-spec**：把已達共識整理成可驗收規格；沿用既有規格即可滿足的
   單位只引用相應段落。規格以行為、契約與測試決策描述，避免程式碼及
   具體實作路徑。prototype 只作外部參考連結，規格正文不內嵌程式碼。
   沿用已批准的公開測試介面；新增或改變驗收語意時才集中確認。
3. **to-tickets**：按可驗證的使用功能切片，列出實際 blockers。
   一票涵蓋該功能需要的資料、邏輯、API、UI 與測試；行情診斷等 CLI
   功能可直接演示，不為湊層數增加 UI。新拆票先呈現粒度及依賴供確認；
   已授權的既有單位按原範圍執行，逐步補票，無需重拆整份總計劃。
   發佈及狀態規則見 [tracker](issue-tracker.md)。
4. **implement + tdd**：開始時記下 unit base SHA、分支、既有修改及
   驗收來源。先用公開介面的行為測試得到預期 RED，再以最少實作得到
   GREEN；每次完成一個行為循環。既有保護性測試沿用，避免測私有細節
   或複製實作的測試。只改文件／安裝技能等低影響工作採適合的檔案驗證。
5. 開發中執行相關測試及適用的型別檢查；單位結束執行適合該改動的
   完整測試。確認失敗原因、修正及重新驗證，再進入 review。

## 獨立 code-review

維持一個實作 Agent；使用者此次要求的獨立審查，授權完成單位後啟動
兩個唯讀 reviewer。兩者均使用全新上下文（`fork_turns="none"`），
並行派送；避免傳入實作對話及實作者的自評結論。兩者均提供審查範圍、
固定基準、完整可重現 diff 命令及 commit 清單（未提交部分明示無 commit），
並給相關文件入口。

- **Standards**：提供適用 AGENTS、現有 coding/contribution 規範的完整
  來源清單，並將 `code-review` 的完整 Fowler smell baseline 原文放進
  reviewer prompt。特別檢查 Shotgun Surgery、Feature Envy、Data Clumps；
  smell 是判斷建議，與明文規範違反分開。專案明文規範優先於 baseline，
  略過已由 tooling 完整檢查的項目。
- **Spec**：讀該單位的 ticket、規格及驗收條件，找缺漏、錯誤或超範圍行為。

兩軸獨立回報與處理。實作者核對 findings 後修正真實問題並重跑相關驗證；
涉及審查範圍的修正交回相應 reviewer 複查。記錄實際審查範圍及剩餘風險。

固定基準使用開始時記錄的 SHA，先確認可解析及 diff 非空。
已提交範圍按技能使用 `git diff <base>...HEAD`。提交前先盤點原有 staged、
unstaged 及 untracked；只有索引原先為空、且所選檔案沒有混合無關改動時，
才 stage 本單位檔案並用 `git diff --cached <base>`。核對 diff 內容及檔案
清單完全符合本單位，包含新檔；審查與提交必須使用同一份已確認範圍。
若索引原先非空或有同檔混合變更，改用獨立 checkout 只載入本單位
修改再審查／提交，保留原 checkout 的工作與索引狀態，checkpoint 記錄
真正提交位置。這是本專案對技能預設 HEAD 比較的適配。

外層非 Git 文件工作提供具名檔案、可取得的修改前後快照／可讀 diff，
雜湊只鎖定輸入版本。若未保存前態，明示只審查列明的現態及已知修改範圍；
不能聲稱驗證了完整差異或原有內容保留。文件審查不需要虛構 commit 清單，
也不能冒稱程式碼 commit-range review。

完成審查及驗證才提交本單位程式變更、更新 checkpoint 與受影響記憶。
自審、測試通過、獨立審查三者分別記錄；過往自審不改寫成獨立審查。
若 reviewer 工具不可用，明示未執行的關卡，保留待審狀態。

## 按需使用的技能

- **improve-codebase-architecture**：用於要求的架構檢查或已觀察到的
  維護問題；先展示局部候選、取捨及驗證方式，由使用者選定改動範圍。
  `codebase-design`／`domain-modeling` 提供設計與術語支援。
- **writing-for-agents**：寫 AGENTS、技能或供 Agent 讀取的文件時使用。
  這是圖片中 `writing-great-skills` 的官方現名；文件用明確觸發條件指向
  單一事實來源，避免每次載入整套技能。
- 領域權威、決策儲存與舊 ADR 處理由 [domain](domain.md) 統一規定。
