# Docs maintenance — audit of 2026-08-19

> Full pass over all 61 markdown docs plus a check of where AI4REALNET stands on
> logging. Every claim below was verified against the code or against the live
> upstream repos on 2026-08-19; the check is named so it can be repeated.
>
> Three parts: **§1** plan currency, **§2** the other docs (overlaps, stale
> pointers), **§3** AI4REALNET logging — who needs what, and through which path.

---

## 0. Headline findings

1. **`docs/reference/architecture.md` is a 13-line German stub** with a T0–T6
   roadmap that finished months ago — yet both `CLAUDE.md` and `README.md:105`
   point at it as the architecture reference. Worst defect found.
2. **`panel-mode-matrix.md` had diverged from the code in both directions** —
   seven panels missing *and* five rows factually wrong (`goal-achievement`,
   `director-weights` and `kpi-filter` are offered in **no** mode today;
   `scenario` is Co-Learning only; `agents` lost Director). Worse than "stale".
3. **Two competing document indexes** (`docs/README.md`, 17 plan links;
   `docs/reference/OVERVIEW.md`, 12) that have drifted apart.
4. **D3.1 and D3.2 are now public** — pulled and read; see §5. D3.1 §7 contains
   an official Director System with **interpretable primitives** that closely
   matches our own delegation thinking, and states the logging norm outright.
5. **`CLAUDE.md`'s "~1085 hardcoded colours" is stale** — the count is now 1272
   (`grep -rEoh "#[0-9a-fA-F]{3,8}\b|rgba?\([0-9]" frontend/src --include="*.scss" --include="*.html" | wc -l`).
6. On logging, AI4REALNET wants **two different things through two different
   pipes**, and our Flatland connection delivers **neither** today (§3).

---

## 1. Plan currency (`docs/plans/`)

| Doc | Claimed status | Verified | Verdict |
|---|---|---|---|
| `agentic-delegation.md` | new (2026-08-19) | — | ✅ current |
| `interaction-logging-plan.md` | rewritten 2026-08-19 | — | ✅ current |
| `flatland-ecosystem-reuse-plan.md` | 2026-08-16 survey | — | ✅ current |
| `recommender-roadmap.md` | two seams | `app/core/recommenders` + `app/policies` exist | ✅ current |
| `widget-linkmap-zwl.md` | planned | no feature dir | ✅ accurate |
| `cities-stations-plan.md` | "no implementation yet" | **stations exist** in `core/models.ts:152` — but derived from train origins/targets, *not* from the generator's city data | ⚠️ **superseded in part** — rewrite around what shipped |
| `layout-grid-model-plan.md` | "no implementation yet", "only fixed pixel columns" | `minWidth` already in `layout.models.ts:73` | ⚠️ premise partly outdated |
| `mode-scoped-layouts-plan.md` | "no implementation yet" | `panel-mode-availability.ts` exists and is consulted by `AppComponent`; the *resolver* still does not | ⚠️ half-landed — update the status line |
| `center-view-tabs.md` | "records the first-cut `view-tabs`" | catalog `view-tabs: first-cut` | ✅ accurate |
| `recommendation-reliability.md` | Variants A/A′ implemented, B–D open | settings for countdown / recommendation duration / auto-pause exist | ✅ accurate |
| `localized-blocking-decisions.md` | "concept + prototype" | `systemHold()` in `session.store.ts` | ✅ accurate |
| `scripted-events-plan.md` | draft | no scripted-event code | ✅ accurate (still the recommended fix for §Variant B) |
| `heterogeneous-tracks.md` | not implemented | no track classes | ✅ accurate |
| `i18n-strategy.md` | Transloco decided, not started | no i18n dependency in `package.json` | ✅ accurate |
| `widget-a1-risk-uncertainty.md` | first cut built | `risk-uncertainty` = `first-cut` | ✅ accurate |
| `widget-a2-decision-log.md` | first cut built | `decision-log` = `first-cut` | ✅ accurate |
| `widget-b1-whatif-compare.md` | first cut | `whatif-compare` = `first-cut` | ✅ accurate |
| `widget-b1-followups-prompt.md` | delegation archive | — | 📦 **move to `docs/archive/`** |
| `widget-b3-network-correlation-graph.md` | planned | no feature | ✅ accurate |
| `widget-timetable.md` | — | `timetable` shipped | ⚠️ add status line |
| `widget-variants-versioning.md` | — | `recommendations-classic` shipped | ✅ accurate |
| `widget-catalog.md` | A1–D2 candidate list | agrees with code on A1/A2/B1; C1, C2, D1, D2, B3 not in code (correct) | ⚠️ **but see §2.1** |
| `workstream-b-rationale-capture.md` | Tier 1 done, Tier 2 open | `rationale-capture` feature exists | ✅ accurate (it already carries a status line — my first pass misread it) |
| `co-learning-direction.md` / `colearning-across-modes.md` | thinking docs | — | ✅ current |
| `scenario-variants.md` | framing | — | ✅ current |
| `ecml2026-flatland-env.md` | to discuss | external | ⚠️ decide or park |
| `onboarding-tickets-2026-06.md` | kickoff draft | the kickoff has happened | 📦 **archive** |

