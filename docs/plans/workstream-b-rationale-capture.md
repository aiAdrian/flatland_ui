# Workstream B — Rationale capture & the Co-Learning learning loop

> **Status (2026-07-11): Tier 1 done & live-verified** — built by GLM 5.2, reviewed
> and end-to-end verified in the browser. See
> [`../delegation/2026-07-11-mvp-rationale-capture-glm.md`](../delegation/2026-07-11-mvp-rationale-capture-glm.md).
> Tier 2 remains open.
>
> Dated plan, 2026-07-10. Detailed breakdown of Workstream B from
> [`colearning-across-modes.md`](colearning-across-modes.md) §4 (deck slides 5 & 7:
> "override → why? → preference hypothesis", plus slide 8 steps 3–5). Split into a
> small **MVP** (build now) and a larger **feedback loop** (separate, later,
> touches the backend and has an open design question).

## Context

Today the app **captures** human overrides but not their **rationale**. On
`setOverride` ([session.store.ts:1053](../../frontend/src/app/core/session.store.ts))
a `CoLearningEntry` ([session.store.ts:36](../../frontend/src/app/core/session.store.ts):
`step / handle / humanAction / aiSuggestion / timestamp`) and a `DecisionLogEntry`
([decision-log.ts:35](../../frontend/src/app/core/decision-log.ts)) are appended —
but neither carries **why** the human chose differently, nor a structured
preference hypothesis. The deck's core idea (slide 5) is to learn the *condition*
under which a trade-off is preferred, not the option. This workstream adds the
capture + display of that signal. It also completes the Co-Learning-effect
placeholder shipped in the recommendations panel (Phase 2 flagship).

Guardrail: Co-Learning is a **cross-cutting shared layer**, not a fourth mode (see
[`colearning-across-modes.md`](colearning-across-modes.md) §0). The capture surface
is mode-specific; the store is mode-agnostic.

---

## Tier 1 — MVP (build now): capture + show the learning signal

Frontend-only. **No LLM, no backend, no ranking feedback.** Comparable in size to
the Phase-2 flagship, slightly less.

1. **Extend the data model** — optional, backward-compatible fields on
   `CoLearningEntry` (and mirror the rationale onto `DecisionLogEntry` where
   useful):
   - `rationale?: string` — the chosen "why".
   - `preferenceHypothesis?: string` — the generated "when {context}, prefer {choice}".
   - `hypothesisResponse?: 'yes' | 'once' | 'no'`.
   *Trivial; touches the two interfaces and the append sites in `setOverride`.*

2. **"Why?" prompt after an override** — the hook already sits at exactly one
   place (`setOverride`, session.store.ts:1053). Surface a small inline prompt in
   the **co-learning-reflection** panel
   ([features/co-learning-reflection](../../frontend/src/app/features/co-learning-reflection))
   and/or the recommendations panel: a short set of **structured reasons**
   (chips) plus an optional free-text note. LLM-free first cut. *Small.*

3. **Preference hypothesis + Ja / Nur diesmal / Nein** (deck slide 7) — generate
   the hypothesis as a **template over the context fields** (no LLM):
   `"When {connection critical} and {added delay ≤ N} and {ripple low}, you prefer
   {chosen strategy}."` Confirm with three buttons. **Keep "Nur diesmal"** — it is
   the explicit overfitting guard (a one-off decision must not become a rule).
   *Small.*

4. **Frontend Learning Store** — a small `core/` service holding confirmed
   records (in-memory; optional `localStorage` for within-browser persistence).
   Display confirmed records as **Learning-Record cards**, reusing the Phase-1
   primitives (`reasoning-list`, `metric-chip`, `score-badge` for the confidence).
   *Small–medium.*

**Reuse, don't rebuild:** the Phase-1 `shared/ui/` primitives cover the display;
the capture hook and the two entry types already exist.

**Deliverable:** deck slides 5 & 7 made real; the recommendations panel's
Co-Learning-effect placeholder gets real content.

## Tier 2 — the feedback loop (separate, later): make preferences act

Larger; touches the backend; carries the open design question. **Do not bundle
into the MVP.**

- **Preference Matcher + Ranking Adjustment** — confirmed preferences must
  actually re-order future recommendations ("ranking nudge, not a hard rule").
  This reaches into scenario **scoring** (today weighted backend-side, surfaced
  as `Scenario.score`). *Open question:* nudge in the frontend re-rank layer, or
  push an adjustment into the backend scoring? (See
  [`colearning-across-modes.md`](colearning-across-modes.md) open points.)
- **Cross-session persistence** + optional **LLM extraction** (rationale →
  structured schema, deck slide 8 step 4) — needs a backend endpoint.
- **AI4REALNET reuse check** (per CLAUDE.md): before building the
  model-of-the-operator, check [`Tokener`](https://github.com/AI4REALNET/Tokener)
  (Co-Learning) and the [`T3.3-3.4-HMI`](https://github.com/AI4REALNET/T3.3-3.4-HMI)
  reference HMI.

## Do-not-touch

`_recordTrajectory` and the scenario-refresh throttling (session.store), the
`_recoverPolicyAndRetry*` fallbacks, and the recommendations-panel countdown /
`bus.emit` paths (Phase-2 flagship left them intact).

## Verification (MVP)

1. `preview_start` frontend + backend; guided demo, **Recommendation** (or
   **Co-Learning**) mode.
2. Override a train's next action → the "Why?" prompt appears.
3. Pick reasons, confirm the hypothesis with **Ja / Nur diesmal / Nein**.
4. Confirm a Learning-Record card renders (and, if `localStorage` used, survives a
   reload); `read_console_messages` clean.
5. "Nur diesmal" does **not** create a persisted rule; "Ja" does.
6. `npm run lint:styles` green (new SCSS hex-free); existing `backend/tests/` green.

## Open questions / risks

- **Hypothesis quality without an LLM** — the template must read naturally across
  contexts; keep it simple and honest, mark generated text as a hypothesis.
- **Context scope per mode** — single train (Recommendation) vs strategy
  (Co-Learning) vs weighting profile (Director); the Learning Record's context
  block differs (see [`colearning-across-modes.md`](colearning-across-modes.md) §2).
- **Connection/Ripple proxies** (from the Phase-2 flagship) feed the hypothesis
  context — clarify the real KPI definitions with the team before Tier 2.
