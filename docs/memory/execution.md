# Execution checkpoint

- 2026-11-27 桌面续建：`universe/directory.py`持久化验证标的；Massive reference核对ticker/us/stocks/active/USD，404与供应商故障/限流分开。
  launcher共享reference/history REST client；目录seed保留既有UUID。ResearchJobs动态读取目录，新标的不需重建队列。
  `research/directory_capture.py`先读本地tape，缺失按需导入370日窗口到昨日；unknown coverage保留，无自动WS订阅。
  同步capture与清单解析移到线程以免阻塞HTTP；超时可停止等待，但正在运行的同步线程无法强制取消，导入锁避免并发半写。
  候选显示目录ticker/公司名及研究入口；解析逐项未知/非法/不可用。完整pytest1520 passed；TLS/清单11 passed；最后名称补充聚焦通过，typecheck/build/lint通过。
  本轮未真实调用reference/LLM，未独立审查；机构来源登记/多来源聚合待办，历史缓存目前已有即复用（未自动刷新）。离线19445重载首轮因旧Python子进程占端口10048失败；确认完整命令后结束旧子进程，新实例已输出ready，原19443/19444保留。


- 2026-11-27 桌面候选首切片；用户从next-stage选项选择desk，基准582c0cb，保留混合未提交。
  `universe/store.py/resolve.py/__main__.py`：不可变证据/观测、UTC时点/到期/排除、1MiB原子导入、50项解析。
  `api/universe.py`与app/launcher接线：会话/Origin/CSRF/START_RESEARCH；读取来源及解析清单。
  `CandidateWorkspace.tsx`替换server首页示例，demo保持原页；逐项未知/非法/已注册→研究中心。
  验证：候选/研究API/launcher 56 passed，补CSRF/回滚2 passed；新Playwright1 passed，typecheck/build/lint及秘密扫描通过。
  既有research-ui/acceptance回归17 passed（2.3m）；未独立审查。新增离线TLS实例19445，/v1/universe未认证401确认挂载；原19443/19444保留。
  未完成：全市场resolver/池外capture、机构自动来源登记、ticker显示/聚合；不声称任意美股研究或完整Task8交付。
  真实LLM明日再验；G2/交易/外部部署不放行。下一步继续候选供应商解析与历史接线。

- 2026-11-27 S5 桌面研究中心前端（本次；分支 feat/research-harness-langgraph，混合脏树未提交）：
  只改 `apps/desk-web/src/**`（不含 generated/schema），新增 `tests/e2e/research-ui.spec.ts`；
  未改后端／scripts／docs／他人 fixture，未提交。
  新增 `apps/desk-web/src/shared/transport/research.ts`（全部业务请求集中于此，本地 wire types，
  不动 canonical schema）、`apps/desk-web/src/features/research/useResearchView.ts`（轮询 hook）、
  `apps/desk-web/src/features/research/ResearchCenter.tsx`（共享组件，full-tab 与 compact 两种形态）。
  `App.tsx` 用局部 `tab` 状态（'overview'|'research'|'stock'）新增 `◎　研究中心` 导航，
  不改 `useRoute` 的 hash 契约，既有指标／宏观／能力 UI 与回归断言全部保留；
  `StockDetail.tsx` 用 `<details data-testid="research-entry">` 挂同一个 `ResearchCenter`（compact）。
  API 消费假设（已与同事后端 `services/gabfin/api/research.py` 逐字段核对一致）：
  `GET /v1/research/status` → `{configured, reason}`；
  `POST /v1/research/jobs` → 202 `{job_id,status:'queued',snapshot_id,instrument_id,role,result,reason,error,checks,snapshot}`；
  `GET /v1/research/jobs` → `{jobs:[...]}`；`GET /v1/research/jobs/{id}` → 同形加 `result/checks/snapshot`。
  写请求 `credentials:'same-origin'`、`cache:'no-store'`、CSRF nonce 取 `__Host-gabfin_csrf` cookie
  送 `X-CSRF-Token`；body 只送 `{instrument_id: UUID, role}`（后端 `extra='forbid'`）。
  轮询在卸载／换 instrument／登出时 abort（含 generation 计数防竞态），401 走既有 `session.expire()`。
  界面诚实性：未配置 → 显示「明日可接入」且 `research-start` 仍渲染但 disabled；任务失败 → 失败横幅且无结论；
  审查拒收 → 明示「被拒收的结果不会当成结论显示」；缺快照／缺证据 → 明说无可引用证据；
  503 → 显示后端 reason 而非报告；demo → 明示未接 AI 且不造数字；旁注「研究只产生分析结论，不会下单」。
  展示 role 结论 + evidence ids + snapshot_id/as_of/data_quality + 审查校验（结构化，
  原始报告折叠在 `research-raw`）。`ExecutionResult` 六个取值中 5 个非 success 判为拒收，与后端一致。
  TDD：先写 12 个 Playwright mock fixture 测试取得 RED，再实现转 GREEN。
  验证：`npm.cmd run build` 干净、`tsc --noEmit` 干净；
  `research-ui.spec.ts` **12 passed**；回归 `secure-market`＋`analysis-ui` **23 passed**、
  `chart` **10 passed**、`market` **7 passed**；同事的 `research-flow.spec.ts` **11 passed**。
  截图：`docs/superpowers/logs/research-ui-shot.png`。
  过程中发现并修复：stash 往返把同事 `styles.css` 压成 UTF-16 导致 vite 报
  「stream did not contain valid UTF-8」，且丢失同事 760px 断点规则造成 390px 窄屏横向溢出 4px；
  已转回 UTF-8 并完整还原同事 CSS（我的样式为纯追加 184 行），溢出复测 `scrollWidth == 390` 已消除。
  未改后端；真实 LLM 仍未验证。

