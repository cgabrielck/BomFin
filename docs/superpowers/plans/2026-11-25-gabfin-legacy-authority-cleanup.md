# GabFin Legacy Architecture Authority Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` task-by-task. 使用者已選單 Agent；必要時可 focused grilling，不重問執行模式。使用者已批准本計劃，兩任務已完成。

**Goal:** 移除舊 ADR 對新 GabFin 的約束，清理會誤導 Agent 的入口、引用及文件測試，然後回到已確認的新架構計劃。

**Architecture:** 唯一產品需求來源是 2026-11-25 的 system design；實作依既有 upgrade plan。舊 repo 的實作只作移植及測試參考。清理文件不改交易行為，也不把舊前端修復變成新架構的前置工作。

**Tech Stack:** 既有本地 Git checkout、Markdown／HTML、PowerShell、已建立的 Python venv／pytest。沒有新增 runtime framework。

**Spec:** [confirmed system design](../specs/2026-11-25-gabfin-system-design.md)，特別是 U02、U13、U14、U16、U18；[upgrade plan](2026-11-25-gabfin-upgrade-plan.md)。本次使用者再次要求移除／不遵循 ADR-003。

## Global Constraints

- 前端全面重寫；保留或替換舊模組由新需求、測試與整合成本決定。
- 架構不以舊 repo、ADR、框架為既定約束。
- 本機開發；沿用 `C:/Users/001/Desktop/GabFin-ai-trade/.worktrees/gabfin-s01`，不另開 clone、不要求 container／sandbox。
- 保留原設計、主計劃、audit evidence、`.venv` 及未追蹤的 `web/package-lock.json`；不覆蓋使用者修改。
- 不啟動交易、不改 runtime 風控、broker、策略、行情權限或聊天能力，不 push／部署。
- 單 Agent；文件任務不新增形式化單元測試。使用既有 regression 及明確文件檢查。
- 本機 canonical 文件在外層 workspace；checkout 內的相對指標須在本機解析成功。日後搬移／整合 checkout 必須同步更新指標，不能恢復舊 ADR 為權威。

## Review Focus

1. 下個 Agent 只讀 checkout 的 `AGENTS.md`，也必須找到新設計，而不是再次接到「ADR-003 MUST FOLLOW」；由 Task 1 驗證。
2. 刪除 ADR-005 會令現有文件測試讀不到檔；Task 2 只替換過時文件斷言，保留手機權限及不能越權下單的測試。
3. 只刪 ADR 檔但留下「Accepted／binding／強制」入口仍會誤導；Task 1 重設入口，Task 2 明確標記其他舊文件並修連結。
4. 原始 baseline、未提交 lockfile 或使用者工作不能因清理而遺失；每個 task 開始／結束核對 diff 與 lockfile hash。
5. 新架構重寫前端、初期使用 SQLite；舊 UI typecheck 與可選 Postgres skip 不應強迫修改新產品方向；Task 2 修正外層 handoff。

## File Structure and Scope

- 唯一檔案清單：[cleanup.files.json](2026-11-25-gabfin-legacy-authority-cleanup.files.json)。所有 repo 路徑均相對於上述 checkout；35 個 tracked files 是本次實際搜尋到的直接引用範圍。
- `replace_authority`：5 個真正入口；重寫權威說明，不假裝新系統已實作。
- `delete_legacy_adrs`：只刪以下 4 個實際存在的舊檔；不使用萬用字元刪檔：
  `docs/ADR-003-live-ai-trading-desk.md`、`docs/ADR-004-chart-engine.md`、
  `docs/ADR-005-mobile-desk-readonly.md`、`docs/ADR-006-futu-opend-desk-observe.md`。
- ADR-001／002 沒有獨立 tracked file；它們嵌在 `docs/ARCHITECTURE_DECISION.md`，重寫此索引時移除舊決策正文。
- `retire_or_relink_legacy_docs`：23 個舊文件／歷史頁。保留可供理解舊實作的內容，但加明確退役標示並修正指向刪除檔案的連結。
- `comments_only`：2 個 Python module 僅改說明，保留所有函數與 API response fields。
- `update_document_assertions`：1 個測試檔，只替換 ADR 文件存在／Draft 狀態的文件測試。
- Git history 保留原文；不改寫歷史、不建立另一份可被當成有效規範的 ADR archive。

