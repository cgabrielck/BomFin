# GabFin 交接文件（Handover）— S0 → S1（2026-11-27）

> **目的**：新 AI 会话读此文件获得完整上下文，立即启动 S1。
> **有效期**：本文件在 S1 完成后由新文件取代。旧内容进 Git history。

---

## 1. 当前状态快照

### 1.1 已完成工作（S0）

| 项目 | 位置 | 状态 | 验证 |
|---|---|---|---|
| 架构设计文件 | `docs/superpowers/plans/2026-11-27-gabfin-session-plan-and-quality-gate.md` | 已写 | ✓ |
| 缺陷汇总 | `docs/superpowers/logs/bug-register.md` | 已初始化（8 条缺陷） | ✓ |
| 日志目录 | `docs/superpowers/logs/` | 已创建 | ✓ |
| Part 1 指标与 tape | `services/gabfin/` | 已提交（WU-0～WU-3） | 1,116 pytest |
| Part 2 路由与分析 | `services/gabfin/` | 已提交（WU-7, WU-9） | 2,388 pytest |
| 研究三角色 LangGraph | `services/gabfin/research/` | 已实现、已测试 | 1,151 pytest + 33 研究测试 |
| S04 前端工作台 | `apps/desk-web/src/` | 已实现（04e） | 925 core + 33 Playwright |
| 前端 handover | `docs/handover/` | 已创建（WU-9-ui） | ✓ |

### 1.2 已知遗留（优先级排序）

| ID | 类别 | 说明 | 阻塞 S1 |
|---|---|---|---|
| BUG-007 | 逻辑 | Alpaca 行情仍在旧计划中，与 Massive-only 决定冲突 | ✓ |
| BUG-008 | 安全 | langgraph 依赖版本未审计 | ✗ |
| G2 权益 | 权限 | 行情权益未放行，不得声称「实时」 | ✗ 长期 |

---

## 2. S1 完整检查清单

### 2.1 第一步（15 分钟）

- [ ] 读 `docs/superpowers/plans/2026-11-27-gabfin-session-plan-and-quality-gate.md` 的 §0 与 §1（本文件不再重复）。
- [ ] 读 `docs/memory/execution.md` 最新一段（确认当前分支与基准 SHA）。
- [ ] 读 `docs/superpowers/logs/bug-register.md` 的 BUG-007（待处理）。
- [ ] 验证 `.env` 中有 `MASSIVE_API_KEY` 与 `MASSIVE_BASE_URL`（不用填 key，仅验证存在）。
  ```bash
  grep -E 'MASSIVE_(API_KEY|BASE_URL)' .env
  ```
  > 注：WebSocket URL 从 `MASSIVE_BASE_URL` 推导（https→wss），不另设 `MASSIVE_WS_URL`。
- [ ] 确认在 `feat/research-harness-langgraph` 分支（或 S1 新建分支）。

### 2.2 S1 目标分解（1.5 小时）

#### 目标：移除过期方案，统一单源 Massive

**步骤 1：标记 Alpaca 行情为弃用（15 分钟）**
  - [ ] 打开 `docs/superpowers/plans/2026-11-27-gabfin-market-data-provider-plan.md`（旧计划）
  - [ ] 在文件顶部加：`> ⚠️ **已弃用（2026-11-27）**：Alpaca 不再用于行情。用户选择 Massive 单源。本文件仅作历史参考。`
  - [ ] 在 Git 中标记（不删除）：`git add docs/superpowers/plans/2026-11-27-gabfin-market-data-provider-plan.md`

**步骤 2：在代码中标记 Alpaca 行情适配器为弃用（20 分钟）**
  - [ ] 检查 `services/gabfin/providers/registry.py`：
    - [ ] 在导入部分，改为：
      ```python
      # from gabfin.providers.alpaca.symbols import is_option as alpaca_is_option  # DEPRECATED (2026-11-27)
      def alpaca_is_option_deprecated(symbol: str) -> bool:
          """DEPRECATED: Alpaca 行情已弃用。"""
          raise NotImplementedError("Alpaca 行情源已弃用（2026-11-27），仅用 Massive。")
      ```
    - [ ] 在 `SourceProfile` 注册部分（约第 182 行），改为：
      ```python
      # DEPRECATED (2026-11-27): Alpaca 行情源已弃用，仅用 Massive
      _ALPACA_PROFILE = SourceProfile(
          source='alpaca',
          ...
      )

      # 然后在 get_profile 或类似的查询函数中，抛出：
      if source == 'alpaca':
          raise NotImplementedError(
              "Alpaca 行情源已弃用（2026-11-27），仅用 Massive WebSocket + REST。"
          )
      ```
  - [ ] 检查 `services/gabfin/providers/alpaca/__init__.py` 顶部加弃用声明（如果该目录存在）。
  - [ ] 添加一条测试确保调用被拒：
    ```python
    def test_alpaca_quote_source_raises_deprecated():
        with pytest.raises(NotImplementedError, match="已弃用|已废弃"):
            registry.get_profile('alpaca')  # 或实际的查询方式
    ```

