# 01：有範圍的期權鏈與報價能力診斷（S03/03d）

Status: done

**What to build:** 使用者可從現有行情診斷 runner 檢查 AAPL 的少量期權，
知道靜態鏈與報價是否可讀，以及訂閱是否已釋放；未知即時性保持明示。

**Blocked by:** S03/03c（已完成）。本票沿用既有授權單位，無新增產品範圍。

**規格：** [主計劃 Task 4](../../../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md#task-4--opend-及行情能力探測)、
[設計 §7](../../../superpowers/specs/2026-11-25-gabfin-system-design.md#7-行情與其他輸入)。

- [x] 限 US.AAPL、紐約當日到未來 30 天內最近一個到期日、350–360 履約價。
- [x] 靜態鏈只取一個到期日；API 無履約價篩選，回傳上限 2000 筆後在本地篩選。
  只選標準、未停牌合約，最多 call／put 各一張，向窗口中央靠近。
- [x] 訂閱前核對 code、標的、到期日、方向、履約價及每張合約股數；
  報價再次核對 strike_price／contract_size。不能把 lot_size 當已證明的通用衍生品乘數。
- [x] 保持 quote-only context、只訂 QUOTE、無 push／延長時段、無帳戶或交易。
- [x] 已嘗試訂閱必須清理；成功訂閱至少持有 61 秒再反訂閱，核對 own_used=0 並 close。
- [x] 清理亦核對獨立 own_option_used_quota=0；失敗須明示待釋放及實際計數。
  訂閱前須保留足夠 deadline，否則回報 budget_exhausted 而不開始訂閱。
- [x] parent 重新驗證 allowlist／數值／身份與一致性；不輸出原始錯誤、SDK stdout 或帳號。
- [x] 公開測試介面沿用 run_probe 與注入 quote context 的 inspection；時鐘及 sleep 可注入。
  每一新行為先 RED 再 GREEN，最後回歸與雙軸獨立審查。
- [x] 嘗試已授權 localhost smoke；失敗時記實際缺口，不冒稱無權益或即時。
  成功／失敗後都檢查 metadata／worker 殘留；不重啟 OpenD、不購買行情。

## Comments

- 本票不含 Greeks、歷史期權、catalog 全映射、allocator、推送、UI 或期權交易。
- 單邊窗口保留一張有效合約並標示 partial；SDK 任意卡住時清理是 best-effort，
  不能把 parent timeout 冒稱已反訂閱。
- 驗證及結果見 [audit report](../../../audit/s03-03d-options-2026-11-25.md)；整個 S03 仍有後續單位。
