# Widget spec — `Combined Actions`

> Authored via `/create-widget`. Mirrors `docs/reference/widget-authoring-process.md`.

## 1. Identity
- **Name:** Combined Actions
- **`kind`:** `decision-support`
- **`granularity`:** `overview-detail` — three compact cards (overview) whose train
  sequence is editable in place (detail), without a dialog.
- **Default zone:** `center`
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
> minutes, in energy, and in the map and the ZWL.

Three things follow from the "immediately see" half, all of them added after the
first cut was reviewed:

- **Variants, not edits.** Dragging a train forks a **new version** beside the AI
  proposal instead of overwriting it, and the card then shows **both orders
  stacked and labelled** (`AI` / `YOU`) with a sentence naming the move — "You
  moved S8_214 1 place earlier, RE_18 1 place later." Position markers alone were
  not enough: a reader had to reconstruct the edit from four small arrows. The
  card then asks which version is kept.
- **Two axes, not one.** Every version carries a predicted **energy** cost beside
  its delay saving, and a small energy-vs-delay plot puts every version of every
  package on the same plane, with an **arrow from each AI proposal to the
  dispatcher's variant of it** — the trade, in the direction it was made, spelled
  out underneath ("1 min less delay saved, 5 kWh more energy"). A single
  "↓ 14 min" hides what those minutes cost: holding a heavy ICE back buys delay
  and pays for it in traction energy.
- **It has to fit its column without scrolling.** The panel lives in a ~430 px
  right-hand column whose body is capped at `min(50vh, 42rem)` by
  `panel-shell.component.scss`. Three open cards plus the plot came to 1220 px in
  a 509 px column — nothing was fully visible. So: one card is open at a time
  (the others keep a headline `↓ 11 min · 302 kWh`), the trade-off plot is behind
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
  `SessionStore.optionPresentation()` (recommended / neutral / none), and
  `SessionStore.agents()` — only to **bind** the fixture service names onto the
  session's real train handles, in the fixed order of `ALL_TRAINS`, so the
  overlay has something to point at. Train sequences and impacts come from
  `core/combined-actions/action-packages.ts` (authored fixtures) +
  `predictImpact()` (deterministic mock) — `dataSource: 'mock'`. Trains beyond
  the session's agent count stay unbound and take no part in the overlay.
- **Actions out** — `setCombinedActionPreview()` (the consequence overlay the map
  and Marey draw) and `setAgentHoverAgents()` (the shared cross-view highlight),
  both cleared on destroy — the same discipline as `previewScenarioId` and
  `whatIfPreview`. Nothing is sent to the simulation: `Apply` sets a local
  confirmation naming the applied version; no train is controlled.
- **Backend table:**

| Field / capability | Available now | To build (flagged) |
|--------------------|:-------------:|:------------------:|
| Deterministic impact per train order (mock) | ✓ | |
| Mode framing (`interactionMode`, `optionPresentation`) | ✓ | |
| Cross-view consequence overlay (`combinedActionPreview`) | ✓ | |
| Per-train delay share + dispatch rank (derived, mock) | ✓ | |
| Predicted traction energy per order (modelled, mock) | ✓ | |
| Real re-solve of a human priority order (PP/CBS, `flatland-blackbox`) | | ✓ flagged |
| Measured energy KPI (backend folds energy into delay today) | | ✓ flagged |
| Packages derived from live conflicts instead of fixtures | | ✓ flagged |
| `Apply` actually committing the order to the planner | | ✓ flagged |
| Decision-log entry per applied/modified package | | ✓ flagged (store's `_appendDecision` is private; no public seam yet) |

## 5. Allocation & accountability touchpoints
- **Loop stage:** decision
- **Owner per mode (`allocation`):** Recommendation → *shared* (AI proposes, human
  disposes) · Co-Learning → *human* · Director → *ai* (read-only supervision).
- **Decision events emitted:** none in this first cut. The widget keeps the
  AI-original vs human-current distinction in its own state so a later
  decision-log seam can record `action: 'override'` with both orders and both
  predicted impacts. Flagged in §4 rather than faked.

## 6. Acceptance scenario
1. Operator opens Combined Actions in **Recommendation** mode. Card A reads
   *Recommended by AI*, `IC_703 → ICE_42 → RE_18 → S8_214`, `↓ 14 min delay`, confidence *High*.
2. They drag `ICE_42` left of `IC_703`. An insertion marker shows where it lands.
3. On drop the chips reorder immediately, the header gains *· Human modified*, and
   the metric shows `Updating prediction…` for ~450 ms.
4. The card forks **Variant 1**: the header gains *· Human modified*, the moved
   trains get ▲/▼ markers, the metric shows `Updating prediction…` and settles at
   `↓ 9 min` with `14 → 9 min` and `AI −14 min · Current −9 min · −8 kWh`.
5. A **Keep** row appears with both versions and their figures
   (`AI −14′ 244 kWh` · `Variant 1 −9′ 236 kWh`); the energy-vs-delay plot gains
   a blue `A′` dot left of and above the orange `A`.
6. Pointing at the card marks its trains on the map with ranks 1–4 and their
   per-train minutes, and shifts their ZWL lines along the time axis.
7. `AI order` shows the AI proposal again **without discarding Variant 1**;
   `Apply` confirms which version was applied.

**Measurable success criterion (Q1 · distinct modes, Q3 · accountability):** in a
walkthrough, a participant can state, without prompting, (a) which of the two
versions on screen is the AI's and which is theirs, (b) the minute *and* energy
cost of their change, and (c) which trains it moves and in which direction —
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
- Trains are fixture ids (`IC_703`, `ICE_42`, …). They are **bound** onto the
  session's handles in `ALL_TRAINS` order purely so the overlay can point at
  something — the binding is an alias ("IC_703 is train 0"), not a claim that the
  session contains those services. Chips stay typed by train **category** rather
  than by `AgentColorService`. Packages derived from live conflicts remain the
  flagged extension.
- The per-train split is a **decomposition of the mock**, not a second model: the
  package's net gain is shared equally and each train's own move is priced at
  `MINUTES_PER_POSITION`, so the parts sum to the headline. `MINUTES_PER_STEP = 1`
  is the demo's step↔minute convention, in one place.
- **Action B is dominated** on the energy-vs-delay plane (it saves less delay
  *and* costs more energy than A, because it holds ICE_42 to last). That is not a
  modelling slip — B's authored purpose is to protect a cross-border connection,
  an objective this plot does not have an axis for. If the plot is used in a
  study, that third axis has to be said out loud or B will read as a bad option.
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
- **The forecast horizon is not yet one decision, and it has to become one.**
  Three surfaces will forecast the same contention over three different spans:
  the contentions endpoint from
  [`widget-e1-live-conflicts-prompt.md`](widget-e1-live-conflicts-prompt.md) caps
  `run_branch` at 50 steps; the alternative Combined Actions variant carries its
  own `horizonMinutes` per conflict window; Learning Moments
  (`backend/app/core/learning_moments.py`, `roman/director-strategies-shift-review`)
  simulates **to the end of the episode**, at a measured 3–4 s per branch.
  The same conflict can therefore show different numbers in two panels on one
  screen, for a reason the operator cannot see. That is a direct hit on Q2
  (calibrated trust) — a figure that changes with an invisible parameter is not
  a figure anyone can learn to rely on. The horizon has to be one named, shared
  parameter, surfaced wherever a forecast figure is: either pinned repo-wide, or
  per scenario and then stated on the panel. Deciding it is a prerequisite for
  using any two of these surfaces together in a study, not a polish item.
