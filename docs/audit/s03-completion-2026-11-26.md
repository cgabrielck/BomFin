# S03 工程交付與驗證

S03 程式收尾完成；**G2 行情權益關卡仍未放行**。完成工程交付不代表已取得
即時／BBO／PRE／POST 權限，也不代表已啟動 paper 或真實交易。

- Checkout：`C:/Users/001/Desktop/GabFin-ai-trade/.worktrees/gabfin-s01`。
- Branch：`codex/s01-source-baseline`；base `3073cf3b41ac2724979442960b314a0c92598ca0`。
- 本機提交：`1802198648ce465db5f3dba79a342756a7f9ccc5`，未 push。
- 審查／測試／提交的同一棵樹：`63f71a854aefff3de147404f82e6fd9fda7b315a`，28 個檔案。
- [工作票](../tickets/s03-stream/issues/02-market-state-recovery.md)、
  [主機使用說明](../../../docs/market-data-host.md)。

## 已交付

- Freshness 在讀取時重新計算來源價格年齡，獨立核對 provider heartbeat、
  calendar 現時 session、權益、BBO、品質與政策。缺證據即拒絕；沒有預設批准秒數。
- Trade bar 使用 UTC session windows，處理 duplicate、late correction、finalization、
  DST／休市、Decimal 精度與保留上限。Trade ID 與 dedup key 同時核對，quote 不產生成交量。
- 單市場 coordinator 提供 latest snapshot、有界 replay、epoch/cursor 及明確 gap。
  來源序號預設 opaque；只有明確宣告 contiguous 才偵測缺號，重置／衝突須新 epoch。
- 補缺逐 instrument/channel/timeframe 核對範圍、唯一紀錄筆數、分頁及空頁證明。
  拒收／時鐘偏移／重複資料不能補齊缺口。Quote snapshot 只恢復 quote 狀態。
- Loopback authenticated internal stream 驗證身份、scope、到期及版本；行情通道拒絕委託。
  Resume 綁定 session 與股票集合；慢讀者或連線錯誤須先取得新 snapshot。
- Managed feed lifecycle 在重試前驗證完整釋放回條；心跳失效會關閉舊 context 再重連。
  清理失敗停止建立 context；有限診斷的訂閱失敗會傳回非成功結果。
- 已接一股 quote-only Futu host、實際 login/quota capabilities 查詢及前景常駐入口。
  `run_plan` 只接受新 context 的可靠完整計劃，不接管不明的舊訂閱。
- 可選 `exchange-calendars==4.13.3` exporter，主程序毋須 pandas／SDK。

## 實際驗證

- 最終完整回歸：**2108 passed、4 skipped、1 warning，exit 0，130.78 秒**。
  [完整輸出](artifacts/s03-rest/full-reviewed.log)、[JUnit](artifacts/s03-rest/full-reviewed.xml)。
  Skip 均因未安裝可選 `psycopg`；warning 為既有 Pandas4Warning。
  沒有重跑未變更的前端 build／已知失敗 typecheck；不宣稱它們通過。
- 獨立 Standards／Spec 以全新 reviewer 上下文審查；修正後對同一最終樹複查，
  未發現剩餘程式 blocker。兩者分別重跑 7／8 個聚焦案例。
  [審查紀錄](artifacts/s03-rest/reviews.json)。
- [RED／GREEN 及失敗修正紀錄](artifacts/s03-rest/review-resolution.md) 保留預期失敗、
  中途測試錯誤與最終結果；較早的 full-before-review／full-final 不取代最後回歸。
- Wheel build／乾淨安裝成功；SHA256
  `11e6e81e0657b6e8d97fb4995861ebfa4980626c8a6d4069c7fe56f0be384e2a`。
  51 個 Python 檔案與 source／安裝內容一致，50 個模組可匯入、schema 一致，
  環境沒有 Futu SDK、pandas 或 calendar extra。
  [驗證](artifacts/s03-rest/wheel-verification.json)、[腳本](artifacts/s03-rest/check-wheel.py)。
- Calendar extra 獨立安裝；最終 wheel 匯出 2026 XNYS 251 個 regular sessions。
  核對 Thanksgiving 休市、翌日提早收市及兩個 DST 開市時刻；
  [日曆驗證](artifacts/s03-rest/calendar-verification.json)、
  [NYSE 官方依據](https://www.nyse.com/trade/hours-calendars)。
- 真實 SDK → coordinator → authenticated stream → **獨立 consumer process** 成功，
  consumer 收到 quote／health，quote 狀態恢復，無 consumer 錯誤。
  明確反訂閱、context 關閉及 worker 退出成功。
  [實際鏈路](artifacts/s03-rest/live-chain.json)、[腳本](artifacts/s03-rest/live-chain.py)。
  行情來源時間／權益／配額的解讀由 [feed register](feed-entitlements.md) 擁有。
- [事後檢查](artifacts/s03-rest/post-live-check.json)：SDK worker 0，原 OpenD PID 29100
  仍監聽 loopback。沒有關閉／重啟 OpenD，沒有交易／帳戶 context、unlock 或下單。
- [保留驗證](artifacts/s03-rest/preservation.json)：543 個原 tracked 檔案，除本單位範圍
  沒有非預期變更；原 untracked `web/package-lock.json` 雜湊一致。
  Full tests 產生的 mock journal 已歸檔；移動前核對 baseline 確認原本不存在及兩端路徑。

## 界線與下一步

- 真實 producer 目前只有一股 quote，缺 BBO／已驗證 session 與 latency 標籤。
  Trade/bar/history 引擎已透過受信 adapter seam 測試；不是實際 Futu tick／bar 補缺證據。
  Catalog 是有限且 caller 核對的 metadata，不是完整市場 security master 匯入。
- 本次取得舊收市價；「connected／quote resynced」與「可用於新入場」分開，
  freshness 實際回傳拒絕。沒有批准 5 秒門檻或任何交易政策。
- G2 具體缺口、解除方法及成本候選見 [feed register](feed-entitlements.md)；
  [後續票](../tickets/s03-stream/issues/03-feed-evidence-g2.md) 保持未完成。
- Source→receive→state→consumer 已有實際 tracing；UI render 尚未量測，續接 S04。
  下一 Section 是 S04 前端殼與圖表；本次沒有開始 S04、部署或啟動 paper trade。
