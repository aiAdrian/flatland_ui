# Widget B3 — Network Correlation Graph

> Spec following [widget-authoring-process.md](../reference/widget-authoring-process.md).
> Status: **planned** (spec only, no code yet).

## 1. Identity
- **Name:** Network Correlation Graph
- **`kind`:** Context (interaction-framework.md §"Context Determination" —
  *why, how bad, whom does it affect?*)
- **`granularity`:** overview → detail (force-directed layout at a glance;
  click a node to focus its neighbourhood + see the correlating KPIs)
- **Default zone:** center or right (companion to Graphic Timetable / Marey,
  not a replacement for the geographic Track Layout map)
- **Sources:** owner's research line (network abstraction, cross-industry
  inspiration) · **AI4REALNET check below**
- **Grounding:** [`AI4REALNET/InteractiveAI`](https://github.com/AI4REALNET/InteractiveAI)
  — the consortium's own multi-use-case HMI platform (PowerGrid, Railway, ATM
  share one frontend). Its `Graph.vue` +
  `stores/components/graph.ts` component is the direct reuse target: a D3
  force-directed graph where nodes are `<circle>` elements coloured by
  `criticality` (`ND/ROUTINE/LOW/MEDIUM/HIGH`, see `types/cards.ts`), sized up on
  focus/selection, and connected by edges whose colour encodes correlation
  strength between two entities' KPIs. Confirmed relevant because
  **Railway is one of InteractiveAI's three built-in use cases**
  (`VITE_RAILWAY_SIMU`), not a foreign domain applied by analogy.

## 2. Promise
The operator can see the railway network as a **relationship graph** —
stations/junctions/trains as nodes positioned by force-simulation (not
geography), coloured by severity, connected by edges weighted by how strongly
they affect each other — so that "what else does this problem touch?" is
answered by proximity and edge weight instead of scanning the geographic map
for cascading effects.

This is a **deliberate escape from the track-grid abstraction**: the same
entities Track Layout (Map) shows spatially are here shown *relationally*,
surfacing structure that geography hides (e.g. two distant stations tightly
coupled through a shared bottleneck resource).

## 3. Per-mode behaviour
- **Recommendation:** the AI's flagged conflict/recommendation highlights its
  node and the nodes it would affect (focus + `.active` link styling, mirroring
  `Graph.vue`'s `showLink`/`focusLink`). Framing = *Recommendation* (one
  highlighted path).
- **Co-Learning:** neutral exploration — the operator can pick *any* node and
  see its correlation neighbourhood, comparing "what does A affect" vs "what
  does B affect" without an AI-picked focus. Framing = *Assessment*.
- **Director:** aggregate view only — shows the graph as the autonomous
  policy's current operating picture (read-only); a newly-HIGH node is the
  exception-handling cue to drill in.

## 4. System interaction
Data **in** (available now):

| Signal / endpoint | Field used | Role |
|---|---|---|
| `store.trains` / agents | position, id | node identity |
| `store.conflicts` / `getConflicts` | affected agent ids, severity | node `criticality` class, edge existence |
| `store.scenarios` / KPI deltas | per-entity KPI values | correlation strength between two nodes (edge weight) — same role as InteractiveAI's `d3Correlations` KPI-pair correlation |

Actions **out:** none that mutate sim state (informational, like A1). Node
click emits a focus event usable by other widgets (e.g. filter Agent Inspector to
the selected train) — same seam as `eventBus.emit('graph:showTooltip', …)` in
the reference implementation, adapted to our existing event bus /
`selectedHandle` pattern instead of a new one.

Backend — **none needed for a first cut.** Correlation strength can start as a
cheap proxy (do two agents share a blocked segment / did their KPIs move
together across the last N scenario rollouts?), same "ensemble-style proxy
before real backend" approach as A1 §4. A true multi-agent correlation signal
is a flagged future extension, not faked as calibrated.

## 5. Allocation & accountability touchpoints
- **Loop stage:** Context Determination (upstream of Decide) — this widget
  answers "whom does it affect", not "what should I do".
- **Allocation:** display-only in all three modes; ownership of the underlying
  decision stays with whichever mode's Decide-stage owner is active (brief §5a).
  This widget does not change control allocation, only situational visibility.
- **Decision events emitted:** none (pure Context widget, like Agent Inspector).
  May be referenced from A2's decision log entries ("operator inspected the
  correlation graph before deciding") if we choose to log widget-view events —
  optional, not required for v1.

## 6. Acceptance scenario
A malfunction affects Train 7 at a junction. On the graph, Train 7's node turns
`HIGH` (red ring) and grows; three other nodes it correlates with (sharing the
same downstream segment) light up with thicker, brighter edges toward it. The
operator, who would not have suspected Train 12 was affected by looking at the
geographic map alone (it's on the opposite side of the layout), sees it via the
graph's proximity/edge-weight encoding and checks its schedule before deciding.
**Measurable success:** operators using the graph identify more of the
correlated-but-geographically-distant trains before deciding, vs. a control
condition using only the geographic Track Layout map (a testable Q5 study
comparison).

## 7. Effort & changes
- **Effort:** M (~1–2 days). A D3 force-directed graph is a new dependency
  pattern for this codebase (existing viz is SVG/Canvas hand-rolled, not D3) —
  budget time for the D3↔Angular/signals integration, not just the visual.
- **Touch:** new `features/network-correlation-graph/`; register at
  `panel-plugin-host` (+`@switch`), `layout-designer` palette,
  `PANEL_MODE_AVAILABILITY` (all modes, behaviour differs),
  `PanelDefinition.kind='context'`; `core/widgets/widget-catalog.ts` entry
  (`catalogId: 'B3'`); `panel-mode-matrix` row. **Colour tokens:** the
  reference `Graph.vue` hardcodes hex (`--red-500: #f55`, etc.) — do **not**
  port that; use our Lyne severity tokens / `visual-encoding.ts` seam per the
  no-hardcoded-colours guardrail (CLAUDE.md).
- **Dependency:** add `d3-force`, `d3-selection`, `d3-drag`, `d3-zoom` (the
  subset `Graph.vue` actually uses) rather than the full `d3` bundle.

## 8. Open questions / risks
- **Correlation proxy honesty:** without a real multi-agent influence model,
  "edge weight" risks being cosmetic. Mitigate the same way A1 does — label it
  ("shared-resource proxy") until backed by a real signal, don't oversell as
  causal.
- **Redundancy with the geographic map:** does a second "trains as nodes" view
  add value or split attention? The acceptance scenario above is the test —
  if operators don't catch anything the map wouldn't have shown, this widget's
  contribution is weak and it should be reconsidered or merged into a Track
  Layout overlay mode instead of a standalone widget.
- **Force-layout stability:** D3 force simulations can be visually noisy
  (nodes drifting) in a live-updating dashboard — the reference implementation
  freezes positions post-drag (`fx`/`fy`); we'd need an equivalent "settle then
  hold" behaviour so the graph doesn't jitter every tick.
- **Scale:** InteractiveAI's demo graph is small (28 nodes). Our Flatland
  scenarios can have many more agents — needs a filtering/clustering strategy
  (e.g. only show nodes above a severity threshold, or cluster by
  station/region) before this scales past a handful of active trains.
