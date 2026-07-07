# Implementation Brief — Three Human-AI Interaction Modes

> For Claude Code. Goal: make the three collaboration modes (Recommendation /
> Co-Learning / Director) **behaviourally distinct and switchable at runtime**,
> following the interaction flows validated with the FHNW study team (AI4REALNET).
> This is a research prototype — clarity of the interaction differences matters
> more than production hardening.

---

## 0. Context

The modes map to AI4REALNET work packages and are already declared in code:

| Mode (`InteractionMode`) | WP | Meaning |
|---|---|---|
| `recommendation` | 3.1 | AI suggests **with a recommendation**, human decides |
| `co-learning` | 3.3 | AI offers **neutral options**, human decides + reflects + simulates |
| `director` | 3.4 | AI acts autonomously; human sets goals up front and supervises |

The scaffolding exists (`SessionStore.interactionMode`, header mode-switcher in
`app.component.html`, `showRecommendations` / `aiInControl` / `isCoLearning`
computeds, `co-learning-reflection` component, `coLearningFeedback` log).
**The problem: today `recommendation` and `co-learning` render identically** —
`showRecommendations` is only `false` in `director`. The whole point of the two
non-autonomous modes is that they differ. This brief closes that gap.

### Two layers of "options" — keep them distinct

The flows below talk about "Handlungsoptionen". In this codebase there are two
candidate surfaces; we use **both, at different altitudes**:

- **Tactical (per-incident):** when a conflict is predicted, the affected
  agent's decision options — `AgentDTO.next_decision.options` (`DecisionOption`)
  — applied via `setOverride()`. This is the primary surface for the study team's
  "AI generates action options based on an expected incident".
- **Strategic (per-policy):** the `recommendations-panel` + `scenario-panel`
  (switch policy / compare branches on the Marey). Secondary surface, reused for
  the what-if comparison in Co-Learning.

The `recommended` vs `neutral` distinction must apply to **both** layers.

---

## 1. The validated interaction flows (source of truth)

These are the consortium-validated sequences (validated against the reference video). Implement the
modes so a user clicking through experiences exactly these steps.

### Mode A — Recommendation (AI-Assisted Human Control, WP 3.1)

1. Situation starts.
2. AI visualises the operating state **and the forecast** (what may happen).
3. On a **predicted incident**, AI generates action options **with a clear recommendation** (one option highlighted, confidence shown).
4. Human picks an option.
5. Situation continues.

### Mode B — Co-Learning (Human-AI Co-Learning, WP 3.3)

1. Situation starts.
2. AI visualises the operating state **and the forecast**.
3. On a predicted incident, AI generates **neutral options — no recommendation, no ranking, no "best" badge**.
4. Human picks an option.
5. When things calm down, the human can **reflect** on what happened.
6. Situation continues.
7. Human can **simulate "what if I had chosen a different option"** and **compare** it against what actually happened.

### Mode C — Director (Trustworthy Autonomous AI, WP 3.4) — *proposed, see §4*

1. **Before the run**, human sets the high-level directive: KPI priorities (weights) and/or which algorithm/policy the AI runs.
2. Situation starts; AI dispatches autonomously.
3. Human watches a **higher-level supervisory view focused on goal achievement** (KPIs vs targets), not per-decision prompts.
4. Human can intervene (override / pause / re-weight KPIs); an override is logged as a manual intervention.

---

## 2. Mapping to existing code

