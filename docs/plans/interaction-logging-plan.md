# Interaction Logging — Behaviour & input capture for later analysis

> **Status:** Draft for discussion (no implementation yet)
> **Context:** For the user studies we need a reproducible record of what the
> operator did and thought during a session — every intervention, every
> reflection answer, every mode/priority change — exportable for offline
> analysis. Some of this already exists in scattered form (`coLearningFeedback`,
> per-session reflection answers in `localStorage`); this plan unifies it into
> one structured, exportable **interaction log**.
> Feeds toward AI4REALNET **D3.2** (agent-as-a-service KPI + event monitoring),
> but is frontend-first and needs no backend to start.

---

## 1. Goal

One append-only, timestamped event stream per session that answers:

- **What did the human do?** interventions (override + the AI hint on the
  table at that moment), decisions taken/dismissed, mode switches, policy /
  KPI changes, directives (Director), play/pause/step.
- **What did the human think?** reflection answers (free text + which prompt),
  each reflection *submission* as its own entry (reflections are now
  repeatable — see [[co-learning-reflection]] `close()`), not one overwrite.
- **Under what conditions?** sim-step, interaction mode, active policy, KPI
  weights, episode-done, session config (seed, grid, agents, malfunction
  params).

Exportable as JSON for R/Python analysis. No PII beyond what the operator
types into reflection notes.

---

## 2. Event schema (draft)

```ts
type LogEventType =
  | 'session_start' | 'session_end' | 'episode_done'
  | 'mode_change'                       // recommendation | co-learning | director
  | 'policy_change' | 'kpi_change'
  | 'directive_start'                   // Director: KPI+policy directive → autonomous run
  | 'play' | 'pause' | 'step'
  | 'intervention'                      // human override (handle, action, aiSuggestion)
  | 'decision'                          // impact-panel item hold/reroute/proceed/dismiss
  | 'reflection_open' | 'reflection_submit';

interface LogEvent {
  seq: number;                 // monotonic per session
  t: number;                   // Date.now()
  simStep: number;             // store.elapsedSteps()
  mode: InteractionMode;
  type: LogEventType;
  payload: Record<string, unknown>;   // type-specific (see below)
}
```

Example `payload`s:

| type              | payload                                                        |
|-------------------|---------------------------------------------------------------|
| `intervention`    | `{ handle, humanAction, aiSuggestion }` (already in `CoLearningEntry`) |
| `decision`        | `{ handle, action: 'hold'\|'reroute'\|'proceed'\|'dismiss' }`  |
| `reflection_submit` | `{ answers: Record<questionKey,string>, interventionCount }` |
| `kpi_change`      | `{ priorities: KpiPriorities, weights: KpiWeights }`          |
| `mode_change`     | `{ from, to }`                                                 |
| `session_start`   | `{ config, seed, sessionId }`                                  |

The session header (config, seed, sessionId, appVersion) is stored once
alongside the event array so an export is self-describing.

---

## 3. Storage & export

- **`InteractionLogService`** (or a `SessionStore` sub-signal) holds
  `logEvents = signal<LogEvent[]>([])` plus the session header.
- Persist to `localStorage` under `flatland_interaction_log_<sessionId>`
  (mirrors how reflection answers already persist per session), debounced.
- **Export:** menu item **“Export session log (JSON)”** → `Blob` download
  `flatland-log-<sessionId>-<date>.json`. (There is already a download helper
  pattern in `layout-designer.component.ts` to reuse.)
- Optional later: `POST /sessions/{id}/log` to the backend for central
  collection (aligns with D3.2). Frontend stays the source of truth.

---

## 4. Integration points (where to emit)

All emit sites already exist as single choke-points — logging is additive,
no behavioural change:

| Event               | Emit from                                                        |
|---------------------|------------------------------------------------------------------|
| `intervention`      | `SessionStore.setOverride()` (already builds `CoLearningEntry`)   |
| `mode_change`       | `SessionStore.setInteractionMode()`                              |
| `policy_change`     | `SessionStore.setActivePolicy()`                                 |
| `kpi_change`        | wherever `kpiPriorities` is set (KPI filter)                     |
| `decision`          | `impact-panel` `_apply()` / `dismiss()`                          |
| `reflection_submit` | `co-learning-reflection` `close()` (capture current `answers`)   |
| `reflection_open`   | `reflectionRequested` → true                                     |
| `session_start/end` | `SessionStore.newSession()` / `endSession()`                    |

Reuse existing state — don't duplicate: `coLearningFeedback` becomes a
*derived view* of `intervention` events (or the log wraps it), so there is
one source of truth.

---

## 5. Guardrails

- Frontend-only to start; **no** payload/trajectory changes (respects the
  CLAUDE.md guardrails). Do not touch `_recordTrajectory` compression.
- Keep `InteractionMode` union as the only mode flag.
- Log is best-effort: a `localStorage`/quota failure must never break the UI
  (wrap in try/catch, same as existing persistence).
- Privacy: reflection notes are free text — flag this in any study consent;
  export is local/manual until a backend sink + consent exists.

---

## 6. Phased rollout

1. **P1** — `InteractionLogService` + emit `intervention`, `mode_change`,
   `reflection_submit`, `session_start/end`; JSON export menu item.
2. **P2** — add `decision`, `kpi_change`, `policy_change`, `directive_start`,
   `play/pause/step`; make `coLearningFeedback` a derived view.
3. **P3** — optional backend sink (`POST …/log`) for central collection (D3.2).

---

## 7. Out of scope (deferred)

- **Save / Load of session state.** Two levels were discussed:
  (A) frontend snapshot of config + seed + layout + log → deterministic
  reproduction via seed (no backend); (B) true Flatland env-state
  serialization for real resume (backend, larger — coordinate with Adrian).
  Not started; revisit after logging P1/P2. The interaction log’s
  self-describing session header (§2) already gives most of what level A
  needs.