- 2026-11-27 S5/S6 本地交付（同分支/基准，混合未提交）：
  [session10](../superpowers/logs/2026-11-27-session-10.md)拥有最终证据、审查、启动和验收边界。
  研究任务API/SQLite有界队列、服务端UTC快照、Origin/session/CSRF/owner/能力检查已接通；
  桌面研究中心展示状态/角色结论/证据/快照/审计，退出/切标的终止轮询。
  launcher接实际tape与配置服务，runtime持久owner；`scripts/start-desk.ps1`一键构建/TLS/启动。
  完整pytest1500通过；typecheck/build、pip check、秘密扫描1012路径0命中、diff-check通过。
  独立审查所列权限/截止/错误字段/整图形状均已修；全套浏览器74通过，唯一旧占位断言修正复跑1通过。
  三角色真实TLS闭环通过；最终独立复查状态见session10，真实LLM仍未验证。
  新版已在https://127.0.0.1:19444/离线运行并返回200，不占第二条Massive连接；原19443保留。
  真实LLM/成本按用户决定明日配置后验证，G2未放行，无下单/paper执行/外部部署。

- 2026-11-27 S5/S6 研究端到端驗收（本次；分支 feat/research-harness-langgraph，混合脏树未提交）：
  新增 4 个文件，未改任何既有 fixture（`market-server.py`／`secure-market.ts` 保持原样）：
  `tests/e2e/fixtures/research-server.py`、`tests/e2e/fixtures/research.ts`、
  `tests/e2e/research-flow.spec.ts`、`playwright.research.config.ts`。
  fixture 用真实 TLS（OpenSSL 自签）、真实 `create_market_app(..., research={'jobs': jobs})`、
  真实 `ResearchStore`／`SnapshotCapture`／`ResearchService`／LangGraph runtime／harness；
  唯一替换件是 model adapter（本地 `FixtureModel`，从渲染 prompt 里读真实 evidence_id，无网络、无 .env）。
  时钟钉在 `FIXTURE_AS_OF=2026-11-27T21:00:00Z`，否则快照前视检查会拒。
  三个 fixture profile：`configured`（全链路成功）／`unconfigured`（无 model 无 capture，status `configured:false`，
  POST 503 `Research model not configured`）／`no-history`（tape 未写过该序列，capture 拒绝，job 真实 failed、
  `error=CaptureError`、snapshot_id/result 皆 null）。配对码只走 stdio 管道，无测试后门 HTTP 路由。
  端口由 OS 分配（`bind(('127.0.0.1', 0))`），不占 19045，故与并行 UI 同事的 dev server 无冲突；
  `playwright.research.config.ts` 不启动 vite dev server，只跑 `research-flow.spec.ts`。
  验证：`npx.cmd playwright test --config=playwright.research.config.ts` **10 passed**（连续三轮全绿）。
  覆盖：technical 报告绑定真实 snapshot UUID + `as_of` + evidence_id + harness verdict `success`/
  `fixture-model-v1`；完整研究页与个股详情 compact 页的报告一致性；SQLite 持久审计与浏览器显示一致；
  缺 CSRF → 403；未知 instrument → 404；未知 role → 422；他人 job → 404；登出清空面板且 session 变 401；
  unconfigured 不产生任何 fake 报告；no-history 真实失败且无结论。
  截图：`runtime/research-acceptance.png`（无配对码）、`runtime/research-acceptance-tab.png`。
  发现的真实 UI 契约（供前端同事对齐）：`research-start` 在 unconfigured 时**仍渲染但 disabled**
  （不是隐藏）；`research-raw` 只在完整研究页出现，个股详情 compact 模式刻意不含原始 JSON；
  `research-data-quality` 仅在 `data_quality` 非空时渲染；`research-report` 卡片在失败 job 时也存在，
  失败表现为 `research-failed` 横幅 + 无 role 结果/快照/证据/verdict。
  已知竞态：`App.tsx` 用 effect 切 tab，pick 股票后需等 `research-entry` 出现才稳定（已用 waitFor 修正）。
  未做：真实 LLM 供应商未验证（既定范围）；未提交、未推送。

