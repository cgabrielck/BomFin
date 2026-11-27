# GabFin Massive-First 架构设计（2026-11-27）

## 执行摘要

**关键决策**：用户明确选择 **Massive WebSocket** 作为主行情源，取代 Futu OpenD。这简化了行情源管理，并对齐用户 HK$400 月度预算（Massive Starter $29/月）。

| 层级 | 现状 | 新决策 |
|---|---|---|
| 行情源 | Futu + Massive（双源） | **Massive WebSocket（单源）** |
| 推送方式 | Futu SDK 进程 + REST fallback | Massive native WebSocket + REST fallback |
| 架构模式 | 多 provider adapter | 单一 Massive adapter，可扩展多 underlying |
| 重写范围 | 保留 Futu adapter | 彻底改写 `services/gabfin/market/feed/` |

---

## 1. 系统分层设计

```
┌─────────────────────────────────────────────────────┐
│          Desktop Web (Vite + React)                 │
│          （仅桌面，无 iPhone/PWA）                  │
└──────────────────┬──────────────────────────────────┘
                   │ HTTPS + 本机开发
┌──────────────────▼──────────────────────────────────┐
│  FastAPI 控制平面（app/）                           │
│  - 身份、会话、CSRF 验证                             │
│  - REST API 路由 + WebSocket 分发                   │
│  - 聊天能力与权限隔离                                │
└──────────────────┬──────────────────────────────────┘
                   │
         ┌─────────┴───────────┬──────────────┐
         │                     │              │
    ┌────▼─────┐          ┌───▼────┐    ┌────▼─────┐
    │ 行情程序   │          │执行程序 │    │研究程序   │
    │(本进程)   │          │(本进程)│    │(受限子进程)
    └────┬─────┘          └───┬────┘    └────┬─────┘
         │                    │              │
    Massive WS           Alpaca Paper    LangGraph
    WebSocket            Adapter         / CLI
    Real-time            + Risk          + Agents
    Quotes               Protection
```

### 层级职责

| 进程 | 负责 | 交互 |
|---|---|---|
| **FastAPI 控制平面** | 路由、鉴权、会话、WebSocket 转发 | 读取其他进程提供的 snapshot |
| **行情程序（in-process）** | Massive 连接、推送接收、快照构建 | 向 API 提供 `/v1/capabilities` 与 `/snapshot` |
| **执行程序（in-process）** | 策略评估、风控、委托状态机、outbox | 读行情快照；写 SQLite 账本与 outbox |
| **研究程序（子进程）** | LangGraph 编排、Agent 任务执行 | 受限沙箱；输出写 SQLite task 表，API 转发 |

---

## 2. Massive 行情源集成

### 2.1 SubscriptionKey 映射与限制

**GabFin SubscriptionKey**（内部约定）：
```python
SubscriptionKey(
    instrument_id=UUID,           # 股票或期权合约
    channel='quote'|'trade'|'agg', # 频道
    timeframe=None|Timeframe      # Agg 时段（1分钟 vs 1秒）
)
```

**映射到 Massive 参数**：
| GabFin | Massive 参数 | 说明 |
|---|---|---|
| `Q.<symbol>` | `Q.<symbol>` | Quote（实时买卖盘） |
| `T.<symbol>` | `T.<symbol>` | Trade（逐笔成交） |
| `A.<symbol>` | `A.<symbol>` | 1秒聚合 |
| `AM.<symbol>` | `AM.<symbol>` | 1分钟聚合 |
| `Q.O:SPY261218C00650000` | 期权具体合约 Quote | 期权 Quotes |
| `T.O:SPY261218C00650000` | 期权具体合约 Trade | 期权 Trades |
| `A.O:SPY261218C00650000` | 期权具体合约 1秒聚合 | 期权 Agg |

**限制遵循**（基于 Massive Starter $29/月）：
- **套餐容量**：单订阅最多 50 参数，双订阅最多 100 参数（股票+期权共用）
- **连接数**：单一连接，所有订阅共用
- **速率**：无固定事件速率限制；仅受账期流量 cap（Starter 120 GB/30天）
- **期权**：仅支持具体合约订阅，不支持全链通配符（如 `Q.O:SPY*`）

### 2.2 多股票支持架构

