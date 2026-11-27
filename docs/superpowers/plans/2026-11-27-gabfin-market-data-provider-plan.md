# GabFin 行情供應商接入與採購計劃

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個可插拔的行情供應商接入層，優先用零成本的 Alpaca Basic 免費層解除 G2 的 BBO／session 缺口，並為將來付費升級保留單一介面。

**Architecture:** `services/gabfin/providers/` 已是 provider-per-directory 的形狀。現時只有 `futu/`，本計劃新增 `alpaca/`（免費 IEX 即時 quote + SIP 歷史日 K）與 `massive/`（付費研究 tape）。每個 provider 實作同一組契約：`capabilities()`／`subscribe()`／`events()`／`snapshot()`／`health`／`cleanup`，事件經 `gabfin.market` 的 `MarketCoordinator` 與 `freshness.py` 統一判定。供應商選擇由一份**版本化 registry 設定**決定，不在程式碼中硬編碼。

**Tech Stack:** Python 3.12、`alpaca-py>=0.45`（已裝）、`requests>=2.34`（已裝）、`pydantic>=2.0` 契約、Futu SDK（僅 owner 機器，owner-only child process）、pytest。

**Spec:** `docs/superpowers/specs/2026-11-25-gabfin-system-design.md`（§5 目標系統圖、§7 provider 邊界、§9 入場新鮮度、§10.2 秘密處理、§12 預算及效能目標）；採購事實基礎見 `docs/audit/feed-entitlements.md` 與 `user_upload_docs/carlos-market-data-and-broker-api-comparison.md`；工作流見 `docs/agents/workflow.md`。

## Global Constraints

- 預算上限 HK$400／月（≈US$51）。期權加額至 HK$500 是**未批准的規劃 envelope**。**本計劃不批准任何購買。**
- 訂閱層級一律**個人／非專業自用**（U10、U01）。Business SKU（Massive $2,499/月）不在本計劃範圍。
- 秘密只在後端環境變數，永不進 URL query、前端 bundle、聊天、日誌、Markdown 或 checkpoint（設計 §10.2）。
- 每個供應商的行情必須帶 `vendor` 標籤與 `asof`；無 vendor 的資料不得進入任何決策路徑（`MODULAR_ARCHITECTURE.md` M2「MUST NEVER」）。
- 免費層與轉售共用金鑰不可作為正式資料來源（比較文件 §6.6）。**本計劃不採用共享／轉售 key。**
- Freshness 政策由呼叫端提供並經 registry 驗證；**不得有預設值**（`contracts/feed.py` `FreshnessPolicy`）。
- 未通過 G2 之前，不得在任何輸出中聲稱「實時行情」或「已取得實時權益」。
- 不得重啟既有 OpenD；不得啟動真實資金交易（U06、U10）；不得 push／deploy。
- 新 provider 必須用獨立子行程或 thread 隔離，不得阻塞事件迴圈（既有 futu adapter 模式）。

## Review Focus

以下五類輸入／失效模式是規格隱含、但沒有任何任務的測試覆蓋、最可能咬到實際使用者：

1. **Alpaca 免費層回傳 SIP 錯誤而非資料**（`42210000 subscription does not permit querying recent SIP data`）—— 若未處理，會靜默退化成空結果或例外崩潰。期望：辨識並回報為「feed 未訂閱」而非「無資料」。
2. **免費層歷史只到 15 分鐘前**—— 請求最近 15 分鐘的 SIP 歷史會失敗。期望：adapter 以 `feed=iex` 或截斷 `end` 明確處理，並在能力快照中標示「歷史最後 15 分鐘不可得」。
3. **IEX 只是約 2.5% 成交量**—— 免費層的「即時」不等於全市場 NBBO。期望：能力快照必須揭露 `venue_coverage`，且 freshness/entitlement 對此標記，不得默認全市場。
4. **WebSocket 只允許 30 個 symbol**（免費層）—— 訂閱第 31 個時行為未定義（可能靜默丟棄或斷線）。期望：adapter 在訂閱前就以容量錯誤明確失敗，不進入半連線狀態。
5. **美股計畫／清單跨越免費層配額**（5 calls/min 基本層、200/min 付費層、150 symbols 基礎層）—— 全市場初篩會觸發限流。期望：批次歷史取數必須自帶節流與 backoff，並記錄被限流的次數，不得靜默截斷結果集。

---

## 檔案結構

| 檔案 | 責任 |
|---|---|
| `services/gabfin/providers/registry.py` | 供應商選擇的版本化設定；從環境變數解析；無預設供應商 |
| `services/gabfin/providers/alpaca/__init__.py` | 匯出 |
| `services/gabfin/providers/alpaca/capabilities.py` | 免費層能力偵測（feed 可用性、歷史窗、30-symbol 上限、限流配額） |
| `services/gabfin/providers/alpaca/quote_worker.py` | 子行程：WebSocket 訂閱 + quote 正規化輸出 |
| `services/gabfin/providers/alpaca/quote_adapter.py` | 對外 adapter：capabilities／subscribe／events／snapshot／health／cleanup |
| `services/gabfin/providers/alpaca/history.py` | 歷史日 K 取數（含 feed 降級、15 分鐘截斷、節流） |
| `services/gabfin/providers/alpaca/feed_guard.py` | SIP 錯誤碼辨識與 feed 能力守衛 |
| `services/gabfin/providers/massive/__init__.py` | 匯出 |
| `services/gabfin/providers/massive/history.py` | Massive／Polygon 研究 tape adapter（REST + 分組日 K） |
| `services/gabfin/providers/massive/feed_guard.py` | Massive 授權／狀態錯誤辨識 |
| `services/gabfin/contracts/feed.py` | 修改：新增 `VenueCoverage` 與 `FeedEntitlement` 欄位（保持向後相容） |
| `.env.example` | 修改：加入新環境變數契約 |
| `tests/providers/test_alpaca_capabilities.py` | 能力偵測測試 |
| `tests/providers/test_alpaca_feed_guard.py` | Review Focus 1、2、3 的守衛測試 |
| `tests/providers/test_alpaca_quote_adapter.py` | adapter 生命週期與 Review Focus 4 |
| `tests/providers/test_alpaca_history.py` | 歷史取數、節流、Review Focus 5 |
| `tests/providers/test_massive_history.py` | Massive tape 測試 |
| `tests/providers/test_registry.py` | 供應商選擇設定 |

