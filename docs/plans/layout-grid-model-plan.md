# Layout Grid Model — giving the designer a spatial vocabulary

> **Status:** Draft for feedback (no implementation yet)
> **Date:** 2026-08-11
> **Context:** Sibling to [`mode-scoped-layouts-plan.md`](./mode-scoped-layouts-plan.md).
> That plan answers *which* layout renders for a given interaction mode. This one
> answers *what a layout can say* — today it can only say "columns of a fixed
> pixel width, each a vertical stack". The Director work on
> `roman/director-strategies-shift-review` needed five things that vocabulary
> cannot express, and worked around all five by hardcoding surfaces into
> `AppComponent`. Frontend-only; presentation only, no payload changes.

---

## 1. The evidence — six widgets that could not be placed

`roman/director-strategies-shift-review` shipped six components. All six rendered
from fixed slots in `app.component.html`, none was in the widget catalog, the
availability map, the palette or the Gallery. They have since been registered
(commit `fffa2ff`), which fixed their *discoverability* — but the fixed slots
stayed, because the layout model still cannot hold them.

| Widget | Why the fixed slot | Model gap |
|---|---|---|
| `strategy-options` | Three equal-width A/B/C cards, full width, above the map | no spanning / no "row of N equal cells" |
| `strategy-forecast` | Needs ~380px for four time columns (Now / +10 / +20 / +30) | no per-panel `minWidth` |
| `shift-review` | Takes over the working area; tiles stay alive behind it (~20 s of planning) | no screen states, no "yields to" |
| `ai-activity` | Right column, below the forecast | placeable — kept adjacent for coherence |
| `strategy-reflection` | Appears only after a strategy is committed | no conditional presence |
| `co-learning-effect` | Right column | placeable |

Director also **drops the left column entirely** (`[class.two-col]`), freeing
~280px for the map and the forecast. That is a different column set for the same
design — also not expressible.

---

## 2. What the model says today (verified in code)

**Designer** — `features/layout-designer/layout-designer.models.ts`:

```ts
DesignerColumn { rowId?, rowHeight?, width: number, panels: DesignerPanel[] }
DesignerPanel  { minHeight: number, height?: number|null }
```

**Runtime** — `core/layout/models/layout.models.ts`:

```ts
LayoutColumn { zone: LayoutZone, width: number | string, minWidth?, maxWidth? }
LayoutState  { columns: LayoutColumn[], panels: PanelInstance[] }
```

Three facts follow, and each one is a gap:

1. **The designer is less capable than the runtime it feeds.**
   `DesignerColumn.width` is `number` (px only); `LayoutColumn.width` is
   `number | string` and already accepts `'1fr'`. Fluid widths exist in the
   target model and cannot be authored.
2. **Panels have a height floor but no width floor.** `minHeight` exists;
   `minWidth` does not — on either side. A widget cannot state the width below
   which it stops being readable.
3. **The runtime hardcodes the minimum to zero.**
   `AppComponent.runtimeRowGridTemplate()` converts px widths into percentage
   ratios and emits `minmax(0, <pct>%)` per column. It is *already CSS Grid* —
   but with `min = 0`, so any panel can be squeezed to nothing, and the px
   numbers the designer stores are only ever used as ratios.

Point 3 is the important one: **the runtime is already a grid renderer.** The
work is not "introduce grid", it is "stop deriving the grid from px ratios and
let the layout state it directly."

### 2b. The saved-layout path is not the problem — the fork is

`@if (useSavedRuntimeLayout())` in `app.component.html` does render designer
layouts, rows and all. But it is an either/or with the hardcoded `@else`
(`.three-col`) branch, and every mode-specific surface — the Director bar, the
strategy tiles, the forecast, the shift screen — lives only in the `@else`.
Activating a saved design therefore loses all Director behaviour. This is the
same finding as `mode-scoped-layouts-plan.md` §1.2; recorded here because it
sets the sequencing in §5.

---

## 3. Proposal — `grid-template-areas` as the layout model

Replace "list of columns, each a stack" with a named-area grid, one per screen:

```ts
interface LayoutScreen {
  /** 'working' | 'shift-review' | … — a layout may define several. */
  name: string;
  /** When this screen claims the canvas. Absent = the default screen. */
  when?: LayoutCondition;
  /** The layout, as a picture. One string per row. */
  areas: string[];
  /** Track sizing, one entry per column / row of `areas`. */
  columns: string[];
  rows: string[];
  /** Which widget type fills which area name. */
  place: Record<string, string>;
}
```

A Director working screen becomes literally readable:

