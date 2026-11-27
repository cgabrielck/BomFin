# GabFin 分段实施计划与 AI 代码质量门（2026-11-27）

> 本文件是唯一的执行指南。每个 AI 会话开始时先读本文件的 §0 与最新 session log。
> 架构依据：[Massive-first 架构](2026-11-27-massive-first-architecture.md)。
> 更正：本文件取代前一版 5-session 草案。那版仍假设 Alpaca／Futu 为行情或执行来源，
> 与使用者 2026-11-27 的决定（只用 Massive，不用 Futu 与 Alpaca）冲突，已废弃。

---

## 0. 上下文与固定约束

- **行情源**：只用 Massive（套餐 1，股票＋期权，1 条 WebSocket，100 参数，REST 1000/分钟，30 天 240 GiB）。
  WebSocket 地址与 REST 地址只从环境变量读取，**不得**写入任何文档、日志或前端。
- **不做**：不买 Futu 行情、不接 Futu OpenD、不接 Alpaca 行情、不下真单、不部署、不 push。
- **指标**：本地计算（MACD／RSI／ATR／Bollinger／Volume），附覆盖标签（coverage）。
- **宏观**：FRED，必须保留 `release_date`，缺失即拒收（防 look-ahead）。
- **研究**：LangGraph 三角色（discovery／technical／portfolio），harness 为唯一权限边界，提示词不做安全依据。
- **期权**：只研究，不下单；Greeks 与 IV 必须标示来源。
- **语言**：面向用户的报告用繁体中文；代码与标识符用英文（见 `.cursor/rules/chinese-reports.mdc`）。
- **工作目录**：`C:/Users/001/Downloads/GabFin-ai-trade`，分支 `feat/research-harness-langgraph`（或后续分支）。

### 0.1 当前已知状态（2026-11-27）

| 项目 | 状态 |
|---|---|
| Part 1 指标／tape／FRED／Alpaca adapter | 已提交（Alpaca adapter 按新决定**不再用于行情**，需在 S1 标记为弃用或删除） |
| Part 2 WU-7 路由、WU-9 分析平面 | 已提交；前端 WU-9-ui 待 Carbon 完成 |
| S04 前端工作台 04e | 已实现，未独立审查 |
| 研究三角色 LangGraph + harness | 已实现并测试；**仅注入 adapter 验证**，无真实 LLM 与真实工具 |
| Massive REST／期权鏈 | **未实现**（`providers/massive/` 仅有 adapter 骨架） |
| G2 行情权益 | 未放行，不得声称「实时」 |

---

## 1. 会话规划（6 个会话，每会话有验收门）

| 会话 | 目标 | 主要产出 | 验收门 |
|---|---|---|---|
| **S1 清理与地基** | 移除过期方案，统一单源 Massive | 删除 Alpaca 行情路径标记；Massive 配置模型；秘密只从环境读取；migration 草案 | 配置测试；秘密不出现在任何 repr／log；pytest 全绿 |
| **S2 Massive 行情与历史** | WebSocket 订阅、REST 历史 bar、期权鏈分页 | `providers/massive/{ws,history,options}.py`；容量（100 参数）、限流（1000/分）、`next_url` 分页 | 契约测试 + 录制 fixture；超容量明确失败；限流有计数 |
| **S3 数据存储与指标** | tape、事件账本、指标增量与全量一致 | tape 写入／读出；指标引擎接 Massive bars；coverage 标签 | 不变式「增量 == 全量」；读回一致；无 vendor 数据拒入决策路径 |
| **S4 研究接线** | 把 LangGraph 三角色接到真实工具与快照 | 工具白名单实装（`read_bars`、`compute_indicators`、`read_observations`…）；快照注册表；审计写入 SQLite | 越权调用测试；引用断裂测试；审计行可追溯到快照与 prompt 版本 |
| **S5 后端 API 与前端对接** | WU-9-ui 整合、研究／指标端点 | Carbon 完成 UI；后端 diff 审查；Playwright | `npm run build` 先于 Playwright；e2e 全绿；合约未被前端改动 |
| **S6 闭环与审查** | 端到端烟雾、独立审查、文档收尾 | 研究→指标→UI 的端到端烟雾；审查报告；执行记录 | 独立审查无阻塞项；memory 文件更新；已知限制列明 |