| Flow element | Already exists | File |
|---|---|---|
| Mode state + switcher | ✅ | `core/session.store.ts` (`interactionMode`, `setInteractionMode`), `app.component.html` header |
| Forecast visualisation | ✅ | `scenario-panel` + `marey-chart` / `graphic-timetable` (branch trajectories) |
| Predicted incident | ✅ (backend) | `backend/app/core/conflict_detector.py`, `notification_manager.py` |
| Per-agent action options | ✅ | `AgentDTO.next_decision.options`, `agent-inspector`, `setOverride()` |
| Recommendation (with confidence/countdown) | ✅ | `recommendations-panel`, `backend/app/core/recommendation_generator.py` |
| Co-Learning intervention log | ✅ | `coLearningFeedback`, captured in `setOverride()` |
| Reflection questionnaire | ✅ (end-of-episode only) | `co-learning-reflection.component.ts` |
| What-if compare | ⚠️ partial | scenario branches on Marey exist, but no "my alternative vs actual" compare |
| Director autonomy | ⚠️ partial | `aiInControl` auto-plays + banner; **no pre-run directive step, no goal-achievement view** |
| **Neutral vs recommended options** | ❌ | core gap — both modes look the same today |

---

## 3. Implementation tasks

### 3.1 Make options mode-aware (the core differentiator)

Introduce a single semantic flag the whole UI reads, e.g. in `SessionStore`:

```ts
/** In recommendation mode the AI ranks/badges a best option; in co-learning
 *  it must present options neutrally; in director the human isn't prompted. */
readonly optionPresentation = computed<'recommended' | 'neutral' | 'none'>(() => {
  switch (this.interactionMode()) {
    case 'recommendation': return 'recommended';
    case 'co-learning':    return 'neutral';
    case 'director':       return 'none';
  }
});
```

Then:

- **`recommendations-panel`**: when `optionPresentation() === 'neutral'`, hide the
  confidence stripe, the "recommended" tag, and the countdown; do **not**
  pre-sort by score (present options in a stable, non-judgemental order); relabel
  the panel ("Options" instead of "Recommendation"). When `'recommended'`, keep
  today's behaviour.
- **`agent-inspector`** (per-agent `next_decision.options`): same treatment — in
  co-learning, render the decision options as equal choices with no AI-preferred
  highlight; in recommendation, highlight the AI-preferred action.
- **`scenario-panel.rankedScenarios`**: in co-learning, drop `isRecommended` /
  `tag === 'recommended'` styling and the score-based reordering; keep the
  baseline pinned but show alternatives neutrally.
- **Backend (optional but cleaner):** let `recommendation_generator` /
  `hmi_scenario_adapter` accept the mode (or have the endpoint strip
  `isRecommended`/`tag`/`confidence` when mode is co-learning) so neutrality is
  enforced server-side too, not just hidden in CSS. Prefer gating in the frontend
  first; only touch the backend if the recommendation framing leaks through.

**Done when:** switching between Recommendation and Co-Learning on the same
incident visibly changes whether the AI pushes a preferred option or stays
neutral — with no other UI difference forced on the user.

### 3.2 Co-Learning: reflection available "when calm" (not only at episode end)

Today `co-learning-reflection` only renders on `episodeDone()`. The storyboard step 5
is "reflect when it's quiet again". Add a lull/calm signal and surface the
reflection entry point then too:

- Add e.g. `readonly isCalm = computed(...)` — true when no agent is `MOLFUNCTION`/
  conflict is pending and `!playing()` (a pause counts as calm). Reuse
  `conflict_detector` output if exposed, otherwise approximate from agent states.
- In `app.component.html`, render `app-co-learning-reflection` when
  `isCoLearning() && (isCalm() || episodeDone())`. Keep it dismissible.
- Reflection answers + `coLearningFeedback` interventions stay client-side for
  now (matches the existing TODO about a persistence layer).

**Official spec (RP2 Part B, T3.3 co-learning HMI):** after operations the
operator "can assess and reevaluate the incidents managed, both with a
**statistical evaluation** and an **open-question reflection module**". The
current `co-learning-reflection` covers the open-question half; add a compact
**statistical recap** (interventions, delay, deadlocks, arrivals for the run)
alongside it. Also note the official design logs human interaction as **training
data for continual AI learning** — keep `coLearningFeedback` structured so it can
later feed that loop (this is the "AI learns from the human" half of co-learning).

### 3.3 Co-Learning: "what if I had chosen differently" compare (step 7)

