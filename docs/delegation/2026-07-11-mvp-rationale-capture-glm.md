# Delegation record — Workstream B Tier 1 (Rationale Capture MVP)

**Date:** 2026-07-11 · **Delegated to:** GLM 5.2 (separate Claude Code session)
· **Reviewed & live-verified by:** Claude (Opus 4.8) · **Branch:** `explore_db`
· **Source plan:** [`workstream-b-rationale-capture.md`](../plans/workstream-b-rationale-capture.md) (Tier 1 only)

Archived for later reflection (see the "reflects on AI usage" practice). Captures
what was delegated, what came back, and the review outcome.

## What was delegated (the brief, verbatim intent)

Build **only Tier 1** of the Co-Learning rationale-capture MVP: capture human
overrides with a reason + confirm a context-conditioned preference hypothesis,
and show confirmed "Learning Records". Frontend-only — **no LLM, no backend, no
ranking feedback** (all Tier 2). Four steps:

1. Extend `CoLearningEntry` / `DecisionLogEntry` with optional `rationale?`,
   `preferenceHypothesis?`, `hypothesisResponse?: 'yes'|'once'|'no'`.
2. "Why?" prompt after a human override (hook at `setOverride`,
   `session.store.ts`) — structured reason chips + free-text, LLM-free.
3. Preference hypothesis as a **template over context fields** + **Ja / Nur
   diesmal / Nein**. "Nur diesmal" = overfitting guard ('once' not persisted).
4. Frontend Learning Store (in-memory + `localStorage`) + Learning-Record cards
   **reusing the Phase-1 `shared/ui/` primitives** (no new visual primitives).

Hard constraints: Angular standalone + signals, SBB Lyne, **no hardcoded
colours** (`npm run lint:styles` green), don't touch `_recordTrajectory` /
scenario-refresh throttling / `_recoverPolicyAndRetry*` / the countdown &
`bus.emit` paths; no fourth `InteractionMode`.

## What came back

New: `core/learning-store.service.ts`, `features/rationale-capture/*`,
`features/learning-records/*`. Modified: `session.store.ts` (+`pendingRationale`
state, `submitRationale`/`dismissRationale`, `_snapshotRationaleContext`,
`_appendDecision` returns `seq`), `decision-log.ts`, `recommendations-panel.{ts,html}`
(hosts the surfaces in Recommendation mode), `co-learning-reflection.{ts,html}`
(hosts them in Co-Learning mode; force-opens while a prompt is pending).

Trigger condition (deliberately narrow): `owner === 'human' && mode !== 'director'
&& (aiSuggestion != null || isCoLearning())`. Rationale patched onto the exact
`CoLearningEntry` (by timestamp) and `DecisionLogEntry` (by seq).

GLM's self-report: ✅ `ng build`, ✅ `lint:styles`, ✅ backend tests — but
⚠️ **no live browser run** (no browser automation in that session).

## Review outcome — CORRECT, and now live-verified

Code review: clean, faithful to the brief, guardrails held (tokens-only, no
touched paths, mode-agnostic store + mode-specific surfaces). The seq/timestamp
patching is robust (captured ids pin the exact entry).

Live verification (guided demo, Recommendation mode, real `setOverride`):
- "Why?" prompt renders (deck slide 7): context "Zug 6 → Halten statt AI:
  Switch to Shortest Path", chips, note, templated hypothesis, three buttons.
- Hypothesis templated honestly from the real scenario proxies.
- **'yes'** → record created, **persisted to `localStorage`**,
  `confirmedPreferenceCount` → 1, DecisionLogEntry seq=1 patched.
- **'once'** → visible in session, **not** persisted, confirmed count unchanged.
- **'no'** → nothing recorded.
- Learning-Record card renders reusing the Phase-1 primitives (deck slide 5).
- **Reload** → only the persisted 'yes' survives (overfitting guard holds).
- No console errors; `lint:styles` green (re-confirmed).

## Known minor limitations (acceptable for MVP; note for Tier 2)

- `pendingRationale` is a **single slot** — a second override before answering
  the first discards the first's prompt (the override itself stays logged).
- Context is derived from the **top recommendation's** scenario, not necessarily
  the overridden train's own situation (proxy limitation).
- Patch is skipped if the `DecisionLogEntry` was trimmed by the rolling cap
  between override and submit (the Learning Record is still created).
- Prompt copy is German; the rest of the app mixes DE/EN (i18n is a separate,
  already-noted task).

## Status

**Tier 1 done & verified.** Tier 2 (Preference Matcher + Ranking Adjustment,
cross-session beyond localStorage, optional LLM extraction, Director
goal-weighting capture, AI4REALNET reuse check) remains open — see the source plan.
