# CLAUDE.md — Flatland Dispatcher (Human-AI Teaming Playground)

## What this repo is
A modular HMI for interactive railway dispatching experiments, part of
**AI4REALNET** (EU Horizon). Frontend: Angular (standalone components + signals)
with SBB Lyne. Backend: FastAPI + Flatland-RL. See `README.md` and
`docs/reference/architecture.md`.

## Current focus — three human-AI interaction modes
We are making the three collaboration modes **behaviourally distinct and
switchable** (they exist in code but currently behave almost identically):

- `recommendation` → WP 3.1 — AI suggests **with** a recommendation, human decides
- `co-learning` → WP 3.3 — AI offers **neutral** options; human decides, reflects, simulates what-ifs
- `director` → WP 3.4 — AI runs autonomously on high-level directives; human supervises (**adjustable autonomy**)

### ► Authoritative spec: `docs/reference/interaction-modes-brief.md`
Read it before touching mode behaviour. It maps each step of the
consortium-validated interaction flows onto concrete files/signals in this repo
(`SessionStore.interactionMode`, `recommendations-panel`, `agent-inspector`,
`co-learning-reflection`, `setOverride`, `conflict_detector`, …), lists what
exists vs. what's missing, gives the implementation tasks, the "do not touch"
list, and a suggested order of work. It is grounded in the official **AI4REALNET
RP2 Part B** report (2nd EU review) — see its §7 for the source quotes.

## Cross-reference the AI4REALNET source code (you have access to the org)
Before reinventing behaviour, check the consortium reference implementations on
the **`AI4REALNET` GitHub org** and align naming/semantics with them:

- **Director / token-based directives (T3.4):**
  [`AI4REALNET/Tokener`](https://github.com/AI4REALNET/Tokener) — two approaches:
  **Hybrid** (CBS+PP planning, token-based interaction) and **Co-Learning**
  (human-in-the-loop, transparent adaptation). The Hybrid approach is the
  reuse target for our own planned PP/CBS planner (brief §4.2b; see
  `recommender-roadmap.md`'s PP-replan-recommender item) — check it before
  building token/negotiation logic from scratch. Also see
  [`AI4REALNET/T3.4-with-HMI`](https://github.com/AI4REALNET/T3.4-with-HMI) —
  a PPO controller + HMI that injects high-level decisions at runtime while the
  controller stays the base decision layer (same seam as our Policy registry +
  Director directives).
- **What-if analysis (T3.1, EnliteAI A3S / TraceRL):**
  [`AI4REALNET/agent-as-a-service-trace-rl`](https://github.com/AI4REALNET/agent-as-a-service-trace-rl) —
  confirmed: a Redis-backed service that restores/simulates-forward/reports
  action spaces (Flatland-configured already), plus a Dash tree-visualisation
  app for branching trajectories (override → alternative future). **Convention:
  human-influenced steps = blue, AI-simulated steps = yellow.** Reuse for our
  Co-Learning compare (brief §3.3) and tile B1 (`tile-catalog.md`).
- **Co-Learning HMI (T3.3, FHNW / Flatland):** the dedicated learning-support
  HMI — formulate-own vs. AI-recommended solutions, impact comparison, and a
  post-run **statistical + open-question reflection** module (brief §3.2/§3.3).
  See also [`AI4REALNET/T3.3-3.4-HMI`](https://github.com/AI4REALNET/T3.3-3.4-HMI) —
  a full PyQt reference HMI covering **both** Co-Learning and Director/Autonomous
  interaction on Flatland; skim it before designing new Co-Learning/Director
  widgets (e.g. tile D1, C2).
- **CDRTrainer (TUD):** human feedback + action shielding + expert demonstrations
  (the one WP3 artefact with a DOI) — reference for the "AI learns from human" loop.
- **Explaining action alternatives (T2.3, D2.3):**
  [`AI4REALNET/T2.3_explaining_action_alternatives`](https://github.com/AI4REALNET/T2.3_explaining_action_alternatives) —
  generates accurate *expected-outcome* explanations per action alternative
  without assuming the operator's reward weights. This is the concrete
  AI4REALNET grounding for our **Assessment** framing (Evaluative AI,
  `interaction-framework.md` §2) — the reuse target for tile C1.
- **Validated HMI surveys (Q5 study instruments):**
  [`AI4REALNET/hmisurveys`](https://github.com/AI4REALNET/hmisurveys) (TU Delft) —
  a modular, **validated** human-factors/cognitive-engineering survey framework
  for human-AI teaming, standalone HTML + JSON export. Check this before
  writing new survey questions from scratch (`features/survey/`,
  `core/survey/survey-configs.ts`); it's an instrument, not an algorithm, but
  the same "don't reinvent" rule applies — validated items beat home-grown ones
  for a study.

If a referenced repo's API or naming differs from this repo, prefer the
consortium convention and note the divergence in the PR.

**Reuse, don't reinvent, the algorithms.** For anything with an AI4REALNET
reference implementation — e.g. **A3S** for what-if / uncertainty (the basis for
tile A1, `docs/plans/tile-a1-risk-uncertainty.md`), or the Tokener negotiation
proxy for Director — integrate the consortium's code/approach by default.
Building our own algorithm from scratch is the exception, not the default: only
do it as an explicit, stated decision (e.g. in the tile spec's Open
questions/risks section), not by omission. This applies to the algorithms
themselves (UQ, calibration, policy negotiation, …); presentation/HMI framing
around them stays ours.

## Guardrails (full list in brief §6)
- Keep mode semantics in the `InteractionMode` union — no parallel flags.
- Don't change trajectory compression (`session.store.ts _recordTrajectory`) or
  the scenario-refresh throttling in `scenario-panel`; don't break the
  `_recoverPolicyAndRetry*` fallbacks.
- Policy is **global per session** today; per-agent policy is a separate backend
  change (brief §4.4) — don't assume it exists.
- Frontend stays Angular standalone + signals + SBB Lyne; backend stays FastAPI +
  Flatland. Prefer gating presentation in the frontend over reshaping payloads.
- **No hardcoded colours.** Never write raw hex / `rgb()` / `rgba()` in component
  SCSS or templates. Use Lyne semantic tokens (`--sbb-color-*`), the app tokens in
  `styles.scss` (`--app-*`, `--color-*`, `--layer-color-*`), or `light-dark(a, b)`
  for theme-aware values. New colours → add a token, don't inline. This keeps a
  future **dark mode** (Lyne `.sbb-dark` / `color-scheme`) a config flip instead of
  a repo-wide rewrite. Agent colours stay in `AgentColorService`, not SCSS. The
  ~1085 existing hardcoded colours are legacy debt — don't add to them; migrate
  opportunistically when you touch a file. Full frontend/Lyne rules:
  `docs/reference/frontend-lyne-conventions.md` (also mirrored for other AI tools
  in `AGENTS.md` and `.github/copilot-instructions.md`).
- Keep existing tests green (`backend/tests/`); add coverage for new backend gating.

## Not yet available
Deliverables **D3.1** (control taxonomy / augment human decision-making) and
**D3.2** (beta software / agent-as-a-service KPI+event monitoring) would sharpen
the Director and goal-achievement design. They're public on ai4realnet.eu; pull
them in if available.
