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
