# 03g — 單股 callback → 有界最新報價

Status: in-progress
Blocked by: none（03f 已完成）

規格：[Task 4–5](../../../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md)、
[行情設計 §7](../../../superpowers/specs/2026-11-25-gabfin-system-design.md)。
沿用已批准 FeedAdapter、MarketEvent、snapshot 公開 seam；SDK／時鐘／程序為外部測試邊界。

## 本單位驗收

- [ ] 單一明確 catalog US equity、quote-only；SDK 在獨立程序，callback 驅動，沒有 snapshot 輪詢。
- [ ] typed quote event 保留來源時間；不虛構 bid/ask、session、權益或 realtime。
- [ ] latest cache 與兩端 pending quote 都有界；慢讀者合併最新觀察，不倒退到較舊來源時間。
- [ ] 拒絕錯誤 instrument／價格／時間／IPC 版本；不讓 raw SDK 訊息外洩。
- [ ] subscribe/unsubscribe、取消、重複 close、worker failure 均可終止；記錄 unsubscribe、quota 確認及 close 結果。
- [ ] 離線 RED/GREEN、完整回歸、兩軸獨立 review、wheel 安裝驗證。
- [ ] 做限時單股真實 callback smoke，或如實記錄外部失敗；初始／舊價不當成持續新鮮行情。

## 執行範圍

03g 先提供最多 120 秒的 quote-only adapter slice；未提供常駐行情服務、
重連補缺、API/UI stream、交易新鮮度政策或期權推送。
SDK 與父程序用繼承的私有 pipe 傳遞具版本的白名單訊息，不開網絡 listener；
Task 5 的 authenticated loopback API 服務仍留待整合。
來源 `last_price` 僅作該來源報價觀察，session/latency 不從本機時鐘推斷。

## Comments

- Unit base: `a8d23d575baab94420595ca5cddf12255fb40ebc`。
- 工程選擇：單股 cache/pending 容量各一；完整 quote 取代完整 quote，沒有 delta 合併猜測。
