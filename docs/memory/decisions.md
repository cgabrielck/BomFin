# Technical decisions

## D001 — Shared repository memory

- Status: accepted by user request.
- Choice: use root `AGENTS.md` as the entry point and five focused Markdown files
  under `docs/memory/` for both Codex CLI and the VS Code Extension.
- Rationale: one portable source of project context, selective reads, small
  updates, and no tool-specific duplicate memory.
- Consequence: memory must be maintained with significant work and verified
  against source. Separate checkouts require normal file synchronization or
  version control to share updates; this is not an automatic sync service.

## D002 — Confirmed product requirements and planning handoff

- Status: requirements confirmed in conversation; grill-me ended 2026-11-25.
- Canonical requirements: [system design](../superpowers/specs/2026-11-25-gabfin-system-design.md), U01–U21.
- Implementation sequencing: [upgrade plan](../superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).
- These files distinguish user decisions from engineering proposals and gates.
  Do not treat proposed stack, risk thresholds or tool adoption as user-approved
  runtime settings. Legacy baseline and the first new contract slice now ran;
  the current implemented boundary is owned by execution and its linked reports.

## D003 — New design authority and local development reaffirmed

- User reaffirmed on 2026-11-25: do not follow ADR-003; the new confirmed design
  and main upgrade plan govern this work. Other legacy ADRs cannot constrain it.
- Use the existing local GabFin checkout. A sandbox/container is not a product
  requirement; keep environment isolation without claiming it is a separate host.
- Legacy UI typecheck failures and optional Postgres skips are recorded findings,
  not automatic prerequisites for the new frontend/SQLite architecture.
- The user approved and execution completed the authority cleanup; its scope,
  commits and verification are owned by the [cleanup report](../audit/legacy-authority-cleanup-2026-11-25.md).

## D004 — Technical dialogue and focused grilling

- The user welcomes engineering/financial depth and focused grilling whenever
  needed, including for blockers. This supersedes the earlier interview-reopening
  restriction; do not repeat settled requirements without a reason.
- Routine authorized work continues autonomously; ask for decisions when their
  answers materially affect requirements, architecture, risk or external actions.

## D005 — Strategy direction and position effect

- User selected `long/short` plus `position_effect=open/reduce/close` for new
  StrategyIntent. Executor conversion to broker buy/sell remains separate.
- The main plan field table is updated; implementation and its limits are owned
  by the [02a report](../audit/s02-02a-contracts-2026-11-25.md). This is not approval
  of any sizing, risk values or trade activation.

## D006 — Market observation boundaries

- Engineering choice within confirmed Task 2: quote events carry full snapshots;
  missing values and source provenance must stay explicit. Session/entitlement
  metadata does not confer trading authority. Exact rules, rationale and costs
  are owned by the [02b report](../audit/s02-02b-market-events-2026-11-25.md).

## D007 — Research citations and incomplete reports

- User accepts per-fact evidence links and explicit inference premises, subject
  to bounded workload; accepts visibly incomplete reports. Horizon reference
  research/selection is delegated to engineering, not a user-fixed preset.
- Sources, engineering horizon choice, validation/cost limits and implementation
  handoff: [02c notes](../superpowers/specs/2026-11-25-gabfin-research-contract-notes.md).

## D008 — Discovery-led research experience

- User accepted all four recommended product choices; canonical U22–U25 owns
  their wording. Architecture review, task mapping and acceptance are in the
  [research experience plan](../superpowers/plans/2026-11-25-gabfin-research-experience-plan.md).
- Existing budget, paper-only scope and strategy approval boundaries remain.
