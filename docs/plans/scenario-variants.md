# Scenario variants — controlled study vs. simulated wild

> **Status:** Framing for discussion (to be deepened with the team / Adrian).
> Two parallel needs that can't be served by one setup: a **controlled** study
> scenario, and a **dynamic, emergent** setup with real algorithms. We think in
> variants — presets along a few independent axes — rather than one config.

---

## 1. Two needs, in parallel

- **Study (controlled):** reproducible, confound-free, comparable across
  participants. The basis for User Study 2.
- **Dynamic / research (emergent):** real algorithms + more random events, to see
  how the algorithms actually perform *with* humans. Higher ecological validity,
  harder to analyse — and that difficulty is itself interesting (see §5).

Both are wanted. You can't optimise one setup for both, so we offer variants.

## 2. No Wizard-of-Oz

We deliberately **avoid WoZ**. We want **real algorithms** driving the AI side,
even though it makes everything harder (real failure modes, less predictable).
That realism is the point — a faked AI can't teach us how human + real algorithm
perform together.

## 3. The variant axes (independent)

A "variant" is a combination of these axes, not a single dial:

| Axis | Pol A — controlled | Pol B — emergent |
|---|---|---|
| **Layout** | curated / fixed (Adrian wants this) | randomly generated (seed) |
| **Events / disruptions** | scripted, timed | emergent (malfunction rate) |
| **Algorithm** | real algorithm (never WoZ) | real RL agents / planners (PPO, CBS/PP) |
| **Pacing** | study (~5–8 min, 2–3 events) | test/dense or realistic |

Important: **real algorithms and scripted events are composable, not either/or.**
You can run real algorithms *with* scripted events around them — the script sets
up the situation (weather, a blockage), the real algorithm reacts, the human
decides. So "scripted" constrains the *world*, not the *AI*.

## 4. Three anchor variants

1. **Study** — curated layout + scripted events + real algorithm + study pacing.
   Controlled, reproducible, comparable. For User Study 2.
2. **Dynamic / research** — generated layout + emergent events + real RL agents +
   realistic pacing. Emergent; for "how do real algorithms perform with humans".
3. **Dev / quick test** — small + emergent + heuristic + fast pacing. For
   iteration (the "I always want something to happen" tester need).

## 5. Research angle: cognition in a *simulated* wild

There's a methodological contribution hiding here. Classic HCI/lab studies are
**over-controlled** — clean, but stripped of the context where real dispatching
cognition actually happens. Hutchins' *Cognition in the Wild* (1995) argues
cognition is distributed across people, artefacts, and environment and is best
studied **in situ**, not in a sterile lab.

We can't (yet) do true *cognition in the wild* — a live railway control room. But
a high-fidelity simulation with **real algorithms and emergent events** is a
middle ground: **"cognition in a simulated wild."** It trades some experimental
control for **ecological validity** while staying measurable and repeatable
enough to run as an experiment.

The open research question this raises:
> How do we design *good* experiments in a more natural, less-controlled
> (simulated) setting — keeping enough rigour to learn something, without
> collapsing back into a sterile lab?

This is a genuine contribution candidate, distinct from the WP3 deliverables —
and it reframes the "dynamic" variant not as a messy fallback but as a
**deliberate naturalistic method**.

## 6. Maps onto existing seams (not a rewrite)

Variants are configurations of what we already have plus two planned pieces:

- **Algorithm axis** → the existing policy registry (heuristics today; real RL
  agents the goal).
- **Layout axis** → env/scenario config (generated today; curated layout planned,
  Adrian's terrain).
- **Events axis** → the planned scripted-events layer (emergent today).
- **Pacing axis** → playback speed + event spacing (a test/study preset).

So "offering variants" = presets selecting along these axes, surfaced in setup —
not a parallel engine.

## 7. Open questions (to deepen)

1. Are these the right axes, and are there more (e.g. number of agents / traffic
   density as its own knob)?
2. For the simulated-wild variant: which **metrics** capture human + real-
   algorithm performance (and human-centric outcomes), given less control?
3. How much scripting is allowed in the "dynamic" variant before it stops being
   naturalistic? (scripted world vs. scripted decisions.)
4. Difficulty matching across variants for any comparative claims.
5. Division of labour with Adrian: curated layout + algorithms are his terrain
   (aiAdrian priority) — how do our variant presets align with his work?

## 8. Connections

- [scripted-events-plan.md](scripted-events-plan.md) — the events axis (study).
- [localized-blocking-decisions.md](localized-blocking-decisions.md) — decision
  model that works in both controlled and emergent variants.
- [heterogeneous-tracks.md](heterogeneous-tracks.md) — curated-layout enabler.
- [recommendation-reliability.md](recommendation-reliability.md) — why emergent
  setups need care to surface decision moments.
