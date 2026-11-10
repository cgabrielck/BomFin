# 資料訂閱建議 — 能長期用的 API，不是爬蟲

**Status:** Recommendation revised to the owner's budget（2026-10-26 Asia/Hong_Kong）。方法頁已 Accepted；**本頁不是訂單。** **本 PR 不購買、不寫入金鑰、不改 runtime。**  
**Binds under:** [AI_SMART_TRADER_METHOD.md](AI_SMART_TRADER_METHOD.md) §3.1 Scout。價錢以下一頁結帳為準；本頁標的是核對日看到的公開標價。  
**Does not:** 購買任何方案、把金鑰寫進 git、把新聞或財報日曆接到 `OrderManager`。

價格核對日：**2026-10-26**。

---

## 0. 給主人的摘要

主人每月資料預算約 **HK$400（約 US$51）**。這是主人給的換算，不是本頁即時匯價。在這個上限裡，只有一份約 $29 的日 K 放得下。**這次 PR 什麼都不買，也不寫金鑰。**

要買的是有文件、有鑰匙、有費率、允許我們自己的紙上桌（之後才談真倉）使用的資料。不要把網站爬下來當主來源。Yahoo 只可拿來對一下，不能當正式行情。財報「預計日期」先用免費日曆；「已經公布」用 SEC 申報（含 XOOMAR）核對。

| | 建議 | 公開標價（核對日） | 為什麼 |
|--|------|-------------------|--------|
| **稍後再買（不是這次 PR）** | **Massive Stocks Starter**（舊名 Polygon；倉庫已有 `POLYGON_API_KEY`／`MASSIVE_API_KEY`） | **約 $29／月** | 落在 HK$400 以內。日 K、分鐘 K（延遲 15 分鐘）、拆股與股息、代碼主檔、技術指標端點、帶股票代碼與原文連結的新聞。付費層不限呼叫次數。免費層每分鐘只有 5 次，不夠當日 K 主帶 |
| **現在不買** | **Massive 上的 Benzinga Earnings** | 定價頁 **約 $99／月／每個資料集** | **超出 HK$400。** 股票方案本身不含這支。財報日曆改走下面的免費來源 |
| **現在就用（免費）** | Alpha Vantage `EARNINGS_CALENDAR`；Finnhub 免費財報日曆 | **$0**（各要自己的免費鑰匙或額度） | 會吐出股票代碼的預計財報日。見 §3.3。只寫候選 |
| **用來核對「已公布」** | SEC EDGAR，以及 XOOMAR 的免費財報 API | **$0** | XOOMAR 的 `reported` 是 8-K Item 2.02 的申報日，並帶 accession。估計日要等 8-K 才算確認 |
| **可後買，且不能與 Starter 疊在這筆預算裡** | Massive **Financials & Ratios**；**Tiingo Power**；Massive **Developer** | **$29／月**；個人 **$30／月**；**$79／月** | $29 加 $30 已超過約 US$51。劇本今天用價量。Developer 仍是延遲，歷史較長，公平回測那扇窗用 Starter 的 5 年已蓋得住 |
| **現在先別買** | Massive Stocks **Advanced**、Alpaca **Algo Trader Plus** | **$199／月**、**$99／月** | 都超出預算。現有股票策略是日線。Plus 的 OPRA 留到期權工作（ns-4）再二選一 |
| **先別買** | Finnhub All-In-One、Twelve Data、Alpha Vantage Premium、Intrinio、Unusual Whales、Earnings Whispers | 見下文 | 與上面重疊、標價互相打架、或是期權流量／機構價。免費層可以當日曆，不能當日 K |
| **現在不要買** | Bloomberg Terminal／B-PIPE／Data License；IBKR 遷移；把研究帶改去 Tradier；付費牆 PDF；淘寶共享鑰匙 | 官網不標價，或見 §9 | 個人紙上桌維持 Alpaca。Tradier 不是研究終端。比較在 §9 |

個人方案（Massive Basic 到 Advanced）是**非專業、自用**。資料不能轉給別人看。若日後這張桌子要顯示給其他客戶，要改買 **Stocks Business（公開標價 $2,499／月）**，不能拿 $29 的鑰匙充數。主人自己的紙上桌，先用非專業個人方案即可。

偵察每兩日可以用這些 API 找名字。找到的名字仍不是買單。

主人要的功能包含期權，不能把訂閱鎖死在「只做股票」。期權仍不是本方法第一階段的驗收項（主人稱為後續北極星 ns-4；倉庫沒有 ns-4 設計頁）。下面是 2026-10-26 的方案比較。券商行情訂閱不是研究終端；紙上單不是真倉；非專業自用不是把行情轉給客戶。

