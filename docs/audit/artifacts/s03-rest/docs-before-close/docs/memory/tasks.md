# Pending tasks

## T018 — S03 / 03h: freshness / heartbeat / bar behavior

- 03g isolated callback/typed bounded cache completed; [03g report](../audit/s03-03g-stream-2026-11-26.md)
  owns tests, review, cleanup and implementation limits.
- Next: define and test freshness/heartbeat and bar boundaries from Task 5:
  capture-time ages vs current eligibility, no-new-trade vs disconnection,
  duplicate/late events and session rules. Quote callbacks cannot supply trade volume.
- Distinguish old-price reads from current realtime/PRE/POST evidence; closed-market
  data alone cannot establish those rights. [Feed evidence](../audit/feed-entitlements.md).
- Full catalog import, live capability manifest/provider apply, persistent SDK
  lifecycle and authenticated API stream/replay
  integration remain future work. No option trading in V1 or account/trade context.
- Implementation/review policy: [workflow](../agents/workflow.md).
- Keep the legacy intermittent Windows JSONIntentStore failure visible;
  evidence and unresolved root cause are owned by the 03g report.
- Preserve source HEAD, evidence and original lockfile. No purchase,
  trading, push/deploy. Do not restart existing OpenD casually.
