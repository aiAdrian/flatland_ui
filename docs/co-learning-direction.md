# Co-Learning — direction & thinking

> Working notes on how we think about Co-Learning in this project (not a spec).
> Captures the key distinction that emerged: Co-Learning is not just "the AI
> learns a better algorithm" — it is the machine **learning to work with the
> human, through the interaction**.

## Co-Learning can live entirely in our own infrastructure

It needs neither InteractiveAI nor an event-based architecture. Those are
optional enhancements (cleaner incident→feedback linkage / persistence), not
prerequisites. Co-Learning has two halves:

- **Human learns from the AI** — Supportive-AI modes (transparency, exploration,
  animation, mirroring). Largely already built here: neutral options (§3.1),
  reflection with mirroring/animation (§3.2), intervention log, what-if (§3.3
  planned). Runs in Angular + FastAPI + Flatland.
- **AI learns from the human** — the bidirectional loop. This is the open part,
  and it splits into two distinct learning targets (below).

## The key distinction: two learning levels

**Level A — the AI learns the task** (task policy)
- Human corrections improve the dispatching policy.
- Needs real RL + training; data- and compute-hungry. Depends on the (paused) RL
  agent decision. Heuristics and a CBS/PP planner do NOT learn.

**Level B — the AI learns to work with the human** (interaction / collaboration policy)
- The machine builds a **model of the operator** and adapts its *collaboration
  behaviour* — not its routing. It learns, e.g.:
  - **Preferences**: what the operator values (punctuality vs throughput), from
    overrides / accept-reject rather than only from KPI sliders.
  - **Trust / autonomy**: frequent overrides → explain more, act less; following
    the AI → take more initiative (= adjustable autonomy, learned from data).
  - **Framing**: when to *recommend* vs *neutral* vs *act* (our `optionPresentation`).
  - **Timing / focus**: when to surface something, which train to flag, when to
    stay quiet.

## Why Level B fits our infrastructure especially well

- It does **not** require heavy task-RL. It learns from the interaction signals we
  **already capture** (`coLearningFeedback`: overrides, accept/reject, KPI
  weights, reflection).
- It feeds **levers we already have**:
  - inferred preferences → the KPI / scenario **scoring** (already wired to the
    backend) — i.e. *inverse-RL-lite*.
  - intervention/trust history → **mode / `optionPresentation`** (auto-adjust
    autonomy and framing).
- It is doable with **light methods** (Bayesian update over reward weights, a
  bandit/heuristic over autonomy level) — no GPU training needed.

## Consortium anchors (not invented here)

- **Supportive-AI / Hybrid Intelligence** (Hamouche/Waefler): continuous mutual
  improvement on both sides — Level B is the machine side of it.
- **"beliefs about operator reward weights"** — `T2.3_explaining_action_alternatives`
  and **`risk-sensitive-inverse-rl`**: learn operator preferences from behaviour.
- **Buçinca et al.** (cited in Hamouche): optimizing human-centric objectives with
  offline RL — optimize for the human, not only task reward.
- **Van Zoelen — mutual adaptation for human-AI co-learning**: both sides adapt.
- **Adjustable autonomy** (Marot et al. / RP2 Part B): autonomy level is exactly
  the variable Level B learns.

## Caveats

- Data-hungry: a single user yields little signal.
- Risk of over-adaptation / "gaming" the operator model.
- Evaluation is harder (human-centric metrics) — but aligns with the survey /
  study track.

## Suggested order

1. **Level B first** — it's the novel part, uses existing signals + levers, and
   needs no heavy RL agent. Concrete first building block: an **operator model**
   in the backend that (a) estimates reward weights from overrides/accept-reject
   → feeds KPI/scoring, and (b) proposes autonomy / `optionPresentation` from the
   intervention/trust history.
2. **Level A later** — bring in a learnable RL agent and an offline feedback→
   training loop (à la CDRTrainer: human feedback + action shielding + expert
   demonstrations) on top of `coLearningFeedback`.
3. **Event-based / persistence** as an optional later data layer — not required to
   start.