**步骤 3：建立 Massive 配置模型（30 分钟）**
  - [ ] 创建或更新 `services/gabfin/providers/massive/config.py`：
    ```python
    from pydantic import BaseModel, Field, SecretStr
    from typing import Optional

    class MassiveConfig(BaseModel):
        """Massive 配置，从环境变量读取。"""
        base_url: str = Field(
            ...,
            description="REST 与 WebSocket 基础 URL（https://...）",
            json_schema_extra={"env": "MASSIVE_BASE_URL"}
        )
        api_key: SecretStr = Field(
            ...,
            description="API key，从 MASSIVE_API_KEY 读取（不放日志）",
            json_schema_extra={"env": "MASSIVE_API_KEY"}
        )
        ws_path: str = Field(default="/ws", description="WebSocket 路径")
        max_subscriptions: int = Field(default=100)
        rest_qpm: int = Field(default=1000, description="每分钟 REST 请求限制")

        @property
        def ws_url(self) -> str:
            """从 base_url 派生 WebSocket URL。"""
            base = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
            return f"{base}{self.ws_path}?key={self.api_key.get_secret_value()}"

        class Config:
            env_prefix = "MASSIVE_"
    ```
    > 注：`SecretStr` 会自动隐藏日志中的 key。
  - [ ] 添加加载函数 `load_config() -> MassiveConfig`，错误时打印「缺少 MASSIVE_BASE_URL」或「缺少 MASSIVE_API_KEY」等明确提示。
  - [ ] 添加测试：环境变量缺失时抛出 `ValidationError`；存在时正确加载；`api_key` 不出现在 `repr` 和日志。
    ```python
    def test_config_loads_from_env(monkeypatch):
        monkeypatch.setenv("MASSIVE_BASE_URL", "https://feed.example.test")
        monkeypatch.setenv("MASSIVE_API_KEY", "test_key_12345")
        cfg = MassiveConfig.model_validate({})
        assert "test_key" not in repr(cfg)  # SecretStr 自动隐藏
        assert cfg.ws_url.endswith("?key=****")  # ws_url 属性也隐藏
    ```

**步骤 4：秘密不出现在任何地方（20 分钟）**
  - [ ] 检查代码库中是否有任何地方出现 WebSocket 完整 URL（包含 key）：
    ```bash
    grep -r "wss://massive" --include="*.py" --include="*.ts" --include="*.md" services/ apps/ docs/
    ```
  - [ ] 检查日志中是否有秘密输出（特别是 HTTP 头的 `X-Proxy-Key`）。添加 redact 函数：
    ```python
    def redact_key(value: str) -> str:
        """隐藏 API key 或敏感值。"""
        if len(value) > 4:
            return f"{value[:4]}****{value[-4:]}"
        return "****"
    ```
  - [ ] 在 HTTP client（如 `requests` headers）中使用 redact：
    ```python
    logger.debug(f"X-Proxy-Key: {redact_key(api_key)}")
    ```

**步骤 5：运行验收测试（15 分钟）**
  - [ ] 跑 pytest：
    ```bash
    pytest tests/gabfin/test_massive_config.py -v
    pytest tests/providers/test_registry.py::test_alpaca_quote_source_raises_deprecated -v
    pytest tests/ -k "not (integration or slow)" --tb=short
    ```
  - [ ] 确保：
    - [ ] 新的 Alpaca 弃用测试通过。
    - [ ] 配置测试通过（缺失环境变量抛出、秘密隐藏）。
    - [ ] 全部回归测试绿色。

### 2.3 验收门（必须全绿）

- [ ] 配置测试 ✓
- [ ] Alpaca 弃用测试 ✓
- [ ] 秘密检查：`git diff` 中无 key 或完整 URL ✓
- [ ] pytest 全绿 ✓
- [ ] `npm run typecheck` 在 `apps/desk-web` 无新错误 ✓

---

## 3. 交接检查清单（新会话必查）

### 3.1 环境确认

```bash
# 验证分支
git branch

# 验证基准 SHA（应该是 research harness 完成的 SHA）
git log --oneline -1

# 验证 .env 中有 MASSIVE_API_KEY 和 MASSIVE_BASE_URL
grep MASSIVE .env

# 验证虚拟环境正确指向（不是旧的 Desktop 路径）
which python
python -c "import sys; print(sys.prefix)"

# 确认在 Downloads checkout，不是 Desktop
pwd
```

