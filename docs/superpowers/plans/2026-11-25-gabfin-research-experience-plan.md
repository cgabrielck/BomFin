# GabFin research experience and architecture implementation plan

> Execute inline with `executing-plans` and TDD, one agent as selected by the user. Product choices below were confirmed in conversation; engineering details are identified separately.

**Goal:** Connect stock discovery, comparison, evidence-backed advice, monitoring and approved paper strategies into one understandable experience.

**Architecture:** Retain the existing API/market/research/execution process boundaries. Add explicit research outputs and lifecycle semantics within those boundaries; do not introduce another execution service. Research documents feed the UI; only an authorized approved strategy may produce an executable intent through risk evaluation.

**Tech Stack:** Existing Python/Pydantic contracts, later SQLite jobs/artifacts and React/PWA views; no new dependency selected here.

**Spec:** [canonical design](../specs/2026-11-25-gabfin-system-design.md), especially confirmed U22–U25; [research reference notes](../specs/2026-11-25-gabfin-research-contract-notes.md).

## Architecture review

| Finding | Resolution / owning tasks |
|---|---|
| Candidate discovery exists, but user-visible reasons for priority are underspecified. | Task 8 emits versioned ranking rationale, horizon, evidence and research depth; Task 14 displays them. A ranking score is not a probability of profit. |
| Research reports have facts/inferences but lack an explicit decision-oriented summary. | Task 2 defines supported/contradicting findings, conditions, missing-data impact and a non-executable research disposition. Task 9 produces it. |
| Tasks 6/9 have budgets, but breadth/depth allocation needs product semantics. | Cheap screening precedes bounded deeper research; requested instruments and material position-related changes get scheduling priority. Deduplicate work, reserve budget and retain starvation protection. |
| Task 14 emphasizes capability security but has few user outcome tests. | Add discovery-to-comparison-to-research-to-watch journeys, partial results and update visibility. Trading controls remain separate. |
| Strategy evaluation exists; research utility needs its own evaluation. | Task 9 measures evidence support/completeness, missing-data disclosure, latency/cost; Tasks 8/16 measure horizon-specific selection outcomes against declared baselines. |
| Diagram Report → Exec can be misread as any report being executable. | Separate advisory report routing from authorized strategy intent production, using principal checks, approved versions and deterministic risk. |
| Documentation still claims no checkout or implementation. | Update stale state statements to point to execution evidence; retain uncompleted gates. |

## Product flow and engineering choices

1. Home shows important holding-related changes, then opportunities with why-now, horizon, provenance and depth labels. User-entered symbols are always reachable.
2. Compare candidates using the same requested horizon/as-of context; explicitly flag incomparable inputs rather than giving a false overall winner.
3. Research detail presents supported facts, inference, counterevidence, assumptions, observation/entry scenarios, invalidation and missing-data impact. No-edge/insufficient-evidence is a valid outcome.
4. Save an item to watch; later reports preserve versions and highlight changed evidence/thesis. Watching does not enable a strategy or order.
5. Approved strategies have a separate status/control surface. Rule-based execution is the comparison baseline; AI-assisted decision variants are experiments until promoted under existing governance.

Engineering choice: a compact opportunity card plus expandable report, rather than a chat-only or giant-report-only interface. It supports scanning on iPhone and detailed inspection on desktop. No fixed number of candidates, confidence threshold or research budget is approved by this layout.

## Global constraints

- Preserve U01–U21, especially autonomous paper within approved strategy bounds, intraday plus swing, long/short, and chat without trade writes.
- Evidence links and partial reports are accepted. Semantic support remains distinct from reference integrity and completeness.
- Horizon distinguishes trading/calendar units and events; as_of, generated_at, deadline and review time have different meanings.
- Reuse evidence/artifacts; no model call per claim by default. Unknown costs are not zero; actual cost/latency requires measurement.
- Contracts do not confer capabilities, reserve budgets, resolve calendars or prove investment merit.
- This plan changes no approved numeric risk values or spending caps. No provider purchase, live trading, deployment or push.

## Bounded next unit: S02/02c

**Files:** Create `services/gabfin/contracts/research.py`, `tests/gabfin/test_research_contracts.py`; keep fixtures local to the new test module unless genuinely shared. Existing common/intent/market contracts remain consumers, not a refactoring target.

**Interfaces:** Versioned `EvidenceItem`, `ResearchRequest`, `ResearchReport`; typed `ResearchHorizon`, `Fact`, `Inference`, `Citation`, `MissingData`, `ResearchSummary`, `ResearchUsage`. Final field signatures belong to the narrow 02c implementation brief before tests are written.

