# S02/02c research contract implementation brief

Execute inline with TDD, one agent. Implements the accepted [research experience plan](2026-11-25-gabfin-research-experience-plan.md); no runtime integration.

## Exact interfaces and engineering choices

- Create only `services/gabfin/contracts/research.py` and `tests/gabfin/test_research_contracts.py`.
- ResearchHorizon union: duration(kind,count strict positive,unit minute/hour/calendar_day/trading_day/week/month/year); event(kind,name,expected_at nullable UTC); unspecified(kind,reason). Event window is nullable duration metadata, not calendar computation.
- EvidenceItem: version, evidence_id UUID, url nullable HttpUrl, artifact_id nullable UUID (at least one), publisher, original_firm nullable, published_at nullable UTC, first_seen_at/available_at UTC, content_hash lowercase SHA256 shape, license_tag. first_seen <= available. No publication timestamp fabricated from a date-only source.
- ResearchRequest: version, request_id, nonempty unique instrument UUIDs, question, horizon, actor_id UUID, nonempty unique capability_scope strings, snapshot_id/budget_id UUIDs, as_of/deadline UTC. deadline > as_of. Metadata does not authenticate actor or reserve money.
- Fact: fact_id, text, nonempty citation UUIDs. Citation: citation_id, evidence_id, locator. Inference: inference_id,text,fact_ids,citation_ids,assumptions,counterevidence citation IDs; at least one supporting fact or citation.
- MissingData: code,description,affected_conclusions tuple of text (may describe omitted conclusions). ResearchSummary: why_now,disposition watch/avoid/no_edge/insufficient_evidence,conditions,invalidation. ResearchUsage: input/output tokens nullable strict nonnegative JS-safe ints, cost nullable Money, cost_state known/unknown; known requires nonnegative cost, unknown requires null.
- ResearchReport: version, report_id/request_id/snapshot_id, horizon, evidence/facts/inferences/citations/missing_data tuples, summary, completeness complete/partial, as_of/generated_at, model_version/prompt_version, usage. partial requires missing_data; complete prohibits missing_data; insufficient_evidence requires partial. generated >= as_of; evidence available <= as_of.
- Report validates unique IDs per collection, all citation/evidence/fact links and duplicate references; empty findings allowed only for partial insufficient_evidence reports. No semantic truth/support claim from ID checks. Facts cannot embed broker fields (extra forbidden). Nested collections are tuples, shared evidence appears once.
- No source fetch, model call, job status lifecycle, watch persistence or automatic StrategyIntent; later services validate request/snapshot ownership and actual principal.

## Steps / expected verification

- [x] Preserve source hashes/lockfile and write tests before production module.
- [x] RED: sanitized pytest new module; missing import failures expected after successful collection.
- [x] Implement exact contracts and run GREEN; test roundtrip, horizons, sources, chronology, dangling/duplicate refs, partial reports and unknown costs.
- [x] Run all gabfin tests and sanitized full regression; inspect skips/warnings; archive only unit-generated journal.
- [x] Check generated schemas, isolated import, pip check and unchanged original hashes; self-review single-agent limits.
- [x] Commit exactly two source paths; update audit and checkpoint with actual results. Whole Task 2 remains incomplete.