**Pattern:** nothing is dangerously wrong, but four plans still say "no
implementation yet" for things that have since partly landed. That is the kind
of staleness that makes a colleague rebuild something that exists.

---

## 2. The other docs

### 2.1 Overlaps

| Overlap | What to do |
|---|---|
| **Two doc indexes** — `docs/README.md` (17 plan links) vs `OVERVIEW.md` §Document map (12) | Pick one. Recommendation: `docs/README.md` is the index; OVERVIEW keeps only the handful of docs a newcomer needs, and links to the index for the rest |
| **Two widget catalogs** — `docs/plans/widget-catalog.md` (candidates A1–D2, with grounding and effort) vs `core/widgets/widget-catalog.ts` (29 registered, with `status`) | Not a duplicate — different jobs (pipeline vs registry). But say so at the top of each, and let the doc cite the code for status instead of repeating it |
| **Three mode docs** — `interaction-modes-brief.md` (spec), `mode-guide.md` (walkthrough), `interaction-framework.md` (authoring framework) | Genuinely different purposes. Add a one-line "this is not X, see X for that" header to each |
| **`ui-exploration-prompt.md` + `ui-exploration-synthesis.md`** (698 lines together, unchanged since July) | The prompt is a delegation artifact → `docs/archive/`; keep the synthesis |

### 2.2 Stale pointers and numbers

- **`architecture.md`** — 13-line stub, German, roadmap T0–T6 all done. Referenced
  from `CLAUDE.md` *and* `README.md:105` as "a more detailed write-up". Either
  write the real thing or repoint both to `OVERVIEW.md` §Architecture.
- **`panel-mode-matrix.md`** — missing `strategy-options`, `strategy-forecast`,
  `strategy-reflection`, `shift-review`, `co-learning-effect`, `ai-activity`,
  `recommendations-classic`. All seven exist in
  `core/layout/panel-mode-availability.ts`, which claims to mirror this doc.
- **`colour-usage-audit.md`** — internally correct, and it already notes that
  CLAUDE.md's number "has grown". Fix the number in `CLAUDE.md` (1085 → 1272).
- **`wp4-validation-alignment.md`** — re-checked 2026-08-16, still accurate as of
  today; its §3 KPI catalog remains unverified by its own admission. §3 below
  adds what was missing.
- **`CLAUDE.md` "Not yet available: D3.1 / D3.2"** — both are now downloadable
  from the AI4REALNET deliverables page (status: draft, pending approval).

### 2.3 Fine as they are

`director-mode.md` (2026-08-07, matches the code), `interaction-modes-brief.md`,
`interaction-framework.md`, `visual-concept.md`, `data-provenance.md`,
`frontend-lyne-conventions.md`, `widget-authoring-process.md`,
`flatland-oekosystem-recherche.md`, the `docs/scenarios/` set, and the two
`docs/delegation/` archives.

---

## 3. AI4REALNET and logging — who needs what, through which pipe

Verified on 2026-08-19 against the live repos and the installed `flatland-rl`.

### 3.1 There are two pipes, and they carry different things

**Pipe 1 — FAB (the Validation Campaign Hub).**
`flatland-association/ai4realnet-orchestrators` (pushed 2026-08-19). Results are
uploaded through `fab_clientlib` as `(scenario_id, key, value)` triples — a
`primary` value plus named scalars. Example from `KPI-RS-058`:

```python
return {'primary': success_rate - base_success_rate,
        'gained_success_rate': ..., 'gained_punctuality': ...}
```

