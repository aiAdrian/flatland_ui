# Agentic delegation — giving the dispatcher an agent to hand work to

> Working notes (2026-08-19) on a question that keeps being asked of us: *"can
> this become more agentic — could a dispatcher hand an agent something to
> solve?"* This is direction and thinking, not a spec. The short answer: the
> agent already exists in the backend; what is missing is the **assignment** —
> a bounded piece of work that can be handed over, worked on, reported back,
> and released.

## 1. What "agentic" means here — and what it doesn't

The word usually gets read as *more intelligence*. That is not the gap. Our
Director policy already searches, re-plans under disturbance and gates its own
recovery on simulation. Adding cleverness to it changes nothing about the
dispatcher's experience.

The gap is a **relationship**: a delegation contract with four parts —
an assignment, a frame the agent must stay inside, a report back, and a release
decision. Everything below is about those four, not about the solver.

A useful negative definition: it is *not* a chat box in front of the simulator.
See §9.

**The consortium has a name for this** (found 2026-08-19, D3.1 §7). AI4REALNET's
own **"Director System"** uses the orchestra metaphor: the operator issues
high-level *directives* that the system executes, and "while the director does
not need to be able to execute the individual functions, they understand the
process and what influence they have over it." Crucially, D3.1 pushes past
directives to **interpretable primitives** derived from Hierarchical Task
Analysis (Dettling et al. 2026) — small, well-defined operations screened on
*clarity of purpose*, *process transparency* and *granularity*, composed into a
traceable sequence. Their stated goal is the same as this document's: humans as
"conductors of the procedure", not "validators of a final recommendation".

## 2. We already have the agent; what is missing is the assignment

Today's Director flow is: switch mode → set a directive **before** the run →
the AI drives → the human watches and may intervene. That is an autopilot with
an off switch. The dispatcher can configure the system and tolerate it, but
cannot **give it something to do**.

What exists (see [`director-mode.md`](../reference/director-mode.md) §1, §3.7,
§3.8):

| Capability | Where |
|---|---|
| Multi-train plan search (greedy / beam / MCTS) | `search.py` `STRATEGIES`, `director_plan` |
| Never worse than baselines *by its own score* | `director_plan` portfolio guarantee |
| Re-plan on disturbance while the current plan keeps driving | `_maybe_replan` → `_start_replan_job` |
| Residual problem expressed as a pinned full-horizon schedule | `replan.residual_plan` |
| Commit only on simulated improvement, ties keep the current plan | `replan.rollout_gate` |
| Refuses to splice a tail that would teleport a train | `replan.splice_entries` → `None` |
| Ground truth for a finished plan | `search.verify_plan` |
| Replan history per env | `_PLAN_INFO[env]["replans"]` |

What is missing is everything on the human's side of the contract:

| Missing | Consequence today |
|---|---|
| A bounded **scope** | Every plan is global; you cannot say "only this incident" |
| Hard **constraints** (not just weights) | "Keep the Olten connection" is not expressible |
| A **report** back | The agent's reasoning, cost and failures stay in the backend |
| A **release** step | Autonomy is a mode, not a per-assignment decision |
| **Visibility** while working | `_start_replan_job` runs invisibly; no status, no cancel |

## 3. The assignment object

The minimum that makes a handover meaningful:

```ts
interface Assignment {
  scope:       { agents?: number[]; area?: string; fromStep: number; toStep?: number };
  goal:        KpiGoal;                    // reuse kpiPriorities vocabulary
  constraints: Constraint[];               // hard, not weighted — see below
  budget:      { maxSteps?: number; maxSeconds?: number };
  release:     'auto' | 'propose' | 'ask-if-unsure';
}
```

Two notes on shape:

