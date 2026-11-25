# S02 completion execution plan

User requested the whole Section, superseding one-unit stopping points. Single-agent inline TDD; existing contracts preserved.

- [x] Remaining support contracts: model gateway, candidate observation, strategy/risk context, broker snapshot/reconciliation, experiments/proposals and health. Use typed references/snapshots, exact Decimal/UTC; no provider calls or runtime spending/trading settings.
- [x] SQLite foundation: explicit open_database/migrate, WAL/foreign keys/busy timeout, six Task 2 tables, atomic versioned migration, unknown-version rejection and rollback tests. No live legacy DB migration.
- [x] Task 3: trusted server-owned principals, role ceilings and ownership, short-lived single-use pairing, expiring sessions, exact HTTPS origins/CSRF, no IP/query-token privilege. Test real local API boundary with fake isolated DB and explicit configured origin.
- [x] Generate deterministic JSON Schema artifact from all public contracts/enums/unions; test regeneration equality and schema validity. No frontend implementation in S02.
- [x] Run targeted RED/GREEN per group, final full sanitized regression, packaging/preservation checks, self-review, local commits and updated evidence/checkpoint.

Final completion requires all groups above; partial progress must not be reported as S02 complete. Session TTLs/rate limits are explicit configuration in tests, not financial policy defaults. No trading, provider purchase, deployment or push.