```python
# 核心概念：一个 Massive 连接，多个订阅参数
# 目前支持模式：

class MassiveMarketCoordinator:
    """单一 Massive WebSocket 连接管理多个 symbol。"""
    
    def __init__(self, instrument_catalog: InstrumentCatalog):
        self._conn = None          # 单一 WebSocket
        self._subscribed = set()   # 当前订阅参数集
        self._streams = {}         # {instrument_id: QuoteStream}
        self._backoff = ExponentialBackoff()
    
    async def subscribe(self, keys: list[SubscriptionKey]) -> None:
        """subscribe 聚合多个 instrument，送一个 JSON 给 Massive。"""
        params = self._keys_to_massive_params(keys)
        new_params = set(params) - self._subscribed
        
        if new_params:
            msg = {
                'action': 'subscribe',
                'params': ','.join(params)  # "Q.AAPL,Q.MSFT,T.AAPL"
            }
            await self._ensure_connected()
            await self._ws.send(json.dumps(msg))
            self._subscribed.update(new_params)
    
    async def unsubscribe(self, keys: list[SubscriptionKey]) -> None:
        # 现阶段 Massive 不支持取消订阅，仅记录状态
        pass
```

### 2.3 现实流量考量

**每月额度预估**（基于文档 Section 6）：

| 场景 | 每秒消息数 | 每秒带宽 | 月消耗（22 交易日 × 6.5h） |
|---|---|---|---|
| 1 只活跃股票 `Q.AAPL` | ~90 条 | ~13 KB/s | ~6 GB |
| 4 只热门股票 `Q+T` | ~600 条 | ~90 KB/s | ~45 GB |
| 预留 50% 波动 | — | — | **~70 GB** |

**额度口径（以 WebSocket 文档为准，非 carlos 文档的 Starter 标价）**：套餐一单订阅 120 GiB／30 天、双订阅 240 GiB／30 天，WebSocket 与 REST 合计计量。70 GB 估算在单订阅额度内，但需以 `/my-license` 实测校正。**注意：WebSocket 文档的套餐价为套餐一单订阅 99 元／30 天、双订阅 198 元／30 天，与 carlos 文档的 USD 标价不同，采购前需核对。**

### 2.4 消息质量与延迟

| 指标 | Massive (WebSocket) | Futu (OpenD) |
|---|---|---|
| 推送延迟 | <100ms（声称） | <100ms（声称） |
| 数据粒度 | Polygon 格式（成交、bid-ask） | Futu 格式（成交、ask-bid） |
| 心跳 | 无心跳（新消息即推送） | OpenD 有定期心跳 |
| 断线恢复 | 客户端自己重连 + 重新订阅 | OpenD 进程管理 |

---

## 3. 重写范围与现有资产迁移

### 3.1 完全重写的模块

| 模块 | 现状 | 新实现 |
|---|---|---|
| `services/gabfin/providers/` | Futu adapter 单向依赖 | Massive adapter（已完成骨架）+ Alpaca adapter |
| `services/gabfin/market/feed/` | FeedAdapter + Subscription 顶层（模糊） | 清晰的 coordinator 模式 |
| `services/gabfin/market/supervisor.py` | Futu 检测逻辑 | 通用 health / reconnect 循环 |
| `runtime/debug_keys.py` | Futu 验证脚本 | Massive 验证脚本 |

### 3.2 保留的现有资产

| 模块 | 用途 | 更新 |
|---|---|---|
| `services/gabfin/contracts/` | 数据结构（QuoteEvent、SubscriptionKey 等） | 不变 |
| `services/gabfin/market/stream.py` | QuoteStream（发出事件） | 不变 |
| `services/gabfin/execution/` | 策略、风控、OMS | 不变（仅调用方改） |
| `apps/desk-web/` | 前端代码 | 对接新 API 路由 |
| `services/gabfin/api/auth.py` | 身份与鉴权 | 不变 |
| `tests/gabfin/` | 单元测试框架 | 迁移 Futu test 到 Massive |

### 3.3 迁移步骤

1. **Phase 1（已完成）**
   - ✅ Massive adapter 骨架 + 消息解析 + 8/8 unit tests
   - ✅ 验证协议（订阅格式、消息格式）

