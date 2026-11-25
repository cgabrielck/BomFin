# Known issues

- Static code findings and evidence are owned by the canonical
  [design](../superpowers/specs/2026-11-25-gabfin-system-design.md), section 3.
  They include polling, execution coupling, backtest timing/cost problems
  and a conditional proxy-auth risk. Do not duplicate findings here.
- Local baseline now ran; confirmed typecheck failures and journal test pollution
  are B01/B02 in [baseline](../audit/baseline-2026-11-25.md), which owns their
  evidence and next fixes. They were recorded, not fixed in 01b.
- Optional Postgres coverage and the pandas warning are B03/B04 there; skipped
  tests do not establish Postgres correctness. Earlier design findings still
  need their own reproduction/regression evidence.
- External feed, account, pricing and runtime-risk approval gaps are tracked as
  gates in the design and tasks in the plan, not confirmed application defects.