Goal: after the human picked option X at a decision, let them replay the branch
where they'd picked Y and compare against what actually happened.

- The machinery largely exists: `scenario-panel` already simulates alternative
  branches and the Marey draws per-branch trajectories. Add an explicit
  **"compare to my actual choice"** affordance:
  - Capture the human's actual chosen option + resulting trajectory (you already
    log the intervention in `coLearningFeedback`; also keep the realised
    trajectory from `SessionStore.trajectories`).
  - Let the user select an alternative option and render **both** lines on the
    Marey (actual vs hypothetical), with a small KPI delta (delay/deadlocks/done)
    using the existing `ScenarioKpis` / `kpiDeltas` shapes.
- This is the embodiment of the "Human Goes First" pattern: *you chose X, the
  alternative Y would have produced Z*. Keep it explicit and non-judgemental.

**Match the official what-if visual convention (RP2 Part B, T3.1 / EnliteAI,
Figure 8):** render **human-influenced steps in blue** and **AI-simulated steps
in yellow** on the trajectory. The official T3.1 flow is exactly: original
trajectory → user injects an action via the control panel → resulting simulated
trajectory. Reuse those semantics so our Co-Learning compare lines up with the
consortium's A3S/TraceRL tool.

**Done when:** in Co-Learning, after a decision the user can pull up their choice
vs one alternative on the Marey with a KPI comparison.

**Mode-awareness (clarification):** what-if/compare is NOT Co-Learning-only. Its
source is T3.1 (EnliteAI), i.e. originally a *Recommendation* tool. Build it
mode-aware, gated by `optionPresentation` like everything else:
- **Recommendation (3.1):** *before* deciding — "follow the AI's recommendation
  vs. my current path", with the AI/recommended branch highlighted.
- **Co-Learning (3.3):** *after* deciding — "what if I had chosen Y", alternatives
  shown neutrally for reflection.
- **Director (3.4):** not a per-decision surface; supervision stays on the
  goal-achievement panel.
Same blue/yellow machinery and KPI delta; only the framing differs.

### 3.4 Director: pre-run directive + goal-achievement view (§4)

See §4 for the proposed design. Two parts:

1. **Pre-run directive step:** before/at session start in director mode, let the
   user set KPI weights (reuse `kpi-filter` / `kpiPriorities`) and pick the
   policy/algorithm (reuse `enabledControlPolicyIds` / `setActivePolicy`). Lock
   per-decision prompting (`optionPresentation() === 'none'` already hides
   options).
2. **Goal-achievement view:** a compact supervisory panel (new
   `features/goal-achievement/`) showing live KPIs against the directive —
   e.g. trains arrived vs total, mean delay, deadlocks, % on-time — sourced from
   the same KPI/scenario data the panels already use. This replaces per-incident
   prompts as the human's primary surface in this mode.

---

## 4. Director mode + adjustable autonomy (control altitudes)

> **Official framing (AI4REALNET RP2 Part B, EU review):** the project defines
> three modalities of control — *full human control*, *shared human–AI
> co-learning*, *fully autonomous AI control* — and the extended HMI enabling all
> three is described as "providing the foundation for **adjustable autonomy**
> (relevant also for T3.4)". So the "combination" below is not a workaround; it is
> the project's own concept. The human-provided data is meant to **tune the level
> of autonomy** of the AI within the decision process.

The three modes are not the whole story. The codebase already exposes the
human's leverage at **three different altitudes**, and a realistic Director mode
is a *combination* of autonomy + optional intervention at any altitude — not
"the human is locked out". This is adjustable autonomy in practice.

### 4.1 The three control altitudes (all already in the API)

| Altitude | What the human changes | Scope | Existing hook |
|---|---|---|---|
| **Strategic — Objective** | KPI weights / priorities | All agents, indirect | `kpiPriorities` / `kpiWeights`, `kpi-filter` |
| **Operational — Policy** | The algorithm that drives the agents | All agents, global | `setPolicy()` / `activePolicy`, `enabledControlPolicyIds` |
| **Tactical — Single agent** | One train's next action / take it over | One agent, local | `setOverride(handle, action)` (one-shot at switch; STOP sticky) |

