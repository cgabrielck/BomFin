---
name: Cgab Desk
description: Quiet dark Operate shell for a paper equity desk. Cyan is the only action color.
colors:
  ink: "#071016"
  hull: "#050b0e"
  console: "#0b1820"
  panel: "#0e1c22"
  panel-raised: "#12242c"
  hairline: "#1a3d44"
  phosphor: "#e8fffb"
  secondary: "#8aa8ae"
  action: "#2de2c5"
  action-hover: "#28cbb2"
  well: "#07141a"
  support: "#3ee0a0"
  resist: "#ff6b81"
  caution: "#e7c36a"
  action-ink: "#052226"
typography:
  title:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "0.02em"
  headline:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "0"
  body:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "0"
  label:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0"
  mono:
    fontFamily: "ui-monospace, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0"
rounded:
  control: "999px"
  panel: "16px"
  well: "12px"
  nav: "11px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "22px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.action-ink}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-primary-hover:
    backgroundColor: "{colors.action-hover}"
    textColor: "{colors.action-ink}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-ghost:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.action}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  button-danger:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.resist}"
    rounded: "{rounded.control}"
    padding: "9px 14px"
  card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.phosphor}"
    rounded: "{rounded.panel}"
    padding: "16px"
  input:
    backgroundColor: "{colors.well}"
    textColor: "{colors.phosphor}"
    rounded: "{rounded.well}"
    padding: "9px 10px"
  chip:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.secondary}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
---

# Design System: Cgab Desk

## Overview

**Creative North Star: "Quiet Operate Desk"**

Cgab is a dark paper desk, not a campaign page. The operator scans status, evidence, and the next paper action. Color is scarce: the ground is near-black teal, type is a cool white, and filled cyan is reserved for the control that does something.

The phone morning report uses the same ground, hairline, and action color. It is a separate read-only layout, not a shrunk trading ticket. Depth comes from one panel on the ground, never from glow, blur, or a card inside a card.

**Key Characteristics:**

- Flat panels, 1px hairline, radius at most 16px
- Cyan only on actions, the current nav item, and focus
- Mint, rose, and caution carry meaning (up, down, withhold), not decoration
- System UI type, tight tracking, no display costume
- Paper honesty stays on the surface: not live, not verified, not an order

## Colors

The palette is a night console: cool blacks, one action teal, and three semantic hues.

### Primary