| 方案 | 適合什麼 | 大概費用 | 是否含期權 | 建議 |
|------|----------|----------|------------|------|
| **Massive 股票 Starter** | 稍後的日 K、新聞、全市場單日 | **約 $29／月**，在 HK$400 以內 | 股票方案**不含**。期權另購；2026-10-26 期權行銷頁**沒有**渲染美元價 | **稍後再買，不是這次 PR。** 只寫候選，不下單 |
| **Benzinga 財報** | 會吐出代碼的付費財報日曆 | **約 $99／月** | 日曆，不是期權鏈 | **現在不買。** 超出 HK$400。先用免費日曆 |
| **Alpaca** | 現有紙上券商。文件已寫股票、ETF、加密與期權（含多腿紙上） | 基本行情 **$0**（股票只 IEX，期權是 indicative）。**Algo Trader Plus $99／月** 才是股票 SIP ＋ 期權 OPRA | 下單文件有。基本行情不是研究級 OPRA | **紙上股票繼續用 Alpaca。** 期權開工時優先沿這條擴下單，並只加一份 OPRA |
| **IBKR**（TWS／API ＋ 行情） | 另一家券商：美股與期權下單、紙上帳戶。不是研究終端 | 非專業：快照套餐底價 **$10**（達佣金可豁免）＋ 每次快照 **$0.01**；「股票與期權串流附加」**$4.50／月**（專業 **$125**）；OPRA L1 另列非專業 **$1.50**、專業 **$32.75**。不按日折算 | 含。未訂 L1 時 OPRA 延遲 **15 分鐘**。API 多數證券要 L1 | **現在不遷移。** 沒有 IBKR 客戶端。Alpaca 期權不夠時才當新券商 |
| **Tradier** | 另一家有文件的美股／ETF／期權券商 API，含沙盒 | Lite **$0**、Pro **$10**、Pro Plus **$35**／月。API 含在帳戶內，沒有另收 API 費。指數期權另計 | 含鏈、Greeks、多腿。沙盒行情延遲 15 分鐘。行情不能當獨立產品轉售 | **不取代 Alpaca。** 倉庫只有期權鏈轉接，沒有下單。備選券商 |
| **tastytrade Open API** | 官方開發文件：股票、期權、期貨報價（DXLink／dxFeed）與下單 | 開發文件**沒有**另標 API 月費；要有帳戶。本輪未核對入金門檻 | 文件有。使用條款限交易與觀察清單，不可收集大截面，不可轉給第三人 | **這輪不買。** 倉庫沒有客戶端，也不能當偵察的研究帶 |
| **Bloomberg**（Terminal／B-PIPE／Data License） | 機構終端與企業饋送：新聞、分析、多資產 | **官網不標價。** Investopedia 詞條寫 2026 年單機年費不到 **$32,000**、多機每座 **$28,320**（腳註指向轉售整理，不是 Bloomberg 發票） | 終端與 B-PIPE 涵蓋與終端相同的資產類別，含期權；企業合約另議 | **個人紙上桌不要買。** 只有日後要彭博新聞室與機構分析、並接受多年座位，才另案。它不取代券商下單 |

**分階段（對齊 HK$400）。** 這次 PR：維持 Alpaca 紙上帳戶；不買 Massive、不買 Benzinga、不開 IBKR、不把研究帶遷到 Tradier、不買 Bloomberg、不買任何 OPRA、不寫金鑰。財報偵察先用 Alpha Vantage `EARNINGS_CALENDAR`、Finnhub 免費日曆；已公布與否用 SEC／XOOMAR 核對。稍後、另一次決定：在預算內買 Massive Stocks Starter（約 $29／月）當日 K。期權（ns-4）仍在股票紙上閉環之後：研究鏈沿 `polygon_options.py` 加一份 Massive Options（結帳看價），或改買 Alpaca Plus 的 OPRA，二者只留一份；下單優先擴展 Alpaca 已寫明的期權紙上路徑。IBKR 或 Tradier 只在那條路不夠時才換券商，而且 Tradier 不當研究帶。三份即時期權不要一起付。報價與候選都不是訂單。

---

## 1. What the desk actually needs

