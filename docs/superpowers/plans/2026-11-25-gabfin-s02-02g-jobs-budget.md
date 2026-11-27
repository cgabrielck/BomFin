# S02/02g job lease and budget reservation contracts

Single-agent, inline TDD slice of [main plan Task 2/6](2026-11-25-gabfin-upgrade-plan.md). Reuse exact Decimal, currency and UTC primitives; create only `services/gabfin/contracts/jobs.py` and `tests/gabfin/test_job_contracts.py`.

## Exact interfaces and engineering rulings

- JobLease: schema_version, job_id/worker_id/lease_token UUIDs, acquired_at/expires_at UTC, attempt strict positive JS-safe integer. expires_at > acquired_at; no current clock check. lease_token repr=False to avoid incidental model repr disclosure, but remains in internal wire serialization. Never expose these documents directly in UI/logs.
- ReservationStatus enum reserved/settled/released/unknown. Reservation: schema_version, reservation_id/budget_id/job_id UUIDs, amount NonNegativeDecimal, currency CurrencyCode, status, actual_amount nullable NonNegativeDecimal, created_at/updated_at UTC. All required, no default cost/budget.
- amount always records original reserved estimate; zero is a known zero estimate, not unknown. Unknown estimate is not a successful Reservation: future service must defer/reject or use separately approved trial authority.
- settled requires explicit actual_amount, including genuine zero. Other states require actual_amount=None. unknown retains reserved estimate for conservative later accounting; it does not mean zero charge or release.
- updated_at >= created_at. Settled actual cost may exceed estimate: preserve observed overrun rather than rejecting real provider spend. Later service handles cap breach/reconciliation; no automatic budget increase.
- Status describes one observation, not a transaction/state-transition validator. No implicit release after timeout/lease expiry; later ledger must resolve unknown costs explicitly.
- Claim ownership/token fencing, secure token generation/rotation, attempt increments, heartbeat, cancellation, monthly caps, currency conversion, idempotency and concurrent reservation accounting remain Task 6 service/DB responsibilities.
- No actual lease/budget/grant, numeric spending cap, model call, DB migration or worker is created by parsing these contracts.

## Steps / expected results

- [x] Snapshot original tracked files, lockfile and journal presence.
- [x] Write tests and run RED from absent module: identity, strict attempts, UTC chronology, status/actual-cost combinations, exact Decimal and unknown vs zero.
- [x] Implement only contracts; all gabfin tests GREEN; self-review expiry/history and overruns without service claims.
- [x] Run sanitized full pytest, schema/isolated import, wheel/pip and preservation checks; archive only new legacy journal.
- [x] Commit explicit two source paths; update audit/checkpoint and remaining Task 2 inventory. Next group: ModelRequest/Result declarations.
