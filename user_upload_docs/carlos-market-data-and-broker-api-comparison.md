# 行情與券商 API 供應商比較表

價格核對日：2026-11-27。所有價格為公開標價頁讀數，下單前請以官網結帳頁為準。

## 一、摘要

本文件比較美股行情與下單 API 供應商，供專案採購決策使用。

| 分類 | 供應商 | 標價 | 一句話結論 |
| --- | --- | --- | --- |
| 券商（落單） | Alpaca | $0 | 已接好，paper 免費 |
| 行情（研究） | Massive | $29/月 | 日線首選，落預算內 |
| 行情（免費） | Yahoo / Futu | $0 | 只能做 fallback，不可聲稱實時 |

## 二、本專案現時實際用緊嘅 API

以下為程式碼事實，並非意向。所有路徑相對 `BomFin/.worktrees/gabfin-s04d/`。

| 角色 | 供應商 / API | 證據位置 | 現況 |
| --- | --- | --- | --- |
| 下單執行 | Alpaca Trading API（Paper） | `backend/trading/alpaca_broker.py`、`requirements.txt`（`alpaca-py>=0.33.0`） | 已接好；Live 通道未開 |
| 新工作台行情接入 | Futu OpenD（quote-only） | `services/gabfin/providers/futu/`（`worker.py`、`quote_push.py`、`history.py`） | 只推 quote；缺 BBO 與 session／latency 證據 |
| 研究行情主路徑 | Polygon / Massive（`POLYGON_API_KEY`） | `backend/agents/polygon_equity.py` | 無 key 時自動 fallback Yahoo |
| 研究行情 fallback | Yahoo Finance via `yfinance` | `requirements.txt`（`yfinance>=1.4.0`） | 非合約，會無預警失效 |
| 期權鏈研究 adapter | Tradier、MarketData、Cboe | `backend/agents/` | 只做研究，未接 OrderManager |
| 財務與財報日曆 | Alpha Vantage、Finnhub、SEC EDGAR | `backend/agents/` | 候選來源，非下單路徑 |

限制：閘 G2（market-data entitlement）仍未放行；新工作台 `apps/desk-web/` 顯示的 K 線全部是 `apps/desk-web/public/demo/` 下的合成 fixture。任何「實時行情」敘述在 G2 通關前都不可寫。

## 三、券商 API（負責落單與成交回報）

| 供應商 | 方案 | 費用 | 佣金／交易費 | 購買位置 | 適用性 |
| --- | --- | --- | --- | --- | --- |
| Alpaca | Trading API Basic | $0 | 美股／ETF／期權佣金 $0 | https://alpaca.markets/ | 已接好，paper 免費，零改動 |
| Alpaca | Algo Trader Plus | $99/月 | 佣金仍 $0（Plus 買的是行情） | https://alpaca.markets/ | 需要 SIP 實時與 OPRA 期權時才買 |
| Alpaca | Broker API StandardPlus3000 | $500/月 | 期權 indicative feed 另加 $1,000/月 | https://alpaca.markets/ | 多用戶商業層，現階段不需要 |
| Alpaca | Broker API StandardPlus5000 | $1,000/月 | 含期權 | https://alpaca.markets/ | 同上 |
| Alpaca | Broker API StandardPlus10000 | $2,000/月 | 含期權 | https://alpaca.markets/ | 同上 |
| Futu OpenD | OpenAPI | $0 額外 API 費 | 佣金同 App 一致 | https://open.futunn.com/ | 免費但每筆要錢；需常駐 OpenD 網關 |
| IBKR | TWS API / Web API | API 免費 | 帳戶佣金另計 | https://www.interactivebrokers.com/ | 本專案未接 IBKR client，需新寫 adapter |
| Tradier | Lite | $0/月 | 股票 $0.35/筆、期權 $0.35/合約 | https://tradier.com/pricing | 有 sandbox 可試；只 L1 |
| Tradier | Pro | $10/月 | 股票與期權佣金免，數據期權仍收 | https://tradier.com/pricing | API 費用已含在月費內 |
| Tradier | Pro Plus | $35/月 | 指數期權 $0.10/合約 | https://tradier.com/pricing | 同上 |
| tastytrade | Open API | 開發文件無另標月費 | 需有帳戶；入金門檻本輪未核 | https://developer.tastytrade.com/ | 文件齊全但本專案無 client |

