# Known issues

- Static code findings and evidence are owned by the canonical
  [design](../superpowers/specs/2026-11-25-gabfin-system-design.md), section 3.
  They include polling, execution coupling, backtest timing/cost problems
  and a conditional proxy-auth risk. Do not duplicate findings here.
- Local baseline now ran; confirmed typecheck failures and journal test pollution
  are B01/B02 in [baseline](../audit/baseline-2026-11-25.md), which owns their
  evidence and next fixes. They were recorded, not fixed in 01b.
- Optional Postgres coverage and the pandas warning are B03/B04 there; skipped
  tests do not establish Postgres correctness. Earlier design findings still
  need their own reproduction/regression evidence.
- External feed, account, pricing and runtime-risk approval gaps are tracked as
  gates in the design and tasks in the plan, not confirmed application defects.
- A legacy JSONIntentStore concurrency test intermittently raised Windows
  PermissionError during 03g full regression; targeted and final full reruns
  passed, root cause unresolved. Preserve/reproduce in an isolated test directory;
  [03g report](../audit/s03-03g-stream-2026-11-26.md) owns failure and rerun evidence.
- Legacy shadow integration uses the current date for a fake bar; a holiday
    removes it and fails the fill assertion, then leaks SQLite cleanup. Reproduced
    in 04c and its unchanged base; [ticket](../tickets/test-determinism/issues/01-shadow-holiday-clock.md)
    owns evidence and repair criteria. 04c full regression is not fully green.
- 04e trace defect (found and fixed 2026-11-27): the browser quote trace counted
  one market event twice, because the HTTP and WebSocket snapshots describe the
  same quote `event_id` but produced separate trace objects, and the trace did
  not check the subscribed channel. Fixed by channel/instrument filtering and
  page-level dedupe; evidence and acceptance criteria are in the
  [04e trace defect note](../audit/artifacts/s04-04e/trace-defect-2026-11-27.md).
- The TLS e2e fixture serves the production build in `apps/desk-web/dist`.
  Frontend changes require `npm.cmd run build` before Playwright runs, or the
  test silently exercises the previous bundle. `npm run test:e2e` now builds
  first (fixed 2026-11-27).
- 04e independent review (2026-11-27) found three blocking defects, all fixed:
  a trace claim was taken before dispatch so a cancelled frame lost the event
  permanently; the event id alone was not a safe dedupe key because a provider
  may derive it deterministically and reuse it in a later epoch; and the
  recorded measurements did not match the artifacts and named the wrong
  environment. Evidence and the corrected figures are in the
  [04e acceptance report](../audit/s04-core-acceptance.md).
- `tests/gabfin/test_market_api.py::test_quiet_websocket_expires_revokes_or_refuses_writes`
  failed once during a WU-1 full regression with close code 1011 instead of
  1008, then passed in isolation and on the next full run. It is a timing
  flake in the existing websocket test, not a WU-1 defect; the Alpaca
  adapter touches no websocket path. Watch it if the full run goes red
  again.
- The Alpaca token bucket initially recomputed its wait inside a loop. After a
  sleep the refilled token count landed a rounding error short of the target,
  so the loop asked for more and never converged: one test ran for over eight
  minutes and died with MemoryError. Fixed by granting the tokens when the
  shortfall is below the rounding tolerance, and by counting the waits so a
  throttled read can be reported instead of looking complete.
- The weighted moving average gave the newest value the full weight while the
  window was still filling, so the first full window disagreed with a direct
  computation. The window shifts every survivor down one position when the
  oldest value leaves, which removes the window's plain total from the
  weighted sum.
- The FRED client puts its API key in the query string, as FRED requires. A
  transport that raised an exception quoting the request URL would have put
  the key into a log. The client now rebuilds such a message from the series
  id and the error type, and every error path redacts the key.
- The analysis route's timeframe parser stripped the digits off the end of
  the text and kept the unit in `unit`, so `1day` produced the unit `day`
  and the count `1` was never read: every valid timeframe was rejected with
  400. The digits are the leading run, not the trailing one.
- The macro route parsed `as_of` inside the plane's `try` block, so a
  malformed date surfaced as a 503 "plane unavailable" instead of a 400
  "invalid macro request". Parameter validation now happens before the plane
  is called, so an invalid request never looks like an outage.
- The analysis routes called `authorize` and `require_scope` without catching
  the `PermissionError` they raise, so a principal without `read_market`
  got a 500 instead of a 403. The market routes already caught it; the
  analysis routes now do too.
- Four test failures predate WU-9 and are not caused by it (confirmed by
  `git stash` and re-running against the untouched base on 2026-11-27):
  `tests/api/test_desk_zone.py::test_zone_sanitize_fail_closed_and_color_only_edits`
  (Chinese literal decoded as `鍓嶉珮` under the Windows GBK console),
  two cases in `tests/api/test_desk_zone_evidence.py`, and
  `tests/trading/engine/test_worker_integration.py::test_shadow_mode_buy_signal_to_fill`.
  The last one is the holiday-clock ticket below.
- The three analysis endpoints had no production path. `create_market_app`
  took `analysis=None` as a default and nothing ever passed it, so the
  routes were never mounted; and `IndicatorPlane` only accepted an abstract
  `BarSource` with no implementation anywhere. A browser would have seen
  404 on every analysis request. Fixed in `cd59fca1`: the tape-backed bar
  source, the runtime that wires it up, and a fixture that mounts
  deterministic planes. The indicator plane now refuses to compute when the
  stored venue is not one the contract accepts, because an indicator
  without a venue is not comparable with anything.
- The tape's `read_partitions` reports how many rows a series holds but not
  what they are, so a caller that computes on history had to re-implement
  the retention and ordering rules. `read_rows` now returns the rows.
- The e2e fixture wrote `backend/data/trade_journal.json` during the full
  Python suite, and it was not ignored, so it would have been committed as
  an execution artifact. It is ignored now.
- `validate_request` requires the request `Origin` to equal the allowed
  origin exactly, so an API call made outside a browser navigation (`page.request`
  in Playwright, `curl`) is refused with 401 unless it states the origin.
  This is the existing session policy, not a defect, but it surprised the
  e2e work and will surprise anything calling the API directly.

