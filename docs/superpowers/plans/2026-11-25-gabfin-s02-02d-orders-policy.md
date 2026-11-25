# S02/02d order and policy contracts implementation brief

Execute inline with TDD, one agent. Spec: [design §9](../specs/2026-11-25-gabfin-system-design.md); [main plan Task 2, 11, 12](2026-11-25-gabfin-upgrade-plan.md).

## Scope and exact interfaces

Create `services/gabfin/contracts/policy.py`, `order.py`, and `tests/gabfin/test_order_policy_contracts.py`. Existing source stays unchanged.

- RiskBounds: per_trade_risk/daily_loss/runtime_drawdown nullable Ratio; gross_exposure_leverage nullable PositiveDecimal; missing_data_policy nullable Literal halt_entries. All required nullable fields, no numeric defaults. Account risk ratios and gross exposure leverage are different units. Additional risk dimensions require later approved service configuration, not invented defaults here.
- PolicyVersion: schema_version, version opaque key, allowed_strategies tuple keys, allowed_sessions tuple pre_market/regular/post_market, allowed_assets tuple equity, risk_bounds, approval_hash nullable lowercase SHA256, approved_at nullable UTC, status draft/approved/retired. Lists unique; non-draft needs complete bounds, nonempty allowlists and approval metadata. Draft cannot claim approval metadata. Declared status is not authenticated approval.
- RiskCheck: code opaque, passed StrictBool. RiskDecision: version, decision_id/intent_id UUID, approved StrictBool, reason_codes nonempty unique keys, quantity/risk_amount nullable (PositiveDecimal/Money), checks nonempty unique-code tuple, policy_version, expires_at. Approval needs quantity, positive risk amount and all checks passing; rejection cannot contain approved sizing. Checks may all pass but other reasons still deny. Parsing never grants authority or checks current wall clock.
- OrderCommand: version, client_order_id/intent_id/instrument/risk_decision_id UUID, side buy/sell, qty PositiveDecimal, type market/limit, limit_price nullable PositiveDecimal, tif day/gtc/ioc/fok, session pre_market/regular/post_market. Limit requires price, market forbids it; extended sessions restrict shape to limit/day. Regular session combinations still need actual broker capability checks. No buy/sell conversion without position context.
- OrderEvent: version, event_id UUID, broker_id nullable key, client_order_id UUID, status proposed/approved/send_pending/acknowledged/partial/filled/canceled/rejected/unknown, cum_fill_qty NonNegativeDecimal, fill_price nullable PositiveDecimal (cumulative average, not last-fill price), fill_evidence unavailable/broker_reported, evidence_id nullable UUID, event_at/received_at/available_at UTC, dedup_key opaque. Missing price remains nullable even with positive cumulative quantity; known price requires positive quantity and broker evidence artifact. Zero quantity has no fill price/evidence. Broker-reported evidence requires positive quantity, broker_id and evidence_id. Partial/filled require positive quantity. Local available>=received; source clock skew is preserved.
- UNKNOWN is not REJECTED; cancellation may retain partial fills. No cross-event monotonicity/dedup store, hash verification, approval authentication, OMS transition logic, provider calls or runtime policy enforcement in this unit.
- HarnessProposal, stop orders/brackets, expanded broker event types and remaining support models stay later slices; no changes to existing risk limits or trading activation.

## Steps and expected results

- [x] Snapshot HEAD/tracked hashes/lockfile and journal presence.
- [x] Write tests for unapproved policy, missing bounds, strict booleans, exact money, malformed sizing, order shape, missing fill proof, UNKNOWN and canceled partial fills. Run RED from absent modules.
- [x] Implement only contract validation; run the new tests and all gabfin contracts GREEN. Self-review negative cases before final regression.
- [x] Run sanitized full pytest; preserve logs/JUnit and archive only new mock journal. Build wheel, verify bytes, schemas, isolated imports, pip check and original hashes.
- [x] Commit explicit three source paths; record actual verification/limits and next bounded unit. Task 2 remains incomplete.

## Review focus / engineering rulings

- Approval metadata cannot authenticate a caller. Costs if misused: forged documents could otherwise bypass governance; service boundaries must verify against trusted registry.
- Extended-session limit/day is a conservative shape constraint, not evidence of broker entitlement. Actual broker/session/short permissions remain runtime checks.
- Cumulative quantity with unavailable price is preserved as incomplete broker observation; it cannot be valued using order limit price. Consumers must reconcile evidence.
- Missing-data policy starts with halt_entries; it does not cancel existing protection or define all future stale-data actions.
- Author self-review only under the user's single-agent choice; no independent review or trade launch in this unit.
