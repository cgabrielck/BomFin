# GabFin 舊架構權威清理結果

使用者已批准 [清理計劃](../superpowers/plans/2026-11-25-gabfin-legacy-authority-cleanup.md)，兩個任務均已完成。沿用本機 checkout，沒有另開 clone、push、部署或啟動交易。

## 已完成的變更

- 刪除四個舊檔：`ADR-003-live-ai-trading-desk.md`、`ADR-004-chart-engine.md`、`ADR-005-mobile-desk-readonly.md`、`ADR-006-futu-opend-desk-observe.md`。原文仍在 Git history；沒有改寫歷史。
- 重寫 checkout 的 `AGENTS.md`、交接頁及架構索引，修正 README／產品記錄。新設計與主計劃是權威，舊 ADR／roadmap 不是新的產品約束。
- 23 個舊文件／歷史頁加上 `LEGACY / SUPERSEDED`；修復指向刪除檔案的引用。`ARCHITECTURE_DECISION.md` 只保留相容指標，原嵌入的舊決策正文已移除。
- 兩個 Python module 只改頂層說明；手機 API 的 `adr_005` metadata 仍保留作舊 API 相容資料，不具有新架構決策效力。
- 文件測試改為檢查新權威索引；手機權限、禁止越權下單及 API 相容資料的既有測試保留。

## 版本與實際驗證

| 項目 | 結果 |
|---|---|
| 原始 legacy baseline | `42f96b3b8a39e40f2e4e579aa9e619814dc80e7b` |
| Task 1 local commit | `4827c3c25d783459a48e7423112166aeb1db33af` — `docs: replace legacy architecture authority` |
| Task 2 local commit／目前 HEAD | `2dba0be7adf1f74a489031a1774edd5fd4dd15d4` — `docs: retire legacy ADRs and repair references` |
| 執行前的舊權威搜尋 | 有預期命中；完成後 5 個入口已沒有過時的 binding 命令 |
| 先確認舊測試會失敗 | 刪檔後原 ADR-005 文件測試：**1 failed**，原因為讀取已移除檔案 |
| 更新後的相關 regression | **58 passed，0 failed／skip**；pytest exit 0，console 5.97 秒 |
| 範圍核對 | 35 個批准 paths：4 刪除、31 修改；沒有超出 manifest 的 tracked 變更 |
| 連結／空白檢查 | 27 處新增／改寫連結無失效；受檢頁面亦未發現原有失效連結；`git diff --check` exit 0 |
| Runtime 保留證據 | 兩個 production modules 去除頂層 docstring 後，AST hash 與 baseline 完全相同 |
| 測試保留證據 | 文件斷言以外的 19 個 function AST 完全相同 |
| 保護既有內容 | canonical design／主計劃、原始 01b 證據及 lockfile hash 不變；沒有新 journal／worker PID 檔 |

回歸只跑受影響的手機文件／權限／OpenD observe 測試，沒有重跑整套 baseline 或 build；這次沒有產品執行碼或前端變更，原始 baseline 結果也沒有被覆寫。

Git 原本沒有設定作者資料。兩個 local commit 使用單次命令的 `Codex <codex@localhost>`，沒有修改全域／repo 的作者設定，也沒有冒用使用者身份。

## 證據與重跑

- [verification.json](artifacts/legacy-authority-cleanup/verification.json)：範圍、AST、連結、雜湊、測試結果。
- [execution ledger](artifacts/legacy-authority-cleanup/progress.md)：兩任務與執行判斷。
- [原文件測試失敗日誌](artifacts/s01-01b/pytest-adr-cleanup-red.log)、[更新後回歸日誌](artifacts/s01-01b/pytest-adr-cleanup.log)、[JUnit](artifacts/s01-01b/pytest-adr-cleanup.xml)。
- 重跑檔案／行為保留檢查：`python docs/audit/artifacts/legacy-authority-cleanup/verify_cleanup.py`。
- 源碼回歸：外層使用 `run-pytest.ps1 -RunName <new-name> -TestPaths`，指定 `tests/api/test_mobile_desk_ro.py`、`tests/trading/test_desk_roles.py`、`tests/observe/test_futu_observe.py`；不要覆寫原始 baseline 日誌。

本次依使用者選擇由單 Agent 實作及自我覆核，沒有宣稱做過獨立 Agent review。換行格式檢查曾發現既有 mixed CRLF／新改行尾空白；只清理新增／改寫行，保留未改動的歷史行。

## 下一步與限制

- checkout 的 tracked／staged 工作樹已乾淨；唯一非忽略的 untracked file 仍是原先的 `web/package-lock.json`，已保留。
- S02／02a：細化並建立新 `services/gabfin/contracts/` 的第一個契約切片，再依主計劃處理 storage／migrations；不為此延續舊前端架構。
- 原 B01 型別錯誤、B02 journal 測試隔離、B03 Postgres skip、B04 pandas warning 仍按 [baseline](baseline-2026-11-25.md) 記錄；本次沒有假稱已修復，也不把它們一律當作開始 S02 的阻塞。
- 真實 provider、交易運行、瀏覽器、私人 HTTPS、安全及負載的關卡，仍依主計劃執行。文件清理不代表這些項目通過。