2. **Phase 2（本规划）**
   - 🔄 Coordinator 与多订阅逻辑
   - 🔄 集成到 `market/supervisor.py`
   - 🔄 写端到端集成测试

3. **Phase 3（启动前）**
   - 实时数据验证（开盘后用真实推送）
   - 性能量测（流量、延迟、内存）
   - FastAPI 路由与 WebSocket 分发对接
   - 前端与 desk-server 验收

---

## 4. API 与前端接口

### 4.1 新增 `/v1/health/market` 端点

```python
@router.get('/v1/health/market')
async def market_health():
    """实时行情程序健康状态。"""
    return {
        'source': 'massive',
        'connected': coordinator.connected,
        'subscribed_params': len(coordinator.subscribed_params),
        'latest_heartbeat': coordinator.last_event_at,
        'quotes_per_second': coordinator.stats['messages_per_sec'],
        'bytes_per_minute': coordinator.stats['bytes_per_min'],
        'traffic_cycle': {
            'start': ...,
            'end': ...,
            'used_gib': ...,
            'remaining_gib': ...
        }
    }
```

### 4.2 现有 `/snapshot/{instrument_id}` 保留

```python
@router.get('/snapshot/{instrument_id}')
async def latest_quote(instrument_id: UUID):
    """返回单只股票最新 QuoteSnapshot。"""
    snapshot = market_coordinator.snapshot(instrument_id)
    if snapshot is None:
        raise HTTPException(404, 'No subscription or stale data')
    return snapshot
```

### 4.3 WebSocket 聊天与实时分发

```python
@app.websocket('/ws/chat')
async def websocket_endpoint(websocket):
    """聊天 + 实时行情推送。"""
    await websocket.accept()
    async for msg in websocket.iter_text():
        # 处理聊天消息
        response = await chat_handler(msg)
        await websocket.send_text(response)
        
        # 同时订阅行情变化
        # （可选：前端启用行情推送时推送实时 quote）
```

---

## 5. 执行程序（In-Process）

### 5.1 策略循环

```python
class StrategyExecutor:
    async def run(self):
        """日内与波段策略主循环。"""
        while not self._closed:
            # 1. 读最新行情快照
            quote = self._coordinator.snapshot(instrument_id)
            if quote is None or quote.too_stale():
                continue  # U15: 行情过期停止新入场
            
            # 2. 评估所有策略
            for strategy in self._strategies:
                intent_list = strategy.evaluate(StrategyContext(
                    quote=quote,
                    account=self._account_state,
                    positions=self._open_positions
                ))
                
                for intent in intent_list:
                    # 3. 应用风控
                    sized_intent = self._risk_engine.check_and_size(intent)
                    if sized_intent is None:
                        log(f'Risk rejected: {intent}')
                        continue
                    
                    # 4. 状态机转移 + 委托
                    self._send_order(sized_intent)
            
            await asyncio.sleep(0.5)  # Scheduler interval
    
    def _send_order(self, intent: StrategyIntent) -> None:
        """提交委托到 OMS，记录 outbox。"""
        order_id = uuid4()
        self._db.orders.insert({
            'order_id': order_id,
            'strategy_id': intent.strategy_id,
            'intent_hash': hash(intent),
            'state': 'PROPOSED',
            'timestamp': now_utc()
        })
        # 在 transaction 外异步向 Alpaca 提交
        asyncio.create_task(self._broker.place_order(...))
```

### 5.2 风控决策

```python
class RiskEngine:
    def check_and_size(self, intent: StrategyIntent) -> SizedIntent | None:
        """U11, U12: 动态止损、风险限额。"""
        
        # U12: 账户最大回撤 40%
        if self._account.max_drawdown > 0.40:
            return None  # Halt
        
        # U11: 计划风险 ≠ 1%，动态配置
        risk_per_trade = self._policy.risk_per_trade  # 从批准政策读
        
        # 计算股数 = 计划风险 / (入场价 - 止损价)
        shares = risk_per_trade / abs(intent.entry - intent.stop_loss)
        
        # 受 BP、杠杆、单股曝险、借券等约束
        final_shares = self._apply_constraints(shares, intent)
        
        if final_shares == 0:
            return None
        
        return SizedIntent(
            **intent.dict(),
            quantity=final_shares
        )
```

