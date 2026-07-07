# Tile catalog — candidates, sources, effort, contribution

> **This doc is the backlog narrative** (sources, effort, contribution). The
> machine-readable counterpart — kind, granularity, status, per-mode behaviour,
> grounding, availability for every tile (built *and* planned) — lives in
> [`core/tiles/tile-catalog.ts`](../../frontend/src/app/core/tiles/tile-catalog.ts)
> and renders in the in-app **Tile Gallery** (`/gallery`). Keep the two in sync;
> author new tiles with the [`/create-tile`](../../.claude/skills/create-tile/SKILL.md) skill.
>
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
- **Status:** **first cut built** — `risk-uncertainty-panel.component.ts`,
  frontend-only, registered at the seams (plugin-host, palette, matrix). Not
  calibrated; label reads "model-reported confidence" until the UQ/calibration
  backend extension lands. See [tile-a1-risk-uncertainty.md](tile-a1-risk-uncertainty.md).
- **Effort:** M. **Change:** frontend tile + backend proxy first (scenario-KPI
  spread, forecast variance across rollouts = cheap ensemble); true epistemic/
  aleatoric = later backend extension (flagged, not faked).
- **Contributes:** Q2 (core), Q1 (framing per mode), Q5 (overtrust proxy data).
  Direct D3.1 family #1; UIX top-bet "consequence-first card + honest uncertainty".

### A2. Decision log & accountability strip — [DB]+[D3.1]
`kind` **Capitalization** · detail. Decisions as owned events
(`accountableOwner`, lifecycle), rendered as a session strip: who decided what,
when, response time, override vs accept; JSON export.
- **Status:** **first cut built** — `features/decision-log/` component + a
  `decisionLog` signal in `SessionStore` fed by the existing choke-points
  (`setOverride` / `clearOverride` / `systemHold`) in all three modes, tagged
  `accountableOwner: human | ai | system`. `coLearningFeedback` (Co-Learning
  only) left untouched. JSON export + override-rate / mean-decision-time
  readout. Registered at the seams (plugin-host, palette, matrix). See
  [tile-a2-decision-log.md](tile-a2-decision-log.md).
- **Effort:** M (rides on [interaction-logging-plan](interaction-logging-plan.md)
  — realises its first slice). **Change:** frontend store already sees decisions
  (`setOverride`, applyOption, auto-decide); add an event record + tile; backend
  optional at first.
- **Contributes:** Q3 (core — override rate, friction asymmetry, decision-time ÷
  acceptance), Q5 (the study instrument), Q4 (owner comes from `allocation`).
- **AI4REALNET check — confirmed WP4 validation-KPI alignment:**
  [`ai4realnet-orchestrators`](https://github.com/AI4REALNET/ai4realnet-orchestrators)
  (the WP4 Validation Campaign Hub / "FAB" integration) has a Railway module
  with a named human-factors KPI catalog (HS-003 intervention frequency,
  AS-005 agreement score, HS-023 response time, RS-091..096 reflection on
  trust/agency/de-skilling/over-reliance/biases) that overlaps almost
  one-to-one with this tile's fields — no code to reuse (those KPIs are
  uncoded, collected via survey/interactive-loop), but the schema should be
  named to map onto these IDs later without a rename. See tile-a2 spec §5b.

### A3. AI track record / reliability history — [DB]+[D3.1]
`kind` **Trust** · overview. Rolling record: how often were AI suggestions
taken / overridden, and how did followed vs overridden decisions turn out
(delay delta). The calibration mirror for the operator.
- **Effort:** M–L (needs outcome attribution per decision → depends on A2).
- **Contributes:** Q2 (appropriate reliance, Weyer-vs-Grote tension made
  visible), Q3, Q5.