Futu 交易費率（2026-08-13 於本專案 `UPGRADE_LOG.md` 記錄，非今日標價）：美股佣金 $0.0049/股（每單最低 $0.99）＋平台費 $0.005/股（每單最低 $1.00）；美股期權 $0.15/合約起（最低 $1.99）＋$0.30/合約平台費；港股每單平台費 HK$15；美股融資利率 4.8%、港股 6.8%（年）。

## 四、行情 API（負責研究 tape、日 K、歷史）

| 供應商 | 方案與標價 | 實時性／歷史 | 關鍵限制 | 購買位置 |
| --- | --- | --- | --- | --- |
| Yahoo Finance（`yfinance`） | $0 | EOD 加盤前盤後報價 | 非合約，可無預警失效，不可作主行情 | 已內建 |
| Massive（舊 Polygon） | Stocks Basic $0／Starter $29／Developer $79／Advanced $199／Business $2,499 | Starter 15 分延遲 5 年；Advanced 實時，全歷史至 2003-09-10 | 付費層無限呼叫；個人層限非專業自用 | https://massive.com/pricing |
| Massive Options | Basic $0／Starter $29／Developer $79／Advanced $199（年付約 8 折） | Advanced 才含實時 OPRA quotes | 股票方案不含期權，須另購 | https://massive.com/options |
| Alpaca | Basic $0／Plus $99 | Plus 為全美股交易所 SIP 加實時 OPRA | Basic 股票只得 IEX（約 2.5% 成交量），期權只得 indicative | https://alpaca.markets/ |
| Tiingo | Starter $0／Power $30（$300/年）／Commercial $50（$499/年） | 30+ 年 EOD 加 IEX 加 24x5 衍生實時 | Starter 有 500 symbols/月陷阱；Power 亦只 IEX 級別 | https://www.tiingo.com/about/pricing |
| FMP | Basic $0／Starter $29（年付 $19）／Premium $69（$49）／Ultimate $139（$99） | Starter 起含實時；Premium 30+ 年 | 顯示或轉售需另外 Data Display and Licensing Agreement | https://site.financialmodelingprep.com/pricing-plans |
| Databento | 按量 $0.40/GB 起；US Equities Standard $199／Plus $1,500／Unlimited $4,000；CME Standard $199／Plus $1,750／Unlimited $4,500 | 45 venues、25,000+ symbols、8+ 年 | 註冊送 $125 credit，六個月過期 | https://databento.com/pricing |
| IBKR 行情 | Snapshot bundle $10 base 加 $0.01/snapshot；Equity and Options Add-On Streaming $4.50（非專業）或 $125（專業）；OPRA L1 $1.50（非專業，$20 佣金可豁免）或 $32.75（專業）；NYSE／NASDAQ／ARCA 各自 $1.50 | 未訂 OPRA L1 時延遲 15 分鐘 | 多數證券 API 取數需 L1；中途取消不按日折算 | https://www.interactivebrokers.com/en/pricing/market-data-pricing.php |
| Futu 行情卡 | OPRA 實時期權 $2.99/月（非專業）或 $40.80（專業）；US Options Lv2 $3.99 或 $59.99；NASDAQ TotalView $20 或 $80；NYSE OpenBook $20 或 $70 | 美股 LV3 現正推廣期免費，含 Nasdaq Basic 加 TotalView、NYSE ArcaBook | 無證券帳戶亦可登 OpenD，送 100 訂閱與歷史 K 額度，7 天一循環；訂閱額度按資產分檔（少於 HK$10k 為 100，達 HK$10k 為 300） | https://qtcard.futuhk.com/intro/usoption-realtime |
| Alpha Vantage | 免費層 25 req/日；Premium $49.99/月（75 rpm）起，至 $249.99/月（1,200 rpm） | 歷史與實時間隔 | 免費層行不動全宇宙；為租 RSI 而付費並不划算 | https://www.alphavantage.co/premium/ |
| Finnhub | 免費 $0（美股 OHLC 空白，財報日曆僅 1 個月）；All-In-One $3,500/月 | — | 免費層不是價格帶 | https://finnhub.io/pricing |
| Twelve Data | Grow $79／Pro $229／Ultra $999 每月（同一頁 schema.org 仍寫 $29／$99／$329，官網本身不一致） | — | 報價以結帳頁為準 | https://twelvedata.com/pricing |
| Benzinga Earnings（於 Massive 購買） | $99/月 每股據集 | 財報日曆，吐出 ticker 與日期 | 超出本專案 HK$400 預算 | https://massive.com/pricing |
| Intrinio | Individual $150/月 | 財務 | 與 Massive 功能重疊 | https://intrinio.com/pricing |
| Earnings Whispers | $2,495/月／$6,995/季／$24,995/年 | 財報預估 | 過貴，不可爬網站替代 | https://earningswhispers.com/data |
| Unusual Whales | Advanced $375/月；Enterprise $750/月 | 期權 flow、暗池 | 不是價格帶，不可接入 OrderManager | https://unusualwhales.com/public-api |