---

## 6. 研究程序（子进程 + LangGraph）

### 6.1 隔离运行

```python
class ResearchRunner:
    """受限子进程，无券商权限、无主程序写入。"""
    
    async def execute(self, job: ResearchJob) -> ResearchResult:
        """
        1. 从 SQLite 读数据快照（immutable）
        2. 启动 LangGraph workflow
        3. 写结果到 task 表
        """
        # 子进程只能读 task 表输入、写输出
        with self._db_readonly() as db:
            context = db.read_research_context(job.context_id)
        
        # 运行 LangGraph
        graph = self._build_graph(job.type)
        result = await graph.invoke(context)
        
        # 子进程通过 IPC 或数据库 job 表返回结果
        self._post_result(job.id, result)
```

### 6.2 LangGraph 构成

```
ResearchRequest
  ↓
capability_check (行情是否可用、指标是否有效)
  ↓
fetch_data (财报、新闻、技术数据)
  ↓
├─ technical_analysis (bar、指标)
├─ fundamentals_analysis (财报、事件)
└─ options_analysis (Greeks、Greeks、payoff)
  ↓
evidence_validation (数值与引用检查)
  ↓
synthesis (综合报告)
  ↓
structured_report + provenance
```

---

## 7. 数据存储（SQLite WAL）

### 7.1 核心表结构

```sql
-- 账户与委托
CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    strategy_id TEXT,
    intent_hash TEXT,
    state TEXT CHECK (state IN ('PROPOSED', 'APPROVED', 'SEND_PENDING', 'ACKNOWLEDGED', 'PARTIAL', 'FILLED', 'CANCELED', 'REJECTED')),
    client_order_id TEXT UNIQUE,
    broker_order_id TEXT,
    filled_qty DECIMAL,
    avg_fill_price DECIMAL,
    timestamp INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 委托 outbox（事务保证）
CREATE TABLE outbox (
    outbox_id INTEGER PRIMARY KEY,
    order_id TEXT REFERENCES orders(order_id),
    event TEXT,
    payload JSON,
    state TEXT CHECK (state IN ('PENDING', 'PUBLISHED', 'DEAD_LETTER')),
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 研究任务
CREATE TABLE research_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT,
    context_id TEXT,
    state TEXT,
    deadline TIMESTAMP,
    input_snapshot JSON,
    output_result JSON,
    cost_tokens_in INTEGER,
    cost_tokens_out INTEGER,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 行情快照（实验用）
CREATE TABLE quote_snapshots (
    instrument_id TEXT,
    as_of TIMESTAMP,
    feed TEXT,
    bid_price DECIMAL,
    ask_price DECIMAL,
    last_price DECIMAL,
    quality TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (instrument_id, as_of)
);
```

---

## 8. 性能指标与量测点

| 指标 | 目标 | 量测点 |
|---|---|---|
| 本机快取 API 响应 | p95 ≤300ms | `/snapshot/{id}` 命中率 |
| WebSocket 推送延迟 | p95 ≤100ms | Massive event_at → UI 显示 |
| 下单前风控检查 | p95 ≤100ms | risk_engine.check_and_size() |
| 研究 job 提交 | p95 ≤500ms | LangGraph 初始化 + 首个 node |
| 月度流量消耗 | ≤120 GB (Starter quota) | 实时监测 `/v1/health/market` |

**监测工具**：
- Python `time.perf_counter()` 记录关键路径
- SQLite `created_at` / `completed_at` 量测任务耗时
- Massiv's `/my-license` 轮询（每 1h 一次）跟踪配额

---

## 9. 启用关卡（G）

| 关卡 | 要求 | 检查点 |
|---|---|---|
| **G1** | 完整 checkout + 基线测试 | Futu adapter 移除，新 Massive 单元测试通过 |
| **G2** | Massive 实时权益确认 | `/my-license` 显示 `products: ["stocks"]` + 流量正常消耗 |
| **G3** | Paper account + 执行唯一性 | Alpaca paper 账户验证，OMS 仅一个执行者 |
| **G4** | 风控数值批准 | 用户批准 `policy.yaml` 中的单笔風險、日虧、杠杆上限 |
| **G5** | 研究环境隔离 | 子进程无券商权限、output 受限 |
| **G6** | 前端与身份验证 | Tailscale 私连 + cookie session + CSRF 测试通过 |
| **G7** | 无前视回测与论文结果 | 策略部署前实现 holdout 验收 |

