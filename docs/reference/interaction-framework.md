# Interaction framework — widgets, functions, allocation, accountability

> The conceptual backbone for **authoring** HMI elements ("widgets") in this
> playground. It answers three questions about any element: **what function** it
> serves in the human-AI loop, **at what granularity**, and **who owns which
> part** of the loop. It is grounded in the AI4REALNET / InteractiveAI reference
> framework and classic control-room theory.
>
> Companions: [visual-concept.md](visual-concept.md) (canonical surface names +
> zones), [panel-mode-matrix.md](panel-mode-matrix.md) (per-panel behaviour per
> mode), [interaction-modes-brief.md](interaction-modes-brief.md) (authoritative
> mode spec). This doc is the layer *above* those: the vocabulary they instantiate.

## 1. Grounding — the AI4REALNET / InteractiveAI vocabulary

The consortium reference is the **AI4REALNET Conceptual Framework for AI-based
Decision Systems in Critical Infrastructures** (arXiv 2504.16133), sharpened by
deliverable **D3.1 "AI4REALNET solutions to augment human decision-making"
(2026)**. It names **eight system functions**:

1. Context Determination · 2. **Anticipation** · 3. Operator Interaction ·
4. Feedback Integration · 5. Interaction Mode Selection · 6. Learning ·
7. Decision Assistance · 8. Compliance Monitoring

The **InteractiveAI** platform (IRT SystemX) instantiates this as an event loop:
**Event → Context → (AI) → Notification → Human Decision → Capitalization
(learning)**.

Two AI capabilities are treated as **distinct** and are the novel core:
- **Prediction (Anticipation)** — *forecasting future events to enable proactive
  intervention.*
