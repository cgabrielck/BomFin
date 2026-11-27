# S04/04e — 核心工作台整合交付

- Base `7b22e6f5666e5160026cd1958a2916c3d838b093`；branch `codex/s01-source-baseline`。
- 執行範圍：[前端計劃 04e](../superpowers/plans/2026-11-26-gabfin-frontend-delivery-plan.md#04e--核心工作台整合交付)。
- 本單位已通過聚焦獨立 review（Standards＋Spec 雙軸）並修正全部 3 個阻塞缺陷，隨後提交。
  修正前的 4 個 modified＋2 個 untracked 檔，加上審查修正（`market-trace.ts`、
  `acceptance.spec.ts`、`market-server.py`、`package.json`、`StockDetail.tsx`）。
  `web/package-lock.json` 仍是 04b 起的既有 untracked 檔，雜湊未動。

## 交付

- `shared/transport/market-trace.ts` 提供跨層 trace：`receive → state → consumer → render` 四點單調時間戳，
  以 `gabfin:market-trace` CustomEvent 送出；不帶 token、cookie、CSRF 或任何憑證。
- `live.ts` 在 snapshot 與每個 WebSocket frame 記錄 receive 時點；`useMarketSubscription`
  在 RAF 合併時補 state 時點；`StockDetail` 以 `useLayoutEffect` 記 consumer／render 時點。
- `tests/e2e/acceptance.spec.ts` 三項：鍵盤對話框 Escape 還原焦點且搜尋仍可用；
  quote trace 對應四層且 30 個 eventId 不重複並驗證時序單調與無憑證洩漏；
  桌面快取導航與首屏時序記錄。
- `playwright.config.ts` 加入 `acceptance.spec.ts` 至 testMatch。

## 缺陷：trace 重複記錄（04e 內部發現並修正）

完整套件 31 passed，但單獨重跑 `acceptance.spec.ts` 會出現 `Expected: 1 / Received: 2`。
診斷確認為**產品程式碼缺陷**，不是測試不穩：

1. `beginQuoteTrace` 對 snapshot 一律取 `quotes[0]`，未核對訂閱 channel／instrument；
   `ChartPanel` 以 `channel:'bar'` 訂閱也會 trace 到 quote 事件。
2. HTTP snapshot 與 WebSocket snapshot 描述同一個 quote event（相同 `event_id`），
   卻各自產生 trace 物件，導致一個事件被記成兩次 render。
3. 讀取端在 session 模式切換時重新 mount，依 component 範圍去重不足以涵蓋。

修正：依訂閱 keys（`channel==='quote'` 且 instrument 相符）過濾；去重改為頁面層級
`Set<string>`，一個市場事件只產生一筆 trace；`live.ts` 把訂閱 keys 傳入 trace 產生點。
完整證據：[trace defect 記錄](artifacts/s04-04e/trace-defect-2026-11-27.md)。

## 驗證

- [RED：trace 未送出](artifacts/s04-04e/red-trace.log)——`__traces.length` 期望 >0 實得 0，4 秒逾時。
  [GREEN：3 passed](artifacts/s04-04e/green-acceptance.log)。
- [production build](artifacts/s04-04e/build.log) exit 0：主 JS gzip 84.85 kB、lazy chart 56.28 kB、
  lazy validator 44.31 kB；不是效能 p95 驗收。
- 修正缺陷後連續 **5 次**重跑 `acceptance.spec.ts` 全部 3 passed；完整套件 **31 passed**（2.8 分鐘），無 flaky。
- 本機（Downloads worktree，Python 3.12.16 venv）重跑：
  `pytest tests/gabfin` → **925 passed**；`pytest tests/gabfin/test_market_api.py` → 25 passed；
  `npm.cmd run typecheck` exit 0；
  `scripts/check-demo-fixtures.py` → 3 quote／3 bar snapshots 通過，60 bars，NVDA 空。
- 實際啟動 Vite dev server（http://127.0.0.1:19045）並用 Edge 開啟：首頁、股票詳情、
  合成 1 分鐘 K 線與 OHLC 數值表正常渲染。已實際查看截圖，非僅 build 成功。

## 量測（分兩個環境，數字均取自提交的 artifact）

兩組數字來自**不同**環境，不可混為一談：

- **API snapshot 與 quote trace** 量自**合成 TLS fixture**（供應 production bundle
  `apps/desk-web/dist`，loopback）。見 `market-measurements.json`。
- **桌面首屏與快取切頁** 量自 **Vite dev server**（`playwright.config.ts` 的 `baseURL`
  `http://127.0.0.1:19045`），**不是** TLS fixture，也**不是** production bundle。
  `navigation-measurements.json` 的 `environment` 欄已如此標明。

- 本機讀 API（`/market/snapshot`，每次 `no-store`、重新解析，**非 HTTP 快取命中**）：n=20，
  median 101.4ms，**p95 141.6ms**，max 150.4ms。對照設計 §12 目標 p95 ≤300ms → 達標。
  `legacyApiMs` 為 null，舊 API 未量測。
- 桌面快取後切頁可用內容（**Vite dev server**）：n=30，median 20.0ms，**p95 29.6ms**，
  max 30.1ms。對照 §12 目標 p95 ≤500ms → 達標。此數字不含 TLS，也不含 production bundle
  的啟動成本。
- 桌面首屏（測試可觀察可用內容上界，**Vite dev server**）：n=20，median 78.6ms，
  p95 122.5ms，max 294.8ms。
- quote 四層延遲（合成 TLS fixture）：receive→state median 0.8ms／p95 2.11ms；
  state→consumer median 0.4ms／p95 0.71ms；consumer→render median 28.85ms／p95 32.86ms；
  receive→render median 30.05ms／p95 35.47ms。30 筆 eventId 全不重複，四層時序全部單調。
- iPhone 私網首屏 p95 ≤2s：**未量測**（無 iPhone 真機，`iphoneHardwareMs` 為 null）。
- 條件限制：單一 Windows 主機；wall clock 比較只作診斷；render 邊界是兩次 RAF paint
  opportunity，不是硬體像素呈現；無 CPU／網絡 throttle。

## 獨立審查與修正（2026-11-27）

聚焦獨立 review（Standards＋Spec 雙軸）發現 **3 個阻塞缺陷**，全部已修正並重新驗證：

1. **trace 永久遺失**：`committed` 在排程 RAF 時就佔位，而 `useLayoutEffect` cleanup 會取消
   前一筆量測的 RAF；該 event_id 已被標記卻永不送出。修正為**送出時才佔位**，
   cleanup 只取消量測、不燒掉 event id。
2. **`event_id` 不可靠作 dedup key**：真實 Futu adapter 由 `(code, event_at, price)` **決定性**
   推導 event id，跨 epoch 可合法重現，會被誤判為重複而漏量。修正為 **epoch + event_id**
   配對；同時把 TLS fixture 改為同樣的決定性推導，讓測試真正觸及此路徑。
3. **量測宣稱與 artifact 不符**：報告數字與提交的 artifact 實算值全數不符，且宣稱全部取自
   TLS fixture，但導航／首屏實際量自 Vite dev server。已改以 artifact 實算值為準，
   並在報告與 artifact 中如實標明各數字所屬環境。

同時收緊：憑證斷言改為**欄位白名單**（原 regex 只檢查結構上不可能出現的詞）；
`committed` 改為有界（500）；`clockSkew` 在來源時間未知時回報 `null` 而非 `false`；
`test:e2e` 前置 `npm run build`，避免 fixture 供應過期 bundle。

新增 2 條測試守住上述路徑：**新 epoch 重用同一 event id 仍須被量到**；
**bar 訂閱者不得為同一 quote 多加一筆 trace**。

## 驗證（修正後重跑）

- `pytest tests/gabfin` → **925 passed**。
- 完整 Playwright 套件 → **33 passed**（原 31，新增 2 條）。
- `npm.cmd run typecheck` exit 0；`npm.cmd run build` exit 0。

## 未完成與界線

- **長駐 operator launcher 與遠端部署未交付**，本單位只交付同源本機驗證。
- 舊 API 的對照量測、legacy 假期測試缺陷、iPhone 真機、其他 Section 頁面均未觸及。
- 未呼叫 OpenD／SDK，未新增市場／帳戶／交易權限，未交易、購買、push 或部署。
- G2 未放行；本單位不構成實時行情或入場依據。
- 提交與 checkpoint 更新隨本單位一併完成。
