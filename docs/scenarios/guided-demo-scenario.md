# Guided demo — scenario approach (real simulation, no scripting)

## Decision
The demo should feel **real** — actual algorithms running on a live simulation,
showing that this is simulation-based — **not** a deterministic script. The lever
is therefore a **setup in which conflicts naturally emerge**, tuned so that a
handful (≈2–6) of solvable conflicts appear per run.

## Why the first attempt felt wrong
Conflicts were actually plentiful (a quick calibration with the real sim showed
5–14 conflict episodes per run across configs). The real bug: the **impact panel
only refreshed on pause/step/override**, not during continuous Play — so the
operator saw only one. Fixed by **polling impact live (~1.5 s) while playing**
(scenarios stay throttled — only impact, which is cheap, polls live).

## Setup (conflict-rich, real)
- Real malfunctions **on** (rate-based) + **bottlenecked topology** (few rails
  between cities, 1 rail-pair per city) + **congestion** (more trains than the
  corridor comfortably holds) → blocking conflicts emerge naturally.
- Demo config (tuned, seed 42): 36×24, 8 trains, 3 cities, rails-between-cities 2,
  rail-pairs-in-city 1, malfunction rate 0.012 (dur 10–22), latest-departure 35,
  400 steps. Same env replayed per mode via `reset()`.
- The "AI" is a **real algorithm** (DLA today; PP/CBS or RL later via the policy
  seam) — so resolutions are genuine, not canned.

## Decision per conflict = **hold** (realistic)
Reroute is often not available (single corridor), so the realistic tactical action
is **hold**. The impact panel recommends reroute only when a switch is genuinely
reachable before the block, otherwise hold.

## Per-mode experience (same env, real conflicts)
- **Recommendation:** conflicts surface live; impact panel shows affected trains +
  recommended hold/reroute → operator decides. Guided demo **auto-pauses** on a
  new conflict (so a decision is made).
- **Co-Learning:** same, neutral options; operator acts → interventions logged +
  reflection.
- **Director:** the AI resolves conflicts autonomously; operator **observes**
  goal-achievement; no auto-pause; can intervene by exception.

## Live surfacing + gentle auto-pause (built)
- Impact polled ~1.5 s during Play → conflicts appear as they happen.
- In the guided demo (Recommendation/Co-Learning only), the sim **auto-pauses** on
  a new conflict onset so the operator must decide; Director never auto-pauses.

## Future (noted, not built)
- **Rec-based timeout → AI auto-applies the best option** if the human doesn't
  intervene (instead of waiting on a pause). Matches "the system decides if no one
  intervenes".
- Difficulty calibration / matched parallel scenarios for the real study.