```ts
{
  name: 'working',
  areas: [
    'bar    bar    bar',
    'tiles  tiles  forecast',
    'map    map    activity',
  ],
  columns: ['minmax(320px, 2fr)', 'minmax(320px, 2fr)', 'minmax(380px, 0.9fr)'],
  rows: ['auto', 'auto', 'minmax(320px, 1fr)'],
  place: {
    'director-directive': 'bar',
    'strategy-options':   'tiles',
    'strategy-forecast':  'forecast',
    'flatland-map':       'map',
    'ai-activity':        'activity',
  },
}
```

and the debrief is a second screen over the same panel set:

```ts
{ name: 'shift-review', when: { signal: 'shiftReviewOpen' },
  areas: ['review'], columns: ['1fr'], rows: ['1fr'],
  place: { 'shift-review': 'review' } }
```

**Why this shape:**

- `grid-template-areas` is an ASCII picture of the layout — legible in a diff,
  serializable without a translation layer, and *is* what the browser renders.
- Spanning is free: repeat the area name. Solves the A/B/C row.
- `minmax(380px, 0.9fr)` is fluid **and** constrained in one token. Solves the
  forecast's four columns and replaces `minmax(0, …%)`.
- A second screen with its own `when` solves the shift-review takeover, and
  "hidden, not destroyed" comes for free — the working screen's panels are not
  unmounted, only un-placed.
- Per-mode is a different `areas` string over the same panels — exactly the
  `mode?: InteractionMode` field from `mode-scoped-layouts-plan.md` §3.
- Responsive is one screen per breakpoint, instead of px columns that overflow.
- Dropping Director's left column is a three-column `areas` picture rather than
  a `[class.two-col]` flag.

### 3b. Companion change — `minWidth` in the widget catalog

`WidgetMeta` already carries `minHeight`. Add `minWidth?: number`, so a widget
declares its own readability floor (`strategy-forecast: 380`), and the designer
can **validate a placement** — "Strategy Forecast in a 240px track: its four
time columns will clip" — instead of clipping silently. This is the piece that
makes the constraint a property of the widget rather than of one hand-tuned
layout.

---

## 4. What this does *not* change

- **Fixed slots stay legitimate.** Some surfaces genuinely carry constraints a
  free-floating panel should not override — the map wants the largest cell, the
  directive bar wants to stay above the fold. The grid expresses those as track
  sizing rather than as template code; it does not make everything draggable.
- **Per-mode behaviour stays in components.** Availability is
  `panel-mode-availability.ts`; behaviour reads `store.interactionMode()`. The
  grid places widgets, it does not gate them.
- **No payload or trajectory changes.** Do not touch `_recordTrajectory` or the
  scenario-refresh throttling.

---

## 5. Sequencing against `mode-scoped-layouts-plan.md`

That plan's P1 is the resolver ("which design for which mode"). The two plans
touch the same code, and the order matters:

> **The grid model should land before, or with, the resolver.** A resolver built
> on `DesignerColumn[]` inherits px tracks and `minmax(0, …)`, and would have to
> be rewritten once tracks become declarative. Conversely the grid model is
> useful on its own: it makes the existing `useSavedRuntimeLayout()` path able
> to hold a Director-shaped layout, which is the precondition for retiring the
> `@if/@else` fork at all.

Suggested phases:

- **G1** — `minWidth` in the widget catalog + designer validation warning.
  Standalone, no model change, immediately useful.
- **G2** — `LayoutScreen` with `areas`/`columns`/`rows`/`place`; runtime renders
  it directly instead of `runtimeRowGridTemplate()`. Migrate existing designs by
  deriving an `areas` picture from their rows/columns (mechanical).
- **G3** — multiple screens per layout + `when` conditions; port the shift-review
  takeover off its `shiftScreenOpen()` flag.
- **G4** — express the hardcoded `three-col` as a seeded, read-only screen set so
  the `@if/@else` fork collapses into one path (see `mode-scoped-layouts-plan.md`
  §10.4, which asks the same question from the other side).

---

## 6. Open questions

1. **Migration of existing designs** — deriving `areas` from today's
   rows/columns is mechanical, but px widths become track sizes with what
   minimum? Draft: `minmax(<stored px * 0.75>, <ratio>fr)`, then let authors
   tune. Or: migrate on open, keep the old field until saved.
2. **How much sizing vocabulary?** Full CSS track syntax is powerful and easy to
   get wrong in a visual editor. Restrict to a picked set
   (`auto` · `1fr` · `minmax(Npx, Nfr)`) or pass strings through?
3. **`when` conditions** — a small named set (`shiftReviewOpen`, `episodeDone`,
   `aiInControl`) is safe and legible; an expression language is not. Draft:
   named signals only, registered in one map.
4. **Does the designer canvas become a grid editor?** Painting area letters onto
   a grid is a different interaction from dragging cards into columns. Worth
   prototyping both before committing — the current drag model may survive if
   areas are inferred from where cards land.
5. **Is `floating` still needed?** With screens, a takeover is a screen, not a
   zone. `LayoutZone.floating` may become dead once G3 lands.
