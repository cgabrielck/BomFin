# S02/02c research contract decisions and reference notes

Scope: refinement of confirmed main plan Task 2, before research contract implementation.
This supplements the [canonical design](2026-11-25-gabfin-system-design.md), not a new ADR or implemented feature.

## User decisions

- User delegates horizon reference research and engineering selection; no personal preset to reproduce.
- User accepts important facts linked to evidence IDs and inferences linked to premises, assumptions and counterevidence, with system workload kept bounded.
- User accepts incomplete reports with explicit known/unknown/unanswerable parts. Missing data must not be fabricated.
- No new model budget, runtime limit, provider purchase or trading permission follows from these decisions.

## References actually inspected on 2026-11-25

| Primary source | Observation | GabFin application (engineering choice) |
|---|---|---|
| [QuantConnect LEAN Insight.cs](https://github.com/QuantConnect/Lean/blob/master/Common/Algorithm/Framework/Alphas/Insight.cs) and [official guide](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework/alpha/key-concepts) | Insight represents a period and prediction end time; constructors support duration/expiry, and end-time calculation accounts for exchange hours. | Store an explicit analysis horizon; keep market calendar semantics. Do not import its executable-signal meaning into ResearchReport. |
| [Microsoft Qlib data documentation](https://github.com/microsoft/qlib/blob/main/docs/component/data.rst) | Alpha158 explains its T+1 to T+2 return label using market execution timing. | Record the exact target horizon and distinguish information cutoff from the future outcome window. Do not copy China-specific T+1 assumptions to US equities. |
| [CFA Institute Standard V(B)](https://www.cfainstitute.org/standards/professionals/code-ethics-standards/standards-of-practice-v-b) | Guidance separates facts/opinions and calls for significant limitations and reasoning to be disclosed. | Typed facts/inferences and visible scope/missing data; no claim of certification or legal compliance. |
| [Gao et al., EMNLP 2023: ALCE](https://aclanthology.org/2023.emnlp-main.398/) | The primary abstract/paper excerpt distinguishes correctness and citation quality; generated citations do not establish adequate support by themselves. | Separate reference integrity from semantic support validation. ID existence alone is not proof a claim is true or supported. |

- GitHub file reads succeeded via connected GitHub tools. LEAN blob SHA `f989fe31a1cd84e8a55b234dc127ef15d074859a`; Qlib doc blob SHA `eeddaec60d01f510160c6555e38af0c4fbbba772`. These are file blob IDs, not repository commits.
- Two guessed LEAN paths returned 404 before the correct path was found. This was a lookup miss, not a project blocker.
- MacKinlay (1997), *Event Studies in Economics and Finance*, was located in a university-hosted scanned PDF; its main body was not reliably text-extracted here. No exact event-window rule or numeric default is adopted from that paper.
- No repository code/dependencies were copied or installed; no claim that these sources provide one universal optimal horizon.

## Horizon design call

- Considered: short/medium/long labels alone (ambiguous), exact duration alone (poor fit for event questions), duration plus event-based horizons (chosen engineering direction).
- Support a count with an explicit unit, or a named event with an explicit analysis window when known. Preserve an unspecified horizon with a reason when a task cannot yet define it; do not invent a duration.
- Trading days, calendar days and months remain distinct. Calendar/session resolution belongs to later services; do not convert all units to fixed seconds.
- A simple UI label may describe the exact stored horizon, but there is no universal short/medium/long numeric mapping in this decision.
- Keep separate: data cutoff/as_of, analysis/prediction horizon, job deadline and report review/expiry time. A 3-month thesis does not imply 3-month quote freshness or a 3-month job runtime.
- Event schedule can be unknown or revised. Do not invent a precise timestamp or treat an expected announcement as an observed event.
- Durations/event windows are analysis metadata; they do not prescribe holding periods, order expiry or trade activation.

## Citation workload and validation boundaries

- Important factual claims carry evidence IDs; inferences point to supporting facts/evidence and retain assumptions/counterevidence. UI summary sentences can refer to structured findings without duplicating the full source text.
- Reuse one evidence object across claims. Fetch/snapshot once per job and reuse by content/version; raw documents remain in artifact storage, not repeated in every node context.
- Deterministic checks cover duplicate/dangling IDs, evidence availability at the stated cutoff and snapshot consistency. Building ID maps and checking links is approximately linear in evidence plus references; this is an algorithmic estimate, not a benchmark.
- No additional model request per claim by default. Semantic evidence validation is a separate bounded harness step; optional critic use follows the existing plan and approved budget.
- Extra citation tokens, evidence retrieval and semantic validation still have real costs. There is no end-to-end workload measurement yet, and no basis for calling the overhead zero or negligible.
- Later Task 9 must compare citation completeness/support, tokens, latency, calls and cost against the simple baseline. Unknown model usage/cost remains unknown, not zero.

## Incomplete reports

- Preserve useful supported findings while listing missing/stale/conflicting/unverified inputs and affected conclusions with reasons.
- Distinguish completeness from factual accuracy, evidence support and task execution status; a complete report is not guaranteed true, and a partial report may contain valid facts.
- Broken/unsupported material cannot be silently presented as verified fact. Surface the validation issue and omit or explicitly qualify the affected conclusion.
- An execution failure must not become an empty successful report; cancellation/failure remains visible in the later job lifecycle.
- Metadata contracts cannot prove source authenticity, citation entailment, principal capabilities or budget reservation. Those remain service responsibilities.

## Handoff

- Next: bounded 02c implementation brief, then TDD for EvidenceItem/ResearchRequest/ResearchReport and their typed support models in `services/gabfin/contracts/research.py`.
- Test horizon roundtrip/unit distinction, source provenance/timestamps, fact/inference separation, reference integrity and partial-report disclosure; then existing contracts/regression and package/scope checks.
- Runtime providers, model calls, storage integration and semantic-verifier performance are later work. No 02c application code or application tests changed in this research-only follow-up.
- [Main plan](../plans/2026-11-25-gabfin-upgrade-plan.md), [checkpoint](../../memory/execution.md).
