# S03/03b isolated quote SDK runner

Single-agent inline TDD follow-up to 03a. [Task 4](2026-11-25-gabfin-upgrade-plan.md); real endpoint details/sign-in remain user-supplied and pending.

- [x] Create separate optional `.tools/futu-sdk` Python 3.12 environment; pin futu-api 10.12.7208 as verified from pip index (web search cache still showed 10.11). Save resolved package versions, keep main app environment unchanged.
- [x] Add runner.py and worker.py under providers/futu, tests/test_feed_runner.py and config/futu-sdk-requirements.txt. No modifications to existing probe/contracts/schema.
- [x] Tests first: real child timeout/kill/wait, crash/malformed/oversized result, raw stdout/stderr discard, strict parent allowlist and endpoint validation before spawn.
- [x] Parent launches absolute SDK Python with -I and worker path, sends endpoint via stdin, uses temporary cwd/output JSON; DEVNULL stdout/stderr, restricted child environment, explicit deadline, no shell. Only sanitized validated JSON returns; result limited to 16KiB. Internal test worker injection is not exposed by CLI.
- [x] Worker imports only OpenQuoteContext after SDK logging redirected/disabled, calls 03a metadata inspector, closes and writes safe result. Localhost plaintext allowed; non-loopback requires explicit protocol encryption plus local RSA path, never raw keys/credentials. SDK settings and actual network encryption still need endpoint smoke.
- [x] CLI accepts python/host/port/timeout and optional encryption/RSA file path; never endpoint/keys/errors in output. No auto-discovery or unapproved network call: real smoke only after endpoint confirmed. No trade context, subscriptions or account queries.
- [x] Verify SDK import/version in isolated child without connection; final app tests, package/preservation and audit/checkpoint. Mark real metadata smoke pending if server details unavailable; do not claim all of 03b live verification complete.

Official references: [quote object](https://openapi.futunn.com/futu-api-doc/en/quote/base.html) (SDK threads can block exit), [basic functions/encryption](https://openapi.futunn.com/futu-api-doc/en/ftapi/init.html), [release compatibility](https://www.futunn.com/en/download/OpenAPI). Process timeout bounds SDK startup, calls and close; no assertion that close alone is a reliable timeout mechanism.