- **Action cyan** (#2de2c5): Filled buttons, the on state, the language pill that is selected, focus, and the paper status pill. Ink on cyan is **Action ink** (#052226).

### Secondary

- **Support mint** (#3ee0a0): Positive P/L, support zone tint, a live-process dot.
- **Resist rose** (#ff6b81): Negative P/L, danger buttons, resist zone tint, refused teaching replies.

### Tertiary

- **Caution** (#e7c36a): Withheld claims, stale or unreachable state, hold. It is a warning, not a glow.

### Neutral

- **Ink** (#071016): Page ground.
- **Hull** (#050b0e): Sidebar.
- **Console** (#0b1820): Top language track, zone panel, inset wells.
- **Panel** (#0e1c22): The one card layer.
- **Panel raised** (#12242c): A second flat tone for toasts only, not a nested card.
- **Hairline** (#1a3d44): Borders and dividers.
- **Phosphor** (#e8fffb): Primary text.
- **Secondary text** (#8aa8ae): Labels, hints, honesty copy.

### Named Rules

**The One Action Rule.** Filled color is cyan. Ghost actions use a cyan hairline. Danger uses rose. There is no second filled brand color.

**The Unused Purple Rule.** A `--purple` variable may remain declared so older notes stay findable. It is not applied to chrome, type, buttons, or charts.

## Typography

**Display Font:** Segoe UI (with system-ui, sans-serif)
**Body Font:** Segoe UI (with system-ui, sans-serif)
**Label/Mono Font:** ui-monospace for zone ids and code only

**Character:** A working face, not a brand campaign. Titles stay at or under 20px. Tracking stays at or under 0.02em.

### Hierarchy

- **Title** (800, 20px, tight tracking): The wordmark only.
- **Headline** (700, 15–16px): Card titles and phone section titles.
- **Body** (400, 13–14px): Desk copy. Phone body can sit at 13px.
- **Label** (500, 12px, no uppercase tracking): Secondary lines under a real heading. Do not put a tiny tracked label above the heading.

### Named Rules

**The Heading Speaks Rule.** A section name is the heading. Do not stack a tracked uppercase eyebrow above it.

## Layout

Desktop is a 248px sidebar plus a fluid column. Content padding is 22px, card gap 12–14px. Below 1100px the grids collapse to one column and the sidebar becomes a drawer. Below 520px the desktop shell hides and points at `/m`.

Phone is a single column, max 480px, with Morning, Agents, and Activity in a bottom dock. The honesty line sits in that dock so it stays with the tabs. Targets that act are at least 48px tall.

## Elevation & Depth

The desk is flat. A panel is a fill plus a 1px hairline. Sidebar groups are labels on the hull, separated by a hairline, not cards. Metrics inside a card are type, not another card.

### Named Rules

**The Flat Panel Rule.** No box-shadow, no blur, no radial wash, no cyan-to-purple sweep. Focus is a 2px cyan outline with no halo.

## Shapes

Controls that are buttons or status pills are fully rounded. Panels stop at 16px. Wells and inputs stop at 12px. Nav items use 11px. Do not stack large radii to fake depth.

## Components

### Buttons

- **Shape:** Full pill (999px)
- **Primary:** Action cyan fill, action ink type, 9px 14px. Hover darkens the fill slightly. No brightness filter and no glow.
- **Ghost:** Transparent fill, cyan hairline and type.
- **Danger:** Transparent fill, rose hairline and type.
- **Phone:** Same pills, full width, at least 48px tall. Copy includes the word paper.

### Chips

- **Style:** Hairline on the panel or ink, secondary type, full pill.
- **State:** Paper uses the cyan hairline. Off and guest use a dim hairline. Caution uses the caution hue.

### Cards / Containers

- **Corner Style:** 16px panels.
- **Background:** Panel on ink.
- **Shadow Strategy:** None. See Elevation.
- **Border:** 1px hairline.
- **Internal Padding:** 16px. Stats inside a card have no second border.

### Inputs / Fields

- **Style:** Console-dark fill, hairline, 12px radius.
- **Focus:** Cyan caret and a cyan border or the global 2px outline. No outer glow.
- **Error / Disabled:** Rose type for the error. Disabled controls drop to about 45% opacity.

### Navigation

Sidebar groups are Navigation, Apps, and More, each a heading plus a short line, then text buttons. The current item is a cyan tint and a cyan dot. There is no color rail and no letter tile. Phone navigation is three equal tabs in the bottom dock.

### Ask Cgab

A desktop teaching panel on the same panel, hairline, and type. The title is phosphor, not cyan. Quick prompts are hairline buttons, not dashed suggestion chips. The send control is the cyan action. The phone shell does not include this panel.

### Zone chrome

The chart tools and the zone panel use the same hairline and pills. Zone fills stay the locked tints: neutral gray-teal, optional support mint, optional resist rose. The panel does not add an order button.

## Do's and Don'ts

### Do:

- **Do** keep cyan as the only filled action, including Ask Cgab send and phone Continue paper.
- **Do** keep one panel layer. Put related numbers in the same card as type.
- **Do** keep the phone honesty line in the bottom dock, and name unreachable Tailscale without offering a public tunnel.
- **Do** theme selection, caret, and the scrollbar from ink, hairline, and cyan.

### Don't:

- **Don't** apply purple, a radial wash, a gradient sweep, or a glow shadow on the shell.
- **Don't** nest a bordered card inside a card, or put a tracked uppercase label above a heading.
- **Don't** add a marketing hero, a landing page, or an Ask Cgab control on `/m`.
- **Don't** stamp verified or live, or add an order CTA on the chart, the teaching chat, or the phone.
