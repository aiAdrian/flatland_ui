# Widget spec — Netz-Zeitansicht (Network Time View)

> **Status:** spec, not built. Dated 2026-09-07.
> **Why it exists:** [mode-layouts-three-zones.md](mode-layouts-three-zones.md) §4
> first proposed the ZWL as Director's default view and then had to retract it —
> a Marey's y-axis is a *linearisation* of cells, so it presumes a line exists.
> That holds for the PF–CH corridor and is a fiction for Olten. This widget is
> the network-scale answer to the question the ZWL answers for a corridor:
> **is the plan going to fit, and what did my objective change?**

## 1 · Identity

- **Name:** Netz-Zeitansicht (Network Time View)
- **Type / slug:** `network-time-view`
- **Catalog id:** **B5** (B4 is the Link-Map/ZWL port, see
  [widget-linkmap-zwl.md](widget-linkmap-zwl.md))
- **`kind`:** Prediction — it shows the planned future and an alternative to it,
  not the current state. Same family as B2.
- **`granularity`:** overview → detail (rows are the overview; pointing at a bar
  is the per-train detail)
- **Default zone:** center
- **Source origin:** `from-scratch UI, deliberately` — but **not** a from-scratch
  *concept*: see grounding.
- **Grounding reference:** the railway **Belegungs-/Sperrzeitendarstellung** —
  occupancy of infrastructure elements over time, the standard instrument of
  railway capacity analysis (blocking-time theory, UIC 406). This widget is a
  simplified blocking-time diagram at *resource* granularity rather than at
  block-section granularity. The ZWL/Marey is its time-**distance** sibling; both
  are control-room practice, they differ in what the y-axis carries.

## 2 · Promise

> Read whether the plan fits through the network's bottlenecks — and see, in the
> same picture, what your objective changed and what it cost.

Differentiation from what exists (checked against `widget-catalog.ts`):

- **`marey` / ZWL** (prediction) — time × *distance along a line*. Needs a line.
  Complementary, not superseded: for a corridor it is the better view.
- **B2 conflict-aware Marey** — adds ribbons to that same linear axis; inherits
  the same precondition.
- **`flatland-map`** (event) — space, no time. Shows *where*, not *when*, and a
  waiting train looks much like a running one.
- **`timetable`** (context) — per train, not per resource. Answers "what is train
  X supposed to do", not "does resource Y hold".
- **B3 network correlation graph** (context) — relational, not temporal.

## 3 · Per-mode behaviour

Offered in **all three modes**; the *framing* differs, and so does the colour
convention, which matters because the repo already has one.

- **Director (WP 3.4) — the primary mode.** Both plans are the AI's: the running
  plan and the previewed one under a candidate objective. Encoding is therefore
  **neutral by identity and loud by change**: unchanged occupancy grey, changed
  occupancy accented, the other plan's position as a dashed ghost. This is the
  evidence surface for the A/B/C strategy decision — it does not carry the
  decision itself (`strategy-options` does).
- **Recommendation (WP 3.1).** One plan plus the AI's proposed action: the ghost
  is *what the recommendation would do*. The contended resource and the window
  are named, so accepting or overriding has a visible consequence.
- **Co-Learning (WP 3.3).** Two plans of *different authorship*, so the existing
  convention wins over the one above: **human-influenced blue, AI-simulated
  yellow** (`--app-whatif-human` / `--app-whatif-ai`, the A3S/TraceRL convention
  from CLAUDE.md and widget B1). Neutral: neither plan is marked better.

Read-only in every mode (`writes: 'view'` — hover and selection only).

## 4 · System interaction

**Data in**

| Need | Source | State |
|---|---|---|
| Train positions over time | `store.history()` / trajectory signals (already feeding `marey-chart`) | ✓ exists |
| The previewed alternative plan | `store.directorPreviewPaths()`, `directorPreviewDivergence()` | ✓ exists |
| Station identity | `SessionStore.stations()` (shared registry, also used by the map stations layer) | ✓ exists |
| **The resource rows** (which cells form "Süd-Ost 59/13–14") | — | ✗ to build, see §4b |
| **Capacity per resource** | — | ✗ to build (declared on the Netz) |

**Actions out** — none that change the run. Hover sets
`store.directorHoverHandle` (Director) / `setAgentHoverAgents` (the pattern
`marey-chart` already uses), so pointing at a bar highlights the same train on the
map and in the Fahrplan. Selection is shared state, not widget-local.

### 4b · The resource rows can be *derived*, not declared

The finding that makes this widget affordable. Reading `olten.pkl` directly:
52 agents carry **24 distinct waypoint cells**, and 23 of them have an
intermediate call between origin and destination. Those waypoint cells cluster
exactly into the infrastructure the timetable cares about — in Olten, row 37
columns 7–16 (the platform tracks) plus four line portals.

