# Flatland Dispatcher — UI Widget Synthesis (cross-model)

> Synthesis of a multi-model brainstorm (OpenRouter, Jun 2026) on how to evolve
> the Flatland Dispatcher interface. **Front half = build-first shortlist mapped
> to our codebase** (for Claude Code). **Back half = full catalog** of every
> distinct idea with its grounding reference and which models proposed it.
>
> Models that produced substantive answers: **GPT-5.5-pro, Gemini Pro, Claude
> Opus 4.8, Grok 4.3, Mistral-medium-3.5, Qwen3.7-plus** (6), plus a later
> retry of **Perplexity Sonar deep-research** (web-grounded, with named standards
> — see "Sonar / named grounding" below).
> Empty/failed on the first run: qwen3.7-max, sonar (retried OK), deepseek-v4-pro.
>
> Companion docs: `docs/interaction-modes-brief.md` (mode behaviour) and
> `docs/reference/ui-exploration-prompt.md` (the prompt that generated these).

---

## The one big signal: strong convergence

Six independent models, different labs, **proposed the same handful of ideas**.
The more models that landed on an idea independently, the more robust the bet.
The headline numbers (out of 6):

| Idea cluster | Region | Convergence | Effort |
|---|---|---:|---|
| Conflict / headway **ribbons on the Marey** | Center | 6/6 | M |
| **Predicted-vs-actual ("ghost") overlay** | Center | 6/6 | S–M |
| **Triage notifications by time-to-act** + lead-time bars | Left | 6/6 | S–M |
| **Honest AI uncertainty** (fan/variance, not bare %) | Right | 6/6 | M–L |
| **Small-multiple mini-Mareys** for policy/what-if compare | Right | 6/6 | M |
| **Demote/replace the geographic map** with a topology view | Center | 6/6 (contrarian!) | L |
| Root-cause **alert grouping / incident bundles** | Left | 5/6 | M |
| **Trade-off frontier / Pareto / radar** of KPIs | Right | 5/6 | S–M |
| **Consequence-first recommendation card** + trivial override | Right | 4/6 | M |
| **Alarm shelving / lifecycle** (ack, shelve, escalate) | Left | 4/6 | S |
| **Explain-the-alert** (causal chain from the sim) | Left | 4/6 | M |
| **Map↔Marey brushing-and-linking** | Center | 4/6 | S |
| **Trust-calibration ledger** (AI right lately?) | Left | 4/6 | S |
| **Autonomy contract / directive controls** (Director) | Right | 4/6 | M |
| Bottleneck / congestion strip or heatmap | Center | 4/6 | M |

The contrarian line is the surprise: **every model independently said the
top-down grid map is the weakest view** for an abstract, non-geographic Flatland,
and should be demoted in favour of a topology/time view. That's worth a real
experiment (see §"Contrarian consensus").

---

## Build-first shortlist (for Claude Code)

Five widgets, ranked by impact-to-effort, each mapped to the files/data we already
have. These reuse existing infrastructure rather than adding new dashboards.

### 1. Conflict-aware Marey — ribbons + predicted lines + plan-vs-actual ⭐ (6/6)
Turn the Marey from a replay into a **predictive conflict instrument**.
- **What:** keep solid actual stringlines; add per-train dashed **forward
  projection** to target, a faint **headway/occupancy ribbon** around each line,
  and a red **conflict marker** where two projected paths overlap before clearing.
  Optionally a faint **plan line** (earliest-departure → latest-arrival) so the
  delay gap is visible in place.
- **Maps to:** `features/marey-chart/` + `features/graphic-timetable/`. Data:
  `AgentDTO.{position,speed,next_decision,delay,earliest_departure,latest_arrival,
  eta_to_depart,time_to_deadline}`, `SessionStore.trajectories`, and predicted
  conflicts from backend `core/conflict_detector.py` (already exists). Mode
  framing via the proposed `optionPresentation` (brief §3.1); what-if branches
  use the **blue=human / yellow=AI** convention (brief §3.3).
