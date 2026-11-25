# 01：有範圍的歷史資料／時段能力診斷（S03/03e）

Status: done

**What to build:** 使用者可從行情 runner 檢查少量 AAPL 歷史分鐘 K、
前後歷史配額及當前 market state，並清楚看到哪些時段仍未驗證。

**Blocked by:** S03/03d（完成）。沿用已授權的 03e，沒有增加產品範圍。

**規格：** [主計劃 Task 4](../../../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md#task-4--opend-及行情能力探測)、
[設計 §7](../../../superpowers/specs/2026-11-25-gabfin-system-design.md#7-行情與其他輸入)。

- [x] 固定 US.AAPL、前一個紐約曆日，K_1M、未調整；RTH 與 ETH 各一次，
  每次最多兩筆、首個 page、永不追 page key，不自動重試／擴大日期範圍。
- [x] API 可能先在 OpenD 取整個指定曆日，client 的 max_count 只限制回傳。
  ETH 表示 RTH 加盤前／盤後，不要求 ALL 或夜盤。
- [x] 前後 get_history_kl_quota(get_detail=False)，只保存 used／remaining。
  配額未知或為零不取歷史；同標的通常七天內不重複計額，不能稱其可退訂釋放。
- [x] 市場狀態只作當前 metadata；歷史時段只分類已返回的常規鐘面時間，
  不冒充完整交易日曆、開市證明、即時權益或 realtime latency。
- [x] 核對 code、日期、分鐘時間、非負有限價格與 OHLC 關係、排序、上限；
  不保存股票名稱、quota detail、page token 或原始 SDK 錯誤。
- [x] 回傳逐 request available／empty／failed／invalid_data／not_attempted，
  部分結果保留已驗證資料；parent 驗證 schema／時段／數值與狀態一致性。
- [x] 沿用已確認 runner／注入行情 context 測試介面，先 RED 後 GREEN。
  parent 有明確 timeout，讀取前檢查剩餘預算；所有路徑 close，不訂閱、不查帳戶。
- [x] 實際 localhost smoke 後檢查 metadata／worker 殘留；無法取得時明示缺口。
  完成必要回歸、乾淨 wheel 驗證與全新上下文 Standards／Spec 審查。

## Comments

- 非交易日可能回傳 empty；不把前一曆日稱為最近交易日，不擴大查詢。
- 不含歷史期權、全量回測下載、交易日曆、live push、catalog／allocator 或交易。

- 完成證據與限制：[03e report](../../../audit/s03-03e-history-2026-11-25.md)。
