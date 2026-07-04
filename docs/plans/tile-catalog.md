# Tile catalog — candidates, sources, effort, contribution

> Working collection of candidate tiles, classified per
> [interaction-framework.md](../reference/interaction-framework.md). Each entry:
> **source(s)**, `kind`, **effort** (Claude-Code tokens ≈ working sessions, and
> calendar days incl. review), **what must change**, and **contribution to our
> core questions**. Ranked within groups by contribution-to-effort.
>
> Sources: **[D3.1]** AI4REALNET solutions deliverable · **[D3.2]** beta software
> (A3S/TraceRL, T3.2 Pareto, INESC UQ, FHNW MARL) · **[UIX]**
> [ui-exploration-synthesis](../reference/ui-exploration-synthesis.md) (cross-model
> convergence) · **[DB]** owner's research line (accountability / trust /
> allocation).
>
> Core questions the playground must serve:
> **Q1** behaviourally distinct modes · **Q2** calibrated trust ·
> **Q3** accountability measurement · **Q4** allocation / Human-in-Control seam ·
> **Q5** study value (User Study 2 instruments).

Effort scale: **S** ≈ ≤150k tokens / ≤1 day · **M** ≈ 150–400k / 1–3 days ·
**L** ≈ >400k / 3–5+ days (backend + frontend + tests).

## A. Trust & accountability (owner's centre of gravity)

### A1. Risk & Uncertainty indicator ("honest uncertainty") — [D3.1]+[D3.2]+[UIX]+[DB]
`kind` **Trust** · overview→detail. Per recommendation/option: reliability
indicator + uncertainty interval; detail view separates *why uncertain* (data vs
model — epistemic/aleatoric per INESC framework as far as backend allows).
- **Effort:** M. **Change:** frontend tile + backend proxy first (scenario-KPI
  spread, forecast variance across rollouts = cheap ensemble); true epistemic/
  aleatoric = later backend extension (flagged, not faked).
- **Contributes:** Q2 (core), Q1 (framing per mode), Q5 (overtrust proxy data).
  Direct D3.1 family #1; UIX top-bet "consequence-first card + honest uncertainty".

### A2. Decision log & accountability strip — [DB]+[D3.1]
`kind` **Capitalization** · detail. Decisions as owned events
(`accountableOwner`, lifecycle), rendered as a session strip: who decided what,
when, response time, override vs accept; JSON export.
- **Effort:** M (rides on [interaction-logging-plan](interaction-logging-plan.md)
  — realises its first slice). **Change:** frontend store already sees decisions
  (`setOverride`, applyOption, auto-decide); add an event record + tile; backend
  optional at first.
- **Contributes:** Q3 (core — override rate, friction asymmetry, decision-time ÷
  acceptance), Q5 (the study instrument), Q4 (owner comes from `allocation`).

### A3. AI track record / reliability history — [DB]+[D3.1]
`kind` **Trust** · overview. Rolling record: how often were AI suggestions
taken / overridden, and how did followed vs overridden decisions turn out
(delay delta). The calibration mirror for the operator.
- **Effort:** M–L (needs outcome attribution per decision → depends on A2).
- **Contributes:** Q2 (appropriate reliance, Weyer-vs-Grote tension made
  visible), Q3, Q5.

## B. Prediction & what-if (A3S/TraceRL line)

### B1. What-if branch compare ("A3S-light") — [D3.2]+[D3.1]+[UIX]
`kind` **Prediction** · detail. Take a decision point, branch: AI plan vs
operator override, simulate both forward (existing `whatIfOverride` + scenario
rollouts), compare side-by-side with KPI deltas. Convention: **human-influenced
steps blue, AI-simulated yellow** (consortium/TraceRL). A3S endpoints Restore /
Action-space / Simulate ≈ our session + overrides + what-if APIs — mostly there.
- **Effort:** M. **Change:** frontend tile (branch view + compare); backend
  mostly exists, maybe a "simulate N steps from current state with overrides"
  convenience endpoint.
- **Contributes:** Q1 (Co-Learning dual-path §3.3!), Q2 (simulation-backed
  interpretability instead of static XAI), Q4 (A3S pattern), Q5.

### B2. Conflict-aware Marey (ribbons + predicted lines) — [UIX 6/6]
`kind` **Prediction/Context** · overview→detail. Marey with conflict ribbons,
predicted trajectories, plan-vs-actual. Strongest cross-model UIX bet; central
to §3.3 (see marey-rethink note).
- **Effort:** L (graphic-timetable is complex; prediction overlay needs care).
- **Contributes:** Q1 (Co-Learning), Q5; less directly Q2/Q3.

## C. Decision support (Evaluative AI)

### C1. Trade-off frontier / scenario small-multiples — [D3.2 T3.2]+[UIX 6/6]+[D3.1]
`kind` **Decision Support (Assessment)** · overview. Scenario alternatives
plotted over 2 KPI axes (Pareto-style), small-multiple previews; operator picks
by situational priority instead of trusting one ranked list. T3.2's "ensemble of
policies = Pareto front" is exactly this; scenario-panel already computes
per-scenario KPIs.
- **Effort:** M. **Change:** frontend only to start (existing scenario KPI
  deltas); true multi-policy Pareto = backend/policy extension later.
- **Contributes:** Q1 (Assessment framing = Co-Learning; ranked = Recommendation
  — the mode switch made visible in one tile), Q2 (trade-off transparency), Q5.

### C2. Triage'd event feed (act-now sorting, lead-time bars) — [UIX 6/6]
`kind` **Event** · overview. Notifications sorted by required action time, not
chronology; lead-time bars; grouping (EEMUA 191 alarm practice).
- **Effort:** S–M (notifications-panel refactor + eta data mostly present).
- **Contributes:** Q5, situation awareness; indirectly Q3 (what did the operator
  see when deciding).

## D. Allocation & autonomy (seams made visible)

### D1. Autonomy dial / allocation panel — [D3.2 A3S #3]+[D3.1]+[DB]
`kind` **Control** · overview. Shows current `allocation` ({loop stage →
human/ai/shared}) as a visible panel; in Director, a dial from
autonomous-recommendation → supervised → override-only → simulation-only.
First step: **display only** (derived from mode) — already valuable as the
"who owns what right now" mirror; runtime adjustment later (seam §5a).
- **Effort:** S (display) → L (true runtime reallocation).
- **Contributes:** Q4 (core), Q3 (control-before-responsibility made visible),
  Q1.

### D2. Partial Non-Control zones — [DB]
`kind` **Trust/Context** · detail. Explicitly mark what the operator *cannot*
influence right now (e.g. malfunction duration, other trains under AI control)
— honest boundary per Grote, precondition for fair accountability.
- **Effort:** S–M (mostly framing/presentation of existing state).
- **Contributes:** Q3 (novel, owner's research contribution), Q2.

## Not tiles (kept off this list deliberately)
- **Full A3S adoption** — architecture stance (service wrapper, Redis/Hydra),
  not a tile; B1 is its minimal in-app expression.
- **Negotiation proxy transparency (FHNW MARL / Tokener)** — needs the MARL
  backend; revisit when real RL agents land (see rl-agents goal).
- **Competence-maintenance / AI-free practice phases** — mode/scenario-level
  design (guardian paradox), not a panel.

## Suggested first wave
**A1 (Risk & Uncertainty)** + **A2 (Decision log)** + **D1 (allocation display)**
— together they materialise Trust, make accountability measurable, and surface
the allocation seam, at ~S+M+M effort. **B1** is the strongest second wave
(Co-Learning §3.3 + A3S pattern), with **C1** as its Assessment complement.
