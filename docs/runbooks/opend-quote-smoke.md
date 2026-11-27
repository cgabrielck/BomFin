# OpenD quote-only metadata smoke

Status: localhost metadata, one-equity and bounded options reads verified;
full instrument/session coverage and remote encryption remain pending.

## Local preparation

- SDK environment: workspace `.tools/futu-sdk`, Python 3.12.16, futu-api 10.12.7208; exact resolved dependencies in checkout `config/futu-sdk-requirements.txt`. Main app venv intentionally has no futu SDK.
- Recreate from workspace: `.tools/uv-bootstrap/bin/uv.exe venv --python .tools/python/cpython-3.12.16-windows-x86_64-none/python.exe .tools/futu-sdk`, then `uv pip install --python .tools/futu-sdk/Scripts/python.exe -r config/futu-sdk-requirements.txt` using the same uv executable.
- OpenD version must be compatible with the pinned SDK. [Official releases](https://www.futunn.com/en/download/OpenAPI) state minimum server requirements; do not upgrade or change an installed server silently.
- User starts/signs into OpenD locally. Supply only host IP, TCP API port, version and signed-in status. Passwords, tokens and private-key contents stay local. Python TCP API port is distinct from any optional WebSocket port.
- Do not expose the OpenD listener publicly. Non-loopback runner connections require explicit SDK protocol encryption and an existing local RSA file configured consistently with OpenD. Encryption compatibility still needs actual handshake verification.

## Run only after endpoint is confirmed

From workspace root (example localhost endpoint, not a live verification result):

```powershell
.venv/Scripts/python.exe -m gabfin.providers.futu.runner --python .tools/futu-sdk/Scripts/python.exe --host 127.0.0.1 --port 11111 --timeout 10
```

For encryption add `--encrypted --rsa-file <local-file-path>`; never paste the file contents. No secrets are accepted by the CLI. IP/paths are passed via private child stdin and not returned in diagnostic JSON.

## Result interpretation

- `ok` + `metadata_available`: quote login and strict subscription counters observed; it does not prove instrument rights, realtime status, historical data or PRE/POST coverage.
- `timeout`: child startup/call/close did not exit before deadline; process is killed and waited for. This does not prove server refusal or lack of rights.
- `sdk_unavailable`: SDK could not import in the configured Python environment.
- `worker_failed` / `invalid_result`: no trustworthy allowlisted result; raw child stdout/stderr is discarded, not saved for debug.
- `invalid_config`: invalid IP/port/deadline, missing Python/key path or plaintext non-loopback connection; no child is started.
- Exit 0 means metadata_available or a complete explicit smoke with verified cleanup;
  exit 2 means a diagnostic gate remains. Instrument rights are operation-specific.

## Bounded options operation

From workspace root, use the same Python/host/port arguments and add
`--operation options_smoke`. It defaults to 110 seconds and accepts explicit
deadlines only from 90 to 120 seconds. Never shorten this to the metadata deadline.
The fixed AAPL/date/strike scope and result limits are in the
[03d report](../audit/s03-03d-options-2026-11-25.md).

It holds attempted subscriptions at least 61 seconds, then verifies both own
normal and own option counters. `window_partial` preserves one available side;
`budget_exhausted` means no subscription started. Any cleanup error/timeout needs
metadata/quota recheck; it does not prove server quota was released.

## Bounded history operation

Add `--operation history_smoke` to the same Python/host/port arguments, omitting
the metadata `--timeout 10`. Default is 110 seconds; explicit range 70–120.
It samples the previous New York calendar date, US.AAPL, unadjusted K_1M,
one page of at most two records per RTH/ETH. It never follows the returned token.
Historical quota can occupy one symbol slot for seven days; close is not a refund.
The pinned private quote transport/decoder and upgrade gate are documented in
[03e report](../audit/s03-03e-history-2026-11-25.md).

`sampled`/`not_sampled` refer to returned historical clock labels. Every live
session right remains unverified. Skipped/empty/failed/invalid_data preserve
explicit gaps; timeout still requires post-check and is never successful cleanup.

## Shared boundaries

- The worker creates only OpenQuoteContext and closes it. Default metadata mode
  uses get_global_state/query_subscription; explicit equity/options modes make
  their documented bounded subscriptions. It never unlocks, queries accounts or sends orders.
- SDK logging is disabled before import; APPDATA and temporary directories are isolated per run, and discarded on completion. This is process/IO isolation, not an OS sandbox or a guarantee against malicious third-party code.
- Parent revalidates the result allowlist, types, counters, timestamp and error codes; oversized/unexpected payloads are rejected. Endpoint and raw exception text are never echoed by runner results.
- [03b evidence](../audit/s03-03b-runner-2026-11-25.md), [entitlements register](../audit/feed-entitlements.md).
