# Co-Learning across the automation levels — brief

> Dated working brief, 2026-07-10. Grounds the *Director Mode × Co-Learning*
> vision deck (`~/Downloads/Director_Mode_Co-Learning.pptx`, 8 slides,
> AI4REALNET-branded) in this repo, and settles one design question:
> **is Co-Learning a fourth mode, or a layer under the three we have?**
>
> Companion to [`co-learning-direction.md`](co-learning-direction.md) (the
> Level A / Level B thinking) and the authoritative
> [`interaction-modes-brief.md`](../reference/interaction-modes-brief.md).

---

## 0. The settled framing

The three interaction modes are **automation levels** — kept behaviourally
distinct mainly as **experiment conditions**, mapping onto a three-level
automation model:

```
Full Human Control  ─────►  Co-Learning  ─────►  Full AI-Based Control
(Recommendation, 3.1)       (3.3)                (Director, 3.4)
```

Co-Learning as a *mechanism* is **cross-cutting** — it operates across all three
levels. It is **not a fourth mode and not a parallel flag** (that would violate
the CLAUDE.md guardrail "keep mode semantics in the `InteractionMode` union").
It is a **shared service/layer** the three modes tap into differently.

What changes per level is the **granularity and source of the learning signal**,
and therefore *what* gets learned.

## 1. Signal economy per level

| Level | Learning signal (source) | AI learns | Human learns |
|---|---|---|---|
| **Recommendation** (3.1) | dense, per-decision: accept/reject each recommendation + "why?" | preference calibration on single decisions | trust/understanding via recommendation, anticipation, forecast, explainability — bounded by cognitive-load / attention |
| **Co-Learning** (3.3) | deliberate, reflective: own solution vs AI, impact compare, post-run reflection | trade-off logic behind deliberate comparisons | causal chains, KPI trade-offs, own heuristics, uncertainty bounds (deck slide 6) |
| **Director** (3.4) | sparse but high-value: goal-weight changes, directives, rare supervisor overrides in "safety mode" | directive→strategy mapping, weights→active strategy (deck slide 2) | supervision, setting the right high-level goals, the safety envelope |

Key asymmetry: a **supervisor override in Director is a much stronger signal**
than a click in Recommendation — rare but highly informative. Same mechanic,
different signal economy.

## 2. Architecture: shared store, mode-specific capture

The deck's slide 8 pipeline (**Event Logging → Context Snapshot → Rationale
Capture UI → LLM Extraction → Learning Store + Preference Matcher + Ranking
Adjustment**) maps cleanly onto this framing:

- The **Learning Store + Preference Matcher + Ranking Adjustment** is a
  **mode-agnostic shared service**.
- The **capture surfaces are mode-specific**:
  - Recommendation → the "why?" override flow (deck slide 7: **Ja / Nur diesmal /
    Nein** on a preference hypothesis).
  - Co-Learning → the reflection / what-if compare modules.
  - Director → goal-weighting (deck slide 2) + directive-level override.
- The **Learning Record** (deck slide 5) is the shared substrate every surface
  fills. Its crucial property: learn the **condition** under which a trade-off is
  preferred, *not* the option. Bad: "User likes Connection Protection". Good:
  "When the connection is critical, added delay is small, and ripple risk is low,
  the user prefers connection prioritisation." Only the **context scope** differs
  by mode: single train (Recommendation) vs strategy (Co-Learning) vs weighting
  profile (Director).

This is the concrete implementation path for **Level B** ("the AI learns to work
with the human") already sketched in `co-learning-direction.md` — and it needs
neither task-RL nor an event-based backend (both remain optional).

## 3. Gap analysis — deck slide 8 vs current repo

| Slide-8 block | Status in repo | Where |
|---|---|---|
| **1. Event Logging** | **Partial** — every override logged in all modes (`_appendDecision` → `DecisionLogEntry`, Tile A2), plus `coLearningFeedback` in Co-Learning. Timestamped + seq-numbered. | `frontend/src/app/core/session.store.ts` (`setOverride`), `frontend/src/app/core/decision-log.ts` |
| **2. Context Snapshot** | **Thin** — `DecisionLogEntry` captures `mode / handle / aiSuggestion / decisionTimeMs`, but **not** the rich "Kontext" of slide 5 (resources, rules, demand, disruptions, options, time-of-day). No point-in-time snapshot. | same |
| **3. Rationale Capture UI** | **Missing** — no "why?" prompt, no `reason` / `justification` field on any entry, no Ja/Nur-diesmal/Nein hypothesis confirmation. | — |
| **4. LLM Extraction Pipeline** | **Missing** entirely (LLM = reflection/explanation/preference-structuring, *not* deciding trains). | — |
| **5. Learning Store + Preference Matcher + Ranking Adjustment** | **Missing** entirely. The mockups' "Applied as ranking adjustment only, not a hard rule" is aspirational. Note: preferences are meant to feed the existing KPI/scenario **scoring** (inverse-RL-lite), which *is* already wired to the backend. | scoring hook exists; matcher/store do not |

**Data-model implication:** neither `CoLearningEntry` nor `DecisionLogEntry`
carries a rationale or a structured context snapshot today. Both are the natural
places to extend.

## 4. Suggested order (smallest useful first)

1. **Rationale field + "why?" override flow** with **Ja / Nur diesmal / Nein**
   (deck slide 7). Small, self-contained extension to `setOverride` /
   `CoLearningEntry` / the reflection surface. "Nur diesmal" guards against
   overfitting single decisions — do not drop it. No backend needed for a first cut.
2. **Learning Record type** (deck slide 5), context-conditioned, filled by the
   capture surfaces; start as a frontend store.
3. **Preference Matcher + Ranking Adjustment** as the shared service that nudges
   recommendation ranking — *ranking adjustment only, not a hard rule*.
4. **Director goal-weighting** surface (deck slide 2) as the Director-level
   capture, once 1–3 exist.

> Steps 1–3 are broken out with an MVP-vs-feedback-loop effort split and a
> file-grounded task list in
> [`workstream-b-rationale-capture.md`](workstream-b-rationale-capture.md).
> **Phase-2 flagship (scored strategy cards + WHY column) is done** — see that
> doc's Context for the seam it left (the Co-Learning-effect placeholder).

**AI4REALNET reuse check** (per CLAUDE.md): before building Level B's
model-of-the-operator, check
[`Tokener`](https://github.com/AI4REALNET/Tokener)'s Co-Learning approach and the
[`T3.3-3.4-HMI`](https://github.com/AI4REALNET/T3.3-3.4-HMI) reference HMI.

## 5. Guardrail reconciliation

This is consistent with "modes behaviourally distinct": the **modes stay distinct
as automation levels / experiment conditions**; Co-Learning is not a fourth mode
but a layer they consume differently. No new `InteractionMode` value, no parallel
flag — a shared learning service plus mode-specific capture UIs.
