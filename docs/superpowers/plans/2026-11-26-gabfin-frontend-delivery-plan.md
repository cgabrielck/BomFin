# GabFin 分段前端 Implementation Plan

> **For agentic workers:** 使用 executing-plans，由單一 Agent 按功能切片實作；審查依
> [精簡工作流](../../agents/workflow.md) 按風險安排，不逐票自動派工。

**Goal:** 先交付可用的股票工作台，再隨後端能力逐步加入研究、帳戶、期權與 paper 控制。

**Architecture:** 保留舊 `web/`，在 `apps/desk-web/` 新建 React 前端。Browser 經同源 API
取得既有契約的 snapshot／updates；API bridge 連接 S03 單一市場程序，SDK／秘密留在後端。
首頁採清晰機會卡與風險摘要，股票詳情採圖表／研究分區；手機逐區閱讀。

**Tech Stack:** React、TypeScript、Vite、TanStack Query、CSS variables、Playwright；
Python FastAPI 與既有 GabFin 契約。依賴版本在安裝時核對並固定於新 root lockfile。

**Spec:** [主設計 U02、U13、U22–24、§10](../specs/2026-11-25-gabfin-system-design.md)、
[Task 7／14／17／18](2026-11-25-gabfin-upgrade-plan.md)、
[研究體驗](2026-11-25-gabfin-research-experience-plan.md)、
[已同意的混合 UI 方向](../specs/2026-11-26-gabfin-ui-references.md)。

## Global Constraints

- 使用者已同意混合布局、分段計劃並授權開始 04a；當前驗證範圍以 execution checkpoint 為準。
- S04 是核心前端縱向切片，不是全產品前端完成；子單位不是固定對話數，也無須一次完成。
- 繁中優先、桌面／手機響應式；有效快取標 age，account／research 慢不阻塞工作台。
- 金額保留 Decimal wire 字串；百分比／價格／成交量單位依契約，不猜單位或來源時間。
- 研究聊天沒有交易寫入能力；paper 控制另區、另 API。S04 不提供可執行交易按鈕。
- G2 權益仍未放行；示範資料、未知權益、舊價及無資料都必須有可見標示。
- 保留原 `web/package-lock.json`、legacy 前端與既有資料；不採購、交易、push 或部署。
- UI 概念可借鑑；複用程式碼／素材前逐檔記 commit、來源、授權及必要 notices。
- 單 Agent；一般 UI 自查及相關測試，權限／資料完整性整合做一次聚焦獨立審查。

## 基線與檔案責任

規劃時 HEAD `1802198648ce465db5f3dba79a342756a7f9ccc5`；branch `codex/s01-source-baseline`。
Tracked tree 乾淨，只有原 untracked `web/package-lock.json`；實作開始時重新核對。
新 `apps/desk-web/`、root `package.json` 尚不存在。現有 `api/auth.py:create_app`
已提供 pairing／cookie session／origin 防護，要求 HTTPS；不能為本機方便而繞過。

| 路徑（相對 source checkout） | 責任 |
|---|---|
| `package.json`, `package-lock.json`, `playwright.config.ts` | 新 private workspace、固定依賴、測試入口 |
| `apps/desk-web/src/app/` | shell、路由、providers、全域樣式及 layout |
| `apps/desk-web/src/shared/contracts/` | 從 `schemas/gabfin-1.0.json` 產生 TS 型別，不手寫另一份 wire model |
| `apps/desk-web/src/shared/transport/market.ts` | 同源 snapshot／stream、取消與恢復 |
| `apps/desk-web/src/features/market/` | 選股、MarketViewState、資料狀態與訂閱 hook |
| `apps/desk-web/src/features/chart/` | chart wrapper、增量／修訂更新及清理 |
| `tests/e2e/market.spec.ts`, `tests/e2e/chart.spec.ts` | 使用者操作及瀏覽器錯誤恢復 |
| `tests/e2e/fixtures/market-server.ts` | 可控制延遲、斷線及亂序的示範 API，明示 fake |
| `services/gabfin/api/app.py`, `market.py`, `market_gateway.py` | 組裝既有 auth、market routes、內部 stream bridge |
| `tests/gabfin/test_market_api.py` | API 身份、scope、origin、到期及資料界線 |