- **Constraints are not weights.** The three Director dials steer preference;
  an assignment also needs promises the agent may not trade away ("do not touch
  train 3", "hold this connection"). The brief calls the official T3.4 form
  *token-based directives* (§4.2b); the consortium's `Tokener` applies similar
  tokens by rewriting edge costs and planning order. The difference here is that
  a token is a constraint on a solver call, while an assignment is a constraint
  **plus** a scope, a budget and an obligation to report.
- **Keep the vocabulary coarse.** The brief's constraint holds: directives stay
  goal-level, never per-decision commands.

## 4. The return is a report, not a plan

The agent should hand back what it did, not just what to execute:

- what changed, against what it was before;
- what it costs, in the KPIs the assignment named;
- **what it could not solve** and why;
- how confident it is, and on what basis (score vs. simulated rollout vs.
  verified episode — these are three different kinds of number, cf.
  `director-mode.md` §5.1).

Almost all of this already exists as data. `DirectorPlan` carries the weighted
score, `rollout_gate` carries the simulated comparison, `verify_plan` gives
ground truth over a whole episode, and `_PLAN_INFO[env]["replans"]` is the
history. None of it is currently surfaced as a report.

## 5. An assignment must be allowed to fail

This is what separates an agent from a function call. A function returns a
result; an agent may also return a reasoned **no**:

- "I held the connections, but train 7 loses 8 minutes — do you want that?"
- "I found nothing better than what is already running."
- "This is outside what I can plan; here is why."

The honesty mechanics are already implemented and simply invisible:
`splice_entries` returns `None` when the new plan does not extend the captured
seed, `rollout_gate` keeps the current plan on a tie ("churn must pay for
itself"), and `_plan` records `source: "avoidance (no models)"` or
`"unroutable"` when it degrades. `director-mode.md` §3.8 is candid about the
measured quality of mid-episode recovery (3 wins vs 3 losses, one catastrophic,
predicted margin does not separate the cases). An agent that reports this is
worth more than one that always has an answer — and it is the only version that
is defensible in a study.

## 6. Long-running assignments are already half-built

`_start_replan_job` captures state, searches on a daemon thread and lets the
current plan keep driving until the result is re-anchored to a fresh capture.
That is exactly the shape a long-running assignment needs: it survives the world
moving underneath it. What is missing is only the outside of it —

- a status ("working on the disruption at train 4, 12 steps in"),
- a cancel,
- and, later, more than one assignment in flight at a time.

Multiple concurrent assignments are the natural end state (three disruptions,
three cases, at different stages), but they need a scheduling story that today's
single global plan does not have. Not a first step.

## 7. Where this sits relative to the three control altitudes

It is **not a fourth mode**. The brief's three altitudes (objective / policy /
single agent, §4.1) stay exactly as they are. Delegation adds two orthogonal
dials:

- **Assignment size** — from "one incident" to "the whole session".
- **Release level** — act and report / propose and wait / ask when unsure.

| | Objective | Policy | Single agent | **Assignment** |
|---|---|---|---|---|
| Recommendation | optional | AI suggests a switch | AI suggests an action | propose-only |
| Co-Learning | optional | neutral options | neutral options + what-if | propose-only, comparable |
| Director | primary lever | swap lever | take-over lever | **act-and-report** |

This keeps the line the project has held so far: the three modes are levels of
automation, and cross-cutting capabilities are layers, not new modes.

## 8. Smallest slice that demonstrates it

One assignment, on one incident, in Director:

1. The dispatcher marks a disruption and picks a goal plus at most one
   constraint.
2. "Take this over" calls the existing `residual_plan` with that scope.
3. While it runs, a status surface shows that an assignment is in flight
   (`ai-activity` is the natural home) and offers cancel.
4. It returns a **report** (§4) and, at release level `propose`, waits.
5. Accept applies it through the existing `apply_residual_plan` path; reject
   keeps the current plan and logs the refusal.

Genuinely new: the assignment object, the status surface, the report. The rest
is wiring to things that exist. Frontend homes already in the tree:
`features/director-directive`, `features/goal-achievement`, `features/ai-activity`,
`features/decision-log`.

## 9. Deliberate non-goals

- **Free text as the command channel.** Our action space is small and formal; a
  structured assignment form is more precise, checkable, and — decisive for a
  study — comparable across participants. Free text produces data that cannot be
  analysed. Language as an *explanation and follow-up* channel (ask why, refine,
  re-run) is a different and later question.
- **Per-agent policy assignment.** Scoping an assignment to a set of trains is
  not the same as giving those trains their own policy; the latter is the
  backend change described in the brief §4.4 and stays out of scope.
- **A separate agent framework.** The delegation layer is state plus a report
  format around the planner we already run in-process. Nothing here needs a new
  runtime.

## 10. Open questions / risks

- **Situation awareness.** The brief's hard constraint (§4.2b) is that the
  director role must not degrade the human's situation awareness or motivation.
  Delegation is precisely the mechanism that could — the dispatcher hands work
  away and stops watching. The report and the goal-achievement view carry that
  burden; this needs to be measured, not assumed.
- **Scoping is not free.** A scoped residual plan is a different optimisation
  problem from the global one, and the trains outside the scope still move. Does
  "only this incident" produce plans that are worse *globally* than not
  intervening? `rollout_gate` can answer this per case, but the systematic
  answer is unknown.
- **Constraint feasibility.** Hard constraints can make an assignment
  unsatisfiable. The agent must distinguish "no better plan exists" from "your
  constraints exclude every plan" — different messages, different next moves.
- **What is the accepted unit of accountability?** An accepted report is an
  approval of a whole bundle of decisions. That is weaker per-decision
  accountability than an override. Worth naming in the study design.

## 11. Suggested order

1. Assignment object + scoped call into `residual_plan` (backend, no UI).
2. Report structure from data that already exists (score / rollout / verified).
3. Status + cancel surface for an in-flight assignment.
4. Release levels, starting with `propose`.
5. Only then: constraints beyond scope, and more than one assignment at a time.

## Consortium anchors

- **D3.1 §7 — the official Director System** (public since 2026-03, checked
  2026-08-19). Its worked example is from *disruption management*: the intent
  "search suitable trains for rerouting" is expressed as a command input and
  executed by composing primitives — (1) identify affected trains and routes,
  (2) filter by train type / capacity, (3) filter for direct-to-destination
  services → a ranked shortlist. That is an assignment with a scope, a
  decomposition and a returned result; compare §3–§4 here.
- **D3.1 §3 — A3S** names "auditing, logging and what-if analysis" as service
  properties, and TraceRL's "structured audit trail of operator decisions, AI
  recommendations and uncertainty estimates" is the reporting half of §4.
  Their autonomy continuum — *autonomous recommendations → supervised mode →
  operator override → simulation-only validation* — is the same axis as the
  release levels in §3.

- Brief [`interaction-modes-brief.md`](../reference/interaction-modes-brief.md)
  §4.1 (three altitudes), §4.2b (token-based directives, negotiation proxy,
  situation-awareness constraint), §4.4 (per-agent policy is a separate change).
- [`director-mode.md`](../reference/director-mode.md) §1, §3.7, §3.8, §5.1 —
  the existing planner, its search strategies, its re-planning and its three
  kinds of number.
- [`AI4REALNET/Tokener`](https://github.com/AI4REALNET/Tokener) and
  [`AI4REALNET/T3.4-with-HMI`](https://github.com/AI4REALNET/T3.4-with-HMI) —
  the token → solver path (tokens rewrite edge costs and planning order before
  CBS/PP replans). Note the divergence: in the reference implementation the
  human input is a constraint on a solver call; here it is an assignment with a
  scope, a budget and a report obligation.
