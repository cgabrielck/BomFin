# Pending tasks

## T017 — S03 / 03g: one-equity callback and bounded cache

- 03f catalog/advisory subscription schedule completed; [03f report](../audit/s03-03f-planner-2026-11-25.md)
  owns tests, review, cleanup and implementation limits.
- Next: implement a one-equity quote FeedAdapter/callback → bounded cache slice
  with typed MarketEvent, source-time preservation, queue/coalescing limits,
  cancellation and close. Offline tests before any bounded provider smoke.
- Distinguish old-price reads from current realtime/PRE/POST evidence; closed-market
  data alone cannot establish those rights. [Feed evidence](../audit/feed-entitlements.md).
- Full catalog import, live capability manifest/provider apply and stream/replay
  integration remain future work. No option trading in V1 or account/trade context.
- Implementation/review policy: [workflow](../agents/workflow.md).
- Preserve source HEAD, evidence and original lockfile. No purchase,
  trading, push/deploy. Do not restart existing OpenD casually.