## Review Focus

1. 舊 ticker 回應／重連資料覆蓋新選股 → 04b／04c 驗證選股 identity 與取消。
2. 有連線但價格舊／權益未知 → 04c 顯示 source age／gap，不能只顯示綠燈。
3. 缺 bar 卻拿 quote 拼 K 線／成交量 → 04d 明示缺資料，quote 與 bar 分開。
4. 私有 token、過期 session 或跨 origin 洩漏 → 04c API 測試及 bundle 檢查。
5. 修訂／離頁／手機縮排導致圖表錯誤或訂閱累積 → 04d／04e 驗證清理與窄屏操作。

## S04 分段執行

### 04a — 可供確認的首頁與股票詳情線框

**Files（外層規劃目錄）:** `docs/design/s04-desk-wireframe.html`、`docs/design/s04-screen-map.md`。
**依賴:** 已同意混合方向；沒有 G2 或模型 API 依賴。

- [x] 做一份無外部服務的 HTML 預覽，涵蓋桌面首頁、股票詳情、手機排列。
- [x] 首頁：持倉重要風險 → 機會卡（why-now／時間尺度／研究深度／缺資料）；股票搜尋隨時可達。
- [x] 詳情：候選／自選清單、圖表區、可展開研究證據；研究內容明示示例，不顯示假分析已完成。
- [x] 固定狀態列呈現 paper、資料來源／時間；離線、缺資料、部分報告、空清單有設計。
- [x] 交付預覽與需求對照；使用者無法親試，授權沿目前方向繼續，未宣稱實機驗收。

**完成標準:** 使用者能看見及比較三個畫面；這是設計預覽，不是已接通的產品。

04a 預覽已交付；[畫面／操作／實際驗證](../../design/s04-screen-map.md)。使用者因 remote 不能親試，已授權沿此方向繼續。

### 04b — 可操作的工作台（完整示範切片）

**Files:** root workspace／Playwright 配置、`apps/desk-web/{package.json,tsconfig.json,vite.config.ts,index.html}`、
`src/app/`、`src/features/market/`、`src/shared/contracts/`、`tests/e2e/{market.spec.ts,fixtures/market-server.ts}`。
**接口:** `useMarketSubscription(keys: SubscriptionKey[]): MarketViewState`；state 含選中 ID、
latest quote／bars、連線／gap／資料狀態、示範模式及錯誤。Wire types 由既有 schema 生成。

- [x] 先寫並跑失敗 e2e：shell 不等待 account；A→B 快速切換後，延遲 A 不覆蓋 B；空資料仍能操作。
- [x] 建新 private workspace／型別生成腳本／fake API，接通首頁到股票詳情；路由分割，未實作功能標「尚未接入」。
- [x] 用 CSS variables 定義色彩／字級／間距及共用狀態元件；參考布局自行適配，不引入整套外部產品。
- [x] 跑上述 e2e、typecheck、build；自查桌面及窄屏，記錄結果後本機 commit。

**完成標準:** 可本機啟動、點選候選／搜尋示範股票、切詳情；所有示範內容有標示。

04b 本機提交 898cc04；[實際驗證及界線](../../audit/s04-04b-desk-2026-11-26.md)。

### 04c — 安全接通行情（snapshot 到 browser updates）

**Files:** `services/gabfin/api/{app,market,market_gateway}.py`、必要的 `api/auth.py` 共用 guard 小改動、
`tests/gabfin/test_market_api.py`、`src/shared/transport/market.ts`、market hook 與 `market.spec.ts`。
**依賴:** 04b；沿用 `InternalMarketClient.connect/receive/close` 與 SessionStore。
**接口決策:** Browser `POST /market/snapshot` 以 JSON body 帶 keys；`/market/stream` WebSocket
首幀帶 keys／resume cursor；cookie session，不把 token 放 URL。`fetchSnapshot(keys, signal)`
返回 canonical `MarketSnapshot`；`subscribeMarket(keys, onFrame, signal)` 返回取消函數。

