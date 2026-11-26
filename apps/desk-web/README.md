# GabFin 示範工作台

這是 04b 的 React 前端殼；全部候選、價格與研究文字都是固定示例。
沒有行情、AI、帳戶、登入或交易服務。K 線區保留空態，等待有來源的 bar。

從 **source checkout root** 執行（Node 24／npm 11 已驗證）：

```powershell
npm.cmd ci
npm.cmd run contracts
npm.cmd run dev -- --port 19045
```

資料來自 `public/demo/` 本機靜態 JSON，開發／preview 都不連外部 provider。
`public/demo/markets/*.json` 是由 canonical Python MarketSnapshot 驗證的 fixture；
`demo-catalog.ts` 是畫面用的固定候選，不是完整市場 catalog。
目前 `useMarketSubscription` 僅讀取單股 quote snapshot，沒有即時推送／輪詢。
自選僅存本頁記憶體，重載會重設。情境選單是示意，不代表真實健康探測。

## 驗證

```powershell
npm.cmd run typecheck
npm.cmd run build
npx.cmd playwright test tests/e2e/market.spec.ts
.venv/Scripts/python.exe scripts/check-demo-fixtures.py
```

Playwright 使用已安裝的 Microsoft Edge，在 loopback 19045 啟動獨立 Vite server。
當前機器的瀏覽器可用；換機器時先核對 Edge 安裝，不把本機通過當跨平台驗收。
Production bundle 可用 `npm.cmd --prefix apps/desk-web run preview -- --port 19046` 本機檢查。

TypeScript wire types 只從 `schemas/gabfin-1.0.json` 生成，勿手寫／修改 `generated.ts`。
修改後端契約後先更新 schema，再跑 `npm.cmd run contracts`。
同源 auth、完整 runtime wire 驗證及安全 bridge 由 04c 接入；示範 sanity checks 不取代它們。

舊 `web/` 與其原 lockfile 保留。新 app 沒有沿用 legacy trading 或第三方產品程式碼。