**未决（需使用者决定，不阻塞 S1–S3）**：
- 纸上交易（paper trading）的执行后端：Alpaca paper 已被「不用 Alpaca」排除，需另选或暂缓。S6 之前不实现下单。
- 研究用 LLM 供应商与成本上限。

---

## 2. AI 代码质量计划

### 2.1 基本原则

1. **先测后码**：每个行为变更先有失败测试（RED），再写实现（GREEN），再重构。见 TDD 技能。
2. **验证先于声明**：没有本会话内的命令输出，不得说「通过」。
3. **边界在代码，不在提示词**：权限、预算、schema、引用校验必须是可测试的代码。
4. **不为通过而改测试**：修改已有断言必须在 bug log 中说明原因。
5. **一个 bug 一条记录**：见 §4。

### 2.2 每次提交前的自查清单（AI 必做）

- [ ] 新增或修改的行为都有测试，且测试曾经失败（记录失败输出的首行）。
- [ ] `pytest tests/gabfin tests/providers` 全绿（记录通过数）。
- [ ] 相关前端变更：`npm run typecheck`、`npm run build`（先）、再 Playwright。
- [ ] `pip check` 无冲突；新依赖已写入 `pyproject.toml` 的可选依赖组并固定版本。
- [ ] 没有 `TODO`、`pass`-式吞错、裸 `except Exception` 无记录。
- [ ] 秘密检查：`git diff` 中无 key、token、WebSocket 完整 URL。
- [ ] 没有修改 `generated.ts`（除非经 `npm run contracts`）。
- [ ] 改动的 memory 文件已更新（execution、progress 或 issues）。

### 2.3 代码审查机制

| 级别 | 触发 | 方式 | 产出 |
|---|---|---|---|
| L0 自查 | 每次提交 | §2.2 清单 | session log |
| L1 聚焦审查 | 涉及交易、金额、权限、秘密、数据完整性 | 新上下文、只读 reviewer，给固定基准 SHA 与 diff | 阻塞／非阻塞分级 |
| L2 整合审查 | 每个会话结束 | 全分支 diff + 规格对照 | 规格偏差表 |
| L3 验收演示 | S6 | 端到端烟雾 + 截图 | 验收报告 |

审查原则（沿用 `workflow.md`）：
- 只追踪**阻塞性缺陷**；非阻塞建议进待办，不循环多轮。
- 修正后只复查受影响范围。
- 审查结论分开记录：**代码规范**与**规格符合**。

### 2.4 AI 特有风险与对策

| 风险 | 表现 | 对策 |
|---|---|---|
| 测试在实现前就通过 | 测试没有测到东西 | 强制记录 RED 输出；必要时删掉实现重写 |
| 静默吞错 | 返回空结果、不报错 | 所有外部错误映射为明确的 `status`；测试断言错误类型 |
| 越权或幻觉工具 | 调用未注册的工具 | 工具在执行前检查（已实现）；测试覆盖 |
| 数据前视（look-ahead） | 宏观或指标用了未发布数据 | `as_of` 与 `release_date` 强制；专门测试 |
| 超时与限流被忽略 | 批量取数耗尽配额 | 限流计数入 log；超限明确失败 |
| 秘密泄露 | key 出现在日志或 URL | redact 测试；grep 检查进清单 |
| 过度声称 | 「已实时」「已验证」 | 状态词只能用 execution.md 定义的词；G2 未过不得称实时 |
| 文档过期 | 旧方案仍在 memory | 每会话结束清理 memory 与旧计划（见 §5） |

### 2.5 质量指标（每会话记录）

- 新增测试数、通过数、跳过数（必须说明跳过原因）。
- 缺陷数（按 §4 分类）、其中在审查中才发现的数量。
- 测试 RED 证据数 ÷ 新行为数（目标 100%）。
- 独立审查阻塞项数（目标：每会话 0 个遗留）。

---

## 3. 每会话的工作流

