# Interaction Logging — study data capture

> **Status:** Plan for review (2026-08-19). Supersedes the 2026 draft of this
> file, which predated the Decision Log. Roughly half of the original phase 1
> now exists; this rewrite records what is actually there, what is missing, and
> the decisions we need to take together before the next study.
>
> **Purpose:** make one session produce one complete, self-describing record —
> so that two sessions run under different modes or designs can be compared
> afterwards.

---

## 1. What a study needs, and what we can answer today

| Question | Data needed | Status |
|---|---|---|
| What did the operator do? | interventions, holds, releases, strategy choices | ✅ captured |
| How fast did they decide? | dwell time per decision moment | ✅ captured (`decisionTimeMs`) |
| Who owned each outcome? | human / AI / system | ✅ captured (`accountableOwner`) |
| Why did they do it? | reason chips, note, hypothesis response | ✅ captured (when prompted) |
| What did they think afterwards? | survey, reflection answers | ⚠️ stored, **not retrievable** |
| **Under which condition?** | mode, design, policy, KPI weights, timings | ❌ **not in any record** |
| **On which scenario?** | seed, grid, agents, malfunction params | ❌ not in the export |
| **Which participant?** | participant + condition id | ❌ does not exist |

The short version: the **dependent** variables are well captured, the
**independent** ones are not. That is exactly the wrong way round for a
comparison of modes or designs.

---

## 2. Verified inventory (what exists today)

### 2.1 Decision Log — the good part

[`decision-log.ts:42`](../../frontend/src/app/core/decision-log.ts) defines a
solid analysis schema: `seq`, wall-clock `t`, `simStep`, `mode`, `handle`,
`accountableOwner`, `action`, `aiSuggestion`, `decisionTimeMs`, plus the
Workstream-B fields `rationale`, `preferenceHypothesis`, `hypothesisResponse`,
`valueAxis`, `tradedAway`.

Written from four choke points in `session.store.ts`:

| Event | Site |
|---|---|
| Any override, all modes (owner human/ai) | `setOverride` → `_appendDecision` (~:1599) |
| System safe-default hold | `systemHold` (~:1656) |
| Release / proceed | `clearOverride` (~:1681) |
| Director strategy choice | `recordStrategyChoice` (~:660) |

Export exists: `exportJson()` in
[`decision-log-panel.component.ts:123`](../../frontend/src/app/features/decision-log/decision-log-panel.component.ts)
writes `{ version, exportedAt, session, mode, entries }`.

### 2.2 Everything else, and where it lives

| Data | Storage | Survives reload | Retrievable |
|---|---|---|---|
| Decision Log | in-memory signal, cap 500 | ❌ | ✅ manual JSON export |
| Survey answers | `localStorage` `flatland_survey_<sid>_post-session-<mode>` | ✅ | ❌ DevTools only |
| Co-Learning reflection | `localStorage` `flatland_colearning_reflection_<sid>` | ✅ | ❌ DevTools only |
| Learning records | `localStorage` `flatland_learning_records` (**global, not per session**) | ✅ | ❌ DevTools only |
| Session settings | `localStorage` `flatland_ui_session_settings_v1` | ✅ | ❌ not attached to any session |
| Trajectories, KPIs | in-memory signals | ❌ | ❌ |
| Backend session | `SessionManager._sessions` dict ([`session_manager.py:51`](../../backend/app/core/session_manager.py)) | ❌ | ❌ no log endpoints |

### 2.3 The condition descriptor already exists — unattached

`persistSessionSettings()` in
[`app.component.ts:559`](../../frontend/src/app/app.component.ts) already
serialises exactly the object a condition needs: `width`, `height`, `agents`,
`maxSteps`, `seed`, malfunction parameters, **and the design knobs**
`surveyParts`, `reflectionLimit`, `decisionCountdown`, `recommendationDuration`,
`autoPauseOnConflict`, `demoMalfunctionTypes`.

It is written for convenience (pre-fill the next session), overwritten each
time, and never stamped into a session record. Reusing this object as the
condition descriptor is the cheapest correct move in this whole plan.

---

## 3. Known failure modes

1. **Silent truncation.** `DECISION_LOG_CAP = 500`, oldest dropped
   ([`session.store.ts:466`](../../frontend/src/app/core/session.store.ts)). A
   long session loses its beginning with no warning.
2. **Volatility.** A reload, a session reset (`clearDecisionLog()`) or a backend
   restart destroys the log. No autosave.
3. **Manual export.** One click, on a panel that must be visible in the current
   layout. If the facilitator forgets, the session is gone.
4. **No identity.** Session ids are random and tied to no participant, no
   condition, no run.
5. **Fragmentation.** Four `localStorage` namespaces plus one in-memory signal;
   nothing joins them, and `flatland_learning_records` is not even per session.
6. **No context stream.** Mode switches, policy swaps, KPI re-weights and
   Director directives leave no trace — see §1.

---

## 4. Design

### 4.1 One session record

```ts
interface SessionRecord {
  version: 2;
  header: SessionHeader;
  decisions: DecisionLogEntry[];   // existing schema, unchanged
  context:  ContextEvent[];        // new, §4.3
  survey:   { config: string; answers: SurveyAnswers; submittedAt: number | null };
  reflections: ReflectionSubmission[];
  learning: LearningRecord[];      // filtered to this session
  kpis:     ScenarioKpis | null;   // final, for the outcome measure
}
```

One file, one session, self-describing. No new state where existing state
already holds the data — the record is assembled at export time from the
signals and `localStorage` entries that exist.

### 4.2 Session header