---

### Task 1: Feed 權益與 venue 覆蓋契約

**Files:**
- Modify: `services/gabfin/contracts/feed.py`
- Test: `tests/providers/test_feed_entitlement_contract.py`

**Interfaces:**
- Consumes: 無（最底層契約）
- Produces:
  - `gabfin.contracts.feed.VenueCoverage` — `Literal` 聯集：`'iex_only' | 'sip_consolidated' | 'opra_l1' | 'opra_full' | 'delayed_15m' | 'end_of_day' | 'unknown'`
  - `gabfin.contracts.feed.FeedEntitlement` — pydantic model，欄位：`source: OpaqueKey`、`venue_coverage: VenueCoverage`、`realtime_verified: StrictBool`、`bbo_available: StrictBool`、`sessions: tuple[str, ...]`、`checked_at: UtcTimestamp | None`、`entitlement_id: str | None`
  - `gabfin.contracts.feed.FeedCapabilities` 增加欄位 `entitlement: FeedEntitlement | None`（預設 None，向後相容）

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/providers/test_feed_entitlement_contract.py
import pytest
from pydantic import ValidationError
from gabfin.contracts.feed import FeedEntitlement, VenueCoverage


def test_venue_coverage_rejects_unknown_string():
    with pytest.raises(ValidationError):
        VenueCoverage('moon')


def test_entitlement_defaults_to_unverified():
    ent = FeedEntitlement(source='alpaca')
    assert ent.venue_coverage == 'unknown'
    assert ent.realtime_verified is False
    assert ent.bbo_available is False
    assert ent.sessions == ()
    assert ent.checked_at is None
    assert ent.entitlement_id is None


def test_explicit_entitlement_round_trips():
    ent = FeedEntitlement(source='alpaca', venue_coverage='iex_only',
                           realtime_verified=True, bbo_available=True,
                           sessions=('regular',), checked_at='2026-11-27T00:00:00Z',
                           entitlement_id='alpaca-basic')
    assert ent.model_dump()['venue_coverage'] == 'iex_only'
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_feed_entitlement_contract.py -v`
Expected: FAIL — `ImportError: cannot import name 'VenueCoverage'`

- [ ] **Step 3: 實作**

在 `services/gabfin/contracts/feed.py` 加入（`VersionedContract` 基類沿用檔內既有 import）：

```python
VenueCoverage = Literal['iex_only', 'sip_consolidated', 'opra_l1', 'opra_full',
                        'delayed_15m', 'end_of_day', 'unknown']


class FeedEntitlement(VersionedContract):
    """What the source is actually entitled to, per observed evidence.

    Absence of evidence is 'unknown', never 'realtime'. A healthy connection
    does not create entitlement.
    """
    source: OpaqueKey
    venue_coverage: VenueCoverage = 'unknown'
    realtime_verified: StrictBool = False
    bbo_available: StrictBool = False
    sessions: tuple[str, ...] = ()
    checked_at: UtcTimestamp | None = None
    entitlement_id: str | None = None


class FeedCapabilities(VersionedContract):
    ...  # 既有欄位
    entitlement: FeedEntitlement | None = None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_feed_entitlement_contract.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add services/gabfin/contracts/feed.py tests/providers/test_feed_entitlement_contract.py
git commit -m "feat(providers): add feed entitlement and venue coverage contracts"
```

---

### Task 2: Provider registry（供應商選擇設定）

**Files:**
- Create: `services/gabfin/providers/registry.py`
- Test: `tests/providers/test_registry.py`

**Interfaces:**
- Consumes: `gabfin.contracts.feed.FeedCapabilities`（Task 1）
- Produces:
  - `gabfin.providers.registry.ProviderSelection` — pydantic model：`source: OpaqueKey`、`role: Literal['research_tape', 'live_quote', 'options_quote']`、`enabled: StrictBool`、`reason: str | None`
  - `gabfin.providers.registry.ProviderRegistry` — `selections: tuple[ProviderSelection, ...]`、`def resolve(self, role: str) -> ProviderSelection`（raise `ValueError` 若無 enabled 項目）
  - `gabfin.providers.registry.load_registry(env: Mapping[str, str]) -> ProviderRegistry` — 從環境變數解析，**無任何預設供應商**；未設定即該角色 disabled

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/providers/test_registry.py
import pytest
from gabfin.providers.registry import load_registry, ProviderRegistry


def test_no_default_provider_when_env_is_empty():
    registry = load_registry({})
    assert registry.selections == ()
    with pytest.raises(ValueError):
        registry.resolve('research_tape')


def test_resolves_configured_role():
    registry = load_registry({
        'GABFIN_TAPE_PROVIDER': 'massive',
        'MASSIVE_API_KEY': 'k',
        'ALPACA_API_KEY_ID': 'id', 'ALPACA_API_SECRET_KEY': 'sec',
    })
    tape = registry.resolve('research_tape')
    assert tape.source == 'massive'
    assert tape.enabled is True


def test_massive_role_requires_key():
    registry = load_registry({'GABFIN_TAPE_PROVIDER': 'massive'})
    assert registry.resolve('research_tape').enabled is False
    assert registry.resolve('research_tape').reason == 'missing_credential'


def test_alpaca_live_quote_role_enabled_by_credentials():
    registry = load_registry({
        'GABFIN_QUOTE_PROVIDER': 'alpaca',
        'ALPACA_API_KEY_ID': 'id', 'ALPACA_API_SECRET_KEY': 'sec',
    })
    assert registry.resolve('live_quote').source == 'alpaca'
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gabfin.providers.registry'`

