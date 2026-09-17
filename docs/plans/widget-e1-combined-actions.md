# Widget spec — `Combined Actions`

> Authored via `/create-widget`. Mirrors `docs/reference/widget-authoring-process.md`.
>
> **This spec now covers a family, not one widget.** Three catalog entries point
> here: `combined-actions` (E1, described below), `combined-actions-package` — the
> same T3.4 unit of interaction with a different interface answer, one package
> instead of three, preceded by a problem statement — and `problem-overview`, its
> layout companion. §1–§8 describe E1; the variants share its grounding (§1) and
> per-mode framing (§3) and differ in presentation. See the catalog entries for
> what each one does differently.

## 1. Identity
- **Name:** Combined Actions
- **`kind`:** `decision-support`
- **`granularity`:** `overview-detail` — three cards (overview) whose train
  sequence is editable in place (detail), without a dialog. One card is open at a
  time; the collapsed ones keep their headline and say what was changed about them.
- **Default zone:** `right` (a full-height column of its own; it started in
  `center` and moved after the review — see §2)
- **Panel `type`:** `combined-actions`
- **Catalog id:** new (`E1`)
- **Source(s):** [UIX] · [D3.4 adjustable autonomy] · [D2.3 action alternatives]
- **Grounding reference:**
  - **T3.4 / [`AI4REALNET/Tokener`](https://github.com/AI4REALNET/Tokener)** — a
    *coordinated multi-train* directive is the unit of interaction, not a
    per-train action. A "combined action" here is exactly a proposed **priority
    order** over the trains contending for the same resource, which is what the
    Hybrid (CBS+PP) approach negotiates.
  - **T2.3 / [`…T2.3_explaining_action_alternatives`](https://github.com/AI4REALNET/T2.3_explaining_action_alternatives)** —
    every alternative carries its **expected outcome** (Evaluative AI framing,
    `interaction-framework.md` §2), so the operator compares consequences, not labels.
  - **A3S / TraceRL colour convention** — human-influenced = blue
    (`--app-whatif-human`), AI-generated = orange (`--app-whatif-ai`). The AI ↔
    human distinction in this widget uses those existing tokens, not new colours.
  - Control-room practice: dispatchers reorder a **train priority list** at a
    bottleneck; the list is the artefact they argue about.
- **Source origin:** `Source: from-scratch, deliberately.` The prediction is an
  explicit **mock** (`core/combined-actions/impact-prediction.ts`) — see §8. The
  reuse target for the *real* version is the CBS/PP solver in
  [`AI4REALNET/flatland-blackbox`](https://github.com/AI4REALNET/flatland-blackbox)
  (the canonical source `Tokener` and `T3.4-with-HMI` both vendor): re-solving with a
  human-supplied priority order is precisely what PP does. The mock is written behind a
  swappable `ImpactPredictor` interface so that substitution is a provider swap.

## 2. Promise
> The operator can fork their own variant of an AI-proposed multi-train action by
> dragging its trains, and immediately see what that change costs or saves — in
> minutes, in kept transfers, and in the map and the ZWL.

Three things follow from the "immediately see" half, all of them added after the
first cut was reviewed:

- **Variants, not edits.** Dragging a train forks a **new version** beside the AI
  proposal instead of overwriting it, and the card then shows **both orders
  stacked and labelled** (`AI` / `YOU`) with a sentence naming the move — "You
  moved S8_214 1 place earlier, RE_18 1 place later." Position markers alone were
  not enough: a reader had to reconstruct the edit from four small arrows. The
  card then asks which version is kept.
- **Two axes, not one.** Every version carries **kept transfers** beside its delay
  saving, and a small plot puts every version of every package on the same plane,
  with an **arrow from each AI proposal to the dispatcher's variant of it** — the
  trade, in the direction it was made, spelled out underneath. A single "↓ 14 min"
  hides what those minutes cost.

  The second axis was **traction energy** in the first cut and was replaced
  (`c0227b6`). Flatland has no traction model, so energy was the one axis with no
  path from mock to simulation — it could only ever be authored. Kept transfers is
  the axis the project already measures: `connections` is one of the three
  Director dials, and the backend scores it in
  `goal_based_policies/connections.py`. The widget deliberately reuses the
  backend's semantics — a transfer is kept iff the feeder is at the station no
  later than the connector, and the break reason there is literally `reordered`.
  That is what makes it a genuine trade-off with delay rather than a second delay
  axis: **the thing that breaks a transfer is exactly the thing this widget lets
  the operator do.** Planned transfers are derived in
  `core/combined-actions/connections.ts` from the per-agent `stops` the session
  payload already carries, so no backend change was needed.
- **It has to fit its column without scrolling.** The panel lives in a ~430 px
  right-hand column whose body is capped at `min(50vh, 42rem)` by
  `panel-shell.component.scss`. Three open cards plus the plot came to 1220 px in
  a 509 px column — nothing was fully visible. So: one card is open at a time
  (the others keep a headline, and say what was changed about them), the plot sits behind
  a header toggle, and opening the plot folds every card, because comparing
  options and editing one are different jobs and the panel has height for one of
  them. Measured at 1440×960: 306 px idle, 389 px with a variant open, 479 px
  with the plot open — no scroll in any state.
- **The consequence lands in the other views.** Pointing at an action marks its
  trains on the **track map** with their dispatch rank and their share of the
  predicted change, and shifts their future lines in the **Marey / ZWL** along
  the time axis. A priority order changes *timing*, not topology — so the
  time-distance view carries the shift and the map carries the ordering. Drawing
  a reroute would be a lie.

## 3. Per-mode behaviour
Decision-Support framing is mode-dependent (Assessment ↔ Recommendation ↔ suppressed).

- **Recommendation (WP 3.1) — *Recommendation framing*.** Package A is badged
  **"Recommended by AI"** and sorted first; each card shows AI confidence. The
  operator may edit any sequence; after an edit the card reads
  **"Recommended by AI · Human modified"** and the recommendation badge is
  visually demoted (the modified sequence is *not* the AI's recommendation any
  more). `Apply` is enabled.
- **Co-Learning (WP 3.3) — *Assessment framing*.** No "Recommended" badge and no
  ranking: A/B/C are presented neutrally in authored order, each with its
  predicted impact as evidence. The edit → re-predict loop is the point of the
  widget here — the operator forms their own order and reads the consequence.
  The AI-vs-current comparison line is always shown once modified. `Apply` is enabled.
- **Director (WP 3.4) — *suppressed → supervisory read-only*.** Dispatch-altitude
  decision support is suppressed in Director (the objective is the human's lever,
  the trains are the AI's — see `strategy-options` in `panel-mode-matrix.md`).
  The widget therefore renders **read-only**: the package the AI is executing is
  marked "AI executing", chips are not draggable, `Apply`/`Reset` are hidden. It
  is a supervision surface, not an intervention surface.

## 4. System interaction
- **Data in** — `SessionStore.interactionMode()` (mode framing),
  `SessionStore.optionPresentation()` (recommended / neutral / none),
  `SessionStore.contentions()` (the live conflict forecast served by
  `backend/app/api/hmi.py`), and `SessionStore.agents()`. Names come from
  `TrainIdentityService.nameByHandle`, never from the roster directly — that is
  what makes a chip resolve to the same train as the map marker, the ZWL line and
  the timetable row.
- **Where the packages come from** — `buildPackages()` turns **one live
  contention group** into three orders over the trains actually contending, each
  with a rationale the operator can repeat: **A** by service weight
  (recommended), **B** by earliest scheduled arrival, **C** most-delayed first.
  Ties break by handle, so the same group always yields the same packages
  (Q2 · calibrated trust). If two orderings coincide, both cards stay and show the
  same figures — a card is never silently dropped and a difference is never
  fabricated. The authored `ACTION_PACKAGES` fixture remains for §6's walkthrough
  and `impact-prediction.spec.ts`; the panel no longer reads it.
- **What is still modelled** — the *impact*, not the inputs. `predictImpact()` is
  the deterministic mock; `transferOutcome()` derives kept transfers from the
  session's own timetable. The catalog says `dataSource: 'mixed'` for exactly that
  reason: real contention input, modelled prediction.
- **Actions out** — `setCombinedActionPreview()` (the consequence overlay the map
  and Marey draw) and `setAgentHoverAgents()` (the shared cross-view highlight),
  both cleared on destroy — the same discipline as `previewScenarioId` and
  `whatIfPreview`. `Apply` writes a decision record through
  `recordCoordinatedAction` — a purpose-made public seam, not the store's private
  `_appendDecision` — carrying both the AI order and the human variant. Nothing is
  sent to the simulation: no train is controlled.
- **Backend table:**

| Field / capability | Available now | To build (flagged) |
|--------------------|:-------------:|:------------------:|
| Deterministic impact per train order (mock) | ✓ | |
| Mode framing (`interactionMode`, `optionPresentation`) | ✓ | |
| Cross-view consequence overlay (`combinedActionPreview`) | ✓ | |
| Per-train delay share + dispatch rank (derived, mock) | ✓ | |
| Kept transfers per order (derived from the session timetable) | ✓ | |
| Packages derived from live contentions | ✓ | |
| One train identity across map, ZWL, timetable and actions | ✓ | |
| Decision-log record per applied action (`recordCoordinatedAction`) | ✓ | |
| Real re-solve of a human priority order (PP/CBS, `flatland-blackbox`) | | ✓ flagged |
| Transfers scored by the backend instead of re-derived in the frontend | | ✓ flagged |
| `Apply` actually committing the order to the planner | | ✓ flagged |

## 5. Allocation & accountability touchpoints
- **Loop stage:** decision
- **Owner per mode (`allocation`):** Recommendation → *shared* (AI proposes, human
  disposes) · Co-Learning → *human* · Director → *ai* (read-only supervision).
- **Decision events emitted:** `Apply` records one coordinated action via
  `recordCoordinatedAction`, carrying **both** the AI order and the human variant
  on a single record. One record per action, not one per train: the unit the
  operator decided about is the order, and four per-train entries would lose the
  fact that they were decided together (D3.1 §3 — "structured, traceable decision
  records").

## 6. Acceptance scenario
1. Operator opens Combined Actions in **Recommendation** mode. Card A reads
   *Recommended by AI*, `IC_703 → ICE_42 → RE_18 → S8_214`, `↓ 14 min delay`, confidence *High*.
2. They drag `ICE_42` left of `IC_703`. An insertion marker shows where it lands.
3. On drop the chips reorder immediately, the header gains *· Human modified*, and
   the metric shows `Updating prediction…` for ~450 ms.
4. The card forks **Variant 1**: the header gains *· Human modified*, the moved
   trains get ▲/▼ markers, the metric shows `Updating prediction…` and settles at
   `↓ 9 min` with `14 → 9 min` and the AI-vs-current comparison beside it.
5. A **Keep** row appears with both versions and their figures
   (delay saved and transfers kept per version); the trade-off plot gains a blue
   `A′` dot beside the orange `A`.
6. Pointing at the card marks its trains on the map with ranks 1–4 and their
   per-train minutes, and shifts their ZWL lines along the time axis.
7. `AI order` shows the AI proposal again **without discarding Variant 1**;
   `Apply` confirms which version was applied.

**Measurable success criterion (Q1 · distinct modes, Q3 · accountability):** in a
walkthrough, a participant can state, without prompting, (a) which of the two
versions on screen is the AI's and which is theirs, (b) the cost of their change
in minutes *and* in kept transfers, and (c) which trains it moves and how —
within 5 s of the prediction settling. And: the same order always
yields the same number (Q2 · calibrated trust — a prediction that jitters is not
trustable), verifiable by reset → re-apply the same edit.

## 7. Effort & changes
- **Effort:** M
- **Files / seams to touch:**
  - `core/combined-actions/{action-packages,impact-prediction,impact-prediction.service}.ts`
  - `features/combined-actions/combined-actions.component.{ts,html,scss}`
  - `features/combined-actions/components/{action-card,train-sequence,train-chip,impact-metrics}/…`
  - Seams 1–5 of `registration-checklist.md` (not 6 — palette-only for now).
  - `docs/reference/panel-mode-matrix.md`, `docs/plans/widget-catalog.md`.

## 8. Open questions / risks
- **Building the predictor from scratch is a deliberate decision, not an omission.**
  The user's brief specifies a mocked deterministic prediction for the first
  version, and the widget's purpose is the *interaction* (human edits a
  coordinated action → system re-evaluates), not the optimiser. The consortium
  reuse target is named in §1 (`flatland-blackbox` PP/CBS via `Tokener`);
  `ImpactPredictor` exists precisely so that swap is a one-line provider change.
  Until then the widget is badged `dataSource: 'mock'` in the gallery so a study
  operator can never mistake it for simulation output.
- The seeded orders (§ brief) are authored, not measured. If this widget is used
  in a study before the real solver lands, the numbers must be described to
  participants as illustrative.
- **Stufe 1 (landed 2026-08-27): packages now come from live conflicts, figures
  still from the deterministic model.** The backend runs a no-override forecast
  branch (`TrajectoryBranchRunner.run_branch(overrides={})`) and returns the
  multi-agent contentions ahead at `GET /{session_id}/hmi/contentions`; the
  panel builds its three packages from the most-urgent group's handles via
  `buildPackages`. `dataSource` stays `'mock'` because the impact figures are
  still modelled — only the package *contents* (which trains, in which order)
  became real. Three design decisions worth recording:
  - **Path-overlap contenders, not adjacency.** The conflict detector's
    `_detect_blocked` was a stub (`pass`); filling it with position-adjacency
    blockers was insufficient for the PF–CH case, where the three trains freeze
    ~25 cells apart on a shared single-track segment and never become
    face-to-face within the forecast horizon. A blocked event's `agents` is
    therefore the stopped train plus every on-map train whose remaining
    shortest path (distance-map gradient) shares a cell with its — the
    contention set, not just the train in the next cell. This is detection,
    not a solver (no scheduling/optimisation); the real PP/CBS re-solve stays
    flagged. Trade-off: on large nets path-overlap is broad (many trains share
    a mainline), so a queue group can name 15 trains — see the cap below.
  - **Group by shared handle, not by position.** The brief said "merge
    conflicts that share a position"; with multi-agent events at different
    positions that would emit duplicate groups, so the endpoint merges by
    handle-connected-components (union-find) — the correct generalisation of
    the brief's intent (one group per contention).
  - **Presentation cap to 4 trains.** A broad contention group (15 trains on
    the Guided-Demo net) would break the panel and is not the interaction the
    widget supports. The frontend caps the most-urgent group to the 4
    most-delayed trains — real handles from the contention, no phantoms
    introduced by the cap. PF–CH (3 trains) is under the cap and unaffected.
    Open: a tighter contention notion (same-cell-same-time rather than
    any-path-overlap) would make the cap unnecessary — deferred to Stufe 2
    alongside the real solver, which produces the contention set directly.
- Trains are fixture ids (`IC_703`, `ICE_42`, …). They are **bound** onto the
  session's handles in `ALL_TRAINS` order purely so the overlay can point at
  something — the binding is an alias ("IC_703 is train 0"), not a claim that the
  session contains those services. Chips stay typed by train **category** rather
  than by `AgentColorService`. Packages derived from live conflicts remain the
  flagged extension.
- The catalog declarations were corrected alongside this spec, after they drifted
  behind the code: E1 is `dataSource: 'mixed'` (packages built from live
  contention groups, impact figures still modelled) and `writes: 'record'`
  (`Apply` writes through `recordCoordinatedAction`). The package variant is
  `writes: 'record'` too — same seam — but stays `dataSource: 'mock'`, because its
  conflict window really is a fixture. `problem-overview` is read-only and
  unchanged.
- The per-train split is a **decomposition of the mock**, not a second model: the
  package's net gain is shared equally and each train's own move is priced at
  `MINUTES_PER_POSITION`, so the parts sum to the headline. `MINUTES_PER_STEP = 1`
  is the demo's step↔minute convention, in one place.
- **A package can be dominated on both plotted axes** and still be the right
  call — the plot has two axes and dispatching has more. With the packages now
  built from live contentions (A by service weight, B by scheduled arrival, C by
  delay), the rationale line on each card is what carries the objective the plot
  does not show. If the plot is used in a study, say that out loud, or a
  dominated card reads as simply bad.
- Reordering is built on **pointer events**, not the native HTML5 drag-and-drop
  that `layout-designer` uses. HTML5 DnD does not fire for touch at all, its drag
  image cannot show the chip sliding between its neighbours, and it cannot be
  driven by synthetic input — so it could not be verified end to end. Pointer
  events cover mouse, touch and pen through one path, and were verified with a
  real mouse drag and a simulated touch drag in the running app. Keyboard
  reordering (`←`/`→` on a focused chip) is the accessible path.
- The widget needs roughly the full window width to keep sequence and impact on
  one line, so it ships with a layout of its own: the `Combined Actions · Demo`
  preset in [`core/layout/layout-presets.ts`](../../frontend/src/app/core/layout/layout-presets.ts),
  selectable in the start screen's Layout dropdown. It is the only two-row preset.
- **Two different things are both called "horizon", and only one of them is the
  Q2 risk.** Distinguished 2026-08-28 while surfacing the contentions lookahead,
  because conflating them would have erased a feature:
  - **Compute budgets** — how far a forecast *looks ahead*: the contentions
    endpoint's `_CONTENTION_MAX_STEPS = 50` and Learning Moments'
    simulate-to-episode-end are budgets, chosen for cost (one `run_branch` call
    stays cheap). These are the surfaces that *can* show different numbers for
    the same conflict, because they look different distances ahead.
  - **A reliability statement** — how far a forecast is *worth trusting*:
    `strategy-forecast.horizonMinutes` (0/10/20/30) shrinks with system load on
    purpose, so the far columns turn 'unknown' instead of pretending to know.
    That shrinking is an honest limit, not a budget.
  Pulling these onto one constant would erase the reliability feature, so the
  Q2 fix is *not* "one horizon repo-wide." It is: surface each surface's own
  horizon on its panel, in one shared unit. Landed: the contentions endpoint
  returns its budget as `horizonSteps` (always present, even with no contention),
  and the panel renders it in minutes via the shared
  `MINUTES_PER_STEP = 1` convention (`combined-actions-preview.ts:26` — the
  single place steps and minutes meet; no second constant). The
  load-shrinking `horizonMinutes` stays separate because it is a different kind
  of number. **Still open:** whether the *budgets* should be pinned to one
  value or left per-surface — deferred until Learning Moments lands on
  `explore_db`, at which point the two budget surfaces actually coexist and the
  trade-off is real. Deciding it now would be premature; deciding it later is
  one line, because the shared convention already makes the two budgets
  comparable.
- **`tests/test_conflict_detector.py` does not specify the detector, and looked
  like it did.** Found 2026-08-27 while briefing the live-conflicts work: all six
  `_detect_*` methods in `ConflictDetectionCallbacks` were empty `pass` stubs
  ("filled in Part 2/3"), so `get_conflicts()` always returned `[]` — yet the test
  file reported green. Verified by running it: `test_blocked_threshold_emits_event`
  *skipped*, and its skip message blamed Flatland ("agents may not be in STOPPED
  state under STOP_MOVING in this seed") rather than the missing implementation;
  `test_blocked_emitted_only_once_per_streak` and
  `test_agent_done_emitted_once_per_agent` *passed vacuously*, because "at most one
  event" is trivially true of zero events. The stubs were filled by the
  live-conflicts task above, but the test file's shape outlives that fix: it asserts
  structure (`info["consecutive_stops"]`, one event per streak) and never that an
  event is produced at all. Anything built on `get_conflicts()` needs its own
  assertions that a known contention actually emits — and a skip whose message
  names an external cause deserves suspicion before it is believed.
- **The contention window is far wider than a bottleneck, and `headway` inherits
  that.** The window is the path overlap that defined the contention in the
  first place — consistent with `_contenders` by design, so that no train can be
  in a group without appearing in its window. But on `pf-ch-corridor-stops` the
  remaining paths of twelve trains overlap across **158 cells**, roughly the
  corridor itself. `headway` is then "steps spent anywhere in half the network",
  not "occupancy of the contended resource": one train reports 50, the entire
  forecast horizon. For the queue model that consumes these figures
  (`combined-actions-package`, `delay_k = max(0, entryDelay_k + Σ headway_before_k
  − slack_k)`) that is too coarse to price a wait. Narrowing it means narrowing
  the *contender* definition too — the two must keep the same criterion — so it
  is one decision, not two: either contenders stay path-overlap and `headway`
  is renamed to what it measures, or both move to a bottleneck definition and
  the PF–CH case (trains ~25 cells apart, never face-to-face inside the horizon)
  has to be caught another way. Recorded rather than patched, because picking
  one changes which trains a package names.