- [x] RED：無權限／錯 origin／到期拒絕；慢讀者及 snapshot_required 後先 snapshot；切股舊回應不能覆蓋。
- [x] 組裝既有 auth，補一條受授權 market bridge；SDK 仍只有市場程序持有，不按瀏覽器請求開新 SDK context。
- [x] API 驗證 instrument scope／有限 key 集合及連線上限；後端內部 service token 不傳 Browser。
- [x] 本機先設定同源 HTTPS 測試入口，保留 Secure cookie／Origin 防護；不公開部署或放寬既有 auth。
- [x] Browser 處理取消、到期、斷線、gap 與完整 reset；age 隨時間更新，連線正常不代表價格新鮮。
- [x] Python API 測試＋相關 e2e GREEN；權限／資料完整性合併做一次聚焦獨立審查，修阻塞問題再提交。

**完成標準:** fake bridge 鏈路及失敗情況可重現；OpenD 可用時另做限時真實 quote smoke。
真實 smoke 與 G2 結果獨立記錄；休市或缺 bar 不阻塞已驗證的 UI 交付，也不冒稱行情驗收通過。

04c 交付／驗證及既有完整回歸失敗見 [報告](../../audit/s04-04c-market-2026-11-26.md)；下一步 04d。

### 04d — 可縮放的增量圖表

**Files:** `src/features/chart/{ChartPanel.tsx,chart-port.ts,bar-series.ts}`、`tests/e2e/chart.spec.ts`。
**依賴:** 04b 的 canonical fixtures；整合時接 04c，不另造價格契約。
**接口:** `ChartPort.applyBars(bars: Bar[]): Bar[]`、`resize(width,height): void`、`dispose(): void`。
回傳目前保留的 canonical bars，供精確數值表使用；不需要的呼叫者可忽略回傳。

- [x] RED：形成中 bar 更新同一區間；晚到修訂改指定區間；重複事件不重計量；切股清理舊 series。
- [x] 實作 wrapper；選用圖表套件前核對目前 API／license 並鎖版本。僅 wrapper 接觸套件 API。
- [x] 初次／reset 才載入完整 series；平時合併批次更新末 bar 或修訂範圍，不每 tick 全量重設。
- [x] 缺 bar 顯示空態；last quote 可獨立顯示，但不拼成交量或偽造 K 線。
- [x] 驗證窄屏、resize、離頁 dispose、重連 snapshot；相關測試／build 通過後提交。

**完成標準:** 可展示正常更新、修訂及缺資料三種情況；示範與實際 provider 證據分開。

04d 已提交 f361264；[結果、修正與截圖](../../audit/s04-04d-chart-2026-11-26.md)，下一步 04e。

04d 執行細化（沿已批准範圍，base `a434de2134550f6dc6ff32b593327192d309ffda`）：

- `ChartPanel` 獨立訂閱 1 分鐘 bar；quote-only host 拒絕 bar 時只顯示圖表缺資料，報價不受阻。
- `bar-series.ts` 負責 bounded／排序／revision／forming→final／重複資料及增量 patch；
  `chart-port.ts` 獨佔 Lightweight Charts 5.3.0 API，`ChartCanvas` 管理 resize／dispose／可讀 OHLC。
- 每個完整 snapshot 給 hook 新 reset identity；切股／reset 清理舊圖，普通更新不 fitContent／setData。
  畫圖時才轉 finite number；原始數值／可讀標籤維持 canonical decimal string。
- Demo quote fixtures 保留；另放 canonical bar snapshots，AAPL／MSFT 提供合成 bars，NVDA 保持缺資料。
  HTTPS fixture 增加可選 bars 模式及私有 stdio 發送修訂，不增加產品測試後門或真實 SDK 訂閱。