| Need | Who reads it | Surviving shape | Not sufficient |
|------|----------------|-----------------|----------------|
| Daily OHLCV, adjusted | Playbook, worker, fair-backtest yardstick | Documented aggregates API, history ≥ 5 years, calls enough for the full `STOCK_UNIVERSE` each session | Yahoo; Alpaca Basic IEX (~2.5% of volume) |
| Optional intraday | Later monitor. Not Phase 1 | Minute bars. 15-minute delay is enough while exits are daily-bar rules | A realtime SIP subscription bought "just in case" |
| Corporate actions | Bars that do not lie after a split | Dividends and splits endpoints on the same vendor as the bars | Scraped split tables |
| Earnings calendar that **emits symbols** | Scout, every ~2 days | One query by date returns many tickers, each with an id and a date | `fetch_next_earnings` (one ticker we already chose, via yfinance) |
| Economic calendar | Optional macro note | A real calendar API. Not required for the equity scout | A $3,500 bundle bought only for CPI dates |
| News with tickers **and** a URL | Scout provenance | `tickers[]` plus `article_url` (or equivalent) | A headline with no link; a tip sheet |
| Reference / universe | Listability, `list_date`, grouped daily bars | One grouped-daily call for the US tape, plus ticker reference | Hard-coding a 12-name list |
| Fundamentals or pre-built indicators | Desk research, not the order ticket | Optional add-on. Local RSI/SMA from our own bars stays the playbook math | Paying a second vendor to recompute RSI |
| Broker fills | Executor only | Alpaca paper trading API (already wired) | Using the broker's free IEX feed as the research tape |

Scout output remains `scout_candidate.v0`: symbol, theme, sources, asof, expiry. The next buy still requires playbook `VALID` → optional judge → mandate → `RiskEngine` → one submitter. See the method doc.

---

## 2. Survive criteria

A feed is eligible as primary only if all of these are true:

1. **Documented API** (REST or official flat file), with a stable host and key auth.
2. **A paid tier with a public price** or a clear self-serve checkout. Free tiers may corroborate. They are not the primary.
3. **License covers this desk.** Personal / non-professional is enough for Gabriel's own paper book. Redistribution or a multi-user product is a different SKU. Record which one was bought.
4. **Rate limit fits** ~70–80 names per session plus one bi-daily market pass. A cap of 25 calls/day or 5 calls/minute does not.
5. **No HTML scrape as primary.** Scraping Yahoo, TradingView, Earnings Whispers, or a paywalled PDF is out.
6. **Commercial-automation hostile ToS is a drop**, even if a key happens to work.

---

## 3. Tier A — the one paid tape that fits the budget

One later purchase, not this PR. Do not also buy a separate "Polygon.io" key: since 2025-10-30 the brand is **Massive**, and this repo already treats `POLYGON_API_KEY` and `MASSIVE_API_KEY` as the same secret (`backend/agents/polygon_equity.py`, default host `api.polygon.io`). Owner monthly cap ≈ **HK$400 (~US$51)**. Stocks Starter at ~$29 fits. Benzinga Earnings at ~$99 does not.

### 3.1 Massive Stocks Starter — primary tape

