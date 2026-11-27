# Matt Pocock 工作流技能安裝及 GabFin 設定

日期：2026-11-25。範圍：安裝使用者文字與圖片所列技能，接入現有開發工作流。
本次未開始 S03/03d，也未變更應用程式或運行 OpenD。

## 來源及安裝

- 官方 repository：[mattpocock/skills](https://github.com/mattpocock/skills)。
- 固定版本：[d65391149dbb5fe76478e76fa8d5122b2aa5a70e](https://github.com/mattpocock/skills/tree/d65391149dbb5fe76478e76fa8d5122b2aa5a70e)。
- 使用 bundled `skill-installer/scripts/install-skill-from-github.py`，
  明確指定上述 `--ref` 與 `--dest C:/Users/001/.agents/skills`；exit 0。
- [官方改名紀錄](https://github.com/mattpocock/skills/commit/1fc6573e0e300118ce342fb9365521c9c34eefd4)：
  `writing-great-skills` → `writing-for-agents`，作者沒有保留 alias。

| 使用者要求 | 本機處理 |
| --- | --- |
| grill-me | 原有 grill-me、grilling 保留，與固定版本一致 |
| to-spec | 新增 |
| to-tickets | 新增 |
| implement + TDD | 新增 implement、tdd |
| code-review | 新增 |
| writing-great-skills | 新增官方現名 writing-for-agents |
| improve-codebase-architecture | 新增 |
| 技能支援 | 新增 codebase-design、domain-modeling、setup-matt-pocock-skills |

共新增 10 個目錄，沿用 2 個既有目錄；保留其他已安裝技能。
既有 `test-driven-development` 與新 `tdd` 各自保留，GabFin 主流程選後者。
新安裝技能預期在下一個對話回合出現在技能清單；本回合已直接讀取其文件配置。
未驗證其他機器、其他帳號或遠端環境的技能發現。

## 專案適配

- [workflow](../agents/workflow.md)：聚焦釐清、既有 spec、垂直功能票、TDD、
  獨立 Standards／Spec 審查，以及實際驗證／提交／checkpoint。
- [tracker](../agents/issue-tracker.md)：本地 Markdown，保留原總計劃與當前單位；
  新票據用持久的 docs/tickets，一票一檔。未建立外部 issue／label。
- [domain](../agents/domain.md)：沿用目前規格與決策記憶，舊 ADR 維持退役。
- 根 AGENTS 新增條件式入口；主計劃的執行提示改指向此工作流。
  應用程式 checkout 原有 AGENTS 已連到外層入口，無需改寫 source。
- 維持一個實作者；完成單位後用兩個全新上下文唯讀 reviewer，分開回報
  Standards／Spec。此次設定沒有把過往自審改稱獨立 review。

## 驗證

- GitHub recursive tree 完整（truncated=false）；逐一比對上述 12 個目錄的
  37 個檔案 Git blob SHA-1，37/37 與固定版本相符，驗證程序 exit 0。
- [上游檔案清單](artifacts/skills-workflow-2026-11-25/upstream-manifest.json)；
  [實際檔案雜湊核對](artifacts/skills-workflow-2026-11-25/verification.json)。
- 獨立 Standards／Spec 文件審查均由全新上下文開始；已修正 reviewer 輸入、
  既有 staged 隔離、明確載入技能、spec 無程式碼與本地狀態映射等問題。
  最終複查兩軸未解決項目均為 0；[審查記錄](artifacts/skills-workflow-2026-11-25/review-results.json)。
- 審查只涵蓋具名設定文件的現態與已知修改範圍；初始修改前快照未保存，
  不能據此聲稱驗證了完整歷史差異。輸入版本由前後兩份 SHA-256 清單鎖定。
- [收尾驗證](artifacts/skills-workflow-2026-11-25/document-verification.json) 檢查
  本地連結、記憶長度／條目、技能入口、review 輸入及 app 狀態；
  [verify.py](artifacts/skills-workflow-2026-11-25/verify.py) 可用 checkout 的 Python 重跑。
- App HEAD 保持 `2607a81a073a5fac2286b0fc0aa5742a5f6fabba`，tracked clean，
  唯一 untracked 仍為原 lockfile；內容 SHA-256 與 03c 前態證據一致。
  本次沒有應用程式變更，未重跑應用程式測試。

## 下一步

按 [execution](../memory/execution.md) 繼續 S03/03d；開工時以新流程讀取
對應需求、界定窄範圍驗收及測試，保留已完成單位與現有文件。
