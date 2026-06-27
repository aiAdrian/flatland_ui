# Flatland Dispatcher Playground — overview & roadmap

A single entry point: **what this is**, **what's built**, **how to try it**, and the
**further ideas** to follow. (For the raw change list see [PLAYGROUND.md](../PLAYGROUND.md).)

## What this is

An interactive HMI for railway dispatching experiments (Flatland-RL), part of
AI4REALNET. The focus: make the **three human-AI collaboration modes behaviourally
distinct** and run a **guided demo** through all three on the same situation.

- `recommendation` (WP 3.1) — AI suggests, human decides
- `co-learning` (WP 3.3) — AI offers neutral options; human decides, reflects
- `director` (WP 3.4) — AI runs autonomously on a high-level directive; human supervises

Stack: Angular (standalone + signals) + SBB Lyne · FastAPI + Flatland-RL.

## How to try it

Two terminals (see the main [README](../README.md) Quick start). Then open
http://localhost:4200.

- **Free play:** "+ New Session" → pick a mode in the header → step / play.
- **Guided demo:** "▶ Guided Demo" → same environment, solve one conflict in all
  three modes in sequence (Recommendation → Co-Learning → Director), a short
  survey after each, then "complete".

## What's built

**Interaction modes (the core).** One `optionPresentation` flag drives the UI:
`recommended` / `neutral` / `none`.
- Recommendation: up to 3 ranked recommendations (no explanation text); scenarios
  ranked + badged.
- Co-Learning: neutral options; intervention log; reflection panel (grounded in
  the Supportive-AI framework — Mirroring stats + Socratic prompts; 2-of-5
  configurable).
- Director: pre-run directive (KPI + policy) → "Start autonomous run" →
  goal-achievement panel; "AI in control" banner.

**Guided demo flow.** Fixed environment, sequential modes, per-mode survey gating,
mode switcher locked, completion screen. (See guided-demo notes below.)

**Impact analysis + recommender seam.** When a train malfunctions, the impact
panel shows which trains are affected (path crosses the blocked cell before it
clears) + a coarse reroute/hold recommendation — mode-aware, clickable
(select/highlight on map), dismiss-on-apply. Behind a pluggable
`InterventionRecommender` interface (Phase-1 proximity today).

**KPI filter → backend scoring.** KPI sliders feed the scenario/recommendation
scoring (not just frontend sorting); collapsible (expanded in Director).

**Layout & situational awareness.** Three-zone IA (situation left · map middle ·
intervention right); Hypervision situation summary; event feed with criticality;
agent details as a map-corner overlay; consistent collapsible panels.

**Surveys.** Config-driven, SBB-styled; selectable instruments in Settings
(NASA-TLX, Trust, UEQ-S, mode-specific, open); per-session localStorage.

**Malfunction legibility.** Resume ETA + destination; optional "(demo)" malfunction
type labels (Flatland has no native type).

## Architecture: two pluggable seams (so other/trained algos slot in)

1. **Policy seam** (`backend/app/policies`) — drives the trains. Heuristics today;
   PP/CBS planners and **trained RL (PPO)** plug in here unchanged.
2. **Recommender seam** (`backend/app/core/recommenders`) — suggests interventions.
   Phase-1 proximity today; greedy what-if, PP-replan, or an RL recommender plug
   in later without UI changes.

Stable data contracts (`Recommendation`, impact items) mean the engine behind
them can change freely. Distinguish **policy change (system-wide)** from
**intervention (local fix for a malfunction)**.

## Document map

- [interaction-modes-brief.md](interaction-modes-brief.md) — the mode spec (§3.1–3.4)
- [mode-guide.md](mode-guide.md) — same task walked through all three modes
- [experiment-storyboard.md](experiment-storyboard.md) — study storyboard, 3 conditions, scenario-difficulty matching
- [railway-scenarios.md](railway-scenarios.md) — AI4REALNET D1.1/D4.1 scenarios + malfunction taxonomies
- [recommender-roadmap.md](recommender-roadmap.md) — policy vs intervention seams, phases
- [variant-visualisation.md](variant-visualisation.md) — ways to show alternatives (beyond the Marey)
- [co-learning-direction.md](co-learning-direction.md) — Level A (task) vs Level B (AI learns to work with the human)
- [event-based-architecture-analysis.md](event-based-architecture-analysis.md) — relationship to InteractiveAI
- [visual-concept.md](visual-concept.md) — canonical names for our surfaces, the 3 zones, and the InteractiveAI lineage
- [scripted-events-plan.md](scripted-events-plan.md) — deterministic scenario events for User Study 2
- [recommendation-reliability.md](recommendation-reliability.md) — guaranteeing a decision moment (variants A–D)

## Roadmap / further ideas

Near-term, frontend-feasible:
- **Deterministic malfunction injection** so the guided-demo conflict is identical
  in all three modes (today malfunctions are rate-based / not perfectly reproducible).
- **Dual-path what-if (§3.3)** + **variant visualisation**: old (blue) vs new
  (yellow) path + small-multiples / KPI comparison of alternatives.
- **Study data persistence + export** (replace localStorage) for real runs.
- **Rethink the time-distance (Marey) diagram.**

Backend / agents wave (pending the RL decision):
- **Intervention recommender Phase 2**: greedy what-if → **PP replan** (block the
  cell, re-plan affected trains coherently) → optimal CBS.
- **Real RL agents** (PPO as a Policy; later an RL recommender) — the project goal:
  real RL, not just heuristics.
- **Custom scenario builder** (consortium JSON; train names/destinations) with
  **matched difficulty** calibration for the study.

Later / optional:
- **LLM-driven reflection dialogue** (Socratic/Animation mode).
- **Event-based architecture** (adopt InteractiveAI's event *pattern*, not the platform).
- **Web deployment** (VPS/Docker + Caddy; fix hardcoded backend URL first).

## Guided demo — how it works (for facilitators)

Same environment (fixed seed) is replayed for each mode via `reset()`; the survey
after each mode advances the flow. Mode order is fixed (Recommendation →
Co-Learning → Director). Limitation: exact conflict timing isn't guaranteed yet
(stochastic malfunctions) — deterministic injection is the planned fix.