- 2026-11-27 S5 研究 API（本次；分支 feat/research-harness-langgraph，基准 582c0cb，混合脏树未提交）：
  新增 `services/gabfin/api/research.py`、`services/gabfin/research/jobs.py`、
  `tests/gabfin/test_research_api.py`；`api/app.py` 最小接入（`create_market_app(..., research=None)`）。
  注入形状固定为 `research={'jobs': ResearchJobs(...)}`；`scripts/desk-server.py` 由并行单位自行接线，
  本单位未改前端／launcher／docs／S4 源码。
  路由：`GET /v1/research/status` → `{configured, reason}`（未配置仍存在）；
  `POST /v1/research/jobs` → 202 `{job_id,status:'queued',snapshot_id:null,instrument_id,role}`；
  `GET /v1/research/jobs/{id}` → 同形加 `result/checks/snapshot`；
  `GET /v1/research/jobs` → `{jobs:[最近20本人]}`。
  安全：服务端注入 capture(instrument_id, as_of=UTC)，客户端不得传 snapshot/context/as_of（extra=forbid → 422）；
  快照只报身份／截止／data_quality／evidence 数／content hash，不泄账户原文；
  权限 START_RESEARCH（建）与 READ_REPORT（读）+ owner 校验；写需 CSRF（403），无会话／错 origin／凭证 query → 401；
  未配置 → 503 `Research model not configured`；未知 instrument/job → 404。
  队列有界（原子检查＋写，默认 max_queue=8／max_concurrency=2），单 job 有截止（默认 300s，**capture 与
  service.run 同受截止约束**），shutdown 经 app lifespan（`app.router.lifespan_context` 扩展，非 deprecated
  `on_event`）取消后台任务；进程重启时 queued/running 在下次打开被标 failed。
  错误只存异常类型名，不存 provider URL／key／traceback；响应同时给 `reason` 与 `error`（前端读 `reason`）。
  **并行 reviewer 的三处 repro 已修**：list 路由原本回传 report body，绕过单 job 路由的
  `authorize(READ_REPORT)`——现无该能力者只看得到自己的 job 身份与状态；
  capture 原本不受截止约束，可能永久占用并发槽；`reason` 字段名原本只有 `error`。
  验证：新增测试 46 passed（先 RED）；完整 pytest 1499 passed；pip check／py_compile／
  秘密扫描 1004 路径 0 命中；`-W error::DeprecationWarning` 干净。未执行独立 review；真实 LLM 未验证。

