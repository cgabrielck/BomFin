# 舊 shadow integration 測試依賴當日交易日

Status: draft
Blocked by: none

## 已確認問題

- `tests/trading/engine/test_worker_integration.py::_fake_ohlcv_bar` 以
  `datetime.now(timezone.utc)` 建假 bar。2026-11-26 的假資料被既有
  `filter_us_equity_daily_bars` 濾走，模擬單因此 CANCELLED，測試卻預期 FILLED。
- assertion 失敗後跳過 `store.close()`，Windows 清除暫存 SQLite 時再出現 WinError 32。
- S04/04c 新樹與 base `898cc04b7850451ae7fde96f5ff422e78250b1a5` 的獨立 checkout
  均重現；calendar 控制實驗保留 Nov25、排除 Nov26。不是 04c 新模組造成的回歸。
- [現樹重現](../../../audit/artifacts/s04-04c/legacy-worker-reproduction.log)、
  [base 重現](../../../audit/artifacts/s04-04c/legacy-at-base.log)、
  [日曆實驗](../../../audit/artifacts/s04-04c/legacy-calendar-proof.json)。

## 建議修復與驗收

- 在測試邊界注入已知有效交易日，避免依賴執行當日；保留休市不得成交的產品規則。
- SQLite store 由 `finally`／context manager 清理，assertion 失敗亦須關閉。
- 以有效交易日、休市日、週末的時鐘重跑相關測試；無真實 broker 呼叫。
- S04/04c 只記錄此缺陷；未修改 legacy 交易邏輯或宣稱完整回歸全過。