- **Effort:** M. Riskiest unknown: a stable track-position ordering for arbitrary
  Flatland topology (loops/branches), and projection accuracy — wrong dashed
  lines erode trust, so fade them with horizon distance.

### 2. Triage'd notification column — sort by "act now", lead-time bars, grouping ⭐ (6/6 + 5/6)
The notifications column is today's weakest link (flat, chronological).
- **What:** re-sort alerts by **time-to-act** (not arrival order); each row gets a
  draining **lead-time bar**; cluster alerts that share a root cause into one
  **incident bundle** ("Train 14 blocks 4 trains at (9,27)"); add **shelve /
  acknowledge** with an auto-unshelve timer (never silently drop a red alert).
- **Maps to:** `features/notifications-panel/` + backend
  `core/notification_manager.py` and `conflict_detector.py`. Data: predicted
  conflicts, `malfunction_remaining`, `time_to_deadline`, blocker→blocked
  relations. Hover→highlight already exists (`notificationHoverHandles`).
- **Effort:** S–M. Mostly information design over data we already have. Riskiest
  unknown: a trustworthy per-alert "time-to-act" estimate; transparent priority
  scoring so operators don't feel alerts are hidden.
- **Grounding:** ISA-18.2 / EEMUA 191 alarm management, aviation EICAS ordering.

### 3. Consequence-first recommendation card + honest uncertainty ⭐ (4/6 + 6/6)
Make "accept vs override" fast, informed, reversible — the core teaming control.
- **What:** for the selected decision, show options as rows (Hold / Proceed /
  Reroute) with their **predicted KPI consequence** and an **outcome spread**
  (fan/whiskers), not a bare confidence %. Equal-weight Accept / Modify / Reject;
  override always one click.
- **Maps to:** `features/recommendations-panel/` + `agent-inspector`
  (`next_decision.options`). **We already have a strong hook:** backend
  `api/overrides.py` computes before/after deadlock & arrival impact of an
  override — surface that as the per-option consequence. Honest-uncertainty
  variant needs multiple rollouts (backend `scenario_runner`); if unavailable,
  show **empirical spread**, never a fake number. Mode-aware via
  `optionPresentation` (recommended / neutral / none).
- **Effort:** M. Directly serves all three modes (brief §3.1, §3.3, §4).
- **Grounding:** TCAS resolution advisories, MCDA tables, Endsley automation
  transparency, Bank-of-England fan charts.

### 4. Scenario small-multiples + trade-off frontier (right column) (6/6 + 5/6)
Compare policies by the **shape of the future**, not four raw numbers.
- **What:** replace/augment the policy cards with tiny **mini-Marey thumbnails**
  per policy/what-if branch (same time/track scale, conflict marks), plus a small
  **Pareto/trade-off plot** (delay × deadlocks, point = policy) so "better" is
  visible, not arithmetic.
- **Maps to:** `features/scenario-panel/` — it **already** computes per-scenario
  trajectories and `ScenarioKpis` (`kpiDeltas`, `score`, `rankedScenarios`,
  `kpiScore`). This is mostly a rendering change: draw the trajectories it already
  has as small stringlines; scatter the KPIs it already has. Co-Learning: human
  branch blue, AI yellow.
- **Effort:** M (mini-Mareys) / S–M (frontier). Riskiest unknown: rollout latency
  and legibility of dense trajectories in the narrow column.
- **Grounding:** Tufte small multiples; Pareto fronts / multi-objective optimisation.

### 5. Map↔Marey brushing bridge (cheap glue, high payoff) (4/6)
- **What:** one shared selection + time-brush across map and Marey: select a
  train/conflict/time-window in either view, the other echoes it; brushing a time
  window dims unrelated agents.
- **Maps to:** `SessionStore` already has `selectedHandle`,
  `notificationHoverHandles`, `previewScenarioId` — add a `brushedTimeRange`
  signal both center views subscribe to. Mostly wiring.
