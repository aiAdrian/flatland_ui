# Onboarding tickets — June/July kickoff discussion

> **Status:** discussion draft for the kickoff call, not assigned yet.
> Curated from existing plan docs — nothing invented here, every ticket links
> back to its source doc. Meant to be picked apart / reassigned live in the
> call, not executed as-is.

## Groups this maps to

- **R-series** — flexible, railway-sector, RL-near, vibecoding-affine
  colleagues joining in June. Concrete code entry points included.
- **A/B/C-series** — interaction design, experiment setup, and Co-Learning
  content, for whoever picks those up (may overlap with R-series colleagues).

---

## R — RL-near / vibecoding (June)

### R1 — Cities = Stations, P1 capture spike
Wrap the `rail_generator` callable so the `agents_hints` dict (`city_positions`,
`train_stations`, `city_orientations`) — which Flatland discards internally
after `RailEnv.reset()` — is captured at generation time instead. Spike only:
verify the captured shape looks right for a couple of seed/config combos, no
schema commitment yet.
- **Entry point:** `backend/app/core/env_factory.py:174-185` (the
  `sparse_rail_generator` call site)
- **Source:** [cities-stations-plan.md](cities-stations-plan.md) §2, §4 P1
- **Size:** S (~1 day)

### R2 — Greedy what-if recommender
New `InterventionRecommender`: for each affected train, simulate its options
(reroute / hold / proceed) via the existing `ScenarioRunner`, score
KPI-weighted, rank up to 3. Registers into the existing recommender seam, no UI
change needed.
- **Entry point:** `backend/app/core/recommenders/` (new file
  `greedy_whatif.py`, same registration pattern as
  `Phase1ProximityRecommender`)
- **Source:** [recommender-roadmap.md](recommender-roadmap.md) "Planned" item 1
- **Size:** M

