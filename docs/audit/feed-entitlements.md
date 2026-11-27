# Feed capability and entitlement evidence

## OpenD — 2026-11-25 preflight

- User confirms OpenD is installed on this computer but not started. Installation location/version has not been verified by this unit.
- Project venv has no `futu` SDK; process inventory found no matching running OpenD/Futu/moomoo process; no listener observed on default port 11111.
- Explicit bounded loopback TCP probe via `python -m gabfin.providers.futu.preflight --check-tcp` returned exit 2 with sdk_unavailable/opend_unreachable. [Safe JSON](artifacts/s03-03a/local-readiness.json).
- Equity quote, bar, option chain, option quote and PRE/POST access remain unverified. No real subscription quota, latency, realtime/delayed classification or instrument entitlement has been obtained.
- This is a readiness gap, not proof of missing paid rights or failed installation. No purchase or alternative provider choice is justified by these observations alone.

## Official references inspected

- [Global state](https://openapi.futunn.com/futu-api-doc/en/quote/get-global-state.html): qot_logined describes market-server login; it is not a per-instrument rights test. Quote contexts should be closed.
- [Subscription status](https://openapi.futunn.com/futu-api-doc/en/quote/query-subscription.html): total_used and remain are separate quota observations; the raw response also contains fields GabFin must not persist in diagnostics.
- [Authorities and quotas](https://openapi.futunn.com/futu-api-doc/en/intro/authority.html): API and App market rights are not necessarily identical. Subscription and historical-data quotas are different concepts.

## Next evidence gate

- In a separate bounded unit, prepare a pinned optional SDK environment/child process; verify actual installed OpenD version/endpoint. User handles account sign-in locally; no credentials in chat/logs.
- Run quote-only login/quota metadata probe before one-stock quote/bar and a bounded option chain/quote smoke. Verify PRE/POST separately; calendar/market status does not establish session entitlement.
- No trade context/unlock, account query, order submission or broad subscription. Do not store raw provider response or child stdout unfiltered; SDK libraries may print their own metadata.
- [03a implementation evidence](s03-03a-preflight-2026-11-25.md). Full Task 4/S03 remains incomplete.

## 03b preparation update

- Isolated SDK import and bounded diagnostic runner are verified offline; see [03b report](s03-03b-runner-2026-11-25.md). Main app venv still has no SDK.
- User is preparing OpenD/SDK details and will supply endpoint/version; no endpoint received or contacted in 03b. Real metadata/entitlement gates above remain open.

## User-provided UI evidence after 03b preparation

- Screenshot shows official OpenD 10.12.7208, a connected/logged-in UI, default loopback listen address and TCP port 11111. No account/phone identifiers copied. UI evidence is not a successful runner or instrument entitlement test.
- Installed SDK version matches the displayed OpenD version; actual metadata smoke still not run. Retain localhost while app and OpenD run on the same PC; a geographic/VPN egress IP is not the local listening address.

## 03b live metadata smoke — 2026-11-25

- User explicitly requested the quote-login/quota read. At 15:39:16 HKT, bounded localhost runner returned metadata_available with quote login true, total_used 0, remaining 300, no diagnostic errors. [Allowlisted API evidence](artifacts/s03-03b/live-metadata-2026-11-25.json).
- Runner exit 0 in about 3 seconds. Post-check found zero quote worker processes; existing OpenD remained responsive. No trade unlock, account query, symbol subscription or market-price request.
- These are query_subscription counters for the observed connection/server, not proof of a separate options quota, historical quota, realtime rights or PRE/POST capability. No public/remote-encrypted connection tested.
- Earlier stopped/unavailable observations above are historical. UI opening issue reported by user was not diagnosed; no OpenD restart/termination or window manipulation performed.

## 03c live equity smoke — 2026-11-25

- Fixed US.AAPL basicinfo returned STOCK, QUOTE/K_DAY subscription and one quote/two D1 bars succeeded in a bounded SDK child. Requested RTH, extended_time=False, unadjusted AuType.NONE. [Sanitized observations](artifacts/s03-03c/live-equity.json).
- Quote source date/time: 2026-11-24 16:00:00 America/New_York; capture began at 15:46:48 HKT on Nov 25. This is a prior regular-session close observation, not proof of live feed latency, session freshness or intraday push operation.
- Explicit unsubscribe after the minimum hold succeeded; own_used=0. Post-close metadata at 15:48:54 HKT showed total_used=0/remain=300, and process inventory found zero SDK workers. [Cleanup evidence](artifacts/s03-03c/post-cleanup-metadata.json).
- No entitlement proof for options/history/PRE/POST yet; no trade unlock/account query/order. [03c report](s03-03c-equity-2026-11-25.md).

## 03d live options smoke — 2026-11-25

- At 17:00:21 HKT, the bounded runner selected expiry 2026-11-25, strike 355,
  CALL/PUT US.AAPL261125C355000 / US.AAPL261125P355000, each verified as 100 shares.
  Last observations were 1.70 / 2.85; source times were Nov 24, 16:12:53.930 /
  16:13:06.360 America/New_York. These are prior-day observations, not live latency proof.
- Both QUOTE reads and explicit unsubscribe succeeded. Own normal/option usage
  were both 0; observed global option used/remain were 0/60. This independently
  verifies the options counters rather than inferring them from normal quota.
- Post-close normal quota was 0/300; zero SDK workers remained. Exact timestamps
  and evidence: [03d report](s03-03d-options-2026-11-25.md). No trading/account access.
- Options can be read for these two contracts at this time. Realtime update,
  history and PRE/POST capability remain unverified; no general-market rights claim.

## 03e historical/session smoke — 2026-11-25

- At 21:23:03 HKT, single-page raw quote adapter read unadjusted US.AAPL K_1M
  for Nov 24: RTH labels 09:31/09:32 and ETH labels 04:01/04:02 New York time.
  Both pages had more data; no token was followed. PRE/RTH historical clock
  windows sampled; POST not sampled. Market metadata was PRE_MARKET_BEGIN.
- Historical quota before/after was used=5, remaining=295. No increase observed;
  this is separate from normal subscription quota 0/300 after context close.
- No SDK workers remained. [03e report and evidence](s03-03e-history-2026-11-25.md).
  Historical samples and market state do not prove live PRE/POST rights or latency.

## 03g callback smoke — 2026-11-26 HKT

- A bounded one-equity callback → typed latest-cache path ran from a clean wheel;
  current-day changing source observations were captured, with explicit unsubscribe,
  own_used=0 and context/process cleanup. It does not certify realtime rights or
  low latency; source session and entitlement remain unknown.
- Final source age, quota (now remaining 100 rather than earlier 300), timestamps,
  limits and sanitized evidence are owned by [03g report](s03-03g-stream-2026-11-26.md).
  The quota difference's cause is unverified. PRE/POST live evidence is still open.

## S03 final chain — 2026-11-26 HKT

- 09:01:48–09:03:00 HKT：clean wheel host 經獨立 SDK、authenticated internal stream，
  向獨立 consumer process 交付 1 個 quote／4 個 updates；health connected、quote state
  resynced、consumer 無錯誤。[實際證據](artifacts/s03-rest/live-chain.json)。
- Source 為 Nov 25 21:00 UTC（16:00 New York）的收市價；capture 已到 Nov 26 01:01 UTC。
  不是當時即時或 POST 價格。Receipt→consumer 約 43.9 ms 只代表這一筆本機轉送，
  不能冒充來源市場 latency。沒有 UI render 量測。
- Freshness 實際拒絕：舊價、缺 BBO、未知 session／entitlement／calendar 及未批准政策。
  Connection／quote resync 不會改成新價格，也不會產生交易授權。
- Metadata 前後均 login=true、total_used=0、remaining=100；capabilities 保留
  latency=unknown、sessions=[]、live_manifest_unverified。未推算其他 quota pools。
  明確 unsubscribe、context close、worker 退出成功；OpenD 保持原 listener。

## S04/04c API chain — 2026-11-26 HKT

- 14:05:38–14:06:51 HKT：同一 OpenD、單股只讀 producer 經 S03 TCP bridge
  到已授權 API snapshot／WebSocket TestClient 成功，登出後 API 拒絕再讀。
  [原始結果](artifacts/s04-04c/live-api-chain.json)；不是實際 HTTPS browser latency 量測。
- Last `355.58`，來源 Nov25 21:00 UTC；接收 Nov26 06:05:48 UTC，相差約 9 小時。
  品質 unknown／incomplete，無 BBO、權益未知；freshness 實際拒絕，不建立 realtime 證據。
- Login=true，metadata 前後 total_used=0／remaining=100；明確 unsubscribe／context close，
  worker stopped、無 cleanup errors。原 OpenD loopback listener／PID 保持不變，未啟動交易。

## G2 未放行項目與路線

| 缺口 | 已有證據及仍欠甚麼 | 解除路線 |
|---|---|---|
| Realtime／BBO | Quote-only last；沒有逐 instrument/channel 權益及 bid/ask 實測 | 核對 API manifest，延伸已獲授權 channel，再作有來源時鐘的限時 smoke |
| PRE／POST | 03e 只有部分歷史 PRE/RTH；本次舊 regular close 不能補證明 | 在適用 session 核對時戳與權益；歷史 POST 與 live POST 分開驗證 |
| Trade/bar 補缺 | 已有診斷與 canonical engine 測試，尚未接真實完整 backfill | 受信 history adapter 提供 scope／pagination／unique-count receipt，再實測斷線恢復 |
| Freshness 批准 | 5 秒仍只是非生產提案 | 量測 feed latency 後批准版本政策；缺證據維持拒絕新入場 |

成本候選（2026-11-26 查閱，沒有購買／切換）：

| 路線 | 官方可見成本與範圍 | 限制 |
|---|---|---|
| 先核實現有 Futu | 增量費用尚未確定，先核對現有 API 權益 | App 與 API 權益可不同；資格、coverage、PRE/POST 與用途不能由 login 推定 |
| Alpaca Basic | 免費，股票即時僅 IEX，WebSocket 30 symbols；期權 indicative | 不能當完整市場 BBO／全市場即時；帳戶與用途資格另核對 |
| Alpaca Algo Trader Plus | 官方 Trading API 個人方案 US$99/月，股票所有美國交易所、期權 OPRA | 尚未接入或購買；PRE/POST、用途授權及合約條件仍需驗證 |

來源：[Futu authorities](https://openapi.futunn.com/futu-api-doc/en/intro/authority.html)、
[Alpaca Market Data plans](https://docs.alpaca.markets/us/docs/about-market-data-api)。
後續驗收由 [G2 票](../tickets/s03-stream/issues/03-feed-evidence-g2.md) 追蹤。