## 五、採購建議

本專案每月資料預算約 HK$400（約 US$51）。下表按「要完成的任務」對應建議。

| 任務 | 建議 | 每月成本 |
| --- | --- | --- |
| Paper 下單 | 維持 Alpaca Paper，不遷移 | $0 |
| 研究用日 K 與歷史 | 購 Massive Stocks Starter | $29 |
| 財報日曆偵察 | 用免費來源：Alpha Vantage EARNINGS_CALENDAR、Finnhub 免費層、SEC EDGAR 核實 | $0 |
| 新工作台即時報價 | 沿用 Futu OpenD，但須補 BBO、session 與 latency 證據先可通過 G2 | $0（開發成本高） |
| 期權（將來 ns-4） | OPRA 只買一份：Alpaca Plus $99，或 Massive Options Advanced $199，或 Futu OPRA $2.99。三者不可同時購買 | $2.99 至 $199 |

現時最省的組合：Alpaca Paper $0 加 Massive Stocks Starter $29 加免費財報日曆 $0，約 $29/月，落在預算內。
最省的另一條路：完全不買，用 Futu OpenD 免費報價加 Yahoo fallback 做日 K。但此路無法通過 G2，不可寫成已取得實時權益。

## 六、界線與注意事項

1. Futu 美股 LV3 免費屬推廣期，不保證永久。本專案 `docs/market-data-host.md` 亦載明 quote-only 仍為 `live_manifest_unverified`。
2. IBKR 佣金豁免互斥且不累加（$20 佣金免 OPRA，$30 佣金免 Snapshot bundle），不可假設兩份同時豁免。
3. 價格會變動。本文所有數字為公開標價頁讀數，作者並無任何供應商帳戶，亦未實測數據質量。落單前請自行開啟結帳頁再核對一次。
4. 倉內 `BomFin/.worktrees/gabfin-s04d/docs/DATA_FEED_AND_SUBSCRIPTIONS.md` 與 `PROCUREMENT_GUIDE.md` 均標示 LEGACY／SUPERSEDED，價格核對日為 2026-10-26；本文件是 2026-11-27 重新核對的版本。
5. 本專案為紙上交易研究用途。個人與非專業授權足以覆蓋自有帳戶；若日後將行情顯示給第三方，須改買對應商業 SKU（例如 Massive Business $2,499/月），不可用個人層金鑰充數。
6. 免費層與轉售共用金鑰不可作為正式資料來源。

## 七、參考來源

- Alpaca Market Data API: https://docs.alpaca.markets/us/docs/about-market-data-api
- Futu API 費用頁: https://open.futunn.com/api/overview/api-fee
- Futu 權限與配額: https://openapi.futunn.com/futu-api-doc/en/intro/authority.html
- Futu 行情卡報價: https://qtcard.futuhk.com/intro/usoption-realtime
- IBKR 行情定價: https://www.interactivebrokers.com/en/pricing/market-data-pricing.php
- Massive 股票方案: https://massive.com/stocks
- Massive 期權方案: https://massive.com/options
- Tradier 定價: https://tradier.com/pricing
- Tiingo 定價: https://www.tiingo.com/about/pricing
- FMP 定價: https://site.financialmodelingprep.com/pricing-plans
- Databento 定價: https://databento.com/pricing
- Alpha Vantage Premium: https://www.alphavantage.co/premium/
- Finnhub 定價: https://finnhub.io/pricing
- Twelve Data 定價: https://twelvedata.com/pricing
- Intrinio 定價: https://intrinio.com/pricing
- Unusual Whales: https://unusualwhales.com/public-api
- 本專案程式碼與文件: `BomFin/.worktrees/gabfin-s04d/`