### R3 — PP-replan recommender
Block the malfunction cell for its duration, run Prioritized Planning on the
affected trains only → one coherent reroute/hold/reorder set instead of
per-train guesses. **Before building:** check
[`AI4REALNET/Tokener`](https://github.com/AI4REALNET/Tokener)'s Hybrid
(CBS+PP, token-based) approach and align naming/semantics with it — don't
write PP/CBS logic from scratch. Watch for the Flatland version mismatch
(4.0.3 vs 4.2.6) noted in the cbs-pp-planner-integration context.
- **Entry point:** `backend/app/core/recommenders/pp_replan.py` (new); possibly
  a dedicated PP-planner building block
- **Source:** [recommender-roadmap.md](recommender-roadmap.md) "Planned" item 2
- **Size:** M–L

### R4 — Widget B1: what-if branch compare
"A3S-light": map/Marey visualisation with two paths — old (blue,
human-influenced) vs. new (yellow, AI-simulated) — plus a KPI delta. Reuse
target: [`agent-as-a-service-trace-rl`](https://github.com/AI4REALNET/agent-as-a-service-trace-rl)
(Redis-backed restore/simulate-forward/report). Spec first via the
`create-widget` skill, then build — effort estimate already documented there.
- **Entry point:** widget registration seams (`panel-plugin-host.component.ts`,
  designer palette); backend needs an alternative-route computation (partly
  depends on R3)
- **Source:** Widget B1 in [widget-catalog.md](widget-catalog.md)
- **Size:** M–L
- **Depends on:** R3 (for a real alternative path, not a placeholder)

### R5 — PPO as Policy (real RL, stretch goal)
Register a trained RL model as another `Policy` implementation — per the
roadmap, explicitly *the* project goal ("train ourselves, no pretrained").
Biggest chunk, most directly in the colleagues' RL wheelhouse, but data-hungry
and multi-week — treat as an optional stretch goal, not a first task.
- **Entry point:** `backend/app/policies/` (new policy implementation, same
  interface as the heuristics)
- **Source:** [recommender-roadmap.md](recommender-roadmap.md) "RL wave"
- **Size:** L

**Dependency note:** R4 needs R3 as its real data source for alternative
paths — assign as a pair if two people want to work on it together. R1 and R2
are independent and make a good same-day parallel start for two people.

---

## A — Interaction design

### A1 — Shift Co-Learning timing to t3
AI alternatives should appear only *after* the human's own hypothesis (today
they appear ~t1). Core to "human goes first" (Evaluative AI).
- **Source:** [experiment-storyboard.md](../scenarios/experiment-storyboard.md) mapping table
- **Size:** S–M

### A2 — "Human-solution" input step
Frame 4: participant enters their own re-scheduling idea first. Missing today
(only overrides exist, no explicit "formulate your solution" step).
- **Source:** same as A1
- **Size:** M
- **Pairs with:** A1, A3 (assign as one package, not separately — they're
  sequentially dependent)

### A3 — Impact analysis on the human's own solution
Frame 5: the AI evaluates the solution *the human proposed*, not just its own
option (expected delays / follow-on conflicts).
- **Source:** same as A1
- **Size:** M

### A4 — Dual-path what-if visualisation
Old (blue, human-influenced) vs. new (yellow, AI-simulated) path + KPI delta
on map/Marey. Same reuse target as R4.
- **Source:** [recommender-roadmap.md](recommender-roadmap.md) item 4 / Widget B1
  in [widget-catalog.md](widget-catalog.md)
- **Size:** M–L

### A5 — Guaranteed decision moment
Today it's not reliably reproducible whether a real conflict occurs during the
guided demo. Recommended fix: scripted events.
- **Source:** [recommendation-reliability.md](recommendation-reliability.md) Variant B
- **Size:** M

### A6 — Trade-off frontier / scenario small-multiples
Evaluative-AI decision support: show several options with trade-offs
side-by-side instead of just a ranking.
- **Source:** Widget C1 in [widget-catalog.md](widget-catalog.md)
- **Size:** M

### A7 — Autonomy dial / allocation panel
Make visible and adjustable how much autonomy the AI currently has (Director
altitudes) — groundwork for "adjustable autonomy".
- **Source:** Widget D1 in [widget-catalog.md](widget-catalog.md); §4.1 in
  [interaction-modes-brief.md](../reference/interaction-modes-brief.md)
- **Size:** M

---

## B — Experiment setup

### B1 — Scenario-authoring schema
Implement Table 1 from the storyboard (Weak Signal, Proaktivitätsfenster, Cue
combination, Trade-off, Outcome, performance indicators) as the actual format
for the custom scenario builder.
- **Source:** [experiment-storyboard.md](../scenarios/experiment-storyboard.md) Table 1
- **Size:** M–L

### B2 — Matched scenario difficulty (Latin square)
Parallel, equally-hard scenarios per condition so no participant sees the same
scenario 3×. Confound control for the study.
- **Source:** [scenario-variants.md](scenario-variants.md)
- **Size:** M

### B3 — Invented place/train names
So participants don't bring real-world expectations about routes/places. Part
of the scenario builder.
- **Source:** [experiment-storyboard.md](../scenarios/experiment-storyboard.md)
- **Size:** S

### B4 — Interaction logging (Log Daten + ICAP)
Currently localStorage only, no export/persistence; the "Log Daten" column in
the storyboard is still empty. Needs an event schema + ICAP engagement tagging
per frame.
- **Source:** [interaction-logging-plan.md](interaction-logging-plan.md)
- **Size:** M–L

### B5 — Deterministic malfunction injection
So the same conflict is exactly reproducible across all three modes (today
rate-based/stochastic). Blocks clean cross-condition comparison in the study.
- **Source:** [OVERVIEW.md](../reference/OVERVIEW.md) roadmap
- **Size:** S–M

### B6 — Open question: impact analysis for the Recommendation group too?
So there's no apples-vs-pears comparison between conditions. A discussion item
first, not a build task.
- **Source:** [experiment-storyboard.md](../scenarios/experiment-storyboard.md)
- **Size:** discussion

---

## C — Co-Learning (content)

### C1 — Operator model (Level B, the "new" part)
Backend model that (a) estimates reward weights from overrides/accept-reject →
feeds KPI/scoring, (b) proposes autonomy / `optionPresentation` from trust
history. No heavy RL needed — light methods (Bayesian update, bandit
heuristic) suffice.
- **Source:** [co-learning-direction.md](co-learning-direction.md) "Suggested
  order" item 1
- **Size:** M–L
- **Do first:** C4 (consortium check)

### C2 — Reflection "when calm", not only at episode end
Offer reflection mid-session during a calm moment too, not only at the end.
- **Source:** §3.2 in [interaction-modes-brief.md](../reference/interaction-modes-brief.md)
- **Size:** M

### C3 — "What if I had chosen differently" compare
What-if compare for the participant's own non-chosen alternative (§3.3, step 7
of the validated flow).
- **Source:** §3.3 in [interaction-modes-brief.md](../reference/interaction-modes-brief.md)
- **Size:** M

### C4 — Consortium check before building Level B
Before building the operator model: review
[`AI4REALNET/Tokener`](https://github.com/AI4REALNET/Tokener)'s Co-Learning
approach ("transparent adaptation through interaction") and
[`AI4REALNET/T3.3-3.4-HMI`](https://github.com/AI4REALNET/T3.3-3.4-HMI) and
align naming/semantics — "reuse, don't reinvent".
- **Source:** [co-learning-direction.md](co-learning-direction.md)
- **Size:** S (research, before C1)

### C5 — ICAP level tagging per frame
Engagement framework (ICAP) per storyboard frame — part of the logging schema,
but also a Co-Learning design question (what counts as "active"?).
- **Source:** [experiment-storyboard.md](../scenarios/experiment-storyboard.md)
- **Size:** S, depends on B4

---

## Related plans

[[mode-scoped-layouts-plan]] · [[cities-stations-plan]] · [[recommender-roadmap]] ·
[[widget-catalog]] · [[co-learning-direction]] · [[experiment-storyboard]] ·
[[scenario-variants]] · [[interaction-logging-plan]] · [[recommendation-reliability]]
