# Recommendation reliability — guaranteeing a decision moment in the demo

> **Status:** Problem statement + solution variants for discussion.
> **Context:** During a guided-demo run it is possible to play a whole episode
> without ever seeing an AI recommendation or a decision moment. For an
> experiment whose whole point is to study human–AI interaction at a decision
> point, that is a real gap.

---

## 1. The problem

There are **two independent sources** of "AI tells the human something", and in a
given run **both can stay empty for the entire episode**:

### Source A — Recommendations panel (policy switch)
`backend/app/core/recommendation_generator.py` surfaces a recommendation only
when an alternative policy beats the **DLA baseline** by at least `SCORE_MARGIN`
and introduces no deadlocks.

- DLA is a strong baseline → alternatives rarely beat it by a clear margin.
- Result: the panel often stays empty for a whole run.

### Source B — Impact panel (conflict-driven decision moment)
`backend/app/core/impact_analysis.py` produces items (and the guided demo's
auto-pause) only when:

1. a train is **malfunctioning**, AND
2. another train's shortest path **crosses the blocked cell before it clears**.

- Malfunctions are random (`malfunctionRate`). A run can have malfunctions that
  block nobody, or — with the wrong settings — none at all.
- Result: no malfunction-that-blocks-a-path → no auto-pause → no decision
  moment the whole episode.

### Net effect
The demo has **no guarantee** that a decision moment ever occurs. Whether the
human is asked to decide is left to chance (seed, topology, malfunction rolls,
and now user-chosen grid/agent settings).

---

## 2. Why it matters

- **For the demo:** a walkthrough that shows no recommendation undersells the
  whole human–AI teaming story.
- **For User Study 2:** the protocol is built around *windows of proactivity*
  (weather warning → consequence). The experiment needs every participant to hit
  comparable decision moments — randomness is a confound.

---

## 3. Solution variants

### Variant A — Cheap interim (IMPLEMENTED)
Tune the existing knobs so decision moments occur **more often** (not guaranteed):

- `SCORE_MARGIN` 0.10 → **0.05** — near-ties now surface in the Recommendations
  panel (`recommendation_generator.py`).
- Demo `malfunctionRate` 0.012 → **0.02** — blocking malfunctions, and thus
  impact-driven decision moments, surface more reliably (`app.component.ts`,
  `demoSessionOpts`).

**Pro:** trivial, already in. **Con:** still probabilistic — no guarantee a run
contains a decision moment, and raising malfunction rate adds noise.

### Variant B — Scripted events (RECOMMENDED, see scripted-events-plan.md)
A deterministic event scheduler fires a **scripted conflict at a fixed step**
(e.g. area block at step 15), which guarantees:

- an impact-driven decision moment at a known time, identical for every run, and
- a recommendation tied to that event (reroute / hold / proceed).

**Pro:** fully reproducible, matches the SBB protocol's proactivity windows,
controllable timing/severity. **Con:** the larger Phase-1 build (see
[scripted-events-plan.md](scripted-events-plan.md)).

### Variant C — Guaranteed-conflict generator
Keep conflicts emergent, but **post-process the generated env** so at least one
guaranteed bottleneck/malfunction is injected on a path that is actually used
(verify by a quick forward simulation at session creation; regenerate or inject
if no conflict is found within the horizon).

**Pro:** keeps the "emergent" feel, still reproducible per seed. **Con:** more
backend logic than A; less controllable than B (timing/severity not authored);
a forward-sim check at creation adds latency.

### Variant D — Couple the two sources
When the impact panel detects a conflict, also **emit a matching Recommendation**
into the Recommendations panel (today they are independent). This doesn't create
decision moments that aren't there, but ensures that **whenever** a conflict
exists, the human sees a concrete, rankable recommendation — not just a neutral
impact list.

**Pro:** removes the "impact exists but Recommendations panel is empty"
mismatch; modest effort. **Con:** still depends on a conflict occurring (so pair
with B or C for the guarantee).

---

## 4. Recommendation

- **Now:** Variant A is in (probabilistic improvement).
- **Next:** Variant B (scripted events) for the guaranteed, reproducible decision
  moment the study needs — and fold in Variant D so the Recommendations panel and
  the impact panel always agree.
- Variant C is a fallback if we want to keep conflicts emergent rather than
  authored.

---

## 5. Code references

- `backend/app/core/recommendation_generator.py` — `SCORE_MARGIN`, policy-switch recs
- `backend/app/core/impact_analysis.py` — conflict → impact items + per-train action
- `frontend/.../impact-panel/impact-panel.component.ts` — auto-pause + decision countdown
- `frontend/.../app.component.ts` — `demoSessionOpts()` (demo env + malfunction rate)
- [scripted-events-plan.md](scripted-events-plan.md) — Variant B design