- EvidenceItem: UUID identity, source URL or artifact reference, publisher/original institution, publication precision, first-seen/available times, content hash and license metadata. Unknown publication time remains unknown.
- ResearchHorizon: discriminated duration/event/unspecified variants. Duration records count/unit; event identifies the event and nullable expected time/window; unspecified requires a reason. No automatic calendar computation.
- ResearchRequest: UUID request/instrument identities, question, horizon, actor reference, requested scope, snapshot/budget references and data cutoff. Scope is requested metadata, validated against actual principal later.
- Fact/Inference/Citation: stable IDs, evidence references and locators; inference references supporting facts/evidence plus assumptions/counterevidence. Reuse evidence once per document bundle; do not embed full raw articles per finding.
- ResearchReport: request/snapshot references, facts/inferences/citations, missing-data impacts, as_of/generated_at, versions/usage and completeness. ResearchSummary conveys why-now, horizon, disposition, conditions and invalidation; no broker order fields.
- ResearchUsage: reported counters and nullable cost with cost state; missing usage/pricing must stay unknown. Full budget accounting remains Task 6.
- Cross-document existence, request/snapshot ownership, authorization and actual artifact hashes require service validation. In-document dangling references and duplicate IDs are deterministic contract checks.
- CandidateObservation/ranking, persisted monitoring lifecycle and aggregate schema remain explicit later slices of Task 2/8; 02c does not silently implement the full research service.

- [ ] Write the narrow 02c brief: exact fields/enums, causal rules and model-vs-service checks; retain user decisions and these constraints.
- [ ] Snapshot HEAD/tracked hashes and existing lockfile; write failing tests for horizon roundtrip, unknown event/publication times, shared evidence, duplicate/dangling refs, conflicting findings, partial disclosure and unknown cost.
- [ ] Run `.venv/Scripts/python.exe -m pytest tests/gabfin/test_research_contracts.py -q`; expected RED from absent new contracts, not fixture collection errors.
- [ ] Implement only the contracts; run the same tests to GREEN. JSON schemas must serialize Decimal as strings and timestamps as aware UTC.
- [ ] Run all `tests/gabfin`, isolated serialization/schema checks and sanitized full regression; verify preservation and package scope. Existing optional skips must be reported rather than counted as passes.
- [ ] Commit explicit verified source paths only; update audit/checkpoint with actual counts and next remaining Task 2 slice.

## Downstream task amendments and acceptance

| Owner / dependencies | Concrete work and acceptance |
|---|---|
| Task 2 remaining support slices | Define CandidateObservation/ranking reason, research depth and watch/update contracts before their consumers. Reject duplicate IDs and incompatible versions. Generate aggregate schema after remaining contracts are present. |
| Task 6 + Task 8 | Add scheduling priorities for requested symbols/material holding events within the existing cap, job deduplication and depth escalation. Test repeated request reuses compatible work; insufficient budget returns visible deferred/partial status; lower-priority jobs are not silently lost. |
| Task 8 | Record ranking method/version, candidate rationale and universe as-of. Test syndicated stories do not multiply independent support; lack of ranking inputs appears as unknown; user-entered stock works outside the opportunity list. |
| Task 9 | Produce decision-oriented partial reports with no-edge permitted. Test contradictory evidence remains visible; one failed branch does not erase valid findings; unsupported claims cannot receive supported status merely because an ID exists. |
| Task 9 + Task 23 | On a fixed fixture set compare simple research baseline and bounded citation workflow: source support/completeness, tokens/calls, latency, cost and failure disclosure. Report measured deltas; set acceptance thresholds only after a baseline exists. |
| Task 14 + Task 18 | E2E: home → candidate → compare → evidence → watch; repeat on iPhone viewport and real device later. Test depth/staleness labels, empty opportunity list, incomplete report, mixed horizon comparison and a newer report changing the thesis. |
| Task 15 + Task 16 | Compare rules-only versus AI-assisted decisions using identical eligible data, time splits and cost assumptions; record rejected experiments and model/time contamination limits. Promotion still requires approved versions; no automatic approval from a positive scorecard. |
| Task 19 | Integrate approved strategy intent path separately from advisory UI. Test report/save/watch actions cannot submit orders and forged research metadata cannot bypass principal/risk checks. |

## Review focus

- A long-term positive thesis must not be presented as an immediate intraday entry; preserve horizon and conditions in summary/UI tests.
- An incomplete report can contain valid findings, but a failed job cannot be disguised as an empty successful report.
- Conflicting evidence and unavailable comparison inputs stay visible; no arithmetic average of incompatible horizons masquerades as certainty.
- A report refresh uses new versions without rewriting what the system knew at an earlier cutoff.
- Priority research cannot block position protection; scheduling tests and existing execution isolation remain separate gates.

## Status and completion boundary

Architecture/requirements review and this plan are complete; implementation checkboxes are intentionally open. The user accepted the four product choices; exact engineering field choices remain part of the narrow implementation brief. No new application code, runtime benchmark or trading activation occurred in this planning update.
The existing 3–5-unit estimate for all of S02 is provisional and now too narrow to rely on: 02a/02b are complete while research/order/policy/support, migrations, schema and authorization still remain. Re-estimate after contract inventory; do not promise a new total from this document alone.