Note: today **policy is global per session** — there is no per-agent policy
assignment in the backend. The only per-agent lever is the action override. If
per-agent *policy* assignment is wanted (e.g. "train 3 runs shortest-path while
the rest run DLA"), that's a backend extension (see §4.4), not a free feature.

### 4.2 Director as a combination, not a lockout

Director = AI runs every agent by the chosen policy, **and** the human may drop
to a lower altitude at any time. Increasing order of intervention strength
(each is logged as an intervention, like an override already is):

1. **Re-weight KPIs** (strategic) — steer the AI's priorities without touching
   any specific decision. Lowest friction. Treat a re-weight as a new directive.
2. **Swap the global policy** (operational) — change how *all* agents decide
   mid-run (`setPolicy`). Bigger, visible shift.
3. **Take over one agent** (tactical) — pin/override a single train; the AI keeps
   driving the rest. This is literally a per-agent blend of autonomous + manual.

This gives a clean answer to "what does a combination look like?": the human
**stays in Director but borrows control at one altitude**, and the system shows
how invasive that was. The KPI filter is the gentle lever; single-agent takeover
is the strong one; policy swap sits between.

### 4.2b How the official T3.4 "director" works (RP2 Part B)

Align the prototype's Director with the project design so it stays consistent:

- The human is a **"director"** who supplies **high-level directives + contextual
  information**, prototyped as **token-based inputs** — *not* per-decision
  commands. Our KPI weights + policy choice are the playground's stand-in for
  these directives; keep them coarse and goal-level.
- A hard design constraint: the director role **must not degrade the human's
  situation awareness or motivation**. Practically → keep the goal-achievement
  view informative (why the AI is doing what it does), and make the override/
  takeover path always available so the human never feels locked out.
- Conflict handling in the real system uses a **negotiation proxy** that
  optimises **global long-term reward** ("the action that benefits the entire
  system, not an agent individually"). Implication for us: in Director the AI's
  objective is **system-wide**, so the goal-achievement panel should show
  **global KPIs**, and a single-agent takeover is explicitly the human overriding
  that global optimisation for one train.

### 4.3 Recommended UI/state shape

- **Keep the global mode chip** (sets default initiative + `optionPresentation`).
- **Add a per-agent control flag** so "take over this train" is explicit and
  persistent (not just a one-shot override):
  ```ts
  // SessionStore: which agents the human has taken over from the AI.
  readonly humanControlledAgents = signal<Set<number>>(new Set());
  takeOverAgent(h: number): void   // human drives this train
  releaseAgent(h: number): void    // hand it back to the AI/policy
  ```
  In Director, AI-controlled agents follow the policy; `humanControlledAgents`
  follow human overrides. (Backend: this is just "override present for that
  handle" today; a persistent takeover = keep applying the human's intent for
  that handle until released.)
- **Director steering tray** — surface the three levers together with an
  invasiveness label and log each use into `coLearningFeedback` (reuse the same
  intervention log so all altitudes are captured uniformly).
- **Goal-achievement panel** (new `features/goal-achievement/`) — live KPIs vs
  targets (trains arrived / total, mean delay, deadlocks, % on-time) from the
  existing `ScenarioKpis`. This is the human's primary surface in Director;
  no countdowns, no per-incident option cards.

### 4.4 Optional backend extension — per-agent policy

Only if you want altitude 2 at agent granularity. Today `OverridePolicy` wraps a
single global `default` policy and injects per-agent action overrides. A
per-agent *policy* would mean: resolve each handle's action from a
handle→policy map, falling back to the session default. This is a real change to
`override_policy.py` / `play_manager` and the session model — scope it
separately; it's not needed for the core three-mode prototype.

### 4.5 Modes × altitudes (how it all fits)

| | Objective (KPI) | Policy | Single agent |
|---|---|---|---|
| **Recommendation** | optional | AI suggests a switch (accept/reject) | AI suggests an action, human applies |
| **Co-Learning** | optional | neutral options, human picks | neutral options + what-if compare |
| **Director** | primary lever | swap lever | take-over lever |

`optionPresentation` (§3.1) controls whether the policy/agent surfaces show a
*recommended* choice, *neutral* choices, or *none*. So the same three altitudes
are reused across all modes — only the framing changes.

Keep KPI targets simple and configurable (e.g. "all trains arrive",
"mean delay < N"); derive pass/fail from existing `ScenarioKpis`.

---

## 5. Definition of done

- Switching modes mid-session changes behaviour live, with no full reset needed.
- **Recommendation:** AI highlights a preferred option + confidence + countdown
  on a predicted incident; human accepts/overrides.
- **Co-Learning:** identical incident, but options are neutral; reflection is
  reachable during a lull and at episode end; what-if compare (actual vs one
  alternative) works on the Marey.
- **Director:** human sets KPI/policy directive up front; AI runs autonomously;
  a goal-achievement panel is the primary surface; override/pause/re-weight work
  and overrides are logged.
- Existing tests stay green (`backend/tests/`); add coverage for any backend
  mode-gating. Frontend: keep components standalone + signals, SBB Lyne styling.

## 6. Do not touch / constraints

- Don't change the trajectory-compression logic in `session.store.ts`
  (`_recordTrajectory`) or the scenario-refresh throttling rationale in
  `scenario-panel` — both are load-bearing and documented.
- Don't break the policy-recovery fallbacks (`_recoverPolicyAndRetry*`).
- Keep mode semantics in the `InteractionMode` union; don't invent parallel flags.
- Frontend stays Angular standalone components + signals + SBB Lyne; backend
  stays FastAPI + Flatland. No new heavy deps for the prototype.
- Prefer gating presentation in the frontend; only reshape backend payloads when
  neutrality/autonomy genuinely needs server enforcement.

---

## 7. Source grounding — official AI4REALNET framework

The mode definitions and several concrete design choices above are taken from
the official **AI4REALNET RP2 Part B** report (submitted for the 2nd EU review),
not invented for this brief. Key anchors:

- **Three modalities of control** = full human control · shared human–AI
  co-learning · fully autonomous AI control. The HMI spanning all three "provides
  the foundation for **adjustable autonomy**" (→ §4).
- **Co-Learning HMI (T3.3, FHNW/Flatland):** on disturbances the operator can
  *"formulate their own solutions or choose from AI-recommended solutions"*;
  impact is *"evaluated and presented … to evaluate trade-offs and compare
  alternatives"*; afterwards a *"statistical evaluation and an open-question
  reflection module"*; human interaction is logged as training data for
  continual AI learning (→ §3.1, §3.2, §3.3).
- **What-if (T3.1, EnliteAI A3S/TraceRL):** override a decision in a trajectory,
  simulate forward; **human steps blue, AI-simulated steps yellow** (Fig. 8)
  (→ §3.3).
- **Director (T3.4):** human gives high-level **token-based directives**; a
  **negotiation proxy** resolves conflicts on **global** long-term reward; design
  must protect **situation awareness and motivation** (→ §4.2b).
- **Autonomy target (O4):** ≥ 70% human acceptance of autonomous AI; validation
  via D3.2/D3.3/D4.2/D4.3.

Not yet incorporated: **D3.1** ("solutions to augment human decision-making")
and **D3.2** (beta software release) would add the detailed control taxonomy and
the agent-as-a-service KPI/event-monitoring interface. They are public on
ai4realnet.eu but were not accessible in this session — drop either into the repo
to fold its specifics in.

---

### Suggested order of work
1. §3.1 neutral-vs-recommended (biggest behavioural payoff, smallest change).
2. §3.2 reflection-when-calm.
3. §3.4 director directive + goal view.
4. §3.3 what-if compare (largest, build last).
