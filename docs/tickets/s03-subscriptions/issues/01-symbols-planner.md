# 01：symbol 身份與訂閱計劃（S03/03f）

Status: done

**交付：** 由已驗證 Instrument 快照及明確行情能力／配額計算訂閱目標，
回報 accepted/rejected 原因、應新增／釋放的本連線 logical keys；先用 fake
FeedAdapter 驗證，不將計劃接到真實 OpenD。

**Blocked by:** S03/03e（完成）。沿用 [Task 4](../../../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md#task-4--opend-及行情能力探測)
及 [設計 §7.1](../../../superpowers/specs/2026-11-25-gabfin-system-design.md#71-動態候選池)。

- [x] Catalog 以 canonical UUID 及 source/symbol 精確映射，拒絕重複／衝突。
  不由 ticker 猜 tick、lot、currency 或 option terms；option underlying 須為已登錄 equity。
  對外回傳防禦性快照，外部修改不能改動 catalog。
- [x] 使用既有 Demand、FeedCapabilities、SubscriptionKey、SubscriptionPlan；
  額外 config／delta 僅屬記憶體內 planner 介面，不修改共用 wire contracts。
- [x] 排序固定 holding > chart > strategy > watchlist > candidate，同級穩定排序；
  精確 instrument/channel/timeframe 去重，多 owner 仍只需一份訂閱。
- [x] demand 到期邊界為 expires_at <= as_of；同 key 有其他有效 owner 時保留。
  最後有效需求消失可釋放；已知配額不足時可淘汰低優先，再新增高優先目標。
- [x] 普通額度按 key 計數；Futu 期權以 underlying／expiry／channel／timeframe
  共用鏈成本，與普通額度分開。Budget 是扣除其他 context 保留額後、供本 planner
  全部目標使用的容量（包含自己現有訂閱），不是只供新增的 remaining。
- [x] Budget 與 capabilities 必須同一 checked_at；TTL 由 caller 明確提供，無固定 runtime
  門檻。未知、過期、未來 snapshot 或 source-wide permission error 暫停變更並回原因，
  即使沒有有效需求亦然；受影響的 current pools 也必須核對。
  不以 FeedCapabilities.history_limits 推定即時 channel 支援；supported 的
  asset_class／session／channel／timeframe 組合逐項明確輸入，不能推定笛卡爾交集。
- [x] latency unknown 保持 unknown；可接受的行情訂閱不代表 realtime 或交易授權。
  未知／不支援身份、source symbol、session、channel、資產及過期期權均有具體拒絕原因。
- [x] 變更只針對 caller 宣告為此 context 擁有的 current keys；沒有真實訂閱 I/O。
  能力／額度不確定時不產生新增或釋放指令；不把既有訂閱冒稱健康或已接受。
  新 catalog 缺少 current binding 時凍結並回 blocked_reasons，不能把缺項視為離頁。
- [x] 公開測試介面為 catalog resolve/get、plan_subscriptions 及返回 delta 配合 fake provider；
  每個新行為先 RED 後 GREEN，最後必要回歸、wheel、獨立雙軸審查及 checkpoint。

## 界線

- 本切片處理 caller 提供的有限 metadata，並非完整市場 catalog 匯入／持久化。
- 不做 timeframe 等價轉換／衍生 bar、批次公平性、stream 協調、實際 entitlement 探測、
  SDK topic 編碼或下單。Demand.owner／priority 為上游已授權輸入，planner 不是 auth 層。

- 驗收、實際限制與證據：[03f report](../../../audit/s03-03f-planner-2026-11-25.md)。