- 2026-11-27 S4整合：[session09](../superpowers/logs/2026-11-27-session-09.md)拥有最终接口与验证；以下模块自查记录不是最终整合结论。
  CLI capture/run/checks、本地冻结工具、SQLite快照/审计、LLM_*可替换adapter已接线；未提交。
  真实Massive tape3 bars→technical离线注入模型→SQLite重开1条audit通过；三角色/HTTP工具往返fixture通过。
  BUG-020至024及future quote时间键已修；最终独立复查tests全套1446 passed，功能审查通过。
  最终接口/审查裁定由session09拥有；真实供应商现场验收待LLM配置，不声明生产全门放行。
  LLM_*实际配置缺失，真实模型未验证；unknown coverage拒指标，缺账户不伪造portfolio；S5未开始。

- 2026-11-27 S3/S4 独立只读复查（基准582c0cb，未提交）：B1（窗口外修订）、BLOCK01（跨月中断）、
  B2（Massive伪SIP）三项经代码与测试双重确认已关闭；S4 FRED接线经`to_point`/`as_of`规范转换后
  capture显式`release_date`已就绪。独立复核：`tests`全套 **1446 passed**（含tests/gabfin 1331）。
  B3结论：账本同timestamp多报价属独立观测，`source_seq`为供应商毫秒时间戳
  （契约 `OpaqueKey | None`，非唯一交易序号），原"一刀切拒绝"不成立，改为如实记录
  "同源时间多事实"限制即可。剩余阻塞：LLM_*实际配置缺失致真实模型未验证（既定范围，非新需求）。
  未修改文件、未发网络、未读.env。

- 2026-11-27 S4 研究存储：`services/gabfin/research/store.py` + `tests/gabfin/test_research_store.py`，
  仅这两个文件，未动其他文件、未提交。`ResearchStore(path)` 自建 `research_snapshots`/`research_checks` 两表，
  不写 `schema_migrations`，不改现有 schema 版本迁移。
  接口：`create_snapshot(*, as_of, context, data_quality, evidence_ids) -> UUID`；
  `get_snapshot(UUID) -> dict`（snapshot_id/as_of/context/data_quality，未知抛 KeyError）；
  `evidence_ids(UUID) -> frozenset[str]`；`append_check(CheckResult) -> None`；
  `checks(UUID) -> tuple[CheckResult, ...]`（按插入顺序）。
  快照不可改：同 id 同内容幂等、不同内容拒绝（conflict），读取回传深拷贝。
  证据：注册集必须是 UUID；context 内 evidence_id 必须在注册集内，否则拒绝。
  前视：as_of 必须 aware UTC（naive、非零 offset 拒绝，零 offset 归一）；
  context 内 event_at/available_at/published_at/first_seen_at 不得晚于 as_of，
  release_date 以日期比较（当日不算前视）；无法解析的文本不推断、不拒绝。
  审计 FK 指向快照，缺快照拒绝；内容 SHA256 写入，读取时校验，篡改 context/as_of/evidence 均报错。
  上下文有界：MAX_CONTEXT_BYTES 1MiB、MAX_CONTEXT_ITEMS 10000、MAX_QUALITY_BYTES 64KiB；
  非 JSON 值（任意对象）拒绝而非 default=str 落库；错误讯息只述限制不回显 payload，
  provider URL/token 不外泄。
  验证：新增测试 52 passed（先 RED 后 GREEN）；完整 pytest 1395 passed；
  pip check 干净、py_compile 干净、diff-check 通过、秘密扫描 990 路径 0 命中。
  仅自查，未执行独立 review；未发网络、未读 .env、未提交。

