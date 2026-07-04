# Recommender roadmap — two pluggable seams

Goal: stay flexible so other / trained (RL) algorithms can be plugged in later,
and keep **policy change (system-wide strategy)** separate from **intervention
recommendation (local fix for a malfunction)**.

## The two seams

1. **Agent / Policy seam** — drives the trains. Existing `app/policies` registry.
   Heuristics, PP/CBS planners, and trained RL (PPO) all implement `Policy` and
   register. This is where RL ultimately lives (a trained model = one more Policy).
2. **Intervention recommender seam** — suggests the local action for a
   malfunction. New `app/core/recommenders` registry (`InterventionRecommender`).
   Stable dict contract so the engine can change without UI changes.

A trained RL model can serve **either** role (Policy for Director, or Recommender
for Recommendation / Co-Learning).

## Status

- ✅ Policy registry (heuristics today).
- ✅ Intervention recommender seam: `InterventionRecommender` + registry;
  `Phase1ProximityRecommender` is the first implementation (wraps the impact
  analysis); `/hmi/impact` resolves the active recommender.
- ✅ Impact panel UX: always visible, **auto-collapses when idle / auto-expands**
  on a malfunction; rows are **clickable** (select + highlight the train on the
  map) and **hover-highlight**; applying **Hold/Reroute dismisses** the item.
- ✅ Consistent **collapsible panels** across the right column (Impact, Scenarios/
  Policy, Recommendations) + KPI filter — click the header to toggle.
- ✅ Up to 3 ranked policy recommendations, **no explanation text**.
- ✅ Clear split surfaced in the UI: **Impact = per-train intervention** (local,
  malfunction) vs **Scenarios/Policy = system-wide strategy**.

## Planned (in order)

1. **Greedy what-if recommender** (`recommenders/greedy_whatif.py`): for each
   affected train, simulate its options (reroute / hold / proceed) with the
   ScenarioRunner, score KPI-weighted, pick best. Up to 3 ranked per situation.
2. **PP replan recommender** (`recommenders/pp_replan.py`): block the malfunction
   cell for its duration, run Prioritized Planning on the affected trains only →
   coherent multi-train reroute/hold/reorder set. First real use of our own PP
   planner ([[cbs-pp-planner-integration]]), scoped locally. CBS variant later.
   **AI4REALNET check:** [`Tokener`](https://github.com/AI4REALNET/Tokener)'s
   Hybrid approach already combines CBS+PP with token-based interaction —
   check it (and note any Flatland-version divergence, per
   [[cbs-pp-planner-integration]]'s 4.0.3-vs-4.2.6 mismatch) before writing our
   own PP/CBS logic from scratch, per CLAUDE.md's "reuse, don't reinvent" rule.
3. **Impact panel: up to 3 ranked intervention options** + mode-aware apply
   (recommendation = highlighted + apply; co-learning = neutral / inspect;
   director = overview).
4. **Dual-path what-if visualisation (§3.3)**: on reroute, show **both** paths on
   the map/Marey — old/current (blue = human-influenced) vs new/rerouted
   (yellow = AI-simulated) — with a KPI delta. Needs the backend to compute the
   alternative route around the block (PP replan / targeted reroute path);
   today only the current path is highlighted on selection and the new forecast
   appears after applying.
4. **Clear UI separation**: intervention recommendations live in the impact panel;
   policy-change recommendations stay in the scenario panel. Label both distinctly.
5. **RL recommender** (`recommenders/rl_recommender.py`): a trained model behind
   the same seam. No UI change.
6. **Recommender selection** (settings / per session): choose the active
   recommender, like policy selection.

## RL wave (Policy seam)

- PPO agent as a `Policy` (the "real RL" goal). Train ourselves (no pretrained in
  T3.4). See rl-agents-goal memory.

Keep the data contracts stable (`Intervention` item dict / `Recommendation` list)
throughout so any engine swap is transparent to the frontend.
