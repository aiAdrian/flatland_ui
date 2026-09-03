# Flatland ecosystem reuse — survey and plan

> Dated working plan, 2026-08-16. Result of a full read of the two AI4REALNET
> HMI repos (`T3.4-with-HMI`, `T3.3-3.4-HMI`) and all 14 repositories of the
> [`flatland-association`](https://github.com/orgs/flatland-association/repositories)
> org.
>
> Purpose: settle what we take, what we leave, and in which order — per
> CLAUDE.md's "reuse, don't reinvent" rule. Several existing plans in this repo
> are blocked on things that already exist; two of our documented assumptions
> turned out to be wrong. Both are recorded in §5.

---

## 0. The headline

Three findings drive the whole plan:

1. **Several of our planned features are waiting for capabilities our installed
   Flatland already has.** `Trajectory.fork()`, targeted malfunction injection
   and multi-objective rewards are all in `flatland-rl==4.2.6` today, untouched.
2. **There is a sibling project with our exact stack.**
   [`flatland-hmi`](https://github.com/flatland-association/flatland-hmi) is
   Angular + FastAPI + Flatland-RL, MIT, actively developed, with a live demo.
   That is a different class of reuse target than the AI4REALNET research
   prototypes.
3. **The scenario/timetable authoring layer is solved upstream**, in
   [`flatland-scenarios`](https://github.com/flatland-association/flatland-scenarios).
   The AI4REALNET drawing board we found first is a fork of it, with outdated
   vocabulary.

---

## 1. Source landscape

### AI4REALNET HMI repos

| Repo | Verdict |
|---|---|
| `T3.4-with-HMI` — Hybrid Approach | **Take.** Real CBS/PP solvers + the token→planner seam. |
| `T3.4-with-HMI` — Co-Learning Approach | **Take ideas.** Reward-mode triple, ensemble agreement, lookahead conflicts. |
| `T3.4-with-HMI` — `src/` (PPO/IMPALA stack) | Leave unless we pursue RL agents. |
| `T3.3-3.4-HMI` | **Take interaction structure only.** No algorithms — the interesting modules are stubs (`InteractionTracker`, `ControllerRef`, `SolutionTranslator` all `pass`). Director mode is WIP; we are ahead. |

Both are a single squashed "Initial commit" (FHNW, 2026-03-26) and pin
`flatland-rl==4.2.2`.

### AI4REALNET org — the rest (43 repos, surveyed 2026-08-16)

Most are power-grid or ATM domain (Grid2Op, BlueSky, sectorisation) and out of
scope. Of the repos this repo's docs had **not** referenced anywhere, four matter:

| Repo | Why it matters |
|---|---|
| [`flatland-blackbox`](https://github.com/AI4REALNET/flatland-blackbox) | **The canonical CBS/PP source** that both `Tokener` and `T3.4-with-HMI` vendor. Has a test suite and a `pyproject.toml`; the vendored copies have neither. Folded into W9. Also ships `2.1_Beta_release.pdf` (5.4 MB) — a deliverable document we do not otherwise have. |
| [`maze-flatland`](https://github.com/AI4REALNET/maze-flatland) | enliteAI (same house as A3S/TraceRL), **MIT**, `flatland-rl==4.2.3` — closest pin to ours of any consortium repo. Substantial: named reward objectives as first-class classes (`delay_based`, `distance_based`, `finish_asap`, `constant`), `env/kpi_calculator.py`, `env/events.py`, and `env/masking/mask_builder.py` (decision-point action masking). See W3 and the note below. |
| [`Human-Assessment-Module`](https://github.com/AI4REALNET/Human-Assessment-Module) | Personalised models for cognitive performance and stress from **physiological data** (ECG), with a full experimental protocol (Baseline → CRTT → TSST → CRTT). Not code we can use — it needs hardware and MATLAB/Psychtoolbox — but it is the consortium's answer to "how do we measure operator state", and therefore context for our study design alongside `hmisurveys`. |
| [`flatland-commnet`](https://github.com/AI4REALNET/flatland-commnet) | PPO/DDDQN + CommNet inter-agent message passing on Flatland. Only relevant if we pursue the RL-agent goal; noted so it is not rediscovered. |

Checked and **not** relevant: `D1.1-decision-making-analysis` (a single
word-embeddings notebook), `XLLM`, `T2.3_explainability_dashboard`,
`distributed_rl`, `network-distributed-q-learning`, `risk-sensitive-inverse-rl`,
`safe-constrained-policy-gradient`, `soft_label_gnn`, `failure_prediction`,
`grid2evaluate`, `GNPDT`, `RL-agent-uncertainty-prediction-module`,
`T2.1_*`, `ATMSectorization`, `bluesky*`, `Grid2Op_MORL`, `pypowsybl2grid`
— other domains or other work packages.

⚠️ The org also mirrors `flatland-rl`, `flatland-book`, `flatland-scenarios`,
`flatland-baselines`, `ai4realnet-orchestrators` and
`flatland-benchmarks-f3-starterkit` as **forks last pushed 2025-09-30 to
2026-02-03** — months behind the `flatland-association` originals. Always read
those from `flatland-association`, never from the AI4REALNET mirrors.

**`maze-flatland`'s reward taxonomy is a second, independent witness for W3.**
Two consortium projects arrived at the same answer: a strategy option is a named
objective/model, not a weighting. `T3.4`'s Co-Learning does it as three trained
PPO models (`safe`/`balanced`/`efficient`); `maze-flatland` does it as reward
classes. Our A/B/C tiles should follow.

The org website (`AI4REALNET.github.io`) is a Vite/Tailwind site with **no
deliverable PDFs** — CLAUDE.md's "D3.1 / D3.2 not yet available; they're public
on ai4realnet.eu" is unchanged by this survey.

### flatland-association org (14 repos)

| Repo | Class | Verdict |
|---|---|---|
| `flatland-hmi` | **A** | Sibling project. Port `link_map.py`; study trajectory API. |
| `flatland-scenarios` | **A** | Scenario model + timetable layer + Olten. |
| `flatland-rl` | **A** | 4.3.0 available; unblocks B4. See §4. |
| `ai4realnet-orchestrators` | **A** | WP4 campaign, 5 railway KPIs, contains a `railway/playground/` runner. |
| `flatland-hmi-hack4rail` | B | Predecessor HMI (Marey + route variants). Ideas only; stale since 2025-06. |
| `flatland-baselines` | B | `DeadLockAvoidancePolicy` as a package — compare against ours. |
| `flatland-benchmarks` (FAB) | B | Platform behind `fab.flatland.cloud`; documents the `interactive-loop`. |
| `flatland-book` | B | Official docs, incl. Stations & Links. |
| `flatland-workshop-2024` | B | Backlog explains provenance ("Human in the Loop and Flatland", "Complex schedules using Netzgrafikeditor"). |
| `netzgrafik-editor-docker-compose` | B | SBB timetable editor, local deploy. |
| `netzgrafik-editor-helm-charts` | C | k8s variant of the above. |
| `ecml2026-starterkit` | C | Already covered by [`ecml2026-flatland-env.md`](ecml2026-flatland-env.md). |
| `flatland-benchmarks-f3-starterkit` | C | Flatland 3 competition. |
| `InteractiveAI` (fork) | C | Covered by [`event-based-architecture-analysis.md`](../archive/event-based-architecture-analysis.md). |

---

## 2. Deliberate non-goals

Recorded so they are not re-litigated:

- **`@flatland-association/flatland-ui` (npm).** "Flatland association *identity*
  UI components" — branding, not railway widgets. Peer-deps Angular ^20.3 +
  Tailwind ^3.4; we are Angular 22 + SBB Lyne. Not adopted.
- **PyQt anything** from either AI4REALNET repo. Presentation only, not portable.
- **`NegotiationProxy.py`** (616 bytes, `perform_negotiation()` is `pass`).
  Confirms [`widget-catalog.md`](widget-catalog.md)'s decision to keep
  negotiation-proxy transparency off the widget list.
- **The floating multi-window paradigm** of `T3.3-3.4-HMI`. Our docked
  widget/layout system is further along.
- **Full A3S adoption** — unchanged from `widget-catalog.md`. Note that
  `Trajectory.fork()` (§3, W1) covers B1's core need without it.
- **The FHNW drawing-board fork.** Superseded by the upstream tool; its
  "Schedule"/"Train Class" vocabulary is the naming Flatland 3 deprecated.

---

## 3. Track 1 — Use what 4.2.6 already ships

No dependency change. Highest value per effort in the whole plan.

### W1. Trajectory forking for What-if compare — [B1]
`Trajectory.fork(data_dir, start_step, ep_id)` exists in our installed
`flatland/trajectories/trajectories.py:449`. `flatland-hmi` wraps it in
`POST /trajectories/{id}/fork` (see its `trajectory_context.py`) — a working
reference for the endpoint shape.

- **Effort:** M. **Touches:** [`widget-b1-whatif-compare.md`](widget-b1-whatif-compare.md),
  `backend/app/core/scenario_runner.py`.
- **Note:** we currently fork via `RailEnvPersister.save` → `load_new`
  ([`scenario_runner.py:318`](../../backend/app/core/scenario_runner.py)). Evaluate
  whether the native fork replaces or complements that path; do not rip out the
  working one before the replacement is proven.

### W2. Scripted, targeted malfunctions — [scripted-events, localized-blocking]
`flatland/envs/malfunction_effects_generators.py` (4.2.6) already provides:

```python
ConditionalMalfunctionEffectsGenerator
on_map_state_condition(env_agent, elapsed_steps)
condition_stopped_intermediate_and_range(start_step_incl, end_step_excl)
condition_stopped_cells_and_range(start_step_incl, end_step_excl, cells)   # ← targeted
make_multi_malfunction_condition(conditions)
```

`condition_stopped_cells_and_range` is a malfunction at **named cells** within a
**named step window** — exactly what
[`scripted-events-plan.md`](scripted-events-plan.md) and
[`localized-blocking-decisions.md`](localized-blocking-decisions.md) describe as
to-build.

- **Effort:** S–M. **Contributes:** reproducible study conditions.

### W3. Real objective functions behind the A/B/C strategy tiles
`flatland/envs/rewards.py` (4.2.6) ships `PunctualityRewards`,
`ECML2026Rewards`, `BasicMultiObjectiveRewards`, `DefaultRewards`.

Pair this with the `T3.4-with-HMI` Co-Learning finding: their three strategy
options are three **separately trained models** with distinct reward modes
(`safe` / `balanced` / `efficient`), not three weightings of one score. Our
`strategy-options` tiles should carry a model/objective identity, not just
weights.

- **Effort:** M. **Touches:** `director-weights`, `strategy-options`,
  [`recommender-roadmap.md`](recommender-roadmap.md).

### W4. Ensemble agreement as the first uncertainty signal — [A1]
From `human_in_loop_compact.py`: with several models recommending at once, the
UI states either *"All models AGREE on this recommendation"* or *"Models
DISAGREE — choose carefully!"*.

Our codebase has no agreement/ensemble concept at all. This is far cheaper than
the evidential NN in `RL_agent_failure_forecast` and is genuinely Co-Learning
shaped: it tells the operator *when their judgement matters most*. Proposed as a
**precursor** to, not a replacement for,
[`widget-a1-risk-uncertainty.md`](widget-a1-risk-uncertainty.md).

- **Effort:** S–M (needs ≥2 recommenders/policies runnable per situation).

### W5. Small HMI borrowings from `T3.3-3.4-HMI`
Cheap, concrete, independent of everything else:

- **On-map / off-map grouping** for malfunctions and incidents. We know `off-map`
  as an agent state but never group notifications by it. Ties into widget D2
  (Partial Non-Control): an off-map malfunction is literally something the
  operator cannot act on visually.
- **Analysis triple** — *Risk assessment · number of sub-actions · impacted
  trains* + per-train predicted effect. Our `models/hmi.py` has none of these.
- **Predicted-vs-actual in the same window shape** — their incident review reuses
  the pre-decision analysis layout, with actual delays replacing predicted ones.
  Good principle for `shift-review` / `decision-log`.
- **Provenance in the title** — "*Formulated* Solution Analysis" vs the
  AI-generated variant.
- **"Adjust" as a third verb** next to accept/reject in `recommendations-panel`.
- **Reflection questions**: the consortium's five exist in German already
  (`reflection_module.png` is a DE design mockup) — relevant to the planned i18n
  toggle. Cross-check against our context-aware questions before adopting.

---

## 4. Track 2 — Port

### W6. Link Map (ZWL) — [B4] · **depends on W8**
[`widget-linkmap-zwl.md`](widget-linkmap-zwl.md) is written and correct. Its
blocker is resolved: `flatland/envs/stations_links.py` shipped in **4.3.0
(2026-08-10)**. The plan's statement that it is "not yet on PyPI … requires
pinning flatland-rl to a git commit" is now stale (§5).

Port `backend/app/link_map.py` (~42 KB) from `flatland-hmi` with MIT
attribution. Port the *pure* transforms from its `marey.component.ts` and
`link-map.component.ts`; rewrite the RxJS layer against our `SessionStore`
signals per CLAUDE.md.

- **Effort:** L.

### W7. Timetable layer in the infrastructure builder
[`docs/infrastructure_builder/requirements.md`](../infrastructure_builder/requirements.md)
already names `flatland-scenarios/scenario_generator` as a target consumer — but
our [`scene.model.ts`](../../frontend/src/app/features/infrastructure-builder/models/scene.model.ts)
has no `lines` / `timetables` / `trainCategories`. Our agents are point-to-point;
upstream's trains are timetable-derived.

Adopt the **upstream key names** so `Scenario.load()` reads our export without a
converter:

```
gridDimensions · grid · overpasses · stations · lines · timetables
trainCategories · flatlandLine · flatlandTimetable
```

and the computation rule (`travel factor` × shortest-path distance, `dwell
time`, `shift`), which upstream resolves down to Flatland's
`earliest_departure` / `latest_arrival`. Their `ScenarioBuilder` already
provides `rescale_timetable`, `add_timetable(shift)`, `sample_timetables`.

Feeds [`widget-timetable.md`](widget-timetable.md),
[`heterogeneous-tracks.md`](heterogeneous-tracks.md),
[`cities-stations-plan.md`](cities-stations-plan.md).

- **Effort:** L. MIT — lifting `scenario.py` / `ScenarioBuilder` is fine.

### W8. `flatland-rl` 4.2.6 → 4.3.0 — **coupled to W6, not a prerequisite**
Deliberately *not* scheduled first. Everything in Track 1 runs on 4.2.6; only
W6 needs the bump.

**What we gain:** `stations_links`, link-map fixes (double slips, non-adjacent
cells), `PolicyRunner.change_policy()`, `DelayRewards`, `trajectory_analysis`,
Cython speedups, and a persistence format that stays readable by older readers
(relevant for the Olten v1/v2 files, generated with 4.0.6/4.1.0).

**Two risks, both to verify before merging:**

| Risk | Detail |
|---|---|
| **No wheel** | 4.3.0 publishes **sdist only** and adds `cython>=3.2.9`. `pip install` compiles from source — affects Docker images and CI, not local dev. 4.2.6 had `py2.py3-none-any.whl`. |
| **Reward semantics changed** | Collision penalty no longer applies when the controller issues `STOP`; an intermediate stop counts as served at *any* halting cell of the station. **4.2.6 and 4.3.0 numbers are not comparable.** Re-baseline before/after. |

Removed APIs (`RailEnv.record_timestep`, `_apply_timetable_to_agents`) — verified
unused by us. `RailEnvPersister.save` / `load_new` signatures unchanged, but that
path received several behavioural fixes; it is our env-fork path, so it is the
place to watch.

- **Effort:** S (bump) + M (verification).

### W9. PP/CBS replan recommender
[`recommender-roadmap.md`](recommender-roadmap.md) item 2.

**The Flatland-version worry that has shadowed this item is largely moot.**
Verified 2026-08-16: `cbs.py` and `pp.py` import **nothing from Flatland** — they
operate on a `networkx` graph plus an agent list. Everything they pull from
`utils.py` (`NoSolutionError`, `get_row/get_col/get_direction`, `normalize_node`,
`is_proxy_node`, `true_distance_heuristic`, `get_start/goal_proxy_node`) is a
pure graph/node helper. Only `utils.py`'s *env-setup and rendering* half touches
Flatland (`sparse_rail_generator`, `RenderTool`, `plotGraphEnv`), and the solvers
never call it — we build our own envs anyway.

So the "4.0.3 vs 4.2.6 mismatch" recorded in [[cbs-pp-planner-integration]] is a
declaration-level mismatch, not a code-level one, for the solver core.

**Take from two places:**

| From | What | Why that one |
|---|---|---|
| [`AI4REALNET/flatland-blackbox`](https://github.com/AI4REALNET/flatland-blackbox) | `solvers/cbs.py`, `solvers/pp.py`, the pure half of `utils.py` | The canonical upstream: proper `pyproject.toml` **and a test suite** (`tests/test_solver.py`, `test_utils.py`) that the vendored copies dropped. |
| `T3.4-with-HMI` `Hybrid Approach/` | `state_extraction.build_rail_digraph`, `plan_follower.plan_to_actions`, `blackbox_adapter`, `token_utils` | The integration layer, written against 4.2.2 — the missing piece between a planner and our `Policy` protocol. |

The solver files in `T3.4-with-HMI` are **byte-identical** to upstream (verified
by diff), so there is nothing to gain from the vendored copy of those — only from
the adapter layer around them.

**Scope note — take the solvers, skip the training loop.** `flatland-blackbox`
ships `2.1_Beta_release.pdf`, the Task 2.1 beta release by Marius Captari and
Herke van Hoof (UvA): *Neural Prioritized Planning*. It explains the repo's name
and the `learned_l` edge attribute that `token_utils.py` writes to. The idea is
to **learn graph edge weights** so that greedy PP lands closer to CBS-optimal,
differentiating through the solver per Vlastelica et al. 2019.

The reported gains are small. On 30×30 maps, mean flow-time:

| Agents | CBS | PP | Trained PP |
|---|---|---|---|
| 3 | 59.75 | 60.74 | 60.38 |
| 7 | 140.86 | 144.39 | 143.03 |
| 11 | 224.33 | 230.14 | 227.67 |

Trained PP recovers roughly a third of the PP→CBS gap, for the cost of a torch
dependency and a training pipeline. **Not worth it for us.** Take `cbs.py` and
`pp.py` as plain solvers; leave `train.py`, `models.py` and the torch dependency.

Two items from its "Perspectives" slide are worth knowing, because they are our
use case and the authors flag them as *not yet done*: *"if breakdowns happen,
replan using updated positions/weights"* and *"learn to assign priorities (learn
to rank)"*. The first is exactly this work item; the second is W10's priority
token. We are not duplicating finished consortium work here.

- **Effort:** L.

### W10. Directives with planner consequences
The smallest high-value idea in the whole survey. Two mechanisms:

```python
# token_utils.py — AVOID_EDGE
G[u][v]["l"] = 1000; G[u][v]["learned_l"] = 1000

# blackbox_adapter.py — PRIORITY reorders the PP planning order
```

That turns a Director directive from a policy swap into something a planner
actually consumes. **No canonical token vocabulary exists upstream** — `AVOID_EDGE`
in one file, `PRIORITY` in another, `Delay/Stop/Prioritise` in the widget. We
define ours, but adopt their names.

- **Effort:** M. **Depends on:** W9. **Touches:** `director-directive`, D1.

---

## 5. Corrections to existing docs

Three statements in the repo are now wrong or too strong:

1. **[`widget-linkmap-zwl.md`](widget-linkmap-zwl.md)** — says `stations_links`
   is "not yet on PyPI (latest release 4.2.6)" and needs a git pin. Superseded by
   4.3.0 (2026-08-10). Update the backend table.
2. **[`recommender-roadmap.md`](recommender-roadmap.md) §Planned item 2** — names
   only `Tokener` (4.0.3 mismatch) as the PP/CBS reuse target. Add
   `T3.4-with-HMI`'s `flatland_blackbox` at 4.2.2 as the closer option.
3. **CLAUDE.md's framing of the scenario/timetable format** — for scenarios,
   timetables and the drawing tool the reference is the **Flatland Association**,
   not AI4REALNET. The AI4REALNET drawing board is a fork with deprecated
   vocabulary.

Additionally worth a line in [`wp4-validation-alignment.md`](../reference/wp4-validation-alignment.md):
the five railway KPIs are implemented in `ai4realnet-orchestrators` as
**AF-029** (AI response time), **AF-051** (agent scalability), **NF-045**
(network impact propagation), **PF-026** (punctuality), **RS-058** (robustness to
operator input). NF-045's method — run the scenario twice, once clean and once
with a single controlled malfunction, compare — is directly reusable for our
impact analysis. RS-058 measures close to what our study asks.

---

## 5b. Cross-domain — what ATM and power grid contribute

AI4REALNET runs the same human-AI teaming question in three domains. The
algorithms do not transfer; **the HMI patterns and the human-factors framing
do**, and two of them beat what we currently plan. Surveyed 2026-08-16.

### From ATM

**[`ATMSectorization`](https://github.com/AI4REALNET/ATMSectorization)** — a
standalone JS + D3 HMI for Dynamic Airspace Sectorization, and the most directly
instructive non-railway artefact in the org. Four ideas:

1. **Draw a no-go area, the planner re-routes.** Hold `CTRL`, drag over a grid to
   activate blocked cells, release — a Theta\* pathfinder re-routes the airways
   around them. That is our `AVOID_EDGE` token (W10) and
   [`localized-blocking-decisions.md`](localized-blocking-decisions.md) as a
   **direct-manipulation gesture on the map** instead of a dropdown. Strongly
   preferable as a Director interaction: the operator paints the constraint and
   watches the plan respond.
2. **Constraint violations rendered in place**, on the geometry itself (minimum
   line length, crossing points too close to an edge), not in a side panel. Our
   `builder-validation-panel` reports; theirs *shows*.
3. **A geometric complexity monitor per polygon.** A per-sector "how hard is this
   area right now" indicator. We have no per-area load/complexity measure at all
   — nothing between global KPIs and single-train detail. Worth considering for
   B3 / the map.
4. **Drill-down from aggregate to time series:** click a bar in the bar chart →
   line chart of predicted aircraft count over the next 120 minutes. Pattern for
   `strategy-forecast` and the KPI cards.

**[`CDRTrainer`](https://github.com/AI4REALNET/CDRTrainer)** (Clark Borst, TU
Delft) — already named in CLAUDE.md as the "AI learns from human" reference;
now concrete: a **single self-contained HTML file** with action shielding, human
feedback and expert demonstrations. Its objective set is the transferable part:

> avoid loss of separation · restore the original heading · minimise cross-track
> deviation · **minimise the number of manoeuvre events**

The last one is an **operator-burden objective** — the plan is worse if it
requires more interventions, independent of delay. Our KPIs (delay, deadlocks,
arrivals) have no such term. For a study about human-AI teaming this is an
obvious gap, and it costs nothing to add as a counted metric. Feeds W3 and
[`wp4-validation-alignment.md`](../reference/wp4-validation-alignment.md).

### From power grid

**[`RL-agent-uncertainty-prediction-module`](https://github.com/AI4REALNET/RL-agent-uncertainty-prediction-module)
— Conformal Prediction.** The single most useful cross-domain find. It wraps a
predictor to produce **distribution-free prediction intervals with a coverage
guarantee**, and it is method-agnostic: it does not care whether the underlying
predictor is a heuristic, a planner or an RL model.

[`widget-a1-risk-uncertainty.md`](widget-a1-risk-uncertainty.md) currently
targets `RL_agent_failure_forecast`'s evidential NN, which requires training a
specific network. Conformal prediction would give calibrated intervals around
our existing delay/ETA estimates **without replacing the estimator** — a far
smaller step, with a stronger honesty property (stated coverage). Recommend
evaluating it as A1's method before committing to the evidential NN. Ordering
against W4 (ensemble agreement): W4 is cheaper still and answers a different
question ("do the models disagree?" vs "how wide is the interval?"); they
compose rather than compete.

**[`risk-sensitive-inverse-rl`](https://github.com/AI4REALNET/risk-sensitive-inverse-rl)**
— "Learning Utilities from Demonstrations in Markov Decision Processes"
(Lazzati & Metelli, **ICML 2025**, AI4REALNET-funded), with a human study of 15
participants. Inverse RL that recovers a **utility function including risk
attitude** from demonstrations. Conceptually this is the formal version of what
Co-Learning's "AI learns from human" claims to do, and of what
`director-weights` asks the operator to state explicitly. Not something to
implement — but the right citation when we argue why we let the operator *state*
preferences instead of inferring them.

**[`XLLM`](https://github.com/AI4REALNET/XLLM)** — a multi-agent LLM pipeline
(generate → critique → refine → evaluate) that turns AC-OPF results into operator
explanations. Context only: it is the consortium's answer to natural-language
explanation for operators, and it is the same idea as `T3.3-3.4-HMI`'s
unimplemented "translate the operator's free-text solution into actions via RAG".
This repo deliberately has no LLM in the loop; noting it so that decision stays
explicit rather than accidental.

**[`T2.3_explainability_dashboard`](https://github.com/AI4REALNET/T2.3_explainability_dashboard)**
— an explainability panel for RL agents, but hard-wired to `ExpertOp4Grid` and an
L2RPN agent. Domain-locked; the sibling `T2.3_explaining_action_alternatives`
(already our C1 reuse target) is the railway-relevant half of Task 2.3.

### What does not transfer

Grid2Op/BlueSky simulators, `T2.1_*` (deep expert, graph neural solver), `GNPDT`,
`soft_label_gnn`, `failure_prediction`, `distributed_rl`,
`network-distributed-q-learning`, `safe-constrained-policy-gradient`,
`grid2evaluate`, `pypowsybl2grid` — domain algorithms with no HMI or
human-factors surface.

## 6. Track 3 — Consortium anchoring (optional, blocked)

`ai4realnet_orchestrators/railway/playground/` contains
`orchestrator_interactive.py` and `test_runner_playground_interactive.py`, and
names an existing benchmark:

```
# Playground: https://ai4realnet-int.flatland.cloud/benchmarks/9fbde927-…/734144d1-…
```

The runner loads Olten `partially_closed`, replays the trajectory and posts live
to InteractiveAI via `flatland.integrations.interactiveai` (present in our 4.2.6
already). That is the documented **interactive-loop**: a human-factors researcher
starts an experiment from the hub, the orchestrator uploads results, the rest is
completed manually.

**Open question — cannot be answered from the code:** is that "Playground"
benchmark entry meant for this project? If yes, Track 3 outranks Track 2 and
becomes the goal rather than a side quest. If no, it stays optional. → Adrian.

Also open: whether the Olten scenarios (v1 = 4.0.6, v2 = 4.1.0) load under our
version. To be tested, not assumed.

---

## 7. Suggested order

| # | Item | Effort | Depends on |
|---|---|---|---|
| 1 | W2 scripted/targeted malfunctions | S–M | — |
| 2 | W5 small HMI borrowings | S | — |
| 3 | W1 trajectory fork → B1 | M | — |
| 4 | W4 ensemble agreement → A1 precursor | S–M | W3 or ≥2 recommenders |
| 5 | W3 real objectives behind A/B/C | M | — |
| 6 | W9 PP/CBS replan recommender | L | — |
| 7 | W10 directives with planner consequences | M | W9 |
| 8 | W8 4.3.0 upgrade | S+M | pull in when W6 starts |
| 9 | W6 Link Map (ZWL) | L | W8 |
| 10 | W7 timetable layer in the builder | L | — |

Items 1–5 need no dependency change and no upstream coordination. That is the
part of this plan that can start immediately.

Two cross-domain items (§5b) slot in without new work packages, because they
change *how* an existing item is done rather than adding one:

- **Intervention count as an objective** → fold into W3. Cheapest item in the
  whole plan and the one most specific to a human-AI teaming study.
- **Conformal prediction as A1's method** → decide before A1 starts, alongside
  W4. It changes the widget's method, not its slot.

And one that would change a decision already taken:

- **No-go areas as a map gesture** → if adopted, W10's directive surface becomes
  drawing on the map rather than selecting tokens. Worth settling before W10
  begins, not after.
