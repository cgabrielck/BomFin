# GabFin S02/02a Contracts Implementation Brief

> Execute the first slice of the already confirmed Task 2 with `executing-plans` and TDD. Single agent, existing local checkout; user requested continuation. This brief refines that task, not a new architecture or approval cycle.

**Goal:** 新命名空間內可獨立安裝、驗證及序列化的精確數值／UTC／advisory 與 strategy intent 契約。

**Architecture:** 僅建立 `services/gabfin/contracts/` 與對應測試，與 legacy backend 並存；不接 API、行情、DB、broker 或 executor。

**Tech Stack:** Python 3.12、已驗證的 Pydantic 2.14.4／pytest 9.2.0、setuptools editable package。

**Spec:** [main plan §2 / Task 2](2026-11-25-gabfin-upgrade-plan.md)；[confirmed design U13/U18](../specs/2026-11-25-gabfin-system-design.md)。使用者本回合已選：StrategyIntent 採 long/short + position_effect。

## Global Constraints

- UUID IDs；金額／價格／數量 Decimal，JSON 字串；比例 0..1；時間帶 offset，輸出 UTC ISO8601。
- 新前端重寫；不修改舊前端或交易路徑，不使用舊 ADR 作限制。
- 無新風險數值、交易啟用、外部服務憑證、push 或部署；保留原 lockfile 與 baseline。
- 僅此工作單位；其餘市場／研究／order／policy 模型、共同 schema artifact、SQLite migrations 仍屬後續 Task 2 切片。

## Files and Interfaces

- Create `pyproject.toml`：只 discovery `services/gabfin`；Python >=3.12、Pydantic ==2.14.4；不納入 legacy backend。
- Create `services/gabfin/__init__.py`、`contracts/__init__.py`：新 package 邊界。
- Create `services/gabfin/contracts/common.py`：
  - `ContractModel`：禁止 unknown fields、validated defaults、frozen fields。
  - `VersionedContract`：必填 `schema_version: Literal["1.0"]`。
  - `ExactDecimal`：Python Decimal／int／decimal string；拒絕 float／bool／非有限值；JSON input/output 一律 decimal string，不量化或截斷精度。
  - `Ratio`：同上，另限 0..1。
  - `UtcTimestamp`：只接受 aware datetime／帶時區 ISO string，轉 UTC；拒絕 naive 與數字 epoch。
  - `Money(amount: ExactDecimal, currency: uppercase-three-letter-code)`：保留負值及小數位，不暗中換匯。
- Create `services/gabfin/contracts/intent.py`：
  - `PositionSide`: long／short；`PositionEffect`: open／reduce／close。
  - `TradePlan`：schema_version、kind=trade_plan、advisory=true、instrument UUID、side、entry_scenarios／exit_scenarios（文字 tuple）、evidence（UUID tuple）、as_of。
  - `StrategyIntent`：schema_version、kind=strategy_intent、intent_id、strategy_version、policy_version、instrument UUID、side、position_effect、setup、invalidation、expires_at、snapshot_id UUID、producer_scope=strategy:emit。
  - `IntentDocument`：以 kind 區分的兩者 union。禁止將 TradePlan model／dump／JSON 直接驗成 StrategyIntent。
- Create `tests/gabfin/test_contracts.py`：真實 model／TypeAdapter 行為測試，不 mock Pydantic。

## Review Focus

1. float／JSON number 造成精度流失：拒絕它們，測試大數、小數、負值及 Decimal("0.10") roundtrip。
2. naive／epoch 時間誤解：拒絕它們；測試跨 offset 與 UTC 輸出。
3. advisory 冒充 execution：必填不同 kind、advisory=true、extra=forbid；模型驗證不等於 actor 授權。
4. long/short 與 buy/sell 混淆：保留 side + position_effect 的六個組合；不在本層轉成委託。
5. 復原歷史資料被 wall-clock expiry 阻擋：允許解析過期 intent，執行時時效檢查留給 risk/context；未知版本、錯 UUID、空白必要字串拒絕。

## Steps

- [x] Snapshot HEAD／lockfile／legacy tracked hashes；記錄 package 不存在，保留現有環境。
- [x] 寫共同契約的測試，執行並確認因功能尚未存在而失敗。
- [x] 實作 common types 與 package metadata，安裝 editable package；重跑 common 測試。
- [x] 寫 intent tagging、版本、期限、scope／方向／advisory 跨驗證測試；確認失敗，再實作最小 models。
- [x] 跑完整新契約測試，從 checkout 外使用 isolated Python import；檢查 serialization schema 的 Decimal string／timezone／discriminator 邊界。
- [x] 跑原專案完整 pytest（使用 sanitized runner／新 log 名稱）；記錄任何 skip、warning 或既有 journal 副作用，保留原始 baseline。
- [x] `git diff --check`、範圍／lockfile／legacy hashes 核對；單 Agent 自我覆核；只 commit 此切片 paths，不 push。
- [x] 更新受影響 memory／checkpoint，明列剩餘 Task 2 工作；本 brief 不宣稱全 S02 已完成。

## Decisions and Boundaries

- 使用者已批准 side + position_effect 的表示方式；沒有批准任何新增 sizing 或風險數值。
- `producer_scope` 是 schema 標記，不能證明 principal 有權產生意圖；Task 3 必須做真正的能力授權。
- 輸入與輸出皆維持精度；貨幣只驗證代碼形狀，不聲稱已驗證完整 ISO 清單或做過 FX。
- Common／intent 是本 slice 的 interfaces；之後其餘契約使用同一套 primitives，SQLite 與 schema artifact 不建立占位實作。
- `setup`／`invalidation` 在此切片只是描述資料，不是可由風控執行的文字指令。接入 RiskService 前，仍須補齊由已批准策略／政策產生的機器可驗證條件；不得解析任意描述文字來批准交易。
- Self-review: covers the first three Task 2 contract acceptance cases plus boundary cases; package, migrations and full schema coverage remain explicitly separated.

## Completion

已完成此切片；實際結果見 [02a report](../../audit/s02-02a-contracts-2026-11-25.md)。其餘 Task 2 內容維持待辦。