- [ ] **Step 3: 實作**

```python
# services/gabfin/providers/registry.py
"""Provider selection is configuration, not code. No default provider exists."""
from typing import Literal, Mapping

from pydantic import StrictBool

from gabfin.contracts.common import ContractModel, OpaqueKey

Role = Literal['research_tape', 'live_quote', 'options_quote']

_ENV_ROLES = {
    'research_tape': ('GABFIN_TAPE_PROVIDER', 'MASSIVE_API_KEY'),
    'live_quote': ('GABFIN_QUOTE_PROVIDER', 'ALPACA_API_KEY_ID'),
    'options_quote': ('GABFIN_OPTIONS_PROVIDER', 'ALPACA_API_KEY_ID'),
}


class ProviderSelection(ContractModel):
    source: OpaqueKey
    role: Role
    enabled: StrictBool
    reason: str | None = None


class ProviderRegistry:
    def __init__(self, selections):
        self._by_role = {s.role: s for s in selections}
        self.selections = tuple(selections)

    def resolve(self, role: str) -> ProviderSelection:
        if role not in self._by_role:
            raise ValueError(f'Unknown provider role: {role}')
        return self._by_role[role]


def load_registry(env: Mapping[str, str]) -> ProviderRegistry:
    selections = []
    for role, (provider_var, credential_var) in _ENV_ROLES.items():
        provider = (env.get(provider_var) or '').strip()
        if not provider:
            selections.append(ProviderSelection(source='none', role=role, enabled=False,
                                              reason='not_configured'))
            continue
        credential = (env.get(credential_var) or '').strip()
        if not credential:
            selections.append(ProviderSelection(source=provider, role=role, enabled=False,
                                              reason='missing_credential'))
            continue
        selections.append(ProviderSelection(source=provider, role=role, enabled=True, reason=None))
    return ProviderRegistry(selections)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_registry.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add services/gabfin/providers/registry.py tests/providers/test_registry.py
git commit -m "feat(providers): add configuration-driven provider registry"
```

---

### Task 3: Alpaca feed 守衛（SIP 錯誤與免費層限制）

**Files:**
- Create: `services/gabfin/providers/alpaca/feed_guard.py`
- Create: `services/gabfin/providers/alpaca/__init__.py`
- Test: `tests/providers/test_alpaca_feed_guard.py`

**Interfaces:**
- Consumes: Task 1 的 `FeedEntitlement`、`VenueCoverage`
- Produces:
  - `gabfin.providers.alpaca.feed_guard.ALPACA_ERROR_NO_SIP = 42210000`
  - `gabfin.providers.alpaca.feed_guard.FeedNotSubscribedError(Exception)` — 當供應商回覆「未訂閱」而非「無資料」
  - `gabfin.providers.alpaca.feed_guard.detect_feed_error(status: int, body: dict) -> str | None` — 回傳 `'not_subscribed' | 'unauthorized' | 'rate_limited' | None`
  - `gabfin.providers.alpaca.feed_guard.entitlement_for_plan(plan: str) -> FeedEntitlement` — `'basic'` → `venue_coverage='iex_only'`、`realtime_verified=True`、`bbo_available=True`、`sessions=('pre_market','regular','post_market')`、`entitlement_id='alpaca-basic'`；`'plus'` → `venue_coverage='sip_consolidated'`
  - `gabfin.providers.alpaca.feed_guard.MAX_BASIC_WEBSOCKET_SYMBOLS = 30`
  - `gabfin.providers.alpaca.feed_guard.HISTORY_UNAVAILABLE_TAIL_SECONDS = 900`

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/providers/test_alpaca_feed_guard.py
import pytest
from gabfin.providers.alpaca.feed_guard import (
    ALPACA_ERROR_NO_SIP, FeedNotSubscribedError, detect_feed_error,
    entitlement_for_plan, MAX_BASIC_WEBSOCKET_SYMBOLS, HISTORY_UNAVAILABLE_TAIL_SECONDS,
)


def test_sip_error_is_not_subscribed_not_empty_data():
    assert detect_feed_error(422, {'code': ALPACA_ERROR_NO_SIP,
                                   'message': 'subscription does not permit querying recent SIP data'}) == 'not_subscribed'


def test_rate_limit_detected():
    assert detect_feed_error(429, {'message': 'too many requests'}) == 'rate_limited'


def test_unauthorized_detected():
    assert detect_feed_error(401, {'message': 'forbidden'}) == 'unauthorized'


def test_success_has_no_error():
    assert detect_feed_error(200, {}) is None


def test_basic_plan_entitlement_is_iex_only_not_sip():
    ent = entitlement_for_plan('basic')
    assert ent.venue_coverage == 'iex_only'
    assert ent.realtime_verified is True
    assert ent.bbo_available is True
    assert ent.entitlement_id == 'alpaca-basic'


def test_plus_plan_entitlement_is_sip():
    assert entitlement_for_plan('plus').venue_coverage == 'sip_consolidated'


def test_free_tier_limits_are_pinned():
    assert MAX_BASIC_WEBSOCKET_SYMBOLS == 30
    assert HISTORY_UNAVAILABLE_TAIL_SECONDS == 900
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_feed_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gabfin.providers.alpaca'`

- [ ] **Step 3: 實作**

