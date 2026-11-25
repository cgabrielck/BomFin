# Legacy product record

<!-- impeccable:product-schema 1 -->

> LEGACY / SUPERSEDED — this record describes the previous implementation, not the new GabFin requirements. Follow the [confirmed design](../../docs/superpowers/specs/2026-11-25-gabfin-system-design.md) and [upgrade plan](../../docs/superpowers/plans/2026-11-25-gabfin-upgrade-plan.md).

Recorded from the accepted Desk handoff (Owner package, 2026-10-30) and ADR-003 / ADR-005. No separate interview was run in this pass.

## Platform

web

## Users

Gabriel operates Cgab as a paper desk: the desktop shell for the trading day, and a private phone morning check (Tailscale, `/m`) to see overnight paper results and choose Continue paper or Pause paper.

## Product Purpose

Cgab Desk is the product UI for a US equity paper desk. It shows session state, scan and research evidence, chart zones, and paper controls in one Operate shell. Success is an honest paper picture the operator can act on without mistaking it for a live or verified book.

## Positioning

One product shell (FastAPI Desk) owns orders, risk release, and live-rule changes. Streamlit stays a lab mirror of the same books. The phone surface is a read-only morning report, not a second order ticket.

## Operating Context

Desktop Desk is the full workspace (sidebar, chart, zone panel, Ask Cgab teaching chat). Phone `/m` is Morning, Agents, and Activity, reached over Tailscale Serve. Paper worker continue and pause are the only phone writes.

## Capabilities and Constraints

- Paper controls stay on Desk. The phone may POST only paper worker continue and pause, and only for an operator. Guests do not see those buttons.
- No live broker path, no Approve live, no AI judge, and no `verified` or `live` stamps in this shell.
- Zone tints stay locked: neutral by default, optional support and resist. They are role labels, not orders. Chart, chat, and phone have no new order CTAs.
- Ask Cgab is a teaching panel on the desktop shell. The phone has no Ask Cgab control.
- Equity curve and event pins are out of the phone P0 surface.
- Merge of this UI is not a runtime acceptance and does not open live trading.

## Brand Commitments

The product name is Cgab. Voice is plain and specific: paper, not live; teaching, not an order agent. The desktop shell is an Operate tool. Marketing landing treatment is out of scope for `web/static`.

## Evidence on Hand

- Product shell: `web/static/index.html`
- Phone shell: `web/static/mobile.html`
- Visual lock: accepted Impeccable Desk handoff (de-purple the shell, cyan as the only action color, Ask Cgab on the same tokens)
- Phone lock: Mobile Desk RO P0 spec, path A

Do not invent fills, seal results, or beat-SPY figures when the book withholds them.

## Product Principles

- Say what the book actually did, including skips and losses.
- Keep order and risk actions on the desktop Desk.
- Keep the phone to a morning decision: read the paper session, then continue or pause paper.
- Do not dress paper state as live, verified, or a buy call.
- Keep Streamlit as the lab mirror.

## Accessibility & Inclusion

Desktop and phone are dark Operate surfaces used for a full session and a morning glance. Body text and controls need to stay readable on that ground; phone actions need at least a 44px target. English and Traditional Chinese are both first-class on the desktop shell.
