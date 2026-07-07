# Flatland Dispatcher Playground — overview & roadmap

A single entry point: **what this is**, **what's built**, **how to try it**, and the
**further ideas** to follow. (For the raw change list see [PLAYGROUND.md](../../PLAYGROUND.md).)

## What this is

An interactive HMI for railway dispatching experiments (Flatland-RL), part of
AI4REALNET. The focus: make the **three human-AI collaboration modes behaviourally
distinct** and run a **guided demo** through all three on the same situation.

- `recommendation` (WP 3.1) — AI suggests, human decides
- `co-learning` (WP 3.3) — AI offers neutral options; human decides, reflects
- `director` (WP 3.4) — AI runs autonomously on a high-level directive; human supervises

Stack: Angular (standalone + signals) + SBB Lyne · FastAPI + Flatland-RL.

## How to try it

Two terminals (see the main [README](../../README.md) Quick start). Then open
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
- [experiment-storyboard.md](../scenarios/experiment-storyboard.md) — study storyboard, 3 conditions, scenario-difficulty matching
- [railway-scenarios.md](../scenarios/railway-scenarios.md) — AI4REALNET D1.1/D4.1 scenarios + malfunction taxonomies
- [recommender-roadmap.md](../plans/recommender-roadmap.md) — policy vs intervention seams, phases
- [variant-visualisation.md](../archive/variant-visualisation.md) — ways to show alternatives (beyond the Marey)
- [co-learning-direction.md](../plans/co-learning-direction.md) — Level A (task) vs Level B (AI learns to work with the human)
- [event-based-architecture-analysis.md](../archive/event-based-architecture-analysis.md) — relationship to InteractiveAI
- [visual-concept.md](visual-concept.md) — canonical names for our surfaces, the 3 zones, and the InteractiveAI lineage
- [scripted-events-plan.md](../plans/scripted-events-plan.md) — deterministic scenario events for User Study 2
- [recommendation-reliability.md](../plans/recommendation-reliability.md) — guaranteeing a decision moment (variants A–D)
- [heterogeneous-tracks.md](../plans/heterogeneous-tracks.md) — track classes/costs so reroute becomes a real trade-off
- [localized-blocking-decisions.md](../plans/localized-blocking-decisions.md) — hold the affected trains/area (not the whole sim) until the human decides; + autonomy agreement idea
- [scenario-variants.md](../plans/scenario-variants.md) — controlled study vs. dynamic "simulated wild" (real algorithms, emergent events); variant axes
- [onboarding-tickets-2026-06.md](../plans/onboarding-tickets-2026-06.md) — curated discussion tickets for the June/July onboarding kickoff (RL/vibecoding, interaction design, experiment setup, Co-Learning)

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
- **Cities = stations** — surface Flatland's generated city/station data
  (currently discarded after `reset()`) as named stations, feeding richer
  train origin/destination info and the reserved `city` visual-encoding role.
  See [cities-stations-plan.md](../plans/cities-stations-plan.md).

Later / optional:
- **Guide screens (mode-intro / demo-complete) via the Layout Designer** —
  compose them as designer layouts instead of hand-authored components; needs
  content-only tiles + a session-less rendering host + the mode-scoped-layouts
  resolver (§9 of [mode-scoped-layouts-plan.md](../plans/mode-scoped-layouts-plan.md)).
- **LLM-driven reflection dialogue** (Socratic/Animation mode).
- **Event-based architecture** (adopt InteractiveAI's event *pattern*, not the platform).
- **Web deployment** (VPS/Docker + Caddy; fix hardcoded backend URL first).

Tooling / process debt (small):
- **Stylelint colour gate covers hex/named only** (`frontend/.stylelintrc.cjs`) —
  `rgba()`/`rgb()` literals aren't auto-linted yet (would need a custom rule to
  avoid false positives on shadows); still forbidden by convention
  (`docs/reference/frontend-lyne-conventions.md` §1).
- **Colour gate isn't wired to CI or a pre-commit hook** — currently a manual
  `npm run lint:styles`, documented in CLAUDE.md/AGENTS.md/copilot-instructions.
  Revisit if new hardcoded colours keep slipping through.

## Guided demo — how it works (for facilitators)

Same environment (fixed seed) is replayed for each mode via `reset()`; the survey
after each mode advances the flow. Mode order is fixed (Recommendation →
Co-Learning → Director). Limitation: exact conflict timing isn't guaranteed yet
(stochastic malfunctions) — deterministic injection is the planned fix.