**当前状态**：G1 ✓（Massive adapter 完成）、G2 ⏳（待 `/my-license` 核验）、G3-G7 未启动

---

## 10. 时间表与依赖

### Phase 2: 核心集成（1-2 周）

| 任务 | 依赖 | 产出 |
|---|---|---|
| Coordinator 多订阅逻辑 | G1 | `market/coordinator.py` |
| 集成 supervisor + health | Coordinator | `market/supervisor.py` 更新 |
| 端到端测试（单机） | Coordinator | `tests/gabfin/test_massive_integration.py` |
| FastAPI 路由适配 | 端到端测试 | `/v1/capabilities` 新路由 |
| desk-server 启动脚本 | FastAPI 路由 | `scripts/desk-server-massive.py` |

### Phase 3: 前端与验收（1 周）

| 任务 | 依赖 | 产出 |
|---|---|---|
| 前端 `/snapshot` 轮询改 WebSocket | desk-server | 实时行情 UI 推送 |
| iPhone PWA 离线 fallback | 前端 | 私网 PWA 可用 |
| 实时性能量测（开盘） | 前端 + 真实数据 | 量测报告 |

### Phase 4: 策略与研究（后续）

| 任务 | 依赖 | 产出 |
|---|---|---|
| 执行程序 + risk engine | G4 | 策略主循环 |
| 研究子进程 + LangGraph | G5 | Research harness |
| 策略验收与部署 | G7 | 首个已批准策略上线 |

---

## 11. 成本与约束

### 月度预算（HK$400 对标）

| 项目 | 单价 | 数量 | 合计 |
|---|---|---|---|
| Massive Stocks Starter | $29/月 | 1 | $29 |
| Alpaca Paper | $0 | 1 | $0 |
| **预留** | — | — | — |
| 研究模型（Claude） | $20/job | 10 jobs | $200 |
| 期权行情（未启用） | $0 | — | $0 |
| **月度合计** | — | — | **~$230** |

**预留空间**：$170/月，用于期权实时行情或模型超用。

### 技术约束

- **Python 3.12** 兼容性检查
- **WebSocket 连接数** ≤1（Massive 限制）
- **订阅参数** ≤50（Starter 套餐）
- **流量 cap** ≤120 GB/30 days

---

## 12. 关键决策与偏差

### 为何不用 Futu 了？

**原因**：
1. 行情推送已非 Futu 强项（Futu 主做港股）
2. Massive 价格更清晰（$29 vs 免费但配额有限）
3. 单一行情源减少调试复杂度
4. WebSocket 协议更标准（Polygon 兼容）

**风险**：
- Massive 是第三方代理，服务终止风险
- 需 LangGraph 额外成本监测

### 为何保留 Alpaca 而不考虑 IBKR？

**原因**：
1. Alpaca paper 已集成、无需迁移
2. IBKR 需 API 重写 + 借券复杂度高
3. 本阶段不需 IBKR 的高级功能

**后续**：可在 `Broker` 接口下并列 IBKR adapter，但不优先。

---

## 12A. 功能覆盖矩阵（对照用户 GabFin 功能清单）