- **Effort:** S. Riskiest unknown: synced re-render performance on Canvas at play
  speed (respect the existing throttling rationale — brief §6).
- **Grounding:** brushing-and-linking (Becker & Cleveland), linked mission-ops consoles.

> These five turn the **two existing center views into a predictive, linked
> decision surface**, fix the **notification overload**, and make the **AI honest
> and comparable** — using data and components we already have. Start here.

---

## Contrarian consensus — demote the geographic map (6/6)

All six models, unprompted, argued the **top-down grid map is the lowest-value
view** for an abstract Flatland that has no real geography, and proposed
replacing/demoting it. They differ only in the replacement:

- **Resource-reservation board** (GPT-5.5-pro): critical switches/corridors as
  rows, future steps as columns, trains as reservation blocks; conflicts are
  literal overlaps. Borrows from interlocking route-locking & runway-slot boards.
- **Time-scaled network graph** (Gemini): stations/switches as nodes, edges whose
  length = traversal time; delayed train stretches its edge; deadlocks look like
  knots. Borrows from Beck's schematic + graph fisheye (Furnas).
- **Conflict-aware stringline primary + on-demand fisheye map inset** (Opus):
  make the Marey full-height; the map shrinks to a focus+context inset around the
  selected conflict only.
- **Conflict-flow Sankey** (Grok): grid collapsed into track-section bands, flow
  ribbons width=train count, hue=delay.
- **4D space-time view** (Mistral): X/Y grid + Z time; trains are tubes,
  conflicts are tube intersections; the current map is just a time-slice.
- **Phase-space risk plane** (Sonar): drop physical position entirely; plot each
  train as a point in (slack/time-to-deadline × predicted conflict-risk),
  colour=delay. The "low slack, high risk" quadrant is where attention goes.
  *Grounding:* operations-research phase-space plots, abstract risk dashboards.
  (Closest to a live-train version of the Pareto idea — cheap, supervisory.)

**Recommendation:** don't rip out the map — it's the trust anchor for novices.
But this is a genuine AI4REALNET research question: build **one** topology/
reservation alternative as a *toggleable* center view (reuse the view-toggle
pattern next to Map/Marey) and validate with eye-tracking on where dispatchers
actually look during conflict resolution. High effort (L), high learning value.

---

## Verified references & use-case scenarios (round 3)

A follow-up round asked Opus, Gemini, Grok (closed) and Qwen, Mistral (open) to
add **named, checkable references** and a **concrete dispatching walkthrough** to
their top-3 widgets, with an explicit instruction to flag uncertain citations
rather than invent them. (GPT-5.5-pro and DeepSeek returned empty this round.)
Notably **Opus and Qwen actually verified/flagged their sources** — Opus
confirmed each against a source and down-graded ISA-18.2 to "standard-level only";
Qwen correctly noted EEMUA is a process/electricity standard, not rail.

### Citation-ready reference list (vetted)

**Strong / named with edition or DOI:**
- **UIC Code 406 "Capacity"** (4th ed., 2013) — blocking-time / consumed-capacity
  method; basis for conflict detection. *(conflict ribbons, predicted overlay)*
- **Pachl, _Railway Operation and Control_** (3rd ed., 2018) — the **blocking-time
  stairway**; overlapping stairways = train-path conflict. *(Opus-verified)*
- **Hauptmann (2006), _Analytical Capacity Management with Blocking Times_** — DOI
  10.24355/dbbs.084-200611210100-0. *(Opus-verified)*