- **AI4REALNET check:** two alternative/complementary UQ approaches to A1's
  evidential-NN target, both power-grid domain (semantic alignment, not
  drop-in) —
  [`RL-agent-uncertainty-prediction-module`](https://github.com/AI4REALNET/RL-agent-uncertainty-prediction-module)
  (Conformal Prediction — distribution-free intervals, arguably simpler than
  evidential NN) and
  [`failure_prediction`](https://github.com/AI4REALNET/failure_prediction)
  (D2.2, classical RF/XGBoost/LightGBM failure-prediction models — the
  "calibration data" reuse candidate for this tile's follow-up-outcome need).

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
- **AI4REALNET check — confirmed, exact reuse target:**
  [`agent-as-a-service-trace-rl`](https://github.com/AI4REALNET/agent-as-a-service-trace-rl)
  is A3S itself (Task 3.1 + Task 2.3), and it already has a **Flatland** config
  (`agent-as-a-service/conf/env/flatland/flatland.yaml`). Two parts:
  `agent-as-a-service` (Redis-backed: restore / simulate-forward / report action
  spaces) and `trace-rl` (Dash app rendering the episode as a **branching tree**
  of decision blocks, override → alternative future). Per CLAUDE.md's "reuse,
  don't reinvent" rule: this is the target, not a from-scratch what-if engine —
  the "convenience endpoint" above should wrap/mirror this rather than diverge
  from its restore/simulate/action-space vocabulary.

### B2. Conflict-aware Marey (ribbons + predicted lines) — [UIX 6/6]
`kind` **Prediction/Context** · overview→detail. Marey with conflict ribbons,
predicted trajectories, plan-vs-actual. Strongest cross-model UIX bet; central
to §3.3 (see marey-rethink note).
- **Effort:** L (graphic-timetable is complex; prediction overlay needs care).
- **Contributes:** Q1 (Co-Learning), Q5; less directly Q2/Q3.
- **AI4REALNET check:** no direct match found (org repos are algorithm/HMI-shell
  focused, not timetable-visualisation specific). `T3.3-3.4-HMI` (PyQt) may still
  be worth a glance for how it renders the Flatland network/schedule, but it is
  not a Marey-style time-distance view — this stays a from-scratch UI build.

## C. Decision support (Evaluative AI)

### B3. Network correlation graph — [DB]
`kind` **Context** · overview→detail. Force-directed graph of trains/stations
(nodes = circles, severity-coloured, sized on focus) connected by
correlation-strength edges — a relational abstraction of the network
alongside the geographic Track Layout map, so "what else does this touch?" is
answered by proximity/edge-weight instead of scanning the map.
- **Effort:** M. **Change:** frontend only to start (KPI-delta correlation
  proxy, same "cheap proxy before real backend" move as A1); new D3
  dependency (`d3-force`/`d3-selection`/`d3-drag`/`d3-zoom` subset).
- **Contributes:** Q1 (Context tile behaves differently per mode's focus
  logic), situational awareness beyond the geographic map; a testable Q5
  comparison (does the graph surface correlated-but-distant trains the map
  misses?).
- **AI4REALNET check — confirmed, exact reuse target:**
  [`AI4REALNET/InteractiveAI`](https://github.com/AI4REALNET/InteractiveAI) —
  the consortium's own multi-use-case HMI (PowerGrid **and Railway** share one
  frontend). Its `frontend/src/components/organisms/Graph.vue` +
  `stores/components/graph.ts` is a D3 force-directed graph with exactly this
  pattern: severity-coloured circle nodes (`criticality` classes
  `LOW/MEDIUM/HIGH`), correlation-weighted edges, focus/zoom/tooltip on
  click — and its `Map.vue` uses the same `criticalityToColor` helper for
  `LCircleMarker` status dots, i.e. the consortium already treats "severity as
  a coloured circle" as a shared idiom across their graph *and* map views. See
  [tile-b3-network-correlation-graph.md](tile-b3-network-correlation-graph.md).
  Domain note: their hex-hardcoded CSS vars (`--red-500: #f55`, …) must **not**
  be ported — reimplement with our Lyne/`visual-encoding.ts` token seam.

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
- **AI4REALNET check — strong match for the Assessment framing itself:**
  [`T2.3_explaining_action_alternatives`](https://github.com/AI4REALNET/T2.3_explaining_action_alternatives)
  (D2.3) generates accurate *expected-outcome* explanations per action
  alternative without assuming the operator's reward weights — this is the
  concrete grounding for "evidence for/against options" (better than citing
  Miller alone; see `interaction-framework.md` §2). For the Pareto/multi-policy
  half:
  [`Grid2Op_MORL`](https://github.com/AI4REALNET/Grid2Op_MORL) confirms a real
  multi-objective-RL/Pareto implementation exists (power-grid domain, semantic
  alignment only). Also see
  [`KPIs-cards`](https://github.com/AI4REALNET/KPIs-cards) (WP4) for the
  consortium's own filterable KPI-card convention — worth aligning small-multiple
  styling with.

### C2. Triage'd event feed (act-now sorting, lead-time bars) — [UIX 6/6]
`kind` **Event** · overview. Notifications sorted by required action time, not
chronology; lead-time bars; grouping (EEMUA 191 alarm practice).
- **Effort:** S–M (notifications-panel refactor + eta data mostly present).
- **Contributes:** Q5, situation awareness; indirectly Q3 (what did the operator
  see when deciding).
- **AI4REALNET check:** no direct match found; EEMUA 191 is external
  control-room practice, not a consortium artefact. Stays a from-scratch build.

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
- **AI4REALNET check — direct matches for the runtime-reallocation half:**
  [`Tokener`](https://github.com/AI4REALNET/Tokener) (Hybrid: CBS+PP,
  token-based interaction — matches "who owns what right now" made explicit
  via tokens) and
  [`T3.4-with-HMI`](https://github.com/AI4REALNET/T3.4-with-HMI) (PPO
  controller + HMI that **injects high-level decisions at runtime while the
  controller stays the base decision layer** — literally the display-then-dial
  progression this tile plans). Skim
  [`T3.3-3.4-HMI`](https://github.com/AI4REALNET/T3.3-3.4-HMI)'s
  `HMI_overview.png` for how they render the allocation/mode state before
  designing this tile's UI from scratch.

### D2. Partial Non-Control zones — [DB]
`kind` **Trust/Context** · detail. Explicitly mark what the operator *cannot*
influence right now (e.g. malfunction duration, other trains under AI control)
— honest boundary per Grote, precondition for fair accountability.
- **Effort:** S–M (mostly framing/presentation of existing state).
- **Contributes:** Q3 (novel, owner's research contribution), Q2.
- **AI4REALNET check:** no match found — this is the owner's own research
  contribution (Grote's Partial Non-Control), not in any consortium deliverable
  found. Stays a from-scratch build, deliberately.

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
