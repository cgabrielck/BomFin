# GabFin 領域文件與權威

## 進入領域／架構工作前

1. 從 [tasks](../memory/tasks.md) 與 [execution](../memory/execution.md) 確認單位。
2. 只讀 [system design](../superpowers/specs/2026-11-25-gabfin-system-design.md)
   的相關需求、領域定義與資料流程，再讀
   [upgrade plan](../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md) 的相關任務／契約。
3. 查 [decisions](../memory/decisions.md) 中相關的已接受取捨，並核對目前程式。
   設計中的提案與未完成 checkbox 並非已實作或已驗證的行為。

## 術語及決策儲存

此專案目前使用一組共享領域語彙，以新版設計及契約表定義為準。
需要新增詞義時先釐清與現有概念的關係；只有產生獨立詞彙表需求時才建立
外層 `GLOSSARY.md`，內容只放術語並從原定義來源連結，避免複製實作規格。

接受的取捨及理由記在現有 `docs/memory/decisions.md`；較長內容放單一
主題文件並連結。沿用這個儲存方式，毋須為技能建立 ADR 目錄。

舊 ADR 已退役為產品約束，包含 ADR-003；新版使用者需求與架構優先。
技能範本所述「讀取／遵循 ADR」在 GabFin 對應上述目前的決策記憶，
不會恢復舊約束。舊文件如因歷史調查而讀取，只能作歷史證據。
這次安裝不刪除既有文件，也不產生新 ADR。