### 3.2 文件完整性

- [ ] `docs/superpowers/plans/2026-11-27-gabfin-session-plan-and-quality-gate.md` 存在
- [ ] `docs/superpowers/logs/bug-register.md` 存在
- [ ] `docs/superpowers/logs/` 目录存在（会话日志放这里）
- [ ] `.env` 有 `MASSIVE_API_KEY` 和 `MASSIVE_BASE_URL`（已核实存在）

### 3.3 Git 状态

```bash
# 应该是干净的或仅有本 S0 的文件
git status

# 应该能看到本轮的 commit
git log --oneline | grep -i "session\|quality\|gate"
```

---

## 4. S1 新会话日志模板

**文件**：`docs/superpowers/logs/2026-11-27-session-01.md`

**基准 SHA**（已核实）：`b435abe` — `Record the repository rebase in the execution checkpoint`
**分支**（已核实）：`feat/research-harness-langgraph`

> 注意：`b435abe` 之前有大量未提交的工作区修改（S0 产生的角色卡、schema、研究代码，
> 以及更早的 Massive adapter、desk-server、前端改动）。新会话开始时先执行
> `git status --short` 盘点，**不要**丢弃这些修改；它们是当前工作的基础。

```markdown
# Session 01 — 2026-11-27 清理与地基

- 模型／代理：Claude Sol High
- 基准 SHA：（从上面 git log 获取）
- 分支：feat/research-harness-langgraph（或新建）
- 目标：移除过期方案，统一单源 Massive
- 完成的步骤：
  - [ ] 标记 Alpaca 行情为弃用
  - [ ] 代码中加 NotImplementedError
  - [ ] 测试弃用行为
  - [ ] 建立 Massive 配置模型
  - [ ] 秘密检查
  - [ ] 验收测试
- 测试命令与结果：
  ```
  pytest tests/gabfin/test_massive_config.py -v
  结果：XX passed

  pytest tests/providers/test_registry.py::test_alpaca_quote_source_raises_deprecated -v
  结果：1 passed

  pytest tests/ -k "not (integration or slow)" --tb=short
  结果：YYYY passed, Z skipped
  ```
- 偏离计划的决定（Ruling）：（如有）
- 未完成与交接：
  - [ ] （例如）配置测试需要上游批准环境变量名称
  - [ ] 交接给 S2：Massive WebSocket 实装
- 质量指标：
  - 新增测试数：3
  - 缺陷数（本会话）：0
  - 修复的遗留缺陷数：1（BUG-007）
  - 独立审查阻塞项数：0
```

---

## 5. 文件路径速查

| 用途 | 路径 |
|---|---|
| 本次交接 | `docs/superpowers/handover-s0-to-s1.md`（即本文件） |
| S1 执行指南 | `docs/superpowers/plans/2026-11-27-gabfin-session-plan-and-quality-gate.md` |
| 缺陷汇总 | `docs/superpowers/logs/bug-register.md` |
| S1 会话日志 | `docs/superpowers/logs/2026-11-27-session-01.md`（新会话创建） |
| 架构参考 | `docs/superpowers/plans/2026-11-27-massive-first-architecture.md` |
| 记忆更新 | `docs/memory/execution.md`（S1 完成后更新） |

---

## 6. 若遇到阻塞

### 配置无法从环境读取
- 确认 `.env` 中确实有 `MASSIVE_API_KEY` 与 `MASSIVE_BASE_URL`。
- 确认 `python-dotenv` 已安装：`pip list | grep python-dotenv`。
- 若 `.env` 格式有问题，检查是否有 `export MASSIVE_BASE_URL=...` 而非 `MASSIVE_BASE_URL=...`（PowerShell 不识别 `export`）。

### pytest 失败
- 读失败输出的最后 20 行，确认是逻辑错误还是环境问题。
- 若是环境，参考 `docs/audit/local-env-setup-2026-11-27.md`。

### 秘密检查发现 key
- 立即打开 `.gitignore`，确保 `.env` 在列中。
- 若已 commit，参考 git-filter-branch 文档清理。

---

## 7. 交接确认

**新会话 AI 开始前，请确认收到此文件并理解：**
1. S1 目标明确：移除 Alpaca 行情标记、建立 Massive 配置、验收秘密。
2. 完成标准明确：列出的所有测试必须通过。
3. 日志位置明确：新会话日志放 `docs/superpowers/logs/2026-11-27-session-01.md`。
4. 若有疑问，回查 `docs/superpowers/plans/2026-11-27-gabfin-session-plan-and-quality-gate.md` 的 §0–§3。

**开始 S1！**