### Task 1: Replace the active architecture authority

**Files:** Modify the exact 5 paths in manifest `replace_authority`。其他 tracked paths 此 task 不改。

**Interfaces:** Consumes the canonical spec／plan；produces a single current authority chain: current user instruction → canonical design → main upgrade plan。`docs/ARCHITECTURE_DECISION.md` 是兼容既有連結的短指標，不再是一套產品規則。

- [x] **Step 1: Capture the starting state.** 在 checkout 跑 `git status --porcelain=v1 --untracked-files=all`、`git rev-parse HEAD`；記錄 lockfile SHA-256。原始 baseline SHA 是 `42f96b3b8a39e40f2e4e579aa9e619814dc80e7b`；若已有新提交／新修改，先辨認並保留，不能 reset。
- [x] **Step 2: Confirm the obsolete instruction.** 跑 `rg -n 'MUST FOLLOW|Binding architecture:|Architecture authority is ADR-003|## Architecture Decision \(ADR-003\)' AGENTS.md README.md docs/LOCAL_CURSOR_HANDOFF.md`。目前應有命中，作為需要清理的證據。
- [x] **Step 3: Rewrite the two agent entry points.** `AGENTS.md` 與 `docs/LOCAL_CURSOR_HANDOFF.md` 改為短指引：先讀外層 AGENTS／memory checkpoint；明確排除所有舊 ADR 的產品約束；指向新 design／plan；只讀與當前單位有關的 source。刪去舊 quick-win／roadmap 待辦及「不准重寫」命令。
- [x] **Step 4: Replace the legacy decision index.** `docs/ARCHITECTURE_DECISION.md` 只保留 `SUPERSEDED` 狀態、新權威指標、舊 ADR 已退役及 Git history 可追溯說明。從此檔指向外層 spec／plan 的相對路徑是 `../../../docs/superpowers/specs/2026-11-25-gabfin-system-design.md` 與 `../../../docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md`。
- [x] **Step 5: Correct product descriptions.** README 的舊 Desk／Streamlit 描述標明「現有實作」，新產品方向指向 canonical design；`PRODUCT.md` 標明舊產品記錄已被新需求取代。不要把未實作的新前端寫成已完成。
- [x] **Step 6: Verify the authority.** 重跑 Step 2，Expected：零命中（rg exit 1 在此代表沒有舊指令）；逐一核對 5 檔的本機連結。`git diff --check` Expected：exit 0；lockfile hash 不變。
- [x] **Step 7: Commit only those paths locally.** `git add -- AGENTS.md README.md PRODUCT.md docs/ARCHITECTURE_DECISION.md docs/LOCAL_CURSOR_HANDOFF.md`；核對 staged diff 沒有混入使用者內容，再 commit `docs: replace legacy architecture authority`。不推送。

### Task 2: Remove old ADR files and repair references without changing runtime behavior

**Files:** Delete manifest `delete_legacy_adrs`；modify manifest `retire_or_relink_legacy_docs`、`comments_only`、`update_document_assertions`。外層更新 `docs/memory/{tasks,execution,decisions,progress}.md`，並在 baseline 追加 handoff 更正；保留原始測試結果。

**Interfaces:** Consumes Task 1 的新權威指標；produces：舊 ADR 檔不存在、本次刪檔造成的引用均已修復、舊文件不再指揮新產品、既有 runtime／權限行為不變。