- 2026-11-27 S4 模型适配器：`services/gabfin/research/model.py` + `tests/gabfin/test_research_model.py`，
  仅新增这两个文件，未改 `research/nodes.py`（`ModelRequest`/`ModelReply`/`async model(request, dispatch)` 保持不变）。
  `ModelConfig` + `OpenAICompatibleModel(config, transport=None)`；`load_model_config()` 仅读
  `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`/`LLM_TIMEOUT_SECONDS`，不自动载 dotenv，缺值即明确失败，不 fallback 假模型。
  固定 role→tool 映射（仅白名单工具）；工具参数只允许空对象；工具往返上限 8 轮。
  累计 input/output tokens，每轮 `max_tokens` 递减；usage 缺失或非法即拒绝。
  回应 model_version 取供应商实际回传的 model（缺则退回设定值）。
  最终 content 必须是 JSON 对象；JSON fence／非对象文字一律拒绝。
  所有例外只输出固定 reason（`ModelProviderError.reason`），不外泄 url／payload／header／key；
  HTTPS only、拒绝 redirect、URL 不得带 credential；pydantic SecretStr 隐藏 base_url 与 key。
  transport 为可注入的同步 callable（`ModelHttpRequest`→`ModelHttpResponse`），在 `asyncio.to_thread` 中执行；
  测试全程注入，不发网络、不读 .env、未新增依赖、未提交。
  验证：新增测试 52 passed；research 子系统 86 passed；完整 pytest 1383 passed
  （余 1 失败在并发中的 `test_research_capture.py`，与本单位无关）；pip check 干净；秘密扫描 990 路径 0 命中。
  仅自查，未执行独立 review；真实 LLM 调用未验证，无供应商成本证据。

- 2026-11-27 S3收尾：[session08](../superpowers/logs/2026-11-27-session-08.md)拥有验收证据；同基准/分支，未提交。
  真实AAPL历史3 bars重复导入/读回一致（2 REST请求），unknown coverage仍拒绝指标决策。
  合成2000事件重开逐条相等、SQLite integrity_check=ok；19.263s，非长时性能证明。
  BUG-019同时间戳OHLCV冲突写前拒绝（RED→GREEN）；中断manifest与阻塞sink停止测试通过。
  完整pytest1240通过；聚焦81通过；pip check/lint/diff-check通过，秘密扫描978路径0命中。
  S3功能验收已补齐，独立数据完整性审查仍待授权reviewer；保持S3，不进入S4。
  跨partition/manifest提交非事务，失败后拒读并需新目录重建；缓存/长时性能与G2限制见session08。

- 2026-11-27 S3续接：见[session07](../superpowers/logs/2026-11-27-session-07.md)，同分支/基准、未提交。
  desk/standalone host将quote先经线程写market-events.sqlite再发布；写盘失败保持gap并关闭feed。
  账本重捕获按source事实去重，保留首条；IndicatorPlane由tape续算新增bars，修订/截短重建，16系列缓存加锁。
  完整pytest1237通过，最后host注入后host/runtime14通过；pip check/lint/diff-check通过，秘密扫描977路径0命中。
  S3基础接线完成，仅自查，无真实网络/长时压测；未知Massive coverage仍拒绝决策，G2未放行。
  下一步S4本地工具白名单/快照/SQLite研究审计；LLM供应商与预算尚未决定。

- 2026-11-27 S3基础切片：同分支/基准582c0cb、未提交；见[session06](../superpowers/logs/2026-11-27-session-06.md)。
  Massive历史store/CLI→Parquet/manifest；保留massive/adjusted/unknown coverage，禁止伪装SIP。
  TapeBarSource验证来源和SHA256；导入前验证旧分区。EventLedger复用SQLite事件表，幂等/冲突拒绝。
  录制bars落盘读回与synthetic SIP 65 bars/7切分点指标一致性已验；未知coverage拒入指标决策。
  完整回归1231通过；最后完整性修正后受影响54通过。pip check/lint/diff-check通过，秘密扫描976路径0命中。
  仅自查；S3尚未完整：常驻feed账本与增量指标接线仍缺；无真实REST导入。本轮无前端修改。