1. 读本文件 §0 与 `docs/memory/execution.md`（只读最新一段）。
2. 读最新 session log（§4.2），确认上一会话遗留。
3. 按 §1 的目标拆成小步；每步：RED → GREEN → 自查。
4. 会话结束前：跑 §2.2 清单，填写 session log、bug log、特殊情况。
5. 需要审查时，按 §2.3 派工（单一 reviewer，固定基准 SHA）。
6. 更新 memory（只改受影响文件），并在 session log 中写明未完成项。

---

## 4. 日志规范（每个 AI 会话必须填写）

日志文件位置：`docs/superpowers/logs/`（每个会话一个文件，命名 `YYYY-MM-DD-session-NN.md`）。
缺陷汇总：`docs/superpowers/logs/bug-register.md`（每条缺陷一行，附会话编号）。

### 4.1 会话日志模板

```markdown
# Session NN — YYYY-MM-DD
- 模型／代理：
- 基准 SHA：
- 分支：
- 目标（对应 §1 的会话）：
- 完成的步骤：
- 测试命令与结果（粘贴通过数，不粘全文）：
- 偏离计划的决定（Ruling）：原因／代價：
- 未完成与交接：
- 质量指标（§2.5）：
```

### 4.2 缺陷与特殊情况日志（bug register）

每条必填字段：

| ID | 会话 | 类别 | 现象 | 根因 | 修复 | 回归测试 | 状态 |
|---|---|---|---|---|---|---|---|
| BUG-001 | S0 | 测试不稳定 | Windows 上超时测试偶发失败（sleep 与 deadline 计时精度） | 依赖墙钟精度 | 改为 deadline 明确终止，断言终止原因 | `test_deadline_cancels_model` | 已修 |

类别只用：`逻辑`、`契约`、`安全`、`并发`、`数据完整性`、`测试不稳定`、`环境`、`文档`、`特殊情况`。

### 4.3 特殊情况记录（必须写）

凡遇到以下情况，写入会话日志的「特殊情况」小节：
- 外部服务的非预期响应（例如套餐限制、错误码、时区）。
- 为满足计划而偏离规格（必须附 Ruling）。
- 环境问题（路径、虚拟环境指向旧机器、依赖版本）。
- 任何已发现但未修复的问题。

### 4.4 已登记的历史缺陷（S0，2026-11-27 本轮）

| ID | 类别 | 说明 | 状态 |
|---|---|---|---|
| BUG-001 | 测试不稳定 | 超时测试在 Windows 上以墙钟断言不稳定，改为检查终止原因 | 已修 |
| BUG-002 | 逻辑 | 工具白名单原本只在调用后检查，越权工具已执行 | 已修（执行前拦截） |
| BUG-003 | 契约 | 输入校验异常未转为 ValueError，错误语义不一致 | 已修 |
| BUG-004 | 逻辑 | 预算按单次尝试计，重试会绕过累计上限 | 已修（累计） |
| BUG-005 | 安全 | 角色名未校验即拼接路径 | 已修（正则） |
| BUG-006 | 环境 | 旧 `.venv` 指向 Desktop 旧 checkout | 已修（重建） |
| BUG-007 | 逻辑 | 旧前提 Alpaca 行情仍在 provider 计划中，与 Massive-only 决定冲突 | 待 S1 清理 |
| BUG-008 | 安全（待查） | `pyproject.toml` 的 research 依赖版本号与 `langgraph==1.2.24` 未经上游安全审计 | 待 S1 确认 |

---

## 5. 文档清理规则

- 只保留一份「当前架构」与一份「当前实施计划」。旧版本移入 Git 历史，不在工作区保留副本。
- 每会话结束时检查：`docs/superpowers/plans/` 中是否有已被取代的计划；列出清单交使用者确认后再删除。
- 删除前必须确认 Git 中可恢复。

---

## 6. 交付物清单（S0 本次）

| 文件 | 状态 |
|---|---|
| 本文件 | 已写 |
| `docs/superpowers/logs/` 目录与 bug register | 待 S1 创建 |
| 旧架构文件清理 | **待使用者确认范围**（见下） |

---

## 7. 下一步

1. 使用者确认旧文件清理范围（见回复中的选项）。
2. S1 开始：清除 Alpaca 行情路径标记、建立 Massive 配置模型、创建 logs 目录。