- [x] **Step 1: Verify the deletion allowlist.** 用 `git ls-files 'docs/ADR-*.md'` 核對只有計劃列出的 4 個候選；如多出其他 ADR，保留它並先更新清單，不擴大成 wildcard 刪除。重查工作樹，保留 Task 1 之後的任何其他改動。
- [x] **Step 2: Remove exactly the 4 files.** 每個解析後的絕對路徑必須在已確認 checkout 的 `docs/` 下。使用單一 PowerShell 流程的 `Remove-Item -LiteralPath`，不遞迴、不清除 Git history。
- [x] **Step 3: Retire and repair the 23 legacy pages.** Markdown 頁首／HTML 可見頂欄加同一狀態：`LEGACY / SUPERSEDED — describes the previous implementation; not instructions for the new GabFin architecture.` 指向本目錄的 `ARCHITECTURE_DECISION.md`（依檔案位置調整相對連結）。所有指向已刪 ADR 的 Markdown／HTML 連結改到此索引；歷史敘述可留，但不可寫成新產品已批准規則。
- [x] **Step 4: Remove authority claims from module comments.** 修改 `backend/trading/intents/models.py` 與 `backend/api/mobile_desk.py` 的舊 ADR 說明，只註明 legacy implementation。保留 `adr_005` API 欄位及其目前值作舊 API 相容資料，不能把它解讀為新架構規則；不更改函數、下單路徑或權限。
- [x] **Step 5: Update the obsolete document assertion.** 在 `tests/api/test_mobile_desk_ro.py`，將 `ADR` 檔指標改為 `ARCHITECTURE_INDEX`；把 `test_serve_doc_is_private_mesh_and_adr_stays_draft` 改為 `test_serve_doc_is_private_mesh_and_legacy_architecture_retired`。保留 `tailscale serve`、`/m`、重新整理／加入主畫面文案、禁止公開入口及無 Capacitor 的既有斷言；將檔案存在／Draft 斷言換成 index 含 `SUPERSEDED` 及 `2026-11-25-gabfin-system-design.md`。其他手機權限、no-order、API 相容欄位測試保持不變。
- [x] **Step 6: Run existing affected regression with sanitized credentials.** 從外層跑 `& .\docs\audit\artifacts\s01-01b\run-pytest.ps1 -RunName pytest-adr-cleanup -TestPaths @('tests/api/test_mobile_desk_ro.py','tests/trading/test_desk_roles.py','tests/observe/test_futu_observe.py')`。Expected：exit 0，沒有新增 failure／error；skip 原因明列。新檔名不能覆蓋 `pytest-baseline.log`／XML。事先記錄 journal 是否存在；若此回歸新產生測試 journal，只搬移本次新產物保存證據，保留原有檔案。只改文件與斷言，不重裝依賴或修舊前端。
- [x] **Step 7: Verify the cleanup boundary.** 4 個 ADR 檔不存在；active authority 5 檔沒有舊 binding 命令；35-file 清單內本次新增／改寫的 Markdown／HTML 連結均解析成功，沒有連結再指向已刪檔案；`git diff --check` exit 0。逐項檢視兩個 Python module 的 diff 僅有說明變更，既有 API 欄位斷言仍保留，lockfile hash 不變。與本次無關的舊失效連結只記錄，不擴大清理。
- [x] **Step 8: Correct the outer handoff.** 將「必須先修舊 TypeScript 才能開始新架構」改為已撤回的排序；保留 B01–B04 實際發現與原日誌。新前端重寫時處理相關型別需求；初期 SQLite 不因可選 Postgres skip 而改方向。journal 隔離仍是已記錄問題；新測試／移植工作採暫存路徑，不把舊 journal 設計移植為新契約；本次限定回歸按 Step 6 保留副作用證據。
- [x] **Step 9: Record the next unit.** canonical plan 的下一個產品工作回到 S02／Task 2：新 `services/gabfin/contracts/` 與 storage／migrations。先細化當前小單位；不直接開始整個新前端、不啟動交易。記錄文件清理後的新 HEAD 與原始 baseline SHA，兩者不混用。
- [x] **Step 10: Commit only the verified cleanup paths.** 依 manifest 的此 task 清單逐路徑 stage，檢視 staged diff，commit `docs: retire legacy ADRs and repair references`。不 stage lockfile、外層文件或不屬本 task 的使用者變更；不 push。

## Self-review and Handoff

- Spec coverage：覆蓋 U18 的舊約束退役；保留 U02 的前端重寫、U13／U14 的能力邊界及 U16 的本機開發；不改其他已確認需求。
- Scope／types：純文件與一個文件斷言；唯一保留的舊 API metadata 明確是相容資料，不新增 runtime interface。
- Five review conditions 均由 Task 1／2 的具體檢查覆蓋；未把舊錯誤自動升格為新產品 gate。
- 狀態：已獲使用者批准並完成；[執行與驗證結果](../../audit/legacy-authority-cleanup-2026-11-25.md)。單 Agent 自我覆核，未宣稱獨立審查。