- **Assessment (Evaluative AI)** — *providing evidence for and against a range of
  options* rather than a single directive (present trade-offs, don't prescribe).
  Concrete AI4REALNET grounding (not just Miller in the abstract):
  [`AI4REALNET/T2.3_explaining_action_alternatives`](https://github.com/AI4REALNET/T2.3_explaining_action_alternatives)
  (D2.3) — generates accurate *expected-outcome* explanations per action
  alternative without assuming the operator's reward weights; the reuse target
  for widget C1.

## 2. Widget `kind` — function in the human-AI loop

The **primary** classification of a widget is its function in the loop, not its
form (text/chart/button). Sub-types can be added under a `kind` later without
reshuffling the top level.

| `kind` | AI4REALNET function | What the widget answers | Examples today | AI-novel |
|--------|---------------------|-----------------------|----------------|:--------:|
| **Event** | Event / Context (detect) | *What is happening?* (event synthesis / Hypervision) | Situation Summary, Event Feed | |
| **Context** | Context Determination | *Why, how bad, whom does it affect?* | Conflict Panel, Train Detail Overlay | |
| **Prediction** | Anticipation | *What happens next / what-if?* | Marey forecast, ETA overlays | ⭐ |
| **Decision Support** | Decision Assistance / Evaluative AI | *Which option, on what evidence?* | Recommendation Panel, Scenario compare | ⭐ |
| **Control** | Operator Interaction / Mode Selection | *Enact / adjust.* | Toolbar, overrides, KPI filter, Director directive | |
| **Capitalization** | Feedback Integration / Learning | *What do we learn from this?* | Co-Learning reflection, feedback log | ⭐ |
| **Trust** | Compliance Monitoring (+ Evaluative AI) | *Can I rely on the AI here?* | (honest-uncertainty, confidence, explanation, reliability) | ⭐ |

### Decision Support has mode-framings (extensible sub-types)
The same decision surface is **framed by the mode** — this is why `kind` predicts
mode-behaviour:
- **Assessment** (Evaluative AI: evidence for/against, neutral) → **Co-Learning**
- **Recommendation** (ranked + confidence) → **Recommendation** mode
- suppressed / read-only → **Director** (AI acts)

`Recommendation` is therefore **not** a peer `kind`: it is a *framing of Decision
Support* that feeds Control, and it stays advisory under **Human-in-Control**
(§4). Further sub-types (e.g. counterfactual, contrastive) can be added later.

## 3. Orthogonal axes (attributes, not kinds)

- **`granularity` — overview ↔ detail.** Shneiderman's mantra ("overview first,
  zoom and filter, details on demand"). The overview end *is* Hypervision (the
  big-board synthesis); the detail end is drill-down / detail-in-context (Train
  Detail Overlay, Event Detail Card). A widget declares where it sits and, ideally,
  what it drills into.

- **`allocation` — who owns each loop stage.** A map `{loop-stage → human | ai |
  shared}`. **Today it is derived from the interaction mode** (static per
  condition — correct for a controlled experiment). It is modelled as its **own
  concept**, *not* baked into `InteractionMode`, so that dynamic reallocation
  becomes a runtime change of the same structure rather than a refactor (§5).

## 4. Human-in-Control — the autonomy principle

"Human-in-Control" is **not a widget kind**; it is the principle governing
`allocation`: actuation authority stays with the human unless explicitly and
reversibly delegated. Grounded in levels-of-automation theory (Sheridan &
Verplank 1978; Parasuraman, Sheridan & Wickens 2000: *types × levels* of
automation) and in AI4REALNET's three collaboration levels (= our three modes).
It is why a prominent Recommendation is still advisory input, not control.

## 5. Reserved seams — designed for, not yet built

These are **deliberately not implemented now**. They are documented so current
choices don't foreclose them.

### 5a. Dynamic function allocation (adaptive/adaptable autonomy)
Today allocation changes only on **mode switch**. The frontier (T3.4 "adjustable
autonomy") is **runtime** reallocation — per situation, per agent, negotiated.
**Seam:** because `allocation` is a first-class data structure (§3), enabling
this later means changing *when/what sets it*, not the model. Do not couple
allocation logic irreversibly to the mode union.

Why this matters for dispatching specifically: complexity does not just differ
between scenarios, it **shifts within a single shift** (routine → disruption →
crisis). Fixed per-mode allocation (ALIGN: low/medium/high complexity → user /
shared / developer) cannot track that; the domain itself argues for
runtime-adjustable allocation, with expertise-priority in the crisis band (HRO).

### 5b. Accountability (responsibility-taking)
Framed after the project owner's research line (Boos 2013, *Controllable
Accountabilities*; Grote, control–accountability alignment): accountability is
**not** moral attribution but a **fit question**. A person can only carry
responsibility when their **control capabilities** match the **accountability
demands** placed on them:

| Control capability (Grote) | ↔ | Accountability demand (Boos et al. 2013) |
|----------------------------|---|------------------------------------------|
| Transparency (understand state) | ↔ | Visibility (answerable to others) |
| Predictability (anticipate behaviour) | ↔ | Responsibility (duty to perform) |
| Influence (act on the situation) | ↔ | Liability (legal / contractual) |

Mismatch either way — accountability without control, or control without
accountability — is a **design fault** (an "impossible role", Bainbridge/Grote),
not an individual failing. Hard rule for our mode design: **first establish who
actually holds the control means in a mode, then assign responsibility — never
the reverse** — and name explicit **Partial Non-Control** zones (where the human
genuinely cannot control and therefore must not be held liable).

Failure modes to instrument against: **HITL-as-alibi / buck-passing** (Kapoor &
Narayanan) — nominal responsibility without real intervention capability (the
owner's "Verantwortungs-Fassade"); **uncontrollable accountabilities**;
**responsibility void** (so diffuse no one is concretely in charge).

**Seam (measurement-ready):** model decisions as **first-class events with an
`accountableOwner`** (derived from `allocation`) and a lifecycle
(`detected → acknowledged → decision → resolved → logged`, per InteractiveAI +
the [interaction-logging-plan](../plans/interaction-logging-plan.md)). The
signals of responsibility-taking then fall out: **override frequency** (never
overridden ⇒ HITL is decorative), **friction asymmetry** (is rejecting as easy as
accepting?), **decision-time ÷ acceptance-rate** as an overtrust proxy (owner
marks this an explicitly falsifiable hypothesis), **skill-maintenance
performance** over AI-free intervals. Build none of it now; but owned decision
events make accountability **analysable later without a refactor**.

Two tensions we must hold, not smooth over:
- **Trust — design goal or warning sign?** Calibrated trust as a goal (Weyer)
  vs. *"trust may be a consequence of lack of control"* (Grote). This is why
  **Trust** is its own kind, and why a trust widget must expose *appropriateness of
  reliance*, not just a confidence number.
- **Guardian-system paradox.** The preferred architecture (system extends
  perception, human keeps control) reproduces the automation irony at second
  order: the better it protects, the rarer the edge case, the more intervention
  competence erodes. The sim should actively create competence-maintenance
  opportunities (edge-case exposure, AI-free practice).

> Essence only — the full briefing (enabling conditions, all failure modes, open
> questions, sources) lives in the owner's notes.

## 6. AI4REALNET D3.1 → this framework

D3.1 names **five solution families**. They map cleanly onto the kinds and seams
above — a good sign the taxonomy is consortium-aligned:

| D3.1 solution family | Our mapping | Consortium repo(s) checked |
|----------------------|-------------|------------------------------|
| **Uncertainty-aware decision support** — epistemic vs. aleatoric; reliability indicators, probabilistic forecasts, failure-risk, uncertainty intervals → *calibrated trust* | **Trust** kind (+ **Prediction** for probabilistic forecasts) | [`RL_agent_failure_forecast`](https://github.com/AI4REALNET/RL_agent_failure_forecast) (INESC, evidential NN — widget A1's reuse target); [`RL-agent-uncertainty-prediction-module`](https://github.com/AI4REALNET/RL-agent-uncertainty-prediction-module) (Conformal Prediction, alternative); [`failure_prediction`](https://github.com/AI4REALNET/failure_prediction) (D2.2, classical models) |
| **Multi-objective reasoning & trade-off transparency** — Pareto sets, reveal objective conflicts, situational priorities | **Decision Support / Assessment** (Evaluative AI, evidence for/against) | [`T2.3_explaining_action_alternatives`](https://github.com/AI4REALNET/T2.3_explaining_action_alternatives) (D2.3, widget C1's reuse target); [`Grid2Op_MORL`](https://github.com/AI4REALNET/Grid2Op_MORL) (Pareto/MORL, domain caveat) |
| **Interactive & co-learning architectures** — explicit/implicit feedback, IRL, explanation, persistent state | **Capitalization** kind | [`Tokener`](https://github.com/AI4REALNET/Tokener)'s Co-Learning approach (human-in-the-loop, transparent adaptation); [`CDRTrainer`](https://github.com/AI4REALNET/CDRTrainer) (TUD, feedback + shielding) |
| **Agent-as-a-Service (A3S)** — see below | Architecture pattern for the **seams** | [`agent-as-a-service-trace-rl`](https://github.com/AI4REALNET/agent-as-a-service-trace-rl) — confirmed, Flatland-configured already; widget B1's reuse target |
| **Trustworthy autonomous operation** — director system, high-level directives, interpretable primitives from hierarchical task analysis, MARL + negotiation + supervision | **Control** kind (director-directive) + Human-in-Control | [`Tokener`](https://github.com/AI4REALNET/Tokener)'s Hybrid approach (CBS+PP, token-based); [`T3.4-with-HMI`](https://github.com/AI4REALNET/T3.4-with-HMI) (PPO + runtime decision injection); [`T3.3-3.4-HMI`](https://github.com/AI4REALNET/T3.3-3.4-HMI) (full reference HMI, both modes) — reuse targets for widget D1 |

**A3S is not a widget — it is the architecture stance** that makes our seams real.
It wraps an autonomous agent in a human-centred service that *exposes* recommended
actions **with uncertainty, context, and traceable decision pathways**, supports
**adjustable autonomy**, and enables **auditing / logging / what-if**. In our terms:
- adjustable autonomy → **dynamic allocation** (§5a),
- traceable decisions + auditing/logging → the **accountability** seam (§5b, decisions-as-events-with-owner),
- uncertainty exposure → the **Trust** kind,
- what-if roll-out (A3S roll-out layer + TraceRL) → **Prediction**.

So "adopting A3S" means shaping *how the AI is exposed to the UI* (a supervised
service with uncertainty + traceability + an autonomy dial), not building one panel.

## 7. What this means for the build

Materialise now: **`kind` + `granularity`** on `PanelDefinition`, and **Trust** as
a first-class kind. Introduce **`allocation`** as a concept derived from the mode
(seam for §5a). Keep accountability as the documented seam in §5b (events with an
owner) — realised together with interaction logging, not before. The widget-spec
template builds on this: `kind × granularity`, then per-mode framing (Decision
Support: Assessment ↔ Recommendation), then system interaction (data in / actions
out), then the grounding reference + acceptance scenario.

## Sources
- AI4REALNET Conceptual Framework — arXiv 2504.16133; AI4REALNET **D3.1** (2026), https://ai4realnet.eu/deliverables/
- InteractiveAI (IRT SystemX) — https://github.com/IRT-SystemX/InteractiveAI
- Situation awareness — Endsley (1995). Levels/types of automation — Sheridan & Verplank (1978); Parasuraman, Sheridan & Wickens (2000).
- Meaningful Human Control — Santoni de Sio & van den Hoven (2018). Moral crumple zone — Elish (2019).
- Trust calibration — Lee & See (2004); Parasuraman & Riley (1997); Weyer (appropriate trust). Information-seeking mantra — Shneiderman (1996).
- Control–accountability alignment — Boos, Günter, Grote & Kinder (2013), *Controllable Accountabilities*; Grote (control–accountability alignment). HITL-as-buck-passing — Kapoor & Narayanan (2024). Ironies of automation — Bainbridge (1983).