| # | 功能 | 数据来源 | 模块位置 | 状态 |
|---|---|---|---|---|
| 1 | instant market data：实时 quote | Massive WS `Q.` | `providers/massive`、`market/` | 已有骨架 |
| 1b | instant market data：order book（L2 深度） | **Massive WS 文档未提供，不承諾** | — | 需更正：原清單寫 Futu order book，Massive 無此頻道，標示為不支持 |
| 1c | full-history bars + volume | Massive REST `/v2/aggs/ticker/{t}/range/...` | `providers/massive/rest.py`（待建）、`market/bars.py` | 未建 |
| 2 | technical indicators：MACD / RSI / ATR / Bollinger | 本地由 bars 計算 | `analysis/indicators.py`（待建） | 未建；覆蓋範圍需標示（bar 數不足、session 不同） |
| 3 | macro：inflation / jobs / rates | FRED API | `providers/fred/`（待建） | 未建；需 vintage／首次公布值，避免回填修訂值 |
| 4 | evidence-based research | SEC／新聞／Massive 數據 | `research/` | 見 §8 |
| 5 | dynamic candidate pool | 機構觀點、事件、scanner | `universe/` | 見 §7.1 |
| 6 | risk analysis：動態止損、倉位、曝險、回撤 | 本地 | `risk/` | 見 §9 |
| 7 | research-only options：chain、Greeks、scenario payoff | Massive REST `/v3/snapshot/options/{underlying}` 分頁 | `options/`（待建） | **未覆蓋，已補充於下** |
| 8 | strategy registry | 本地 | `strategies/`、`experiments/` | 見 §9 |
| 9 | auto trading（paper） | Alpaca paper | `execution/` | 見 §9.3 |
| 10 | paper trading：US$100,000、盤前／RTH／盤後、多空 | Alpaca | `execution/`、`risk/` | 見 §9.2 |
| 11 | full trade history：data → evidence → intent → fill | SQLite 追溯表 | `storage/` | 見 §7 |
| 12 | chat assistant：只讀、分析、研究、方案，不下單 | 後端 capability | `api/chat` | 見 §10.1 |
| 13 | data integrity flags：stale／indicative／delayed、缺口、來源 | `QuoteQuality` 等 | `contracts/`、`market/` | 見 §7.2 |

**不在範圍**：Massive 文檔明確不提供 Futures、Indices、Forex、Crypto、Flat Files。指數期權鏈 `I:SPX` 屬 Options，可用。

### 12B. 期權研究模組（補充，原規劃缺失）

- **數據**：REST `GET /v3/snapshot/options/{underlying}?limit=250`，分頁跟隨 `next_url`（去除上游 key，改用客戶 key）。單合約：`/v3/snapshot/options/{underlying}/{contract}`。
- **可用字段**：Greeks（Delta/Gamma/Theta/Vega）、IV、open_interest（上一交易日）、underlying_asset。**部分合約可能缺失 Greeks 或 IV。**
- **限制**：Snapshot Greeks 為當前快照，**不可查任意歷史時刻 Greeks**；GEX、Gamma Wall 等需自行計算。
- **研究功能**：期權鏈瀏覽、Greeks 顯示、情境 payoff 計算（本地）。**不提供下單**（與用戶清單一致）。
- **權限**：需期權單訂閱或雙訂閱；股票單訂閱不能訪問。
- **費用**：文檔 WebSocket 套餐不含期權即時 OPRA 價；期權實時行情需確認權限與價格，列為 G 關卡。
- **實施順序**：先 REST 快照（不需 WS 期權訂閱），再視預算加 WS 期權合約訂閱。

### 12C. 指標與 bars 的口徑約束

- 指標只消費 `final` bar；`forming` 不計入信號。
- REST bars 與 WS `AM.` 聚合的 session 定義需一致，否則指標結果不可比。
- 覆蓋不足（bar 數 < 指標所需窗口）時輸出 `coverage: insufficient`，不補假值。

## 12D. Agent 角色與 Harness 設計（2026-11-27 確認方向）

**已確認**：執行方式 LangGraph 節點 + 自有 harness；首版 3 個角色；角色定義採 YAML 角色卡 + Jinja2 prompt。

### 12D.1 首版角色（3 個）

| 角色 | 職責 | 工具白名單（只讀） | 禁止 |
|---|---|---|---|
| `discovery` | 從授權來源找候選並寫納入理由 | `resolve_symbols`、`read_observations`、`read_massive_snapshot` | 讀取憑證、輸出可執行 intent |
| `technical` | 讀 finalized bars 與指標，給出 setup、失效條件、時間尺度 | `read_bars`、`compute_indicators`、`read_quote_snapshot` | 用 LLM 估算指標數值 |
| `portfolio` | 讀帳戶快照與候選，給曝險與集中度建議 | `read_account`、`read_risk_limits`（只讀） | 調高任何政策上限 |

其餘 3 個（fundamentals/events、options、experiment）延後至首版驗證後再加。

### 12D.2 角色卡格式（每角色一個 YAML）