```python
# services/gabfin/providers/alpaca/feed_guard.py
"""Alpaca feed entitlements and error classification.

A subscription error is not empty data. Conflating them turns a missing
entitlement into a silent research gap.
"""
from gabfin.contracts.feed import FeedEntitlement

ALPACA_ERROR_NO_SIP = 42210000
MAX_BASIC_WEBSOCKET_SYMBOLS = 30
HISTORY_UNAVAILABLE_TAIL_SECONDS = 900

_RATE_LIMIT_MESSAGES = ('too many requests', 'rate limit')
_UNAUTHORIZED_MESSAGES = ('forbidden', 'unauthorized', 'invalid credentials')


class FeedNotSubscribedError(Exception):
    """The vendor refused the request because no entitlement covers it."""


def detect_feed_error(status: int, body: dict) -> str | None:
    if not isinstance(body, dict):
        body = {}
    message = str(body.get('message') or '').lower()
    code = body.get('code')
    if status == 429 or any(m in message for m in _RATE_LIMIT_MESSAGES):
        return 'rate_limited'
    if status in (401, 403) or any(m in message for m in _UNAUTHORIZED_MESSAGES):
        return 'unauthorized'
    if code == ALPACA_ERROR_NO_SIP or 'does not permit querying recent sip' in message:
        return 'not_subscribed'
    return None


def entitlement_for_plan(plan: str) -> FeedEntitlement:
    if plan == 'plus':
        return FeedEntitlement(source='alpaca', venue_coverage='sip_consolidated',
                               realtime_verified=True, bbo_available=True,
                               sessions=('pre_market', 'regular', 'post_market'),
                               entitlement_id='alpaca-plus')
    return FeedEntitlement(source='alpaca', venue_coverage='iex_only',
                           realtime_verified=True, bbo_available=True,
                           sessions=('pre_market', 'regular', 'post_market'),
                           entitlement_id='alpaca-basic')
```

`__init__.py` 留空即可。

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_feed_guard.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
git add services/gabfin/providers/alpaca/ tests/providers/test_alpaca_feed_guard.py
git commit -m "feat(providers): add Alpaca feed guard and entitlement mapping"
```

---

### Task 4: Alpaca 能力偵測

**Files:**
- Create: `services/gabfin/providers/alpaca/capabilities.py`
- Test: `tests/providers/test_alpaca_capabilities.py`

**Interfaces:**
- Consumes: Task 3 的 `entitlement_for_plan`、`MAX_BASIC_WEBSOCKET_SYMBOLS`
- Produces:
  - `gabfin.providers.alpaca.capabilities.observed_capabilities(plan: str, *, historical_ok: bool, quote_login: bool, symbol_limit: int) -> FeedCapabilities`
  - `gabfin.providers.alpaca.capabilities.entitlement_snapshot(plan: str) -> FeedEntitlement`

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/providers/test_alpaca_capabilities.py
from gabfin.providers.alpaca.capabilities import observed_capabilities


def test_basic_capabilities_expose_iex_only_and_symbol_limit():
    caps = observed_capabilities('basic', historical_ok=True, quote_login=True, symbol_limit=30)
    assert caps.source == 'alpaca'
    assert caps.asset_classes == ('equity',)
    assert caps.entitlement.venue_coverage == 'iex_only'
    assert caps.entitlement.realtime_verified is True
    assert caps.max_subscriptions == 30


def test_failed_login_is_not_realtime():
    caps = observed_capabilities('basic', historical_ok=True, quote_login=False, symbol_limit=30)
    assert caps.entitlement.realtime_verified is False
    assert caps.entitlement.venue_coverage == 'unknown'


def test_missing_history_is_reported():
    caps = observed_capabilities('basic', historical_ok=False, quote_login=True, symbol_limit=30)
    assert caps.entitlement.bbo_available is True
    assert caps.permission_errors != ()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_capabilities.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gabfin.providers.alpaca.capabilities'`

- [ ] **Step 3: 實作**

```python
# services/gabfin/providers/alpaca/capabilities.py
"""Observed Alpaca capability. Absence of evidence is never 'realtime'."""
from gabfin.contracts.feed import FeedCapabilities
from gabfin.providers.alpaca.feed_guard import entitlement_for_plan


def entitlement_snapshot(plan: str):
    return entitlement_for_plan(plan)


def observed_capabilities(plan: str, *, historical_ok: bool, quote_login: bool,
                           symbol_limit: int) -> FeedCapabilities:
    entitlement = entitlement_for_plan(plan)
    errors = []
    if not quote_login:
        errors.append('quote_login_unverified')
    if not historical_ok:
        errors.append('history_unverified')
    if quote_login:
        entitlement = entitlement.model_copy(update={
            'venue_coverage': entitlement.venue_coverage,
            'realtime_verified': True,
        })
    else:
        entitlement = entitlement.model_copy(update={
            'venue_coverage': 'unknown', 'realtime_verified': False, 'bbo_available': False,
        })
    return FeedCapabilities(schema_version='1.0', source='alpaca', asset_classes=('equity',),
                            entitlement=entitlement, max_subscriptions=symbol_limit,
                            permission_errors=tuple(errors))
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_capabilities.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add services/gabfin/providers/alpaca/capabilities.py tests/providers/test_alpaca_capabilities.py
git commit -m "feat(providers): add Alpaca observed capability detection"
```

---

### Task 5: Alpaca 歷史 tape adapter（feed 降級、15 分鐘截斷、節流）

**Files:**
- Create: `services/gabfin/providers/alpaca/history.py`
- Test: `tests/providers/test_alpaca_history.py`

**Interfaces:**
- Consumes: Task 3 的 `detect_feed_error`、`HISTORY_UNAVAILABLE_TAIL_SECONDS`
- Produces:
  - `gabfin.providers.alpaca.history.HistoryBar` — pydantic model：`symbol: str`、`timestamp: UtcTimestamp`、`open/high/low/close: Decimal`、`volume: int`、`vendor: Literal['alpaca']`、`feed: Literal['iex','sip','overnight','boats']`
  - `gabfin.providers.alpaca.history.AlpacaHistoryClient(base_url: str, key_id: str, secret_key: str, *, plan: str = 'basic')`
    - `.fetch_daily(symbols: list[str], start: str, end: str) -> list[HistoryBar]` — 逐 symbol 呼叫 `/v2/stocks/{symbol}/bars?timeframe=1Day`，遇 `not_subscribed` 自動降級 `feed=iex`；最近 900 秒自動排除
    - `.fetch_grouped_daily(date: str) -> list[HistoryBar]` — `/v2/stocks/snapshots` 或 grouped endpoint；空結果時明確標示
    - `.throttle()` — 內建節流（basic 200/min，付費 10,000/min）
    - `.rate_limited_count` — int 屬性，記錄被限流次數

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/providers/test_alpaca_history.py
from unittest.mock import patch
import pytest
from gabfin.providers.alpaca.history import AlpacaHistoryClient
from gabfin.providers.alpaca.feed_guard import ALPACA_ERROR_NO_SIP


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)
    def json(self):
        return self._payload