**FAB ingests numbers, not event streams.** An interaction log has no slot in
this contract. The human-factors half is explicitly expected to be *manually
completed* by the researcher through the FAB UI/CLI (this is the "interactive
loop" workflow) — which is exactly where survey exports would go.

**Pipe 2 — InteractiveAI.** Live operational display: contexts (train positions
with lat/lon) and events (malfunctions). Not an analysis archive.

### 3.2 What our Flatland connection actually delivers today

The installed `flatland-rl==4.2.6` ships
`flatland/integrations/interactiveai/` with **three** client APIs — `event_api`,
`context_api` and `historic_api`. The `historic_api` is the trace/archive one
(`TraceIn` = `{data, date, step, use_case}`, with `api_v1_traces_post`).

**But `FlatlandInteractiveAICallbacks` constructs the historic client and never
posts to it.** In `interactiveai.py` the only calls are
`api_v1_events_post` (on a new malfunction) and `api_v1_contexts_post` (agent
positions each step). The trace endpoint is wired up and unused.

So: our Flatland connection would give AI4REALNET a **live picture**, not a
**record**. Nothing about human interaction crosses it at all — the callbacks
only ever see the env.

### 3.3 What the interactive-loop demo actually uploads

`railway/playground/test_runner_playground_interactive.py` replays the Olten
`partially_closed` scenario, posts live to `interactiveai.flatland.cloud`, and
its `run_scenario()` ends with:

```python
return {}
```

**Nothing is submitted to FAB.** The playground entry is a demonstration
surface. This confirms the earlier reading in `wp4-validation-alignment.md` §3
at a finer resolution.

### 3.4 Where the human-factors data is expected to come from

Nowhere automatic. The named human-factors KPIs have no code anywhere in the
org; they are meant to arrive through the interactive-loop workflow as a
**manual submission** by the researcher. Practically that means: whatever we
export ourselves is the data. Which makes
[`interaction-logging-plan.md`](interaction-logging-plan.md) not just our
internal need but the only mechanism on this path.

### 3.5 One upstream convention worth adopting

`KPI-RS-058` ("robustness to operator input") records its runs in **Flatland's
own trajectory format** — `ActionEvents.discrete_action.tsv`,
`TrainMovementEvents.trains_positions.tsv`,
`TrainMovementEvents.trains_rewards_dones_infos.tsv`,
`TrainMovementEvents.trains_arrived.tsv` — and measures robustness by running
the same scenario twice, once clean and once with 10% of actions overridden by a
random "human" policy.

Two consequences for us:

- **Format:** if our session export carries the run in that layout alongside our
  own interaction record, an upstream KPI runner could read it without a
  converter. Cheap to do at export time, and it is a real answer to "will this
  ever be usable by WP4".
- **Method:** their clean-vs-intervened A/B is a better baseline than our
  current impact analysis, and it is the closest thing in the consortium to what
  the user studies measure. Worth borrowing regardless of integration.

### 3.6 Bottom line

| Question | Answer |
|---|---|
| Is interaction logging covered by our Flatland connection? | **No.** The callbacks see only the environment; the trace API is never called |
| By FAB? | **No.** FAB ingests scalar KPI values per scenario |
| By InteractiveAI? | **No** for analysis. It is a live display; its historic API exists but nothing in the Flatland integration writes to it |
| So who covers it? | **We do.** The interactive-loop workflow assumes the human-factors researcher submits it manually |
| What should we align to? | FAB's `(scenario, key, value)` result shape for the KPI summary, Flatland's trajectory file layout for the run itself, and A3S/TraceRL's vocabulary for the decision trail (§5.2) |

---

## 4. Suggested order

1. Fix the pointers that mislead: `architecture.md` (or repoint `CLAUDE.md` +
   `README.md`), the colour count, the D3.1/D3.2 availability line.
2. Refresh `panel-mode-matrix.md` from `panel-mode-availability.ts` — seven rows.
3. Update the four "no implementation yet" status lines (`cities-stations`,
   `layout-grid-model`, `mode-scoped-layouts`, plus status lines for
   `widget-timetable` and `workstream-b`).
4. Archive `onboarding-tickets-2026-06.md`, `widget-b1-followups-prompt.md`,
   `ui-exploration-prompt.md`.
5. Collapse the two doc indexes into one.
6. Pull D3.1 + D3.2 and re-check §3 against what they actually specify.

---

## 5. D3.1 and D3.2, read (added 2026-08-19)

Both PDFs were downloaded from the AI4REALNET deliverables page and read. They
change three things.

### 5.1 There is an official Director System, and it goes further than ours

D3.1 §7 defines the **"Director System"** on the orchestra metaphor — the
operator issues high-level *directives*, executed autonomously by the
components. Beyond that it introduces **interpretable primitives** derived from
**Hierarchical Task Analysis** (Dettling et al. 2026): small, well-defined
operations screened on *clarity of purpose*, *process transparency* and
*granularity*, composed into a traceable sequence. The stated aim: humans as
"conductors of the procedure", not "validators of a final recommendation".

Its worked example is **disruption management**, and it reads like a
specification of the assignment object in
[`agentic-delegation.md`](agentic-delegation.md): the intent *"search suitable
trains for rerouting"* is expressed as a command input and executed as
(1) identify affected trains and routes → (2) filter by train type / capacity →
(3) filter for direct-to-destination services → ranked shortlist.

The architecture in §7.2 also confirms the pieces we had inferred from the code:
graph model of the Flatland environment, a **negotiation proxy**, a human
director, RL agents, a learning algorithm, and an **experience clustering
module** — plus "direct manipulation by the human agent to add context
information (for example, removing edges…)", which is exactly Tokener's
`AVOID_EDGE` token.

### 5.2 Logging: the norm is stated, the mechanism is A3S

- D3.1 §1198: *"trustworthy autonomy demands robust monitoring, auditing, and
  logging infrastructures. Algorithms should generate structured, traceable
  decision records that allow operators to analyze system performance,
  investigate anomalies, and understand failure mechanisms."* That is the
  requirement, stated normatively.
- D3.1 §301–304: A3S "exposes recommended actions together with uncertainty
  estimates, contextual information, and traceable decision pathways… The
  service-oriented design facilitates **auditing, logging, and what-if
  analysis**."
- TraceRL produces a **"structured audit trail of operator decisions, AI
  recommendations, and uncertainty estimates"**, called "a natural fit for
  regulatory compliance and post-incident review".

So the consortium's answer to "where does logging live" is **A3S/TraceRL**, not
FAB and not InteractiveAI. This does not contradict §3 — it sharpens it. A3S
records *decision points, actions, uncertainty and rollouts*. It still does not
record what a study needs about the human: mode, design condition, dwell time,
survey, reflection. Those remain ours.

**One passage is worth quoting to the team** (D3.1, Co-Learning section): the
self-reflection module's data — *"Logging and anonymizing this data allows it to
be evaluated and shared with other operators, enabling knowledge sharing
throughout the organization."* Anonymisation is named as part of the design, not
as an afterthought. That is direct support for decision §6.3 of
[`interaction-logging-plan.md`](interaction-logging-plan.md).

### 5.3 Consequences

1. `agentic-delegation.md` now cites D3.1 §7 as its consortium anchor, and the
   primitives concept is a concrete refinement to consider for the assignment
   object.
2. The logging plan's §4.1 record should align its vocabulary with A3S's
   (decision point, action space, rollout) where the concepts match, so a later
   bridge is a mapping rather than a redesign.
3. `CLAUDE.md`'s "Not yet available" section is replaced by a real summary of
   both deliverables.

---

## 6. Done on 2026-08-19

| Item | Status |
|---|---|
| Real `architecture.md` written (replaces the 13-line stub) | ✅ |
| `CLAUDE.md`: colour count 1085 → ~1270 | ✅ |
| `CLAUDE.md`: "Not yet available" → summary of the public D3.1 / D3.2 | ✅ |
| `panel-mode-matrix.md` regenerated from `panel-mode-availability.ts` | ✅ |
| Status lines: `cities-stations`, `layout-grid-model`, `mode-scoped-layouts`, `widget-timetable` | ✅ |
| Archived: `onboarding-tickets-2026-06`, `widget-b1-followups-prompt`, `ui-exploration-prompt` (inbound links repointed) | ✅ |
| Two doc indexes collapsed — `docs/README.md` is the index, `OVERVIEW.md` keeps a five-entry start-here | ✅ (verified: every doc listed, no dead entries) |
| D3.1 + D3.2 pulled and §3 re-checked | ✅ (§5) |

Not done, because they need a decision: the six questions in
[`interaction-logging-plan.md`](interaction-logging-plan.md) §6.
