# S02/02f identity declaration contracts

Single-agent TDD slice of [main plan Task 2/3](2026-11-25-gabfin-upgrade-plan.md). Implements declarations only; authorization is a later server responsibility.

## Interfaces and engineering rulings

- Create `services/gabfin/contracts/identity.py` and `tests/gabfin/test_identity_contracts.py`; reuse ContractModel/VersionedContract and UUID.
- Role StrEnum: owner/chat/research/strategy/executor. Strategy is explicit because existing StrategyIntent producer_scope is strategy:emit; it does not make arbitrary research a strategy principal.
- Capability StrEnum: read_account, resolve_symbols, start_research, read_report, draft_trade_plan, read_market, manage_watchlist, propose_strategy, strategy:emit, submit_order, cancel_order, start_worker, pause_worker, resume_worker, write_policy, approve_proposal. These are names, not grants. No wildcard or unknown string accepted.
- Principal: schema_version, actor_id UUID, role Role, scope tuple Capability. All required; scope may be empty, must have no duplicates. No implicit owner privileges or role-derived default scope. Extra credential/session/IP/forwarded fields forbidden.
- ResourceKind StrEnum: account/instrument/research_job/research_report/watchlist/order/strategy/policy/proposal/artifact. Resource: schema_version, kind, id UUID, owner UUID. No inferred/shared ownership; future public resources need an explicit service model rather than owner=None.
- Parsing even a well-shaped chat principal claiming submit_order does not grant that capability. Task 3 must obtain the principal from trusted session/registry and enforce role ceiling plus requested scope and resource ownership; no client Principal accepted as authenticated identity. Avoid introducing an incomplete permission matrix here.
- No rewriting ResearchRequest.capability_scope metadata or StrategyIntent marker, no session issuance or actual authorize function in this unit. Capability enumeration expansion is a versioned contract change.

## Steps / checks

- [x] Snapshot original tracked files, lockfile and journal presence.
- [x] Write RED tests for all enum values/roundtrips, missing scopes/owners, invalid UUIDs, duplicate/wildcard capabilities and extra credential/IP fields.
- [x] Implement declarations; verify GREEN and self-review empty scope/no implicit grants/schema behavior.
- [x] Full sanitized regression; wheel/schema/import/pip/preservation checks; archive only generated journal.
- [x] Commit exactly two paths and update checkpoint; next remaining support group is job/budget declarations.