- 2026-11-27 S2：同分支、基准 `582c0cb`，未提交。REST/历史/期权基础见
  [初轮日志](../superpowers/logs/2026-11-27-session-02.md)；运行接线见
  [续作日志](../superpowers/logs/2026-11-27-session-03.md)。
  WS 独立读循环与确认分发，adapter 满足 ManagedFeedAdapter 并接入 supervisor；
  desk-server/market host 行情入口已迁移 Massive，不再要求 SDK/OpenD。
  真实服务验证：授权 active/未过期，股票+期权、1连接/100参数；历史3 bars、期权第二页、
  单连接 receive 期间追加订阅与 quote、关闭均成功；白名单录制 fixture 已入测试。
  录制证据见 [真实验收日志](../superpowers/logs/2026-11-27-session-04.md)。
  最新TLS验收：[session05](../superpowers/logs/2026-11-27-session-05.md)；真实Massive→TLS snapshot到达，
  配对/刷新/登出撤销正常。BBO展示现已实现：买卖价各自时间/年龄、last独立；
  BBO-only及会话清空TLS5项通过；真实Massive UI复验显示BBO与登出清空正常。
  build/typecheck通过；Playwright49通过/2窄屏失败（规格仅桌面）。续作修复BUG-011
  （session两读间撤销导致None索引；CSRF同窗口）及审查BUG-014/015/016（仅https/wss、
  mint按模式校验TLS、缺现有数据库安全报错）；均先RED后GREEN，独立聚焦复查通过（130组合测试通过）。
  最新完整pytest1212通过、TLS撤销/过期/刷新4通过、秘密扫描972路径0命中；详情由session05拥有。
  BUG-012/013已修。ACK已录制并重放；ready改为绑定后输出，真实立即TLS200；
  正常运行后5468ms退出0、1连接开/关确认。相关58测试通过，秘密扫描973路径0命中。
  BUG-017已确定性修复，真实早停1249ms、exit0、1开1关；本轮仅自查，未独立审查。
  最终60项受影响测试通过；真实最终轮ACK成功但有界观察无报价、1次重连，2开2关、5389ms退出0。
  Windows实际Ctrl+C未验；仍单equity host，行情稳定性/gap及G2未放行。不推送、部署或交易。

- 2026-11-27 S1 清理与地基：分支 `feat/research-harness-langgraph`，实际基准
  `582c0cbce545c02ab18f1696a5138526f3aa5322`；保留既有修改，未提交。
  默认 registry 以 Massive 替换 Alpaca，Alpaca 查询明确拒绝；旧离线工具保留。
  `providers/massive/config.py` 显式读取环境，SecretStr、隐藏端点输出、无凭证 ws_url；
  `scripts/check-massive-secrets.py` 检查当前真实配置值，不输出值本身。
  最终验证：完整 pytest **1171 passed**；typecheck、pip check、编辑器 lint 通过；
  秘密扫描 0 命中。RED/GREEN、迁移裁决及边界见
  [S1 日志](../superpowers/logs/2026-11-27-session-01.md)。
  仅自查，独立安全审查及 BUG-008 漏洞数据库审计未执行；G2 未放行。
  S1 后续接线进度由上方 S2 checkpoint 拥有。

- 2026-11-27 research 單位：在 `feat/research-harness-langgraph` 延續既有未提交角色卡，
  基準 `b435abe92f17da33dcb859fe62f7f127aedbd1cb`；保留其他既有修改。
  `research/nodes.py` 實作 discovery → technical → portfolio 的 LangGraph，
  各節點獨立 prompt、輸出 schema 必驗、執行前工具拒絕、總時限與累計 token 檢查。
  `schemas/research/` 為節點 DTO；不是既有 canonical `ResearchReport` 的替代。
  已宣告 research extra 並安裝 LangGraph；真實 LLM/provider 工具、數值來源比對、
  持久化審計及快照儲存接線仍待後續，現時只以注入 adapter 驗證。
  驗證：`tests/gabfin + tests/providers` 1151 passed；最後超時終止修正後
  research 聚焦測試 33 passed；`pip check` 與編輯器 lint 無錯誤。
  本輪自查；未執行獨立 reviewer，不視為 production 安全放行。

- Section / unit: **Part 2 即時主線進行中**。WU-7（provider routing）與
  WU-9（分析平面 + 三個端點 + 合約擴充）已提交並交接前端。分析平面的生產接線
  已於 `cd59fca1` 補上。G2 仍未放行。
- Checkout: `C:/Users/001/Downloads/GabFin-ai-trade`（repo 根目錄）。
  2026-11-27 起使用者指定只改 Downloads 內；舊 Desktop checkout 不再作工作位置。
  同日起原始碼由 `.worktrees/gabfin-s01` 提升至 repo 根目錄，路徑引用已改為根層相對路徑。