**So the row set comes from the timetable for free.** What still has to be
declared is:

1. **Capacity** per resource (a platform track is 1, a four-track station is 4).
2. **Sections nobody calls at** — a single-track stretch is a resource with no
   waypoint on it. These are exactly the `bottlenecks` field proposed in
   [scenario-infrastructure-gallery.md](scenario-infrastructure-gallery.md) §4.1.
3. **Grouping and naming** — merging adjacent cells into one readable row.

This partially answers that plan's open question §10.1 ("is `affords` declared or
derived?"): for station-shaped resources, derived; for sections, declared.

**Backend table**

| Capability | Available now | To build (flagged) |
|---|---|:---:|
| Agent trajectories `(i, t, r, c)` | ✓ | |
| Waypoints per agent incl. scheduled times | ✓ in the env (`agent.waypoints`, `waypoints_earliest_departure/_latest_arrival`) — **not currently exposed by any endpoint** | ✓ expose |
| Resource registry (rows + capacity + member cells) | | ✓ new — `GET /{id}/hmi/resources`, following `models/hmi.py` conventions |
| Occupancy intervals per resource per plan | | ✓ derive — from trajectories server-side, or in the frontend from data it already holds |
| Capacity violation spans | | ✓ trivial once the two above exist |

Honest scoping: the first cut can derive occupancy in the frontend from the
trajectory signals it already receives, with a declared resource list shipped as
Netz metadata. Nothing here needs a new algorithm; it needs a vocabulary.

## 5 · Allocation & accountability

- **Loop stage:** *monitor / assess*, never *act*. It is the evidence behind the
  Director's one decision, not the decision surface.
- **Owner (`allocation`):** the AI owns the plans being compared in Director and
  Recommendation; in Co-Learning one of the two branches is the human's.
- **Decision events emitted:** none of its own — a deliberate boundary. The
  decision record belongs to `strategy-options` (Director) / the recommendation
  accept-or-override (Recommendation).
- **Possible study instrument (optional, off by default):** which resource rows
  the operator pointed at before deciding is attention data, and would feed the
  same seam as
  [interaction-logging-plan.md](interaction-logging-plan.md). Flagged, not
  assumed — logging gaze-like proxies needs a consent decision, not a code
  decision.

## 6 · Acceptance scenario

Olten, the window from step 100 to 580 (the real fixture data, §9.2).

1. The operator is in Director. The running plan is under focus **A · minimise
   delay**. The row **Süd-Ost 59/13–14** shows a red band at steps 385–395: train
   h11 is leaving southbound while h15 is entering from the south, on a
   capacity-1 approach.
2. They preview focus **C · stability**. Three bars move: h15's approach slot
   shifts from 385–440 to 425–480, its platform call at Gleis 37/13 from 445–475
   to 485–515, and its onward eastbound slot from 540–560 to 560–580. The red band
   is gone.
3. The price is in the same picture, not in a separate KPI panel: h15's eastbound
   slot now ends *after* its arrival window of 560.
4. They commit focus C, or reject it because that window matters.

**Measurable success criterion:** shown the two focuses, an operator names (a) the
resource that stopped being contended and (b) the train that pays for it, without
opening another panel. Target ≥ 80 % correct on both parts across participants —
the honest test of whether "how do my inputs take effect" is answered by the
picture. Ties to **Q1** (behaviourally distinct modes: Director's supervision has
its own instrument) and **Q2** (calibrated trust: the cost of the AI's plan is
visible, not asserted).

## 7 · Effort & changes

**L overall** (>400k tokens / 3–5 days), decomposing into three parts that can
land separately:

| Part | Effort |
|---|:---:|
| The view itself (rendering, lanes, hover linkage, mode framing) | M |
| Resource registry + capacity as Netz metadata (backend + fixtures) | S–M |
| Occupancy derivation for both plan states | M |

Registration points (per
[widget-authoring-process.md](../reference/widget-authoring-process.md)):
`features/network-time-view/`, `panel-plugin-host` (`@switch` + `.ts`),
`layout-designer` palette, `panel-mode-availability.ts`,
`core/widgets/widget-catalog.ts`, and `features/view-tabs/center-views.ts` (it is
a centre view, so it belongs in the tab registry).

**Sequencing:** this comes *after* the two cheap items in
[mode-layouts-three-zones.md](mode-layouts-three-zones.md) §4 — the
"Was ändert sich" companion and the Fahrplan Δ column — which answer a thinner
version of the same question using data that already exists.

## 8 · Open questions / risks