| | |
|--|--|
| Pages checked 2026-10-26 | [massive.com/stocks](https://massive.com/stocks), [massive.com/pricing](https://massive.com/pricing), [subscriptions](https://massive.com/knowledge-base/article/what-are-the-different-massive-subscriptions-i-can-use), [non-pro](https://massive.com/knowledge-base/article/what-are-pro-and-non-pro-classifications-for-massives-stock-data), [history](https://massive.com/knowledge-base/article/how-much-historical-stock-data-does-massive-have) |
| List price | **$29/month.** Developer $79. Advanced $199. Basic $0. Business **$2,499/month** for commercial display. Annual billing is advertised; use checkout for the discounted figure |
| Covers | Daily and minute aggregates, snapshots, second aggregates, corporate actions, reference, technical-indicator endpoint, flat files, WebSocket. **15-minute delayed** on Starter and Developer. Real-time quotes only on Advanced / Business |
| Grouped daily | [`GET /v2/aggs/grouped/locale/us/market/stocks/{date}`](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary) is on **all** Stocks plans. History on Starter is **5 years**; recency is 15-minute delayed. One call is the whole US tape — this is the scout's price sweep, not 74 serial Yahoo calls |
| News | [`GET /v2/reference/news`](https://massive.com/docs/rest/stocks/news) is on **all** Stocks plans, including Basic. Each article has `tickers[]` and `article_url`. History on Basic is 2 years; Starter and above are "all history". Updated hourly |
| Repo today | `polygon_equity.py`: daily bars and `list_date` only. No grouped daily, no news, no corporate-action call. `equity_ohlcv.py` already prefers this vendor when the key is real |
| Allowlist | Use existing `polygon_grouped_daily` and `polygon_reference`. **Add** `massive_news` in the Phase 1.5 PR (same host as Polygon). Do not label these rows `yahoo_news_ticker` |
| Free-tier trap | Basic is 5 calls/minute, end-of-day, 2 years of bars. It will not carry the worker. Do not "start on free and see" |
| License | Individual plans are **non-professional personal use**. Not for showing the feed to other customers |

Starter's 5-year window, counted back from 2026-10-26, reaches about October 2021. That covers the fair-report window (`2023-09-28` → `2026-09-26`) and a 2022 down market. Developer ($79) is the upgrade when a study needs more than 5 years, not the first invoice.

### 3.2 Benzinga Earnings on Massive — symbol-emitting calendar

| | |
|--|--|
| Pages checked 2026-10-26 | [massive.com/pricing](https://massive.com/pricing) (Benzinga "$99/month per dataset"), [earnings endpoint](https://massive.com/docs/rest/partners/benzinga/earnings), [partner index](https://massive.com/docs/rest/partners/overview) |
| List price | **$99/month per Benzinga dataset** on the Massive pricing page. The earnings route is plan-gated to **Benzinga Earnings**, not to Stocks Starter. Confirm at checkout that the $99 SKU is earnings and not ratings, news, or guidance. Direct Benzinga licensing is quote-only ([docs.benzinga.com](https://docs.benzinga.com/introduction/introduction), `licensing@benzinga.com`) — do not scrape benzinga.com while waiting |
| Covers | `GET /benzinga/v1/earnings` filtered by `date`. Each row has `ticker`, `benzinga_id`, `date`, `date_status`. That is a scout candidate: symbol + ref + asof. It does not include a side or a size |
| Repo today | No Benzinga client |
| Allowlist | Store as `earnings_calendar` with publisher `benzinga` and `ref` = `benzinga_id` or the request URL. This matches the method's existing type. It is not an order |

**Do not buy this under the HK$400 cap.** ~$99 is above ~US$51, and stacking it on Starter (~$128) is further over. Stocks Starter alone does not include this endpoint. Use the free calendars in §3.3 until a later budget says otherwise. Do not scrape benzinga.com.

### 3.3 Free earnings calendars — use these now

Checked 2026-10-26. None of these is a daily-bar tape. None of them is wired by this PR. A symbol they return is still a candidate.

| Source | What the public page says | How the scout may use it | Limit |
|--------|---------------------------|--------------------------|-------|
| Alpha Vantage `EARNINGS_CALENDAR` | [Documentation](https://www.alphavantage.co/documentation/#earnings-calendar): CSV of expected earnings. No `symbol` returns the full list. `horizon` is `3month` (default), `6month`, or `12month`. A free key is required | One call every two days emits symbols with a report date. Store as `earnings_calendar`, publisher `alpha_vantage`, `ref` = the request URL | Standard free limit on the premium page is **25 requests/day**. One calendar call fits. The same free key **cannot** walk `STOCK_UNIVERSE` for OHLCV. Repo client `alpha_vantage_data.py` is not this endpoint today |
| Finnhub earnings calendar | [Pricing](https://finnhub.io/pricing): free tier includes a **1 month** US earnings calendar, 60 calls/minute. US OHLC is blank on Free | A second free symbol list for the next month. Store as `earnings_calendar`, publisher `finnhub` | One month is short. Do not buy All-In-One ($3,500/month) to lengthen it. No Finnhub client in the repo |
| SEC EDGAR | [Access policy](https://www.sec.gov/os/accessing-edgar-data): 10 requests/second, declare a User-Agent | Confirm a result was **reported** (8-K Item 2.02), not merely estimated. Store as `sec_edgar_filing` with the accession or filing URL | Filings are not prices and not a forward calendar by themselves. `sec_analyzer.py` is per name |
| XOOMAR earnings API | [xoomar.com/markets/api/earnings](https://xoomar.com/markets/api/earnings): `reported` = filing date of an 8-K with Item 2.02 since January 2023, with `accessionNo`. `estimated` stays until that 8-K arrives. Window default today → +14 days, up to 120 days. No key: 10 requests/minute per IP; free key: 30/minute. At least six months of history on the free API | Prefer `status=reported` to confirm. An estimate is an expected week, not an announced day. Store reported rows as `sec_edgar_filing` or `earnings_calendar` with publisher `xoomar` and `ref` = accession. Credit XOOMAR if the rows are republished | No XOOMAR client in the repo. Foreign issuers that file 6-K, and results that appear only on a 10-Q, are absent. No time-of-day |

---

## 4. Tier B — later, for analysis

| Product | List price checked 2026-10-26 | Why it can wait | Repo |
|---------|-------------------------------|-----------------|------|
| Massive Financials & Ratios | $29/month on individual plans ([massive.com/stocks](https://massive.com/stocks)) | Playbooks do not read statements. Add when Desk research wants ratios from the same key | None |
| Tiingo Power | $30/month individual, $50/month internal commercial or $499/year. Free Starter is $0 ([tiingo.com/about/pricing](https://www.tiingo.com/about/pricing)) | Independent EOD (30+ years) and news. Power: 10,000 requests/hour, 100,000/day, 110,377 symbols/month. **Fundamentals are a paid add-on, contact sales — not inside the $30.** Internal use means do not display the data to anyone else | No client |
| Tiingo free / Starter | $0 | **Trap:** 500 unique symbols/month, 50 requests/hour, 1,000/day. A full-universe plus scout month can exceed 500 symbols | — |
| Quiver API Trader | $75/month; Hobbyist $30. No commercial use on those tiers ([api.quiverquant.com/pricing](https://api.quiverquant.com/pricing/)) | Congress, 13F, lobbying. Useful color, not the price tape or the earnings calendar | None |
| Massive Stocks Developer | $79/month | Deeper history and trades. Same 15-minute delay. Buy when a backtest needs >5 years. **$79 exceeds the HK$400 cap** | Same client as Starter |

Indicators: Stocks Starter already lists a technical-indicator endpoint, and this repo computes RSI and moving averages from bars in `technical_analyzer.py` and the strategy modules. Do not buy Twelve Data or Alpha Vantage Premium in order to rent RSI.

---

## 5. Tier C — later or do not buy

| Product | What was on the public page 2026-10-26 | Decision |
|---------|----------------------------------------|----------|
| Massive Stocks Advanced | $199/month, real-time, quotes, full history back to 2003-09-10 | Not while strategies are daily bars |
| Massive Stocks Business | $2,499/month | Only if the feed is shown to other users |
| Alpaca Algo Trader Plus | $99/month, full SIP, 10,000 calls/minute, history since 2016. Basic is free IEX, 200 calls/minute, latest 15 minutes withheld ([docs](https://docs.alpaca.markets/us/docs/about-market-data-api)) | Broker stays Alpaca paper. Do not use IEX as research OHLCV. Do not buy Plus **and** Massive Advanced |
| Finnhub All-In-One | **$3,500/month**, billed annually, personal use. Free tier: 60 calls/minute, 1 year of company news, **1 month** US earnings calendar, websocket 50 symbols. US OHLC column is blank on Free and filled only on All-In-One ([finnhub.io/pricing](https://finnhub.io/pricing)) | Do not buy. Free calendar is too short and not a price feed |
| Twelve Data | Page body: Grow **$79**, Pro **$229**, Ultra **$999** per month. The same URL's schema.org block still says **$29 / $99 / $329** ([twelvedata.com/pricing](https://twelvedata.com/pricing)). Credits: a statement pull can cost 100 credits per symbol. Basic is 8 credits/minute and 800/day | Do not buy until checkout shows one price. Even then it duplicates Massive, and heavy fundamental calls will not scan a wide book on the cheap tier |
| Alpha Vantage Premium | $49.99/month for 75 requests/minute, up to $249.99 for 1,200/minute. Page says the standard limit is **25 requests/day** ([alphavantage.co/premium](https://www.alphavantage.co/premium/)). Premium terms are personal unless a written commercial agreement exists | Do not buy as primary. Repo client: `backend/agents/alpha_vantage_data.py`. Free tier cannot walk `STOCK_UNIVERSE` |
| Intrinio Individual | $150/month personal, no redistribution. Startup starts at $333/month and steps up ([intrinio.com/pricing](https://intrinio.com/pricing)) | Overlaps Massive. No client. Not first |
| Unusual Whales | Options flow, dark pool, congress. API Advanced **$375/month**. A lower plan is on the page; its dollar figure did not render in this check ([unusualwhales.com/public-api](https://unusualwhales.com/public-api)). Enterprise startup $750/month | Out of Phase 1.5 (no options auto-trading). Do not point its MCP at `OrderManager` |
| Earnings Whispers data | **$2,495/month**, $6,995/quarter, or $24,995/year, internal license ([earningswhispers.com/data](https://earningswhispers.com/data)) | A real feed, and too expensive next to a $99 calendar dataset. Do not scrape the website |
| TradingEconomics | Pricing URL returned **403** on 2026-10-26 ([tradingeconomics.com/api/pricing.aspx](https://tradingeconomics.com/api/pricing.aspx)). No price is recorded here | Optional macro calendar only after a human can read the price. Not required for the equity scout |
| TradingView | Charting product and site. No worker REST in this evaluation | Not a primary API. Scraping the site is rejected. Desk charts stay on our OHLCV |
| Bloomberg, FactSet, Refinitiv, Capital IQ | No public list price on Bloomberg's own pages. See §9 | Not a purchase for this desk. §9 records when a terminal would even be the question |

---

## 6. Honest gaps already in the repo

| Source | Role | Limit |
|--------|------|--------|
| Yahoo via `yfinance` (`data_fetcher.fetch_news`, `fetch_next_earnings`, worker fallback bars) | Corroboration and today's unlabeled fallback | Not a contract, not a universe scout, breaks without notice. Session card must not call it the primary once a Massive key exists |
| SEC EDGAR ([access policy](https://www.sec.gov/os/accessing-edgar-data), reviewed by the SEC 2024-06-26; rate **10 requests/second**; declare a User-Agent) | `sec_edgar_filing`. Free, public, survives. `data.sec.gov` JSON and daily index files list CIK, form, date | Filings are not prices and not a confirmed earnings date. `sec_analyzer.py` is per name, not a market sweep. A later scout may read the daily index |
| Alpaca paper (`alpaca_broker.py`) | Equity orders and account. Options trading is documented by Alpaca and is **not** wired through `OrderManager` | Not research. Basic market data is IEX for equities and an indicative feed for options |

`WORKER_UNIVERSE_CAP` empty still means the full core book. A paid grouped-daily call does not justify shrinking that book. It makes a wide sweep cheaper than a Yahoo loop.

---

## 7. How a bi-daily scout uses this without trading

One slow job, `SCOUT_INTERVAL_DAYS=2`, after Phase 1's paper loop exists:

1. **After** Massive Stocks Starter is purchased (later, inside the HK$400 cap; not this PR): grouped daily for the last session → liquid names not already in `STOCK_UNIVERSE` (positive price, non-zero volume; no new dollar floor in this document). Until that key exists, this step is skipped, not faked.
2. **After** that same Starter key: Massive news since the previous run → symbols on `tickers[]` with `article_url`.
3. **Now, at $0:** Alpha Vantage `EARNINGS_CALENDAR` and the Finnhub free calendar → symbols with a report date. Then SEC / XOOMAR `reported` (8-K Item 2.02, accession) to confirm the result was filed. Do not call Benzinga.
4. Optional EDGAR daily index → CIK mapped to a ticker only when `company_tickers.json` says so.
5. Write `scout_candidate.v0` rows. Drop empty sources, unknown source types, non-listable symbols.
6. Union onto `STOCK_UNIVERSE` and holdings. Do not delete the core book.

None of those calls import `OrderManager`, `place_desk_order`, or `upsert_active_intent`. A name reaches a paper order only if a playbook later marks it `VALID` and risk approves. Headlines still do not open positions (ADR-003 D1).

Phase 1 does not need these keys. The method already says `SCOUT_ENABLED` stays off until that PR.

---

## 8. Non-goals

- Tip-sheet or analyst-rating auto-buy. Benzinga ratings exist (`/benzinga/v1/ratings`) and stay off the order path even if someone later buys that dataset.
- Paywalled PDF scrape.
- A FactSet, Bloomberg, or Refinitiv contract written down as if it were signed.
- A second realtime tape (Massive stocks Advanced **and** Alpaca Plus, or Massive Options quotes **and** Alpaca Plus **and** an IBKR OPRA line).
- Buying an options feed during Phase 1 / 1.5, or sending an options quote to `OrderManager`.
- Shared or resold API keys.
- Treating Twelve Data's schema.org prices as the invoice.

---

## 9. Broker, terminal, and options — comparison (checked 2026-10-26)

Three different products get conflated. This desk needs them separated.

| Role | What it is | What it is not |
|------|------------|----------------|
| Research tape | Bars, news, calendars the scout and playbook read | A license to show that tape to other customers |
| Broker | The account that can paper- or live-fill an order | A research terminal. Alpaca Basic IEX is not the scout's OHLCV |
| Terminal | Bloomberg-class newsroom, analytics, and chat | A drop-in replacement for `OrderManager` |

Paper is not live. A non-professional personal license is not a redistribution license. Options are a later capability (owner: ns-4). They are not Phase 1 of the smart-trader method. The buy below must still leave an options door so the desk is not rewritten twice.

### 9.1 What each stack actually is

| Stack | Research or broker | Options | Public price checked 2026-10-26 | Repo today | Decision |
|-------|--------------------|---------|----------------------------------|------------|----------|
| **Massive Stocks Starter + Benzinga Earnings** | Research. Same vendor as Polygon. Stocks and Options are **separate subscriptions** ([subscriptions](https://massive.com/knowledge-base/article/what-are-the-different-massive-subscriptions-i-can-use)) | Stocks plan does **not** include OPRA. Options page lists bars, trades, quotes, chains, Greeks, IV, open interest, from OPRA across 20 exchanges; index options need the Options sub (`I:SPX` for snapshot Greeks) ([massive.com/options](https://massive.com/options)). Dollar tiers **did not render** on that page or on [pricing?product=options](https://massive.com/pricing?product=options). Knowledge base names Options Basic / Starter / Developer / Advanced / Business and says quotes are Advanced and Business only; bars on Basic and Starter are 2 years, Developer 4 years, Advanced all history back to 2014-06-02 ([history](https://massive.com/knowledge-base/article/how-much-historical-stock-data-does-massive-have), [non-pro](https://massive.com/knowledge-base/article/what-are-pro-and-non-pro-classifications-for-massives-options-date)). Do not copy the stocks $29 / $79 / $199 ladder onto options | Stocks Starter **$29/month**. Benzinga **$99/month per dataset** on the pricing page. Options list price: **not recorded** | `polygon_equity.py` for bars. `polygon_options.py` uses the same key family and is a chain adapter, not an order path. A stocks-only key is not entitled to options | **Buy Stocks Starter later**, inside HK$400, not in this PR. Do not buy Benzinga now. Buy Options only when options work starts, and then only one options tape |
| **Alpaca** | Broker for this desk's paper equities. Market data is a second product | Trading API documents single-leg and multi-leg options, including paper; paper accounts are described as Level 3 without a live options application ([learn article](https://alpaca.markets/learn/how-to-trade-options-with-alpaca)). Data: Basic is free IEX equities + **indicative** options; Algo Trader Plus **$99/month** is all-exchange equities + **OPRA**, 10,000 calls/minute ([market data](https://docs.alpaca.markets/us/docs/about-market-data-api)). Basic is the default on both paper and live | Plus **$99/month**. Basic **$0** | `alpaca_broker.py` / `OrderManager` are the equity path. No options order type in that path | **Keep Alpaca paper.** When options orders start, extend this broker first. Do not also buy Plus during the stock-only phases |
| **IBKR** | Broker + exchange market-data subscriptions. TWS API and Web API. Not a research terminal | US options exist as their own lines. Delay table: OPRA is **15 minutes** until "OPRA Top of Book (L1)". Package table: **OPRA (US Option Exchanges) (L1)** non-pro **$1.50** / pro **$32.75**. A waiver example lists that same **$1.50** fee with a **$20** commission threshold — the $20 is not a second price. **US Equity and Options Add-On Streaming Bundle** is non-pro **$4.50** / pro **$125**. The sample table pairs that add-on with the snapshot bundle for US equity NBBO. Footnote numbers on the fetched page did not line up cleanly enough to assert that the $4.50 already includes the OPRA line; confirm at checkout. Snapshot bundle: non-pro **$10** base waived for activity + **$0.01** per snapshot. Network A/B/C L1 are **$1.50** non-pro (pro $45 / $25 / $25). Fees are not pro-rated. API market data for most securities requires L1 ([intro](https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction.md)). Paper: Web API and TWS API work on paper with minimal differences; the simulator does not penny-fill US options and limits combos ([glossary](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/)) | [market-data-pricing.php](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php) | **No IBKR client.** Procurement guide already defers IBKR | Credible **later** broker if Alpaca's options path is not enough. A new adapter, not a data add-on on today's worker. Do not migrate the paper book now |
| **Tradier** | Brokerage API for US equities, ETFs, and options. Sandbox and production. Market data is not sold separately | Chains, Greeks, multileg, OCO/OTOCO. Production quotes are real-time (some indexes delayed 15 min). Sandbox is delayed 15 min and paper-fills. L1 only. No history for expired options. Personal use without Partner status. Data cannot be redistributed and is not a standalone product ([getting started](https://docs.tradier.com/docs/getting-started), [build](https://tradier.com/build)) | [pricing](https://tradier.com/pricing): Lite **$0**, Pro **$10**, Pro Plus **$35** per month. Equity and ETF options: Lite $0.35/contract, Pro and Pro Plus $0. Index options still charged. API access is on every plan | `tradier_options.py` is a chain adapter, not `OrderManager` | Other real options broker. Do not switch Alpaca paper, and do not use Tradier as the research tape |
| **tastytrade Open API** | Broker API for account holders. Quotes via DXLink (dxFeed) | REST quotes by type include `equity-option`; streaming is DXLink. Official docs: [market data](https://developer.tastytrade.com/docs/concepts/market-data/), [stream](https://developer.tastytrade.com/docs/guides/stream-market-data/). Terms (PDF reviewed 2026-10-26): personal, non-transferable license; data use is limited to trading and related watchlists; large cross-section collection is not permitted; no third-party redistribution ([terms](https://assets.tastyworks.com/production/documents/USA/open_api_terms_and_conditions.pdf)) | Developer docs do **not** list a separate API monthly fee. Account minimum was **not** checked this run | No client | Real API, wrong shape for the scout tape, and no client. Not a buy in this recommendation |
| **Bloomberg Terminal / B-PIPE / Data License** | Enterprise terminal and enterprise feeds. News, analytics, reference, pricing, fundamentals, estimates, history. B-PIPE is the real-time consolidated feed for the same asset classes as the Terminal ([B-PIPE](https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/)). Data License (DL/DL+) is the bulk/API enterprise product ([Data License](https://professional.bloomberg.com/products/data/data-license/)). BLPAPI is the terminal-connected API, not a self-serve REST key | Covered as part of that enterprise surface, including options. Not a personal OPRA checkout | **No price on those official pages.** Secondary only, not a Bloomberg invoice. Investopedia's terminal article, retrieved 2026-10-26, says the single-terminal annual fee is just under **$32,000** as of 2026, and **$28,320** per terminal with multiple units; its footnote points at a reseller write-up ([Investopedia](https://www.investopedia.com/terms/b/bloomberg_terminal.asp)). A NeuGroup note on a customer letter for subscriptions beginning or renewing on or after 2025-01-01 reported **$31,980** single and **$28,320** multi, and said that increase also applied to data licenses and B-PIPE ([NeuGroup](https://connect.neugroup.com/public/blogs/bloomberg-terminals-how-much-more-youll-pay-next-year)). Treat both as ballpark | No client, no contract | Overkill for a personal non-pro paper desk. Justified only if a later seat needs the terminal network (newsroom, messaging, institutional analytics) and a multi-year contract is acceptable. It still does not replace the broker |

Unusual Whales stays in §5. It is options **flow**, not the chain or the order path, and it is not one of the stacks above.

### 9.2 Phased buy

**This PR.** Purchases nothing. Writes no keys. Changes no runtime.

1. Keep **Alpaca paper** as the stock broker. Do not migrate the book to Tradier, and do not use Tradier as the research tape.
2. Do not buy Bloomberg. Do not open IBKR. Do not buy Massive Options, Alpaca Plus, Benzinga Earnings, or an OPRA line.
3. Earnings names, when a later scout PR runs, come from the free calendars in §3.3.

**Later, still inside ≈ HK$400 (~US$51), and not this PR.** Buy **Massive Stocks Starter (~$29/month)** for daily OHLCV, grouped daily, and news. That is the only paid tape that fits. Do not add Tiingo Power ($30) or Benzinga (~$99) on top of it inside this cap. Phase 1 of the method still passes with no new key. Phase 1.5 is the first job that reads candidates; it can start on the free calendars before Starter exists.

**When options work starts (ns-4, after the stock paper loop).** One options tape and one options order path.

1. **Orders:** extend `OrderManager` on Alpaca's documented options paper API. Do not greenfield a second equity broker in the same change.
2. **Tape:** either a **Massive Options** subscription behind the existing `polygon_options.py` (separate from Stocks; read the price at checkout, because it was not on the page), **or** Alpaca **Algo Trader Plus ($99/month)** if the OPRA feed should sit on the same broker. Not both, and not also IBKR OPRA.
3. **Only if that path is insufficient:** IBKR (new broker adapter; non-pro rows above; paper API exists but is a simulator with the limits in the glossary) or Tradier (new order adapter; sandbox is delayed; data stays inside the account). tastytrade is documented and still not the recommendation.
4. Personal / non-pro remains the license. Showing the feed to other users changes the SKU (Massive Business, IBKR professional rows, Tradier partner, tastytrade redistribution ban).

Candidates and option quotes still do not open positions.

## 10. Related

- [AI_SMART_TRADER_METHOD.md](AI_SMART_TRADER_METHOD.md) — scout rules and the closed allowlist. Options orders are outside Phase 1 and Phase 1.5.
- [PROCUREMENT_GUIDE.md](PROCUREMENT_GUIDE.md) — older buy-order (VPS, Alpaca paper, Polygon daily). This page is the 2026-10-26 price check for scout feeds and the options-capable comparison. It does not replace the VPS / broker section. Where the older guide says "IBKR later" and "do not buy Bloomberg," that still matches §9.
- [PAID_DATA_PIT_PLAN.md](PAID_DATA_PIT_PLAN.md) — worker already prefers Polygon bars when the key is real.
- [ACCOUNT_MANAGEMENT_DESIGN.md](ACCOUNT_MANAGEMENT_DESIGN.md) §8.1 — options UI is research until a separate evidence gate.
- [ADR-006-futu-opend-desk-observe.md](ADR-006-futu-opend-desk-observe.md) — **Accepted**（Gabriel 2026-11-10 Asia/Hong_Kong / HKT；**Accepted ≠ runtime**；不是採購）。Owner 自營的富途 OpenD 觀察路徑（Desk 細時框／報價）。不是本頁的購買 SKU，也不取代上文 Massive Stocks Starter 稍後再買的建議。Alpaca paper 仍是券商。