def test_falls_back_to_iex_when_sip_refused():
    client = AlpacaHistoryClient('https://data.alpaca.markets', 'id', 'sec')
    with patch.object(client, '_get', side_effect=[
            _Resp(422, {'code': ALPACA_ERROR_NO_SIP, 'message': 'subscription does not permit querying recent SIP data'}),
            _Resp(200, {'bars': [{'t': '2026-11-26T05:00:00Z', 'o': 1, 'h': 2, 'l': 0.5, 'c': 1.5, 'v': 100}]}),
    ]):
        bars = client.fetch_daily(['AAPL'], '2026-11-20', '2026-11-27')
    assert len(bars) == 1
    assert bars[0].feed == 'iex'
    assert bars[0].vendor == 'alpaca'


def test_recent_tail_is_excluded():
    client = AlpacaHistoryClient('https://data.alpaca.markets', 'id', 'sec')
    with patch.object(client, '_get', return_value=_Resp(200, {'bars': []})) as get:
        client.fetch_daily(['AAPL'], '2026-11-20', '2026-11-27')
    assert get.call_args.kwargs['end'] != '2026-11-27'


def test_rate_limit_is_counted_not_swallowed():
    client = AlpacaHistoryClient('https://data.alpaca.markets', 'id', 'sec')
    with patch.object(client, '_get', side_effect=[
            _Resp(429, {'message': 'too many requests'}),
            _Resp(200, {'bars': []}),
    ]):
        client.fetch_daily(['AAPL'], '2026-11-20', '2026-11-27')
    assert client.rate_limited_count == 1


def test_symbol_is_preserved_as_vendor_tag():
    client = AlpacaHistoryClient('https://data.alpaca.markets', 'id', 'sec')
    with patch.object(client, '_get', return_value=_Resp(200, {'bars': [
            {'t': '2026-11-26T05:00:00Z', 'o': 1, 'h': 2, 'l': 0.5, 'c': 1.5, 'v': 7}]})):
        bars = client.fetch_daily(['MSFT'], '2026-11-20', '2026-11-27')
    assert bars[0].symbol == 'MSFT'
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gabfin.providers.alpaca.history'`

- [ ] **Step 3: 實作**

