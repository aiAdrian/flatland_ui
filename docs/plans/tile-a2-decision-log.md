# Tile A2 — Decision Log & Accountability Strip

> Spec following [tile-authoring-process.md](../reference/tile-authoring-process.md).
> Status: **first cut built.** See
> `frontend/src/app/features/decision-log/decision-log-panel.component.ts` +
> `frontend/src/app/core/decision-log.ts` and the `decisionLog` signal in
> `SessionStore`; the row in `docs/reference/panel-mode-matrix.md`. Backend
> `POST /sessions/{id}/log` mirror remains deferred (§4).

## 1. Identity
- **Name:** Decision Log & Accountability Strip
- **`kind`:** Capitalization (the loop's "what got decided and by whom"
  record — see `interaction-framework.md` §2)
- **`granularity`:** detail (a session strip/list, not an overview badge)
- **Default zone:** right column, below Recommendations/Risk & Uncertainty, or
  a dedicated bottom strip — decide during build based on how long the list
  gets in practice
- **Sources:** owner's own research line (accountability/control seam) +
  AI4REALNET **D3.1** (control-accountability alignment) + the WP4 validation
  KPI catalog (§5b below — confirmed via the AI4REALNET GitHub org, not
  assumed)
- **Grounding:** Boos/Günter/Grote/Kinder (2013) Control-Accountability
  alignment triads (Transparency↔Visibility, Predictability↔Responsibility,
  Influence↔Liability); Kapoor & Narayanan's HITL-as-alibi critique — logging
  *who* decided is what makes "human in the loop" a real claim instead of a
  buck-passing gesture (see `interaction-framework.md` §5b for the full
  grounding, already written for this framework).

## 2. Promise
Every decision in a session — human or AI-default, accepted or overridden —
becomes an **owned, timestamped event** the operator (and later, a
researcher) can see as a session strip: who decided, when, how long it took,
whether it was an accept or an override. This is the concrete, inspectable
form of "human in control," not just a slogan, and it is the raw material for
override-rate / friction-asymmetry / decision-time metrics used elsewhere
(A1's overtrust proxy, A3's track record).

## 3. Per-mode behaviour
- **Recommendation:** each strip entry shows the AI's suggestion alongside
  what the human actually chose (accept vs. override) — the comparison *is*
  the point.
