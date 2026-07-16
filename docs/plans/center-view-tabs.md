# Center view tabs — one tabbed surface instead of stacked panels

> Dated plan, 2026-07-12. The center column stacks big views vertically, which is
> hard to navigate. Idea (danib): make the center a **tab layout** where one
> situation *view* is shown at a time. This doc fixes the principle that decides
> what becomes a tab vs. an overlay, lists the candidate views, and records the
> first-cut `view-tabs` container.

## Decision — tabs vs. overlays

The organising principle that sorts the candidate list:

| Type | What | UI pattern |
| --- | --- | --- |
| **Situation *views*** — mutually exclusive, full-size, "how do I look at this run" | Map · Marey · Timetable · Goal Achievement · (future) Power diagram | **Center tabs** — one at a time |
| **Episodic / cross-cutting *tasks*** | Reflection · Survey · LLM chat | **Overlay / popup** — floats over the active view |

- View-type widgets answer *"how do I look at the same run"* — you want **one big
  one at a time**, not stacked. Tabs fit.
- **Reflection is NOT a tab** (danib's instinct, endorsed): it is a moment of
  stepping back (post-run, statistical + open questions), not a live operational
  view. It fits the **survey overlay** pattern, triggered at episode end / on
  demand. This also matches the framing that Co-Learning is an orthogonal
  cross-cutting layer (memory: `colearning-crosscutting-layer`), not a 4th mode —
  a reflection overlay *over any view* is exactly "cross-cutting".
- **LLM chat** = a persistent, collapsible companion overlay available across all
  views. Also not a center tab.

## The `view-tabs` container — registry- and config-driven (not hardwired)

A single center panel (`type: 'view-tabs'`) with a lightweight button tab bar
(no Lyne tabs component exists; styled with `--sbb-color-*` tokens like the
layer chips — no hardcoded colours). **Nothing about the views is hardwired in
the container:**

- **Registry** (`features/view-tabs/center-views.ts`): the single source of
  truth mapping each center-view `type` → `{ label, component, inputs }`. Adding
  a new view (e.g. a power diagram) = one entry here. Current: Map
  (`flatland-map`), Marey (`graphic-timetable`), Timetable, Goal Achievement
  (gets the forwarded `[panel]` via its `inputs`).
- **Generic rendering**: the active tab renders through `NgComponentOutlet` +
  the registry's `inputs` bag — the container has no per-view template code.
- **Config-driven tabs**: which views are tabs (and their order) comes from the
  panel's `settings.tabs` (else all registered views). Set in the **layout
  designer**: selecting a `view-tabs` panel shows a "View Tabs" settings group
  with a checkbox per available view; the choice is stored in `settings.tabs`
  and flows to the runtime panel (same path as the toggle-view split setting).

`features/view-tabs/view-tabs.component.*`. Registered at the usual seams
(panel-plugin-host, layout-designer palette + settings, widget-catalog).
Generalises the Map/Marey `view-toggle` checkboxes into a configurable
one-at-a-time tab bar. Active tab is component-local (a signal) for now.

## Done

- Registry + generic `NgComponentOutlet` rendering (no hardwired views).
- Config-driven tab selection via the layout designer (`settings.tabs`).

## Open questions / next

- **Persist the active tab** (per session / per mode) — currently component-local.
- **Mode-aware default tab** — e.g. Director opens on Goal Achievement, Co-Learning
  on Marey. Deferred; the container is mode-agnostic for now.
- **Reorder tabs in the designer** — order currently follows the registry; a
  drag-to-reorder in the settings group is a small follow-up.
- **Power diagram** and other future views slot in with one `center-views.ts`
  entry — they then appear automatically in the designer checkbox list.
- **Relationship to `toggle-view`** — the older Map/Marey composite stays; view-tabs
  is the alternative. If the team prefers tabs, view-tabs can supersede it.
- **Reflection / chat overlays** — separate work; this doc only commits the tabs.