```ts
interface SessionHeader {
  sessionId: string;
  participantId: string;      // entered at session setup
  conditionId: string;        // e.g. "B2-director-noforecast"
  runIndex: number;           // nth session for this participant
  startedAt: number; endedAt: number | null;
  mode: InteractionMode;      // mode at start; changes appear in `context`
  config: SessionSettings;    // the object from §2.3, verbatim
  activePolicy: string;
  layoutId: string | null;    // which surface arrangement was on screen
  appVersion: string; backendVersion: string;
}
```

`participantId` and `conditionId` are the two fields without which nothing else
can be compared. Everything else in the header is already available.

### 4.3 Context events (the missing independent variables)

```ts
type ContextEventType =
  | 'session_start' | 'session_end' | 'episode_done'
  | 'mode_change' | 'policy_change' | 'kpi_change'
  | 'directive_start'                     // Director: KPI + policy directive
  | 'play' | 'pause' | 'step' | 'speed_change'
  | 'layout_change'                       // which widgets were on screen
  | 'survey_open' | 'survey_submit'
  | 'reflection_open' | 'reflection_submit';
```

Same envelope as a decision entry (`seq`, `t`, `simStep`, `mode`, `type`,
`payload`) so both streams merge on a common time axis in analysis.

Emit sites all exist as single choke points — this is additive, no behavioural
change: `setInteractionMode()`, `setActivePolicy()`, the KPI filter's setter,
the Director directive start, the play/pause controls, the survey and
reflection components.

### 4.4 Overflow instead of silent drop

When the cap trims, push the trimmed entries into an overflow buffer that the
export includes, or raise the cap and warn once. Never lose the beginning of a
session without saying so.

### 4.5 Export and autosave

- **One button, whole record.** "Export session data (JSON)" — not one export
  per panel. Reuse the existing download helper.
- **Autosave** the assembled record to `localStorage` under
  `flatland_session_record_<sid>` on episode end and on survey submit, so a
  forgotten click is recoverable.
- Filename `flatland-<participantId>-<conditionId>-<runIndex>-<sid>.json`, so a
  folder of exports is analysable without opening the files.

### 4.6 Backend sink (later)

`POST /sessions/{id}/record` plus persistence, so data does not depend on one
browser profile. The `explore_db` branch is the natural landing place. The
frontend stays the source of truth; the sink is a mirror.

---

## 5. Phases

| Phase | Content | Effort |
|---|---|---|
| **P1** | Session header (incl. participant/condition id at setup), single whole-record export, autosave | S–M |
| **P2** | Context events (§4.3), overflow handling | M |
| **P3** | Join survey + reflections + learning records into the record; make `coLearningFeedback` a derived view of the decision stream | M |
| **P4** | Backend sink + persistence (`explore_db`), central collection | L |

P1 alone removes the two failure modes that lose data outright (no identity, no
autosave). P1+P2 make a mode/design comparison possible at all. P4 is a
convenience and a robustness upgrade, not a precondition.

---

## 6. Decisions we need to take together

1. **Where does truth live?** Browser export as the record of study, with the
   backend as a later mirror — or backend-first from the start?
   *Recommendation: browser first (P1–P3), sink in P4. It unblocks the next
   study without a schema negotiation.*
2. **How does the participant id get in?** A field in session setup, a URL
   parameter for the facilitator, or a study-mode dialog?
   *Recommendation: a field in the existing setup form, remembered per run
   index — least new UI.*
3. **Free text is personal data.** Reflection notes and the open survey question
   are free text. Consent wording, retention, who holds the files, and whether
   we anonymise on export need an owner. **This blocks nothing technically and
   everything ethically.**
4. **Granularity.** Semantic events only (this plan), or also UI telemetry —
   hovers, panel opens, gaze-substitutes? *Recommendation: semantic only for
   now. Telemetry is a separate decision with real cost and real noise.*
5. **Reproducibility ambition.** Should the record be enough to *replay* a
   session (seed + full trajectory), or only to *describe* it? The former pulls
   in the deferred save/load work (§8).
   *Recommendation: describe now, replay later — the header already carries the
   seed, which covers most of it.*
6. **One file per session, or an append-only run file per participant?**
   *Recommendation: one file per session; joining is trivial in analysis, and a
   crashed session cannot corrupt the others.*

---

## 7. Guardrails

- Frontend-first; no payload or trajectory changes. Do not touch
  `_recordTrajectory` compression or the scenario-refresh throttling.
- `InteractionMode` stays the only mode flag; `mode_change` events describe it,
  they do not duplicate it.
- Logging is best-effort: a `localStorage` quota failure must never break the
  UI (try/catch, as the existing persistence does).
- Do not duplicate state. The record is *assembled* from existing signals and
  storage keys; `coLearningFeedback` becomes a derived view, not a second truth.
- Keep the existing `DecisionLogEntry` schema — it works; only the envelope
  around it changes.

---

## 8. Out of scope

- **Save / load of session state.** Frontend snapshot (config + seed + layout +
  log → deterministic re-run) is the cheap version; true Flatland env-state
  serialisation is the expensive one. Revisit after P2; the header covers most
  of the cheap version already.
- **Automatic analysis.** The record is an input for R/Python, not a dashboard.
- **Cross-session participant modelling.** `flatland_learning_records` is
  currently global; making it per-session is in P3, making it a longitudinal
  model is not in this plan.

---

## 9. Related

- [`widget-a2-decision-log.md`](widget-a2-decision-log.md) — the decision stream
  as a surface; this plan is its persistence and export story.
- [`scenario-variants.md`](scenario-variants.md) — what a condition can vary.
- [`onboarding-tickets-2026-06.md`](../archive/onboarding-tickets-2026-06.md) — experiment
  setup discussion tickets.
- AI4REALNET **D3.2** (agent-as-a-service KPI + event monitoring) is the
  consortium-side counterpart of P4; align field names there if we build it.