1. **Occupancy width.** A fixture gives scheduled *times*, not occupancy
   *durations*. Real widths come from trajectories at runtime; for a *previewed*
   plan they come from the forward simulation. Widths for a plan that has not been
   simulated would have to be estimated — and an estimated bar next to a measured
   one is exactly the kind of quiet fiction the provenance rules exist to prevent.
   Draft: only ever draw simulated plans; no estimation.
2. **How many rows before it stops being readable?** Olten needs ~11 in a 480-step
   window. A larger station area could need 40. Filtering (only contended
   resources, only resources on a changed train's path) is then not a nicety.
3. **Row order.** Geographic order is meaningless without a line — that is the
   premise of this widget. Candidates: by contention, by first occupancy, grouped
   by station/approach. Probably operator-switchable, defaulting to grouped.
4. **Does it subsume B2?** If conflict ribbons are added here, a conflict-aware
   Marey may only be worth building for corridor scenarios. Decide when B2 comes
   up, not now — B2 has a UIX cross-model mandate this widget does not.
5. **Two colour conventions in one widget** (§3) is a real risk: grey/accent in
   Director, blue/yellow in Co-Learning. The alternative — blue/yellow everywhere
   — would claim human authorship for a plan the human did not write. Keeping two
   conventions is the lesser evil, but it must be visible in the legend.

## 9 · Worked examples

### 9.1 Corridor (the simple case)

Resources are the stations and the single-track sections along the line; the same
view degenerates gracefully to what a ZWL would show, because a corridor's
resources happen to be linearly ordered.

| Resource | Cap. | Focus A · minimise delay | Focus C · stability |
|---|:--:|---|---|
| Einspur WN–WAL | 1 | IR2401 18–34, RE4820 30–46 → **overlap 30–34** | RE4820 shifted to 50–66 |
| Bf Walenstadt | 2 | RE4820 22–30 | RE4820 22–**50** (holds) |
| Tunnel Murg | 1 | RE4820 48–60 | 68–80 |
| Bf Sargans | 3 | RE4820 62–74 | 82–94 |

One objective change, one conflict removed, one train ~20 steps later. Illustrative
numbers, not from a fixture.

### 9.2 Olten (the case that motivates the widget)

**From `backend/app/fixtures/olten/olten.pkl`, read 2026-09-07:** 60 × 35 grid,
518 track cells, 52 agents, `max_episode_steps` 1300, departures spread over steps
0–1140. 24 distinct waypoint cells. The platform cluster is row 37, columns 7–16;
the portals are row 0 cols 23–24 (north), row 59 cols 4–5 and 13–14 (south-west,
south-east), col 34 (east), col 0 (west).

The 14 trains departing between steps 60 and 420 — real handles and real
scheduled times:

| Handle | Start | `earliest_departure` | Call (row 37) | Target | `latest_arrival` |
|---|---|--:|---|---|--:|
| h5 | 37/13 | 100 | 37/13 @ 100 | 59/5 | 160 |
| h7 | 0/24 | 100 | 37/15 | 37/15 | 200 |
| h6 | 37/15 | 120 | 37/15 @ 120 | 59/14 | 160 |
| h10 | 21/34 | 140 | 37/13 @ 240 | 59/14 | 300 |
| h8 | 37/7 | 220 | 37/7 @ 220 | 49/0 | 300 |
| h9 | 37/14 | 240 | 37/14 @ 240 | 0/23 | 320 |
| h49 | 0/24 | 280 | — | 18/34 | 320 |
| h14 | 21/34 | 300 | 37/9 @ 400 | 37/9 | 420 |
| h11 | 37/16 | 320 | 37/16 @ 320 | 59/14 | 380 |
| h12 | 37/15 | 340 | 37/15 @ 340 | 0/23 | 440 |
| h13 | 59/4 | 340 | 37/11 @ 400 | 20/34 | 460 |
| h16 | 49/0 | 360 | 37/7 | 37/7 | 480 |
| h15 | 59/13 | 400 | 37/13 @ 460 | 20/34 | 560 |
| h17 | 21/34 | 400 | 37/9 | 37/9 | 480 |

Rows for this window: seven platform tracks (37/7, 37/9, 37/11, 37/13, 37/14,
37/15, 37/16) and five approaches (Nord, Süd-West, Süd-Ost, Ost, West) — **twelve
rows for fifty-two trains**, of which fourteen are in the window. That ratio is
the argument: the view's height is set by the infrastructure, the traffic only
makes the rows denser. The map scales the other way.

> **Provenance of the example.** Handles, start cells, target cells, departure and
> arrival times and the call cells are read from the fixture. The **bar widths**
> (occupancy durations), the **capacities**, the **grouping of cells into named
> resources** and the **focus-C plan** are constructed for the illustration —
> the fixture holds scheduled times, not occupancies, and no alternative plan.
> Whether h11 and h15 genuinely contend on the south-east approach depends on the
> section geometry, which was not evaluated.
