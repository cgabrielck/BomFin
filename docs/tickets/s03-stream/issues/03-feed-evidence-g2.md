# G2 — 真實行情權益與 channel 證據

Status: blocked
Blocked by: 缺少已核對的 instrument/channel/session 權益與可用時段證據；不是使用者批准不足。

規格：[主計劃 Task 4–5](../../../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md)、
[設計 §7.2](../../../superpowers/specs/2026-11-25-gabfin-system-design.md)。

S03 工程已交付；本票保留外部 release gate，不代表即時行情已可用於自動交易。
權益事實、觀察時間及成本候選由 [feed register](../../../audit/feed-entitlements.md) 擁有。

## 驗收與解除方法

- [ ] 核對 API 的 instrument/channel/session/latency manifest，不能以 UI LV3、
  quote login、quota 或舊收市價代替權益證明。
  股票與期權分開核對，列明歷史資料粒度／範圍及用途限制。
- [ ] 在可用交易時段，限時取得有來源時間的 BBO／last、PRE／POST 證據；
  未獲授權的項目逐項說明，不能偷偷更改 feed／latency 標籤。
- [ ] 視已證實的 channel 延伸 Futu adapter，接 canonical catalog／history recovery；
  Trade/bar 的真實 provider 補缺驗證與 fake 測試分開記錄。
- [ ] 取得足夠 latency 證據後另行批准 freshness policy；未批准維持拒絕新入場。

不採購、不改會員權益、不讀帳戶、不開交易 context。若需供應商切換或付費，
先提供具體 coverage／限制／費用供使用者決定。S04 的離線 UI 工作可獨立進行。