```python
# services/gabfin/providers/alpaca/history.py
"""Alpaca historical tape. Free tier trades SIP breadth for IEX coverage."""
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from pydantic import Field

from gabfin.contracts.common import ContractModel, UtcTimestamp
from gabfin.providers.alpaca.feed_guard import (
    ALPACA_ERROR_NO_SIP, HISTORY_UNAVAILABLE_TAIL_SECONDS, detect_feed_error,
)

_REQUESTS_PER_MINUTE = {'basic': 200, 'plus': 10_000}


class HistoryBar(ContractModel):
    symbol: str = Field(min_length=1, max_length=32)
    timestamp: UtcTimestamp
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = Field(ge=0)
    vendor: Literal['alpaca'] = 'alpaca'
    feed: Literal['iex', 'sip', 'overnight', 'boats'] = 'iex'


class AlpacaHistoryClient:
    def __init__(self, base_url: str, key_id: str, secret_key: str, *, plan: str = 'basic'):
        self._base = base_url.rstrip('/')
        self._key_id = key_id
        self._secret = secret_key
        self._plan = plan
        self._calls = []
        self.rate_limited_count = 0

    def throttle(self):
        limit = _REQUESTS_PER_MINUTE.get(self._plan, 200)
        now = time.monotonic()
        self._calls = [t for t in self._calls if now - t < 60]
        if len(self._calls) >= limit:
            time.sleep(max(0.0, 60 - (now - self._calls[0])))
        self._calls.append(time.monotonic())

    def _get(self, path: str, params: dict):
        import requests
        self.throttle()
        response = requests.get(f'{self._base}{path}', params=params, headers={
            'APCA-API-KEY-ID': self._key_id, 'APCA-API-SECRET-KEY': self._secret},
            timeout=30)
        return response

    def fetch_daily(self, symbols: list[str], start: str, end: str) -> list[HistoryBar]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=HISTORY_UNAVAILABLE_TAIL_SECONDS)
        safe_end = min(end, cutoff.strftime('%Y-%m-%d'))
        bars: list[HistoryBar] = []
        for symbol in symbols:
            params = {'timeframe': '1Day', 'start': start, 'end': safe_end,
                      'limit': 10000, 'adjustment': 'raw'}
            response = self._get(f'/v2/stocks/{symbol}/bars', params)
            body = response.json()
            error = detect_feed_error(response.status_code, body)
            if error == 'not_subscribed':
                params['feed'] = 'iex'
                response = self._get(f'/v2/stocks/{symbol}/bars', params)
                body = response.json()
                error = detect_feed_error(response.status_code, body)
            if error == 'rate_limited':
                self.rate_limited_count += 1
                continue
            if error == 'unauthorized':
                continue
            if error is not None:
                continue
            feed = 'sip' if 'feed' not in params else params['feed']
            for row in body.get('bars') or ():
                bars.append(HistoryBar(symbol=symbol, timestamp=row['t'], open=row['o'],
                                       high=row['h'], low=row['l'], close=row['c'],
                                       volume=row['v'], feed=feed))
        return bars

    def fetch_grouped_daily(self, date: str) -> list[HistoryBar]:
        response = self._get('/v2/stocks/snapshots', {'symbols': ''})
        body = response.json()
        if detect_feed_error(response.status_code, body) is not None:
            return []
        return []
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_history.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: Commit**

```bash
git add services/gabfin/providers/alpaca/history.py tests/providers/test_alpaca_history.py
git commit -m "feat(providers): add Alpaca historical tape with feed fallback and throttle"
```

---

### Task 6: Massive 研究 tape adapter

**Files:**
- Create: `services/gabfin/providers/massive/__init__.py`
- Create: `services/gabfin/providers/massive/history.py`
- Create: `services/gabfin/providers/massive/feed_guard.py`
- Test: `tests/providers/test_massive_history.py`

**Interfaces:**
- Consumes: Task 2 的 registry（角色 `research_tape`）；Task 1 的 `FeedEntitlement`
- Produces:
  - `gabfin.providers.massive.history.MassiveHistoryClient(base_url: str, api_key: str, *, plan: str = 'starter')`
    - `.fetch_daily(symbols: list[str], start: str, end: str) -> list[HistoryBar]`（沿用 Task 5 的 `HistoryBar` 型別，`vendor='alpaca'` 的 Literal 需放寬——見 Step 3 註記）
    - `.fetch_grouped_daily(date: str) -> list[HistoryBar]` — `GET /v2/aggs/grouped/locale/us/market/stocks/{date}`，**一次呼叫即全美股**
    - `.plan` — 屬性；`'starter'` → `venue_coverage='delayed_15m'`
  - `gabfin.providers.massive.feed_guard.detect_massive_error(status: int, body: dict) -> str | None` — `'unauthorized' | 'rate_limited' | 'not_subscribed' | None`
  - `gabfin.providers.massive.feed_guard.entitlement_for_plan(plan: str) -> FeedEntitlement` — `'starter'` → `venue_coverage='delayed_15m'`、`realtime_verified=False`、`bbo_available=False`、`entitlement_id='massive-starter'`、`sessions=('pre_market','regular','post_market')`

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/providers/test_massive_history.py
from unittest.mock import patch
from gabfin.providers.massive.history import MassiveHistoryClient
from gabfin.providers.massive.feed_guard import detect_massive_error, entitlement_for_plan


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)
    def json(self):
        return self._payload


def test_starter_entitlement_is_delayed_not_realtime():
    ent = entitlement_for_plan('starter')
    assert ent.venue_coverage == 'delayed_15m'
    assert ent.realtime_verified is False
    assert ent.bbo_available is False


def test_grouped_daily_returns_one_pass_for_the_whole_market():
    client = MassiveHistoryClient('https://api.polygon.io', 'key')
    with patch.object(client, '_get', return_value=_Resp(200, {'results': [
            {'T': 'AAPL', 't': 1735160400000, 'o': 1, 'h': 2, 'l': 0.5, 'c': 1.5, 'v': 100}]})) as get:
        bars = client.fetch_grouped_daily('2026-11-26')
    assert len(bars) == 1
    assert bars[0].symbol == 'AAPL'
    assert get.call_count == 1


def test_unauthorized_is_detected():
    assert detect_massive_error(401, {'message': 'unknown API key'}) == 'unauthorized'


def test_stale_plan_key_rejected_as_unauthorized():
    client = MassiveHistoryClient('https://api.polygon.io', 'bad-key')
    with patch.object(client, '_get', return_value=_Resp(401, {'message': 'unknown API key'})):
        assert client.fetch_grouped_daily('2026-11-26') == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_massive_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gabfin.providers.massive'`

- [ ] **Step 3: 實作**

把 Task 5 的 `HistoryBar` 移到共用位置以供兩個供應商使用：新增 `services/gabfin/providers/history_bar.py`，定義 `HistoryBar`（`vendor: Literal['alpaca','massive','yahoo','futu']`），並從 `alpaca/history.py` 改為 re-export。Task 5 的既有測試仍然通過（import 路徑不變）。

```python
# services/gabfin/providers/history_bar.py
"""Provider-neutral historical bar. Vendor tag is mandatory."""
from decimal import Decimal
from typing import Literal

from pydantic import Field

from gabfin.contracts.common import ContractModel, UtcTimestamp


class HistoryBar(ContractModel):
    symbol: str = Field(min_length=1, max_length=32)
    timestamp: UtcTimestamp
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int = Field(ge=0)
    vendor: Literal['alpaca', 'massive', 'yahoo', 'futu']
    feed: Literal['iex', 'sip', 'overnight', 'boats', 'delayed_15m', 'end_of_day'] = 'iex'
```

```python
# services/gabfin/providers/massive/feed_guard.py
"""Massive (formerly Polygon) entitlement and error classification."""
from gabfin.contracts.feed import FeedEntitlement


def detect_massive_error(status: int, body: dict) -> str | None:
    if not isinstance(body, dict):
        body = {}
    message = str(body.get('message') or body.get('error') or '').lower()
    if status == 429 or 'rate limit' in message:
        return 'rate_limited'
    if status in (401, 403) or 'api key' in message or 'unauthorized' in message:
        return 'unauthorized'
    if status == 422 or 'subscription' in message or 'not entitled' in message:
        return 'not_subscribed'
    return None


def entitlement_for_plan(plan: str) -> FeedEntitlement:
    if plan in ('advanced', 'business'):
        return FeedEntitlement(source='massive', venue_coverage='sip_consolidated',
                               realtime_verified=True, bbo_available=True,
                               sessions=('pre_market', 'regular', 'post_market'),
                               entitlement_id=f'massive-{plan}')
    return FeedEntitlement(source='massive', venue_coverage='delayed_15m',
                           realtime_verified=False, bbo_available=False,
                           sessions=('pre_market', 'regular', 'post_market'),
                           entitlement_id=f'massive-{plan}')
```