- **Co-Learning:** entries show the option the human formulated vs. the
  neutral alternatives shown (no "AI was right/wrong" framing) — feeds the
  reflection prompt ("here's what you decided vs. what was neutrally
  available").
- **Director:** entries are mostly system auto-decisions (owner = AI); the
  operator's entries are the rarer **exception interventions** — the strip
  makes this asymmetry visible (how often did the human have to step in?).

## 4. System interaction
Data **in** — reuses existing choke-points, no new capture mechanism (per
`interaction-logging-plan.md` §4, already identified):

| Event | Emit from (existing code, verified) |
|---|---|
| `intervention` (human override) | `SessionStore.setOverride()` (`session.store.ts:942`) — already builds a `CoLearningEntry {step, handle, humanAction, aiSuggestion, timestamp}` in Co-Learning; this tile needs the same capture **in all three modes**, not just Co-Learning |
| `decision` (impact-panel outcome) | `impact-panel.component.ts` `applyOption()` (:336) / `_apply()` (:360) / `dismiss()` (:248) — hold/reroute/proceed/dismiss |
| `system_hold` (safe default, NOT a human decision) | `SessionStore.systemHold()` (:987) — explicitly documented in code as *not* a human intervention; the log must keep this distinct (`accountableOwner: 'system'`), not conflate it with an override |
| `mode_change` | `SessionStore.setInteractionMode()` |

Actions **out:** none that mutate sim state — this tile is purely a read
model over events already happening elsewhere. Optional: click a strip entry
to jump to/highlight that train (same interaction pattern as impact-panel
rows).

Backend: **none required for the first cut** — entirely a frontend read
model over `SessionStore` state, persisted to `localStorage` per
`interaction-logging-plan.md` §3. A backend `POST /sessions/{id}/log`
mirror is explicitly deferred (that plan's §3, "optional later").

## 5. Allocation & accountability touchpoints

### 5a. The core mechanism
- **Every entry has an `accountableOwner`**: `'human'` (override/formulated
  option), `'ai'` (accepted recommendation / autonomous Director action), or
  `'system'` (safe-default hold, e.g. `systemHold()` — deliberately not
  attributed to either party, per the code's own comment at
  `session.store.ts:987`).
- **Decision events schema** (extends `interaction-logging-plan.md`'s
  `LogEvent`, does not replace it):
  ```ts
  interface DecisionLogEntry {
    seq: number; t: number; simStep: number; mode: InteractionMode;
    handle: number;
    accountableOwner: 'human' | 'ai' | 'system';
    action: 'hold' | 'reroute' | 'proceed' | 'accept' | 'override' | 'dismiss';
    aiSuggestion: string | null;
    decisionTimeMs: number | null;   // null for system/autonomous entries
  }
  ```
- This directly powers: override-rate, friction-asymmetry (how much harder is
  overriding vs. accepting), and — combined with A1's shown-reliability field
  — the decision-time ÷ acceptance-rate overtrust proxy already named in the
  A1 spec (§5).

### 5b. WP4 validation alignment (checked against the AI4REALNET GitHub org)

**Confirmed finding, not assumed:** the consortium's own WP4 validation
infrastructure — [`AI4REALNET/ai4realnet-orchestrators`](https://github.com/AI4REALNET/ai4realnet-orchestrators)
("AI4REALNET Validation Campaign Hub Orchestrator", integrates with the
"FAB" Validation Campaign Hub) — already has a **Railway domain module**
(`ai4realnet_orchestrators/railway/`) and, in
`orchestrator_definitions.py`, a named catalog of WP4 KPIs for Railway. Most
are still unimplemented (commented-out scaffolding; the 3 that exist —
`KPI_AF_029` AI Response time, `KPI_NF_045` Network Impact Propagation,
`KPI_PF_026` Punctuality — are `raise NotImplementedError()` stubs for
Docker-based closed-loop RL-agent benchmarking, a different evaluation mode
than our live HMI session). The **human-factors KPIs have no code at all** —
per the repo's own README, those are collected via the **interactive-loop**
workflow (partial auto-upload + manual completion via FAB UI / survey,
i.e. the `hmisurveys` repo's role), which is exactly our situation.

This tile's fields should be **named so they map cleanly onto these KPI IDs
later**, without a rename exercise, if the project ever participates in a
validation campaign. No campaign integration work is being done now — this
is purely a naming/scoping precaution.

| Our field / metric | WP4 KPI (Railway) | Note |
|---|---|---|
| Override rate (`accountableOwner: 'human'` ÷ total) | **KPI-HS-003** Human intervention frequency | direct mapping |
| Accept-vs-override ratio | **KPI-AS-005** Agreement score | direct mapping |
| `decisionTimeMs` | **KPI-HS-023** Human response time | direct mapping |
| — (not this tile; backend latency) | **KPI-AF-029** AI Response time | different metric, note so it isn't confused with `decisionTimeMs` |
| Session reflection answers (planned, see `co-learning-reflection`) | **KPI-RS-091..096** Reflection on trust / agency / de-skilling / over-reliance / additional training / biases | our reflection module already covers nearly the same taxonomy — align question categories with these IDs when reflection is next revised, not in this task |
| A1's shown-reliability + reliance signal | **KPI-TS-038/039** Trust in AI / Trust towards the AI tool | cross-reference in A1, not owned by A2 |
| D1's allocation display | **KPI-HS-018** Human control/autonomy over the process | cross-reference in D1, not owned by A2 |

**Scope decision:** do **not** build any FAB/orchestrator integration now —
that infrastructure is operated by WP4 admins against submitted benchmark
runs, not something our HMI calls into. The only action this task takes is
naming the schema fields above so a future export mapping is a rename, not a
redesign.

## 6. Acceptance scenario
Over a 10-minute Recommendation-mode session, the operator accepts 6
suggestions and overrides 4. The strip shows all 10 entries in order, each
tagged `accountableOwner: 'human'` (the override + accept decisions) with
`decisionTimeMs` populated, plus 2 `system_hold` entries clearly marked as
not human decisions. **Measurable success:** override rate and mean
decision-time are directly readable from the strip without needing the raw
JSON export, and the two `system_hold` entries are visually distinct from
human overrides (an operator should never look at the strip and think the
system's safe-default was their own decision).

## 7. Effort & changes
- **Effort:** M (rides on `interaction-logging-plan.md`, which does most of
  the schema/capture design already; this task adds the *tile* + extends
  capture to all three modes, not just Co-Learning, + the `accountableOwner`/
  `system` distinction).
- **Touch:** new `features/decision-log/`; extend `SessionStore.setOverride()`
  capture to fire in all modes (not gated to `isCoLearning()`); add
  `accountableOwner` tagging at `systemHold()` and at Director autonomous
  actions; register in `panel-plugin-host` (+`@switch`), `layout-designer`
  palette, `PANEL_MODE_AVAILABILITY` (all modes), `PanelDefinition.kind=
  'capitalization'`; JSON export button (reuse the download-helper pattern
  already in `layout-designer.component.ts`).

## 8. Open questions / risks
- Does capturing intervention data in **all** modes (not just Co-Learning)
  change `coLearningFeedback`'s existing contract/consumers (the reflection
  panel reads it)? Needs a check before widening capture — may need a
  separate signal rather than repurposing `coLearningFeedback` directly.
- How long does the strip get in a long session, and does it need
  pagination/collapse — or is a rolling "last N + full export" enough for
  the first cut?
- Reflection-question alignment to KPI-RS-09x (§5b) is flagged for later,
  not this task — don't let it scope-creep into a reflection-module rewrite
  here.
