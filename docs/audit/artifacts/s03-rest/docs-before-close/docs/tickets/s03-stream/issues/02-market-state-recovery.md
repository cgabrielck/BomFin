# S03 remainder — 行情狀態、新鮮度及恢復

Status: in-progress
Blocked by: none（03g 已完成）

規格：[主計劃 Task 4–5](../../../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md)、
[設計 §7.2](../../../superpowers/specs/2026-11-25-gabfin-system-design.md)。
本票執行使用者授權的 S03 剩餘範圍；不進入 S04 UI 或交易。

## 驗收

- [ ] Freshness 以讀取時 now／來源時間判斷，heartbeat 與最後市場事件分開；
  未知／延遲權益、clock skew、gap、錯誤 session 或未批准政策禁止新入場。
  不預設任何已批准的秒數；結果只是行情條件，不是交易授權。
- [ ] TradeMarketEvent 建 bar：duplicate 不重算 volume，late event 修訂正確時間窗，
  forming/final/corrected、來源時序、交易所 session/DST／休市與有界記憶體皆可測。
  Quote 不會冒充 trade 或產生虛構成交量。
- [ ] Coordinator 以 apply/snapshot 公開介面提供 latest 狀態、序號及有界 replay；
  斷線時 gap 明確，只有已驗證完整補缺才解除，重播不使用尚不可得資料。
- [ ] 私有跨程序 stream 僅監聽 loopback，驗證版本、身份、scope、到期；
  慢讀者有界／斷線且必須重新 snapshot，行情通道拒絕委託事件。
- [ ] 接通 feed lifecycle 與同一市場狀態；取消、重連、補缺失敗不變成健康。
  有限診斷與常駐主機行為的驗證範圍明示，不把 fake 當 provider 真實證據。
- [ ] 覆核既有 quota／catalog／entitlement smoke，列明 G2 缺口及可選路線；
  不採購、不升級權益、不啟動交易。
- [ ] 完整回歸、獨立 Standards／Spec 審查、wheel／乾淨安裝及限時真實鏈路驗證。

## 公開測試面及工程取捨

沿用已批准 apply(MarketEvent)、snapshot、entry_eligible 與 FeedAdapter。
跨程序測試以真實本機 socket/process 加外部時鐘／SDK／history fake 驗證。
Calendar 輸入必須有明確來源／版本及 UTC session windows，不能只靠週一至五猜假期。
重播 cursor 的 epoch／保留範圍不符就要求完整 snapshot，不默默漏資料。
S04 的真實 UI tracing 留給前端整合；本單位提供到 consumer 的時間紀錄及 tracing 接點。

## Comments

- Base `3073cf3b41ac2724979442960b314a0c92598ca0`，分支 codex/s01-source-baseline。
- G2 未證實的項目必須保持 open；完成實作不代表可以啟動 paper/live execution。