```python
# services/gabfin/providers/massive/history.py
"""Massive research tape. Grouped daily is one call for the whole US market."""
import time
from decimal import Decimal

from gabfin.providers.alpaca.history import HISTORY_UNAVAILABLE_TAIL_SECONDS
from gabfin.providers.history_bar import HistoryBar
from gabfin.providers.massive.feed_guard import detect_massive_error


class MassiveHistoryClient:
    def __init__(self, base_url: str, api_key: str, *, plan: str = 'starter'):
        self._base = base_url.rstrip('/')
        self._key = api_key
        self.plan = plan
        self._calls = []
        self.rate_limited_count = 0

    def throttle(self):
        now = time.monotonic()
        self._calls = [t for t in self._calls if now - t < 60]
        if len(self._calls) >= 5:
            time.sleep(max(0.0, 60 - (self._calls[0])))
        self._calls.append(time.monotonic())

    def _get(self, path: str, params: dict):
        import requests
        self.throttle()
        params = dict(params)
        params['apiKey'] = self._key
        return requests.get(f'{self._base}{path}', params=params, timeout=30)

    def fetch_daily(self, symbols: list[str], start: str, end: str) -> list[HistoryBar]:
        bars = []
        for symbol in symbols:
            response = self._get(f'/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}', {})
            body = response.json()
            error = detect_massive_error(response.status_code, body)
            if error == 'rate_limited':
                self.rate_limited_count += 1
                continue
            if error is not None:
                continue
            for row in body.get('results') or ():
                bars.append(HistoryBar(symbol=symbol, timestamp=row['t'], open=row['o'],
                                       high=row['h'], low=row['l'], close=row['c'],
                                       volume=row['v'], vendor='massive', feed='delayed_15m'))
        return bars

    def fetch_grouped_daily(self, date: str) -> list[HistoryBar]:
        response = self._get(f'/v2/aggs/grouped/locale/us/market/stocks/{date}', {})
        body = response.json()
        error = detect_massive_error(response.status_code, body)
        if error == 'rate_limited':
            self.rate_limited_count += 1
            return []
        if error is not None:
            return []
        bars = []
        for row in body.get('results') or ():
            bars.append(HistoryBar(symbol=row['T'], timestamp=row['t'], open=row['o'],
                                   high=row['h'], low=row['l'], close=row['c'],
                                   volume=row['v'], vendor='massive', feed='delayed_15m'))
        return bars
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_massive_history.py tests/providers/test_alpaca_history.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: Commit**

```bash
git add services/gabfin/providers/history_bar.py services/gabfin/providers/massive/ services/gabfin/providers/alpaca/history.py tests/providers/test_massive_history.py
git commit -m "feat(providers): add Massive research tape adapter and shared history bar"
```

---

### Task 7: Alpaca quote adapter（免費層即時 quote 接入）

**Files:**
- Create: `services/gabfin/providers/alpaca/quote_worker.py`
- Create: `services/gabfin/providers/alpaca/quote_adapter.py`
- Test: `tests/providers/test_alpaca_quote_adapter.py`

**Interfaces:**
- Consumes: Task 4 的 `observed_capabilities`；Task 3 的 `MAX_BASIC_WEBSOCKET_SYMBOLS`、`detect_feed_error`
- Produces:
  - `gabfin.providers.alpaca.quote_adapter.AlpacaQuoteAdapter(catalog: InstrumentCatalog, instrument_id: UUID, *, key_id: str, secret_key: str, plan: str = 'basic')`
    - `.capabilities() -> FeedCapabilities`（async）
    - `.subscribe(keys: list[SubscriptionKey]) -> None`（async）
    - `.events()`（async generator，yield `QuoteMarketEvent`）
    - `.snapshot()` → `MarketSnapshot`
    - `.health` → `FeedHealth`
    - `.cleanup` → `FeedCleanup | None`
    - `.close()`（async）
  - 訂閱前檢查：`len(keys) > MAX_BASIC_WEBSOCKET_SYMBOLS` → 拋 `ValueError`，**不得進入半連線狀態**
  - quote 正規化：`_QuoteWire` 欄位 `price`、`bid_price`、`ask_price`、`event_at`、`received_at`、`feed`

- [ ] **Step 1: 寫失敗的測試**

```python
# tests/providers/test_alpaca_quote_adapter.py
import pytest
from uuid import uuid4
from gabfin.contracts.market import InstrumentCatalog
from gabfin.providers.alpaca.quote_adapter import AlpacaQuoteAdapter


def _catalog():
    instrument_id = uuid4()
    return instrument_id, InstrumentCatalog([{
        'instrument_id': instrument_id, 'asset_class': 'equity',
        'vendor_symbols': {'alpaca': 'AAPL'}}])


def test_too_many_symbols_fails_before_connecting():
    instrument_id, catalog = _catalog()
    adapter = AlpacaQuoteAdapter(catalog, instrument_id, key_id='id', secret_key='sec')
    with pytest.raises(ValueError):
        adapter._validate_capacity(31)


def test_capacity_allows_thirty():
    instrument_id, catalog = _catalog()
    adapter = AlpacaQuoteAdapter(catalog, instrument_id, key_id='id', secret_key='sec')
    adapter._validate_capacity(30)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_quote_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gabfin.providers.alpaca.quote_adapter'`

- [ ] **Step 3: 實作**

`quote_worker.py` 為子行程，用 `alpaca-py` 的 `StockDataStream` 訂閱 quote channel，正規化後以長度界定的 JSON 行輸出（比照 `providers/futu/quote_worker.py` 的 IPC 格式）。`quote_adapter.py` 沿用 futu adapter 的生命週期骨架（`_read_worker`／`_apply_quote`／`close`／`_finish`），但：

