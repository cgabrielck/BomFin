# GabFin

A personal stock research and market workspace, being rebuilt toward evidence-based research and controlled AI-assisted paper trading.

English first · [繁體中文](#繁體中文)

## Current status

Completed through **S04/04d**: a responsive React workspace, secure read-only market integration, and incremental one-minute candlestick and volume charts. The interface currently uses Traditional Chinese.

- Browse three sample stocks, search, open stock details, and maintain a temporary watchlist.
- Inspect clearly labelled synthetic charts, exact OHLC values, missing data, source timestamps, and connection gaps.
- Pair with a local HTTPS market host using secure sessions. Expiry and logout clear prices; reconnects start with a full snapshot.
- Quotes and bars are independent: a quote-only provider does not produce invented candles or volume.

**AI research, real opportunity discovery, account integration, automated paper trading, and live trading are not connected to this new workspace yet.** Market entitlement gate G2 remains open. No trading is started by the demo commands below. S04/04e integration acceptance and latency tracing are next.

## Run the demo

From this repository root, using Node.js 24 and npm 11 (the versions tested locally):

```powershell
npm.cmd ci
npm.cmd run dev -- --port 19045
```

Open **http://127.0.0.1:19045**. On macOS/Linux, use `npm` instead of `npm.cmd`; those platforms have not been verified. The demo needs no broker credentials or paid data subscription. AAPL/MSFT candles are synthetic; NVDA deliberately has no bars. Watchlists reset on reload.

For production build inspection:

```powershell
npm.cmd run typecheck
npm.cmd run build
npm.cmd --prefix apps/desk-web run preview -- --port 19046
```

HTTP preview is demo-only. Server market mode requires a trusted local HTTPS bootstrap and an existing S03 market listener; a persistent operator launcher and remote deployment are not included. See the [workspace guide](apps/desk-web/README.md) for integration details.

## Repository layout

| Path | Purpose |
| --- | --- |
| `apps/desk-web/` | New React/Vite workspace |
| `services/gabfin/` | Versioned contracts, sessions, market state, and read-only API bridge |
| `schemas/` | Canonical contract schemas |
| `tests/e2e/` | Browser integration and bar patch tests |
| `tests/gabfin/` | New Python component tests |
| `backend/`, `web/` | Preserved legacy application; separate from the new workspace |

The planning/memory documents live in the outer development workspace. They are not included in this source-root branch. Older ADRs do not govern this redesign. The original README is preserved as [historical documentation](docs/README-legacy.md); its feature descriptions and test badges are not current acceptance evidence.

## Verification and limits

```powershell
npx.cmd playwright test
```

The S04/04d checkpoint passed **28 Playwright tests** (23 browser cases and 5 bar patch cases), TypeScript checks, and the production build on Windows with Microsoft Edge. HTTPS fixture tests additionally require the configured Python environment, `gabfin[web]`, `httpx2`, and Git OpenSSL; see the workspace guide. These are recorded checkpoint results, not a guarantee for every environment.

The earlier full Python regression had one legacy holiday-dependent shadow-test failure and four optional PostgreSQL skips. It is not fully green. This checkpoint does not establish real-time data rights, real provider bars, iPhone hardware acceptance, or trading readiness.

Charts use Lightweight Charts 5.3.0. Its attribution and license are retained under `apps/desk-web/public/third-party/` and displayed in the chart UI.

---

## 繁體中文

GabFin 是逐步重建中的個人選股研究及行情工作台，目標包括具證據的研究，以及受控的 AI 輔助模擬交易。

### 目前進度

已完成至 **S04/04d**：響應式 React 工作台、安全只讀行情接入，以及 1 分鐘 K 線／成交量增量圖表。目前介面採用繁體中文。

- 可搜尋三檔示範股票、查看詳情，並維護本頁暫存自選。
- 圖表明示合成資料，提供精確 OHLC 數值、缺資料、來源時間及連線缺口。
- 本機 HTTPS 主機使用安全 session 配對；到期／登出清除報價，重連先取得完整快照。
- Quote 與 bar 獨立；只有報價的來源不會被拼成假 K 線或成交量。

**新工作台尚未接入 AI 研究、真實機會池、帳戶、自動 paper trade 或真實交易。** G2 行情權益關卡仍未放行。以下示範指令不會啟動交易；下一步為 S04/04e 整合驗收及延遲追蹤。

### 啟動示範

在 repository 根目錄，以本機已驗證的 Node.js 24／npm 11 執行：

```powershell
npm.cmd ci
npm.cmd run dev -- --port 19045
```

開啟 **http://127.0.0.1:19045**。macOS/Linux 可改用 `npm`，但尚未實測。示範不需要券商憑證或付費行情；AAPL／MSFT K 線為合成資料，NVDA 刻意缺 bar，自選重載後重設。

建置及檢查：

```powershell
npm.cmd run typecheck
npm.cmd run build
npm.cmd --prefix apps/desk-web run preview -- --port 19046
npx.cmd playwright test
```

HTTP preview 只供示範。伺服器行情模式需要可信本機 HTTPS bootstrap 及既有 S03 listener；未包含長駐操作 launcher 或遠端部署。整合設定見[工作台指引](apps/desk-web/README.md)。

### 程式位置及驗證界線

`apps/desk-web/` 是新前端，`services/gabfin/` 是新契約、session、行情狀態與 API，`schemas/` 保存 canonical schema。`tests/e2e/` 與 `tests/gabfin/` 分別驗證瀏覽器及新 Python 元件；`backend/`、`web/` 保留舊程式。

規劃／memory 文件留在外層開發工作目錄，未包含於這個以 source 為根的分支。舊 ADR 不約束新版；[原 README](docs/README-legacy.md) 僅供歷史參考，其功能描述及徽章不代表目前驗收。

S04/04d 在 Windows／Microsoft Edge 通過 **28 項 Playwright 測試**（23 個瀏覽器案例及 5 個 bar patch 案例）、型別檢查與 build。HTTPS 測試另需 Python 環境、`gabfin[web]`、`httpx2` 及 Git OpenSSL，詳見工作台指引。

較早的 Python 全套回歸仍有一項依賴假期日期的舊 shadow 測試失敗，以及四項可選 PostgreSQL skip，不能宣稱全套通過。現有結果亦不代表即時權益、真實 provider bars、iPhone 真機或交易準備已驗收。

圖表使用 Lightweight Charts 5.3.0，署名與授權文件保留於 `apps/desk-web/public/third-party/`，畫面亦有署名。
