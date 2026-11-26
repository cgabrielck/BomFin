# GabFin 工作台

這是 S04 的 React 工作台。預設示範模式使用固定資料；04c 新增同源 HTTPS
配對登入與只讀行情。候選清單及研究文字仍是設計示例；AI、帳戶及交易尚未接入。
04d 已新增 1 分鐘 K 線／成交量圖、縮放及精確數值表；缺 bar 時保持空態。

從 **source checkout root** 執行（Node 24／npm 11 已驗證）：

```powershell
npm.cmd ci
npm.cmd run contracts
npm.cmd run dev -- --port 19045
```

資料來自 `public/demo/` 本機靜態 JSON，開發／preview 都不連外部 provider。
`public/demo/markets/*.json` 是由 canonical Python MarketSnapshot 驗證的 fixture；
`demo-catalog.ts` 是畫面用的固定候選，不是完整市場 catalog。
示範報價讀單股 quote snapshot；伺服器模式取得快照後透過 WebSocket 增量更新。
K 線使用獨立 bar 訂閱，不因來源只支援 quote 而阻塞報價。`public/demo/bars/` 另有
AAPL／MSFT 各 30 根合成 K 線，NVDA 刻意空白；不是實際市場歷史或交易績效。
自選僅存本頁記憶體，重載會重設。情境選單是示意，不代表真實健康探測。

## 驗證

```powershell
npm.cmd run typecheck
npm.cmd run build
npx.cmd playwright test
.venv/Scripts/python.exe scripts/check-demo-fixtures.py
```

`scripts/generate-chart-fixtures.py` 可離線重建 canonical 合成 bars；quote 樣本維持原檔。

Playwright 使用已安裝的 Microsoft Edge，在 loopback 19045 啟動獨立 Vite server。
當前機器的瀏覽器可用；換機器時先核對 Edge 安裝，不把本機通過當跨平台驗收。
Production bundle 可用 `npm.cmd --prefix apps/desk-web run preview -- --port 19046` 本機檢查。

TypeScript wire types 只從 `schemas/gabfin-1.0.json` 生成，勿手寫／修改 `generated.ts`。
修改後端契約後先更新 schema，再跑 `npm.cmd run contracts`。
`market.schema.json` 同樣由 schema 生成，供伺服器模式的 runtime validation 使用；
示範 sanity checks 不取代它。金額維持 decimal string，不轉成浮點數。

## 伺服器模式

HTTP Vite preview 只供示範。伺服器模式須由可信本機 bootstrap 組裝
`create_market_app(store, allowed_origin=..., gateway=..., static_dir=Path(...))`，
以 TLS server 提供已 build 的 `dist`。Origin 必須是完全相同的 `https://host:port`；
綁定 loopback、關閉 proxy headers，設定憑證／私鑰並限制同時連線。
正常使用須由瀏覽器信任該本機憑證，不能停用正式環境 TLS 驗證。

Gateway 使用 `MarketGateway.from_store(...)`，接至既有 S03 listener 並共用該主機的
SessionStore；只能由可信主機設定有限 `registered_keys` 及 source，不能接受 browser
提供內部地址或憑證。每次連線發行 read_market service lease，關閉時撤銷。
SDK 仍由 S03 程序持有，沒有為每個 browser 啟動 SDK。前端目前只有三個固定候選 ID，
bootstrap 必須配置相符的 canonical ID；任意 symbol resolution 留待後續 Section。

主機經私有本機操作建立短效單次配對碼，使用者在「資料模式 → 伺服器行情」輸入。
此工作單位提供 factory 與完整測試入口，尚未交付長駐操作 launcher 或遠端部署。
登入 cookie 是 Secure／HttpOnly／SameSite=Strict；可讀 CSRF nonce cookie 綁定同一 session。
沒有把 auth／internal token 存入 URL、localStorage 或前端 bundle。斷線有界重試三次；
每次重連先收完整 snapshot。失效或登出會清除報價；資料來源時間與缺口獨立顯示，
連線正常不能當成價格新鮮或權益已核實。
一般斷線錯誤也會在 2 秒時限內向 `/session` 核對；401 即清除報價並要求配對，
避免代理或內部憑證同時到期時，遺失 policy close code 而保留已失效畫面。

## 增量圖表

只有 `features/chart/chart-port.ts` 接觸 Lightweight Charts 5.3.0；library／canvas 只在有 bar
時 lazy load。初次、完整 snapshot reset、插入缺失歷史區間或容量壓縮時才 `setData`；
普通 bar 走 `update`，歷史修訂走 `historicalUpdate`。不因每筆更新重設使用者縮放。
Bar book 保留最多 1000 根，超過時壓縮到最新 500 根，避免滑動窗口每根都全量重畫。
切股、登出、到期、空 snapshot 或離頁會清除舊圖、observer 及訂閱。

OHLC／volume 的原始欄位與數值表保留 decimal string；只在繪圖邊界轉 number。
繪圖拒絕非 finite、負數、超過 MAX_SAFE_INTEGER 或介乎 0 與 1e-8 的值；
不能畫的 bar 明示錯誤，quote 仍獨立顯示。volume 缺失用空點，從不推算或相加。
形成中更新覆寫同一區間，舊 revision／舊 receipt 不倒退，final 不退回 forming；
同版本 final 衝突拒絕顯示。時間為 UTC；目前只有 1m，沒有任意週期或真實 provider bar 證據。

圖表署名、官方 [NOTICE](https://raw.githubusercontent.com/tradingview/lightweight-charts/v5.3.0/NOTICE)
及 Apache 2.0 license 保留於 `public/third-party/`，畫面有 TradingView 連結。

`secure-market.spec.ts` 每測試啟動臨時 TLS/API/S03 socket fixture，私有 stdio 提供配對碼。
需要主機安裝 `gabfin[web]`、測試依賴 `httpx2` 及 Git 的 OpenSSL。測試的自簽憑證例外
只限 Playwright context；所有價格是明示 `fixture` 來源的合成資料，未代表 OpenD 驗收。

舊 `web/` 與其原 lockfile 保留。新 app 沒有沿用 legacy trading 或第三方產品程式碼。