- 按 `ChartPort`／bar patch 公開結果與 browser 操作兩個既有測試邊界做 RED→GREEN；
  先測形成中更新，再歷史修訂／去重／reset／切股，最後 resize／手機與取消清理。
- 驗證 typecheck／build／相關 e2e／canonical fixtures，資料完整性作一次聚焦獨立審查；
  本次不改 Python 產品邏輯，不重跑無關 legacy 全套，不重新做 OpenD smoke。

### 04e — 核心工作台整合交付

**Files:** 前述 e2e、`docs/audit/s04-core-acceptance.md`、必要的前端啟動說明。

- [ ] 執行 source root：`npm.cmd --prefix apps/desk-web run typecheck`、
  `npm.cmd --prefix apps/desk-web run build`、`npx.cmd playwright test tests/e2e/market.spec.ts tests/e2e/chart.spec.ts`。
- [ ] Python 相關回歸：`.venv/Scripts/python.exe -m pytest tests/gabfin/test_market_api.py`。
  後端變更在此整合里程碑跑適用完整回歸；只改前端不反覆跑整個 legacy suite。
- [ ] 實際看桌面／手機 viewport；核對 loading／empty／error／stale、鍵盤焦點及資料單位。
- [ ] 記 bundle size、首屏及 source→receive→state→consumer→render tracing；無來源時間就標未知。
- [ ] 核對 source 未超過設計 §12 的相應效能目標；未量測／未達標明列，不用 build 成功代替效能驗收。
- [ ] 更新 checkpoint／功能矩陣；S04 結束時明示仍為核心工作台，未完成後續產品頁。

## 後續 Sections 的前端交付

| Section | 前端功能 | 必要後端／完成條件 |
|---|---|---|
| S05 | 真實機會池、來源／why-now／深度標籤、任意股票清單分析入口 | Tasks 6／8 的候選、證據、job／預算；替換 S04 示例卡，保留部分失敗 |
| S06 | 研究進度、可展開報告、支持／反證／缺資料 | ResearchRunner 與 report，完成來源及深度驗證；不是只做聊天框 |
| S07 | 回測結果／策略比較的最小呈現 | 可信回測引擎與成本後結果；不提前顯示模擬績效為真績效 |
| S08–09 | 隨服務提供最小只讀 paper 狀態、保護／對帳／治理狀態 | OMS／風控／保護能力先驗證；完整控制介面續接 S10 |
| S10 | 完整研究聊天、比較／追蹤、帳戶／委託、獨立 paper 控制、期權研究、iPhone PWA | Tasks 14／17／18；控制與聊天權限分離，手機真機驗收 |
| S11 | 跨功能錯誤恢復、可追溯日誌、效能／安全整合 | 完整閉環驗收；不能用單頁 demo 當完整產品 |
| S12 | 操作指引、遷移／回退及交付入口 | Paper evidence、部署／發布適用授權與驗收 |

這是同一前端逐步擴充；不為每個 Section 建一套 app。
私人 HTTPS／iPhone 遠端存取主要屬 S10；S04 僅本機同源驗證。
實際部署仍按後續發布／安全關卡執行，不因 UI 完成自行發布。

## 計劃自查與下一步

- 已核對既有來源：auth 實際位於 `api/auth.py`，沒有 `api/http.py`；bridge／新前端尚未存在。
- Task 7 的切股／慢 account／stale／增量圖表／build／tracing 分別落在 04b–04e。
- U22–24 的真實研究體驗落在 S05／S06／S10；S04 只交布局及明示示例，沒有移除需求。
- 規劃時未安裝依賴；04a 其後交付獨立 HTML 並跑瀏覽器檢查，正式 app 建置／測試仍未開始。
- 04a–04d 已交付；下一步 04e。單 implementer；04c／04d 按風險各作一次聚焦 code review，沒有文件派工審查。