- **EEMUA 191, _Alarm Systems_** (4th ed., 2024; App. 3 **"Time to Consequence
  (TTC)"**, shelving, flood mitigation). ⚠️ origin is process/electricity industry
  — transfer the *principle* to rail, don't imply it's a rail standard.
- **ISA-18.2 / IEC 62682, _Management of Alarm Systems_** — shelving,
  rationalisation. Cite at **standard level** (clause numbers unverified).
- **Stephen Few — bullet graph:** _Information Dashboard Design_ (2006) + Bullet
  Graph Design Spec (Perceptual Edge, 2013). *(Opus-verified)*
- **Tufte:** _Envisioning Information_ (1990, small multiples/layering);
  _Beautiful Evidence_ (2006, sparklines).
- **Human-AI teaming:** Endsley (1995, situation awareness); Parasuraman,
  Sheridan & Wickens (2000, levels of automation); Parasuraman & Riley (1997,
  "Humans and Automation").
- **Kale et al. (2019, CHI / PLOS ONE)** — Hypothetical Outcome Plots ("fan of
  futures"). *(what-if branch / uncertainty)*
- **Aviation:** TCAS / FAA AC 120-55C — Tau (time-to-closest-approach);
  **ETCS Level 3 / ERTMS** Movement Authority (moving block); **Eurocontrol MTCD**
  trajectory look-ahead; ECMWF ensemble "postage-stamp" plots.
- **SBB RCS-Dispo** — see the named-grounding links below.

**⚠️ Verify before citing (possibly garbled / unverified specifics):**
- "D'Ariano & Prague, 2009" (Mistral) — almost certainly a garbled
  **D'Ariano & Pranzo** (real alternative-graph conflict-detection work). Check
  author/year before use.
- "Ericsson AXE-10 alarm shelving" and "SBB RCS-Dispo shows policy trade-offs in a
  matrix" (Mistral) — specific claims unverified; treat as illustrative, not citable.
- DB Netz Soll/Ist Bildfahrplan overlay (Qwen) — practice is real, but there's no
  single citable standard for the *overlay* convention.

### Use-case walkthroughs = ready-made acceptance scenarios
These concrete scenarios (consolidated from the round) double as **test/acceptance
criteria** for Claude Code — each states the measurable win:

- **Conflict-aware Marey:** step ~118, Train 11 routes toward malfunctioning Train
  14 at (9,27); red ✕ appears at ~step 130 *inside* Train 14's occupied block →
  hold Train 11 one block back → converts a 2-train deadlock into an ~11-step hold
  → **+1 arrival, −1 deadlock**.
- **Triage + grouping:** step 40, HIGH Train 11 ("reaches in 1") is buried below
  three MEDIUM cards; re-sort by Time-to-Consequence + collapse 4 alerts into
  "Train 14 blocking 4 trains at (9,27)" → act on root cause + Train 11 first →
  **−1 to −4 deadlocks**, fewer wasted decision-steps.
- **Bullet-bar policy + honest rec:** step 5, DLA vs Shortest-Path both show "12
  deadlocks"; bullet bars + reject-cost "+4 deadlocks" → keep DLA → **avoids +4
  deadlocks** a delay-only read would have caused.
- **Moving-block ribbons:** step 40, AI recommends routing Train 14 head-on into
  Train 11's corridor; overlapping green/yellow ribbons at (9,27) → reject → averts
  head-on gridlock (2 agents saved).
- **Small-multiple mini-Mareys:** step 200 (Director), Shortest-Path and DLA both
  read "0 deadlocks", but SP's thumbnail shows lines bunched at 2-step margins vs
  DLA's 10-step margins → pick DLA → survives a step-210 malfunction that would
  otherwise cascade (**4 arrivals vs 4 locked**).
- **What-if branch timeline (Co-Learning):** step 22, "Hold" (yellow) shows a
  confident narrow convergence vs "Reroute" (blue) thick/uncertain → pick the
  counter-intuitive Hold → resolves in 22 vs 28 steps and **builds calibrated trust**
  (the number-only view would have pushed Reroute).

---

## Fusion review (GPT-5.5-pro meta-analysis) — corrections & build-readiness gaps

GPT-5.5-pro was re-run not for more ideas but as a **critical fusion layer**: it
analysed Opus + GPT + Gemini against each other and surfaced consensus,
contradictions, and blind spots. This is the verification pass the idea rounds
lacked — treat it as the "before you build" checklist.

### Citation & claim corrections (apply these)
- **Misattributed paper:** "_Railway operations, timetabling and control_ (2013)"
  is by **Marinov, Şahin, Ricci & Vasic-Franklin — NOT Corman.** Corman has
  separate 2010–2013 rescheduling / bi-objective conflict papers; cite those if
  you mean Corman. (One model had this wrong.)
- **Don't overclaim ETCS/CBTC as the UI basis:** ETCS Level 3 / CBTC / IEEE
  1474.1 ground train *separation and headway*, **not** a prescribed dispatcher
  visualisation. The direct grounding for the Marey widget is **Marey/Ibry train
  graphs + Hansen/Pachl blocking-time theory** (and resource-occupation diagrams).
- **EEMUA/Honeywell overstated:** EEMUA 191 *guides* grouping/suppression/flood
  control — it does not "mandate" suppression. "Honeywell Experion time-to-
  consequence shelving" is overstated; Experion supports shelving + dynamic
  suppression, but not that specific claim.
- **Use the Train 14 @ (9,27) walkthrough**, not the "Train 4 + drag-departure-
  vertex" variant — the latter isn't supported by Flatland mechanics.
- **A line crossing ≠ a conflict** unless it maps to the **same protected
  resource** (cell/edge, direction, time, capacity). Bare Marey intersections are
  insufficient — conflicts must be tied to exact resources. Critical for the
  conflict-ribbon implementation.
- **All the hard consequence numbers disagree across models** (e.g. "+18 vs +12
  delay", "0 vs 0–1 deadlocks") and are only valid if produced by a defined
  **Flatland counterfactual rollout / reservation solver** — show them as
  *estimated*, never as fact, until a rollout backs them.

### Extra references it surfaced (worth checking)
- Rail-specific operational precedents: **Network Rail CCIL** (incident log →
  alarm-bundling precedent), **Hitachi TMS** (rule-checked ML + timetable-change
  viz → explainable rec cards), Dutch **TROTS** (train-describer process mining /
  conflict ID — note: *offline* analysis, not live dispatch), DB **LeiDis**,
  Thales **ARAMIS**, **SBB RCS** (flag exact module/UI parity as uncertain).
- HITL analog: **ATC solution-space-diagram EID study** (Cognition, Technology &
  Work, 2017) — strong precedent for *showing operators why* automation advice is
  valid; pairs with **Ecological Interface Design**.
- Missing assurance/ergonomics standards to add: **CENELEC EN 50126/50128/50129**,
  **IEC 62290**, **ISO 11064** (control-room ergonomics).

### Build-readiness gaps to close before/while implementing (for Claude Code)
1. **Ground walkthroughs in real Flatland APIs**, not narrative: action IDs,
   `info['malfunction']`, `action_required`, agent speeds, resource occupancy,
   predictors, reservation-table construction. Our repo already exposes much of
   this (`AgentDTO.next_decision.options`, `malfunction_remaining`, `decision_cells`,
   `conflict_detector`).
2. **Separate the ontology:** alarm vs event vs incident vs recommendation vs
   command vs route-setting. Alert **bundling** needs explicit criteria —
   causal link, time window, same resource — plus a **child-alarm lifecycle**
   (raise / ack / shelve / auto-clear). Ties to brief §3.2 and `notification_manager`.
3. **Resource semantics for the Marey ribbon:** every conflict marker needs
   cell/edge + direction + time + capacity, derived from `conflict_detector`, not a
   pixel crossing.
4. **Uncertainty handling for consequence cards:** define horizon, rollout method
   (Monte Carlo?), confidence intervals, and calibration against realised outcomes
   — otherwise the honest-uncertainty widget isn't honest. `scenario_runner` /
   `overrides.py` before-after is the starting point.
5. **Operator authority & auditability:** preview → apply → undo, acknowledgement,
   suppression accountability, human-consent boundaries (esp. Director mode).
6. **Define an evaluation plan per widget:** alarm-rate reduction, time-to-detect,
   false-bundling rate, deadlocks avoided, delay cost, workload — this is also the
   natural AI4REALNET experiment design (ties to D4.1 test protocols).
7. **Classify every operational reference** as live control-room tool vs
   offline/post-hoc analysis vs vendor claim vs secondary web description — don't
   cite marketing as a deployed-UI precedent.

> Net: the cited real-world systems support *pieces* of each workflow, but **none
> proves the exact proposed widget UI**. Build them as grounded hypotheses to test
> in Flatland, not as settled patterns.

---

## Mapping table — idea cluster → our code

| Cluster | Component(s) | Key data already available | New backend? |
|---|---|---|---|
| Marey ribbons / predicted lines | `marey-chart`, `graphic-timetable` | trajectories, speed, next_decision, delay, deadlines | conflict projection (extend `conflict_detector`) |
| Plan-vs-actual overlay | `marey-chart`, `track-layout` | earliest_departure, latest_arrival, delay, eta | no |
| Map↔Marey brushing | `SessionStore` signals, both views | selectedHandle, trajectories | no |
| Bottleneck / congestion | new center widget | rail_grid, rail_tiles, positions, predicted conflicts | aggregation helper |
| Topology / reservation view (contrarian) | new center view + view-toggle | rail topology, decision_cells, trajectories | topology abstraction (L) |
| Triage + lead-time + grouping + shelving | `notifications-panel`, `notification_manager` | predicted conflicts, malfunction_remaining, time_to_deadline | root-cause grouping, time-to-act |
| Explain-the-alert | `notifications-panel` popover | conflict graph from `conflict_detector` | expose causal chain (no LLM) |
| Trust-calibration ledger | new small widget | logged recommendation outcomes vs realised KPIs | log store |
| Small-multiple mini-Mareys | `scenario-panel` | per-scenario `trajectories`, `ScenarioKpis` | no (data exists) |
| Trade-off frontier / radar | `scenario-panel` | `ScenarioKpis`, `kpiDeltas`, `kpiWeights` | no |
| Consequence-first rec card + uncertainty | `recommendations-panel`, `agent-inspector` | next_decision.options, override before/after impact (overrides.py), confidence | rollout spread (optional) |
| What-if branch tree (blue/yellow) | `scenario-panel` / co-learning compare | scenario trajectories, kpiDeltas | multi-branch sim |
| Autonomy contract / directive controls | new `goal-achievement` widget (brief §4.3) | kpiWeights, ScenarioKpis, mode | directive plumbing |

---

## Full catalog (every distinct idea)

Notation: **[models]** = which proposed it. G=GPT-5.5-pro, GE=Gemini, O=Opus,
GK=Grok, M=Mistral, Q=Qwen.

### CENTER
- **Conflict / headway ribbons on the Marey** — band around each line; overlap =
  tight margin/conflict. *Grounding:* UIC 406 blocking-time stairways, ETCS
  headway, SBB Bildfahrplan-Konfliktbänder. **[G GE O GK M Q]**
- **Predicted forward-projection + conflict marker** — dashed path to target, ✕
  where projected paths cross. *Grounding:* ATC trajectory probe (URET). **[G O GK Q]**
- **Plan-vs-actual / ghost overlay** — faint planned line vs actual; gap = delay;
  red at deadline breach. *Grounding:* flight ghost-tracks, Viriato/OpenTimeTable. **[GE O M Q]**
- **Reachability envelope / space-time prism** — shade earliest–latest feasible
  region per train; intersecting envelopes = likely deadlock. *Grounding:* cone of
  uncertainty, time-geography. **[GE]**
- **Moving-block / occupancy ribbons on the map** — reserved track ahead glows;
  head-on ribbons = imminent gridlock. *Grounding:* ETCS L3 / ERTMS. **[GE Q M]**
- **Bottleneck occupancy strip / congestion heatmap** — critical cells/corridors
  × future steps, colour = occupation. *Grounding:* track-circuit panels, UIC
  capacity charts, Maps traffic. **[G GK M Q]**
- **Decision-horizon lens / next-decision in place** — fisheye expands the next
  8–12 decision points; ghost paths per option. *Grounding:* focus+context
  (Furnas), rail timetable editors. **[G GE GK Q]**
- **Train slack ladder** — vertical urgency index sorted by time-to-deadline.
  *Grounding:* PERT slack, horizon-graph sparklines. **[G]**
- **Topology-grouped Marey bands** — group the Marey's vertical axis into logical
  corridors/station clusters (not flat abstract position); lines jump bands when a
  train changes corridor, making route changes visible. *Grounding:* String
  Charter 2, Railroad Traffic Planner stringline grouping. **[S]** *(fresh — best
  single refinement of the Marey itself; ties to our rail topology + decision_cells)*
- **Deadlock-risk horizon gauge** — compact global deadlock-risk curve over the
  next N steps; a supervisory glance for Director mode. *Grounding:* risk-horizon
  plots in grid-ops dashboards. **[S GE(≈delta)]**
- **Map↔Marey brushing bridge** — shared selection + time-brush. *Grounding:*
  brushing-and-linking (Becker & Cleveland). **[G O GK GE]**
- **Topological junction graph / fisheye grid** — collapse straight track,
  expand junctions. *Grounding:* CTC mimic panels, Beck schematic. **[G GE GK]**

### LEFT
- **Triage queue / shelf by time-to-act + lead-time bars** — "Act now / soon /
  monitor"; draining countdown per alert. *Grounding:* ISA-18.2, EEMUA 191,
  EICAS. **[G GE O GK M Q]**
- **Incident bundle / causal cascade grouping** — one root cause, nested
  symptoms. *Grounding:* alarm-flood suppression, event correlation (ASM,
  PagerDuty). **[G GE O M Q]**
- **Alarm shelving / lifecycle** — new/ack/shelved/escalated/resolved; auto
  re-arm; no silent drop of red. *Grounding:* ISA-18.2 shelving. **[G O GK M]**
- **Explain-the-alert popover** — causal chain + "do-nothing projection", from
  the sim (not an LLM). *Grounding:* XAI "because…", aviation memory-items. **[O M Q GE]**
- **Alert place-time linker / spatial anchoring** — thumbnail or Marey-axis
  alignment locating each alert. *Grounding:* brushing-and-linking, Tufte
  marginalia. **[G GE O GK]**
- **Trust-calibration ledger / override strip** — was the AI right lately?
  accept/override rate per alert class. *Grounding:* reliability diagrams,
  Parasuraman & Riley trust calibration. **[G GK O Q]**
- **Lead-time / frequency sparkline per alert type** — trend rising/falling.
  *Grounding:* Tufte sparklines. **[M Q]**
- **Notification KPI lens** — filter/rank alerts by their impact on the KPI that
  matters now (delay vs deadlocks vs completions); slider to emphasise one
  dimension. *Grounding:* KPI-oriented alarm categorisation; AI4REALNET per-scenario
  KPIs. **[S]** *(fresh — wires the existing `kpi-filter`/`kpiWeights` into the
  notifications column; cheap, high integration value)*

### RIGHT
- **Scenario small-multiple mini-Mareys** — tiny stringline per policy/branch,
  same scale. *Grounding:* Tufte small multiples; git-branch viz. **[G GE O GK M Q]**
- **Honest uncertainty (fan chart / variance band / whiskers)** — outcome spread
  + evidence source, never a bare %. *Grounding:* BoE fan charts, ensemble
  forecasts. **[G GE O GK M Q]**
- **Trade-off frontier / Pareto / KPI radar** — policies as points/polygons;
  ideal corner labelled. *Grounding:* Pareto fronts, MCDA, profile charts. **[G GE M Q]**
- **Consequence-first recommendation card + trivial override** — options × KPI
  consequence, equal Accept/Modify/Reject. *Grounding:* TCAS RA, clinical decision
  support. **[G O]**
- **Next-decision action lattice** — discrete options × projected KPI impact +
  uncertainty whiskers. *Grounding:* ETCS DMI lattices, RL HITL matrices. **[GK]**
- **What-if branch tree (blue/yellow)** — fork now → human vs AI branch, KPI delta
  per leaf. *Grounding:* decision trees, git-branch diff. **[O Q]**
- **Bullet-bar policy comparison** — KPIs as aligned bullet bars vs current
  reference. *Grounding:* Tufte/Few bullet graphs. **[O]**
- **"Commit vs branch" intent canvas** — Simulate-&-Compare vs Commit, to lower
  fear of executing AI moves. *Grounding:* Figma branching, undo history. **[GE]**
- **Autonomy contract / directive sliders / interruptibility meter** — what the AI
  may do, handoff triggers, KPI targets (Director). *Grounding:* Sheridan &
  Verplank LoA, NASA Playbook adjustable autonomy. **[G GK Q M]**
- **Decision trace / human-AI ledger timeline** — past human (blue) & AI (yellow)
  actions + events. *Grounding:* event timelines, flight-data recorder. **[M Q]**

---

## Notes on the model run

- **Best signal-to-noise:** GPT-5.5-pro, Opus 4.8, Gemini Pro (detailed, grounded,
  honest-AI emphasis). Grok 4.3 tighter but with good SBB-specific references
  (Konfliktbänder). Qwen3.7-plus (open) thorough. Mistral comprehensive but more
  generic in places.
- **Failed / empty:** qwen3.7-max, perplexity sonar-deep-research, deepseek-v4-pro.
- **Worth one more model?** Generally no — convergence is reached; more general
  chat models repeat the same clusters. The exception with real added value was
  **`perplexity/sonar-deep-research`** (retried successfully): web-grounded, it
  confirmed the same clusters and added three fresh, citation-backed widgets
  (topology-grouped Marey bands, notification KPI lens, phase-space risk plane).

### Sonar / named grounding
Sonar's value is the **named standards & tools** behind the patterns the other
models quoted from memory — useful for the "fundiert" angle and for a paper:

- **Alarm management:** EEMUA 191, ISA-18.2, ABB SCADA alarm practice (triage,
  shelving, rationalisation, nuisance-alarm rates).
- **Control-room HMI human factors:** task-centred display design guidance.
- **Stringline / time–distance tools:** String Charter 2, Railroad Traffic
  Planner (basis for the topology-grouped Marey).
- **Real dispatching system (SBB RCS-Dispo):** the production traffic-management
  tool of SBB's operations control centres — unified real-time process image
  (target/actual), whole network recomputed ~every 2 s with a ~2 h forecast
  horizon; also deployed in Belgium and at DB. The closest real-world analogue to
  what this playground prototypes. Primary source = the RCS-DISPO brochure.
  - Overview: https://company.sbb.ch/de/bahnentwicklung/bahnbetrieb/bahninformatik/rcs.html
  - RCS-DISPO brochure (PDF): https://bahninfrastruktur.sbb.ch/content/dam/internet/bahninfrastruktur/downloads/de/produkte-dienstleistungen/bahninformatiksysteme/bahnbetrieb/Broschuere-RCS-DISPO.pdf.sbbdownload.pdf
  - Product site: https://sbbrcs.ch/
- **AI4REALNET D1.1:** transparency / trustworthy human-in-the-loop framing.

> ⚠️ **References caveat:** Sonar's answer carries 143 inline `[n]` citation
> markers, but OpenRouter's JSON export did **not** include the resolved source
> list (URLs). The named standards above are recoverable from the prose; the full
> bibliography must be copied from the OpenRouter UI if you want the links. (The
> only URLs in the export are your own repo links you passed in.)

## Next: develop with Claude Code
Point Claude Code at this file + `docs/interaction-modes-brief.md` + `CLAUDE.md`.
Suggested first build: **shortlist #1 (conflict-aware Marey)** and **#2 (triage'd
notifications)** — highest impact, mostly reuse existing data. The mini-round
prompt in `docs/reference/ui-exploration-prompt.md` (and below) can turn any single widget
into a build-ready Angular component spec first.
