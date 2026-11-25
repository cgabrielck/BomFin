# Execution checkpoint

- Section / unit: S03 / 03f — symbol identity/subscription planning completed.
- Checkout: `C:/Users/001/Desktop/GabFin-ai-trade/.worktrees/gabfin-s01`.
- Branch: `codex/s01-source-baseline`.
- Unit base: `87e295311fd7ef9dbb77c930084b15dc1b4dff23`.
- Current HEAD: `a8d23d575baab94420595ca5cddf12255fb40ebc`, not pushed.
- Working tree: tracked clean; original untracked web/package-lock.json retained.
- Added finite InstrumentCatalog and advisory Futu US subscription schedule;
  scoped support, independent quotas, priority/refcount and conservative freeze.
- Actual source times, rights and counters: [feed register](../audit/feed-entitlements.md).
  Historical PRE/RTH samples only; POST/live rights/latency remain unverified.
- Tests, independent Standards/Spec review, wheel/clean install and preservation:
  [03f report](../audit/s03-03f-planner-2026-11-25.md). All required unit checks ran;
  existing optional skips/warning remain explicit there. Test journal archived.
- Next exact action: S03/03g one-equity FeedAdapter/callback → bounded cache;
  use typed MarketEvent, preserve source time and initial/stale distinctions,
  test queue bounds, cancellation and context cleanup before a bounded real smoke.
- Implementation/review routing: [workflow](../agents/workflow.md).
- S03 remains incomplete: realtime/PRE/POST evidence, live manifest/apply,
  pushes/cache/freshness, bar building and replay. No account access or trading.