```yaml
version: 1
role: technical
purpose: 由 finalized bars 產出技術面結論
inputs: schemas/research/technical_input.json     # 快照 ID、bars 引用
outputs: schemas/research/technical_output.json   # 結論、引用、缺口、coverage
tools: [read_bars, compute_indicators, read_quote_snapshot]
forbidden:
  - 不得輸出 StrategyIntent 或任何可執行訂單
  - 不得以文字估算指標數值，數值必須來自 compute_indicators
  - 證據必須引用 snapshot 內存在的 ID，否則視為無效
budget:
  max_input_tokens: 20000
  max_output_tokens: 4000
  max_attempts_per_node: 2
  deadline_seconds: 120
prompt:
  system: prompts/technical/system.md.j2
  user: prompts/technical/user.md.j2
  version: 1
```

### 12D.3 Prompt 模板結構（參考 RD-Agent 的 system / user 分離）

- `system.md.j2`：角色身份、職責邊界、證據規則（無來源不下結論；缺口必須列出）、輸出 JSON schema。**固定內容，不含動態數據。**
- `user.md.j2`：快照 ID、數據質量標記（stale/indicative/delayed）、上游 observations。
- 渲染採嚴格模式（缺變量即報錯，不靜默補空）。
- 版本號進入 cache key（與 §8.1 一致）。

### 12D.4 Harness 職責（自有代碼，不交給 LangGraph）

| 項目 | 規則 |
|---|---|
| 工具執行 | 只允許角色卡 `tools` 內的工具；越權調用直接拒絕並記錄 |
| 輸出校驗 | 必須通過 `outputs` schema；失敗最多重試 1 次，之後標記 `invalid` |
| 證據校驗 | 引用 ID 必須存在於快照；數值與工具輸出比對 |
| 預算與 deadline | 每 job 記 token、耗時、次數；超出即取消 |
| 審計 | 每次調用記錄：角色、prompt 版本、模型、輸入快照 hash、輸出 hash、錯誤 |
| 權限邊界 | 角色無下單工具；即使 prompt 被注入，也無法觸發交易 |

LangGraph 只負責節點順序與並行，**不判斷權限**。

### 12D.5 驗收門檻（進入實作前）

- [ ] 3 個角色卡通過 schema 校驗
- [ ] 每個角色至少 1 個「越權調用被拒」測試
- [ ] 證據引用不存在時，輸出被標記 `invalid`
- [ ] 同一快照重跑，cache key 一致

### 12D.6 尚未決定（需後續確認）

- LLM provider 與模型選擇（API 或授權 CLI，見 §8.1）
- 角色卡放置位置（`config/agents/` 或 `services/gabfin/research/roles/`）

## 13. 附錄：關鍵文件清單

### 新增

- `services/gabfin/providers/massive/adapter.py` ✅
- `services/gabfin/providers/massive/__init__.py` ✅
- `services/gabfin/market/coordinator.py` 🔄
- `services/gabfin/market/supervisor.py` 🔄 (重写)
- `services/gabfin/api/routes/health.py` 🔄 (新路由)
- `runtime/massive_ws_probe.py` ✅
- `tests/gabfin/test_massive_adapter.py` ✅ (8/8)
- `tests/gabfin/test_massive_integration.py` 🔄
- `scripts/desk-server-massive.py` 🔄

### 修改

- `services/gabfin/api/main.py` — 移除 Futu 相关路由
- `apps/desk-web/src/features/market/StockDetail.tsx` — 迁移到 Massive 数据源
- `docs/memory/execution.md` — 更新 checkpoint

### 删除

- `services/gabfin/providers/futu/` — (慎重保存历史备份)
- `runtime/debug_keys.py` (Futu 验证) — 改 Massive 版本

---

## 结论

**Massive-first 架构**对齐了用户需求（单一高可靠行情源）、预算约束（Starter $29）、实现复杂度（WebSocket 标准协议）。  
通过清晰的分层设计（行情 → API → 执行 → 研究），可在 2-3 周内启动第一版交易系统，后续按需扩展期权、多策略、研究 Agent。

**立即启动**：Phase 2 核心集成，实现 Coordinator 与多订阅、端到端测试，准备开盘验证。
