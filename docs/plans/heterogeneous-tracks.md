# Heterogeneous tracks — track classes, costs & meaningful reroutes

> **Status:** Concept for discussion (not implemented).
> **Origin:** Came out of the "reroute is always n/a" question — reroute is only
> ever offered when a diverging switch lies before the block, so in our sparse
> demo topology the only real option is usually *Hold*. The deeper fix is not
> "more switches" but giving tracks **different characteristics**, so that a
> reroute becomes a genuine trade-off.

---

## 1. The idea

Not all tracks are equal. A realistic network has:

- **Through tracks** — the default, fast, preferred path (Durchfahrtsgleis).
- **Platform tracks** — also continuous, but closer to the platform; slower,
  used for stops or when the through track is occupied (Perrongleis).
- **Sidings / exception tracks** — only used in exceptional cases (blockage,
  overtaking, maintenance).

This mirrors the SBB User-Study-2 scenario directly: "steep section vs. flatter
diversion route" and the boarding situation at the north station (Turgi). So
heterogeneous tracks are not a nice-to-have — they are already implied by the
study scenario.

## 2. Why it matters here

- **Makes reroute a real decision.** Today reroute is binary "an alternative
  branch exists or not". With track classes it becomes a *trade-off*:
  "reroute via the platform track → +4 steps, but avoids the block." That is far
  more interesting than "Hold vs. n/a".
- **Gives the empty KPI sliders meaning.** `platformRouting` / `trainRouting`
  exist in the UI but are currently placeholder weights with no real signal
  behind them (`scenario_builder.scoring_weights_from_kpi`, "Provisional
  operationalisation"). Track costs are exactly the missing signal.
- **Ideal calibrated-trust material.** *When* is the exception track worth it,
  and does the human learn to trust the AI's call here? (See the co-learning /
  calibrated-trust thread.)

## 3. What Flatland does and does not model

- **All rail cells are equivalent.** No native per-cell cost and no per-cell
  speed. Speed is **per agent** (speed profile), not per track.
- Consequences:
  - "Slower track" cannot be a true per-cell speed. Model it instead as either
    (a) a **longer detour** (more cells = more steps — already free), or
    (b) a **soft time/cost penalty** in scoring (an approximation).
  - "Use only in exception" = a **soft routing cost**: prefer through tracks,
    propose platform/siding only when it pays off.

So this is an **overlay on top of Flatland**, not an engine change.

## 4. Proposed approach (overlay, no engine fork)

1. **Track-class / cell-cost layer** as session metadata: each rail cell carries
   a class (`through` / `platform` / `siding`) and a cost factor.
2. Wire that cost into:
   - **Scoring / recommender** — feed the real signal into `platformRouting` /
     `trainRouting`; a reroute over an expensive track costs in the score, so the
     recommender only suggests it when justified.
   - **What-if forward-sim** (the new `what-if-override` endpoint) — the feedback
     line then reads "Reroute via platform track → +4 steps, avoids block"
     instead of "n/a".
   - **Visualisation** — colour track classes on the Network Map (ties into
     layer-visibility and the visual-concept naming).

## 5. Dependency: curated/annotated layouts

To know which cells are platform vs. through, we need **authored or annotated
layouts** — which lines up with:
- the "hand-curated rail layout" option in [scripted-events-plan.md](scripted-events-plan.md), and
- the station scenario from the SBB protocol.

On randomly generated topology only **heuristic labelling** is possible (e.g.
"straightest path through a city = through track; parallel rails = platform"),
which is fuzzier and less controllable.

## 6. Connections

- [recommendation-reliability.md](recommendation-reliability.md) — makes reroute
  a substantive option, not just "Hold or n/a".
- [scripted-events-plan.md](scripted-events-plan.md) — curated layouts + events
  (an event could mark a track temporarily "exception only").
- [visual-concept.md](../reference/visual-concept.md) — track classes as a Network Map layer.
- Co-learning / calibrated trust — the exception track as a trust-calibration
  decision.

## 7. Open questions

1. Where do track classes come from — curated layouts, or heuristic labelling of
   generated topology?
2. Model "slower" as a longer detour (engine-free) or as a soft penalty
   (approximation)? Probably both, per track type.
3. How many classes do we need (through / platform / siding — or more)?
4. How is the cost surfaced to the operator (map colour, in the reroute
   feedback, in the KPI sliders)?