- Branch: `codex/s01-source-baseline`（GitHub 對應 `cgabrielck/BomFin` 的 `gabriel-dev`）。
- Current HEAD: `8cd7449`（`Rebase the repository on the current architecture`）。
  2026-11-27 原始碼由 `.worktrees/gabfin-s01` 提升至 repo 根目錄；legacy
  `backend/`、`web/` 舊前端、30 個 legacy 文件與 139 個 legacy 測試已移除，
  歷史保留在 BomFin 的 `legacy-full` 分支。根層重建後驗證：
  **1099 pytest passed**（tests/gabfin + tests/providers）、`npm run typecheck`
  與 `npm run build` 乾淨、**50 Playwright passed**。
  新增依賴宣告：`pyarrow`（tape）與 `jsonschema`（schema artifact 測試）。
- 前端交接狀態：`docs/handover/HANDOVER.md` 的 `stage: ready-for-ui`，
  任務卡 `docs/handover/ui-tasks/WU-9-ui.md`。Gemini 4 Carbon 可開始。
  **後端此時不可動 `apps/desk-web/src/**`。**
- 驗證：**2388 pytest passed / 4 skipped**（另有 4 個本輪之前即失敗的既有失敗，
  見 [issues](issues.md)）、**39 Playwright passed**、tsc --noEmit 乾淨。
- 詳細見 [progress](progress.md) 與
  [供應商執行計劃](../superpowers/plans/2026-11-27-gabfin-provider-execution-plan.md)。
- WU-9 修正三個真實缺陷：
  1. `_timeframe` 用 `rstrip` 去掉數字、把單位留在 `unit`，導致 `1day` 完全無法解析。
  2. `_date` 在 macro 的 `try` 內被呼叫，日期格式錯誤被吞成 503 而非 400。
  3. `authorize`／`require_scope` 丟出的 `PermissionError` 未被捕捉，會變成 500。
- `cd59fca1` 修正第四個更根本的缺口：三個分析端點沒有任何生產路徑掛載
  （`analysis=None` 預設），且 `IndicatorPlane` 沒有任何 `BarSource` 實作。
  已補 `analysis/sources.py`、`analysis/runtime.py`、`tape.read_rows`，
  並讓指標平面在 venue 未知時拒絕計算。
- 前端交接機制（`docs/handover/`）與多模型分工邊界見 [decisions](decisions.md) D011。
- 04e 交付、量測與界線：[s04-core-acceptance](../audit/s04-core-acceptance.md)；
  evidence 在 [artifacts/s04-04e](../audit/artifacts/s04-04e)。
- 本機實測（04e）：**925 core／33 Playwright passed**。量測分兩個環境：
  API 與 quote trace 量自合成 TLS fixture；首屏與快取切頁量自 Vite dev server。
- 使用者已授權並上傳 source 至 `cgabrielck/BomFin` 的 `gabfin-s04d` 分支；原 main 保留。
- Freshness、trade bars、coordinator/recovery/replay、managed lifecycle、
  authenticated loopback stream 及 quote-only host 已交付。
- [工程票](../tickets/s03-stream/issues/02-market-state-recovery.md) 已完成；
  [G2 票](../tickets/s03-stream/issues/03-feed-evidence-g2.md) 保持未完成。
- 04b／04c／04d 交付報告見 [audit](../audit) 目錄。
- Next exact action: **等待 Carbon 完成 WU-9-ui**，之後後端做 diff 審查、整合、
  跑 pytest 與 Playwright、commit。Part 2 剩餘 WU-4 Futu bid/ask、WU-5 order book
  （**BBO 暫緩**，使用者 2026-11-27 決定）。`npm.cmd run build` 必須在 Playwright 之前。
  長駐 operator 入口與遠端部署仍待交付。
- G2 可以另作有界驗證；缺 channel／權益證據及未批准政策維持拒絕新入場。
- 不購買、不啟動交易、不部署；不重啟既有 OpenD。
- 實作／審查路由：[workflow](../agents/workflow.md)。