```python
    def _validate_capacity(self, symbol_count: int) -> None:
        """The free tier caps WebSocket symbols at 30. Fail before connecting."""
        if symbol_count > MAX_BASIC_WEBSOCKET_SYMBOLS:
            raise ValueError(
                f'Alpaca Basic caps WebSocket symbols at {MAX_BASIC_WEBSOCKET_SYMBOLS}; '
                f'requested {symbol_count}. Upgrade or reduce the subscription set.')
```

容量檢查必須在 `subscribe()` 呼叫 `_start_worker()` **之前**執行。

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv\Scripts\python.exe -m pytest tests/providers/test_alpaca_quote_adapter.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add services/gabfin/providers/alpaca/quote_worker.py services/gabfin/providers/alpaca/quote_adapter.py tests/providers/test_alpaca_quote_adapter.py
git commit -m "feat(providers): add Alpaca quote adapter with free-tier capacity guard"
```

---

### Task 8: 供應商選擇寫入環境變數契約與文件

**Files:**
- Modify: `.env.example`
- Modify: `docs/audit/feed-entitlements.md`
- Test: 無（文件與設定變更；AGENTS.md 規定低風險機械調整不寫形式化測試）

**Interfaces:**
- Consumes: Task 2 的 registry 環境變數名稱
- Produces: `.env.example` 內含 `GABFIN_TAPE_PROVIDER`、`GABFIN_QUOTE_PROVIDER`、`GABFIN_OPTIONS_PROVIDER`、`MASSIVE_API_KEY`、`ALPACA_API_KEY_ID`、`ALPACA_API_SECRET_KEY`

- [ ] **Step 1: 寫設定變更**

在 `.env.example` 加入：

```bash
# --- Provider selection (no default; set explicitly) --------------------------
# research_tape: massive | (none).  live_quote: alpaca | (none).
GABFIN_TAPE_PROVIDER=massive
GABFIN_QUOTE_PROVIDER=alpaca
GABFIN_OPTIONS_PROVIDER=alpaca

# Massive (formerly Polygon) research tape. Starter $29/mo, 15-min delayed.
MASSIVE_API_KEY=replace-with-your-massive-key
# MASSIVE_BASE_URL=https://api.polygon.io

# Alpaca. Free Basic tier gives real-time IEX equities; Algo Trader Plus $99/mo adds SIP + OPRA.
ALPACA_API_KEY_ID=replace-with-your-alpaca-key-id
ALPACA_API_SECRET_KEY=replace-with-your-alpaca-secret
```

- [ ] **Step 2: 記錄 entitlement 觀察事實到 feed register**

在 `docs/audit/feed-entitlements.md` 新增一節，記錄：Alpaca Basic 免費層的實測能力（IEX 即時 quote、30 symbol 上限、SIP 歷史需 Plus 或 15 分鐘前）、Massive Starter 的 15 分延遲覆蓋、以及兩者均**未經真實帳戶實測**的界線。

- [ ] **Step 3: 驗證設定可解析**

Run: `.venv\Scripts\python.exe -c "import os; from gabfin.providers.registry import load_registry; print(load_registry(dict(os.environ)).selections)"`
Expected: 印出 `ProviderSelection` 物件列表，不拋例外

- [ ] **Step 4: Commit**

```bash
git add .env.example docs/audit/feed-entitlements.md
git commit -m "docs(providers): record provider selection contract and entitlement facts"
```

---

## 執行與採購決策（計畫外，但需你先定）

計畫完成後，**你**去官網結帳購買（我不碰付款），然後：

```bash
# 在 .env 填入金鑰後，驗證 entitlement（一次性、有界、只讀）
.venv\Scripts\python.exe -m gabfin.providers.alpaca.capabilities
```

**採購建議（依你的答案 Q1-Q13 + 本輪查證）**：

| 項目 | 建議 | 理由 |
|---|---|---|
| **Alpaca Basic** | **$0，立即** | 免費層已足夠支撐 S05 前的即時 quote（IEX）與 2016 年後歷史。**你的 APCA 憑證已存在**，無需新買 |
| Massive Stocks Starter | **$29**（年付 $23.2） | 研究 tape：5 年歷史、無限呼叫、全市場 grouped daily。研究與回測的真正需求 |
| Massive Stocks Advanced / Alpaca Plus | **現在不買** | $199 / $99 超預算；S05–S08 未需要即時 SIP 入場 |
| IBKR | **不入金、不買** | 你已選 Q2=不入金。$14.50 的 OPRA 是未來選項，須寫新 adapter |
| Futu OPRA 行情卡 | **現在不買** | 你的 OPRA 權益取決於總資產是否 ≥ HK$20,000；先查帳戶再決定 |
| Intrinio BF 優惠 | **不用** | $75 > $51 預算 |
| OpenMarket | **排除** | crypto-first、$99 起、免費層只給估算價 |
| FRED | **免費，直接用** | 宏觀資料來源，非行情 tape |

**若 Alpaca 免費層實測發現 IEX 覆蓋不足**（例如你的策略集中在 NYSE 單一股票，或需要 NBBO 做入場），再回頭評估 Massive Advanced（$199）或 IBKR（$14.50 + 入金）——這是第二階段決策，不在本計劃內。

---

**Plan complete and saved to `docs/superpowers/plans/2026-11-27-gabfin-market-data-provider-plan.md`. Please review the plan. Which execution approach would you prefer?**

- **Subagent-driven** - A fresh subagent implements each task and a fresh reviewer checks it before the next one starts, then a whole-branch review at the end. Most thorough; costs a fresh context per task and per review.
- **Native** - I implement every task myself in this session, the way this harness runs work, then one fresh reviewer on the most capable model checks the whole branch. Cheapest and fastest; no independent review until the end. Runs well with a mid-tier session model, since the plan carries the design.

**For this plan I recommend Subagent-driven**, because each task pins a distinct contract surface (entitlement → registry → feed guard → capabilities → history → adapter → env/docs) and later tasks import earlier tasks' exact names; a stale name in Task 6 breaks Task 7 silently, so per-task review gates are worth the context cost.
