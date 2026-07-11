# ECML 2026 Flatland env — reuse the challenge topology & scenarios

> Dated plan, 2026-07-11. Idea (danib): reuse the **ECML 2026 "Real-World
> Baselines" Flatland challenge** environment for our own experiments — same map
> and scenarios, and possibly the challenge *results* (winning policies) later.
> This continues the consortium "reuse, don't reinvent" line (CLAUDE.md) and
> gives us a fixed, realistic, community-recognised network instead of random
> maps. **We are NOT entering the competition** — we only reuse the env.
> Source: https://flatland-association.github.io/flatland-book/challenges/ecml2026.html
> · starter kit: https://github.com/flatland-association/ecml2026-starterkit
> To be discussed in the team.

## What ECML 2026 is (one paragraph for the team)

One fixed real-world-style map (**120×150**, **28 stations**), carved into **5
scenes** (regions). Trains have **intermediate stops with time windows** and a
mandatory station order — a more realistic dispatching problem than earlier
Flatland challenges (which were mostly "reach your target, avoid deadlock"). The
full competition is a grid of **7 levels × 5 scenarios** where difficulty scales
by agent count (**8 → 532**), schedule tightness, and malfunctions/delays. The
scene = *where* on the map; the level = *how hard*. Submissions are Docker images
scored on the hidden eval set — **none of which we need**; we only want the env.

## Why it fits — verified, not assumed

- **Same Flatland version.** Challenge requires `flatland-rl` 4.2.5/4.2.6; our
  backend already pins **4.2.6** (`backend/requirements.txt`). All ECML classes
  (`RailEnvPolicy`, `rewards.ECML2026Rewards`, `core.policy.Policy`,
  `RailEnvPersister`) import cleanly in our `backend/.venv`.
- **We already load `.pkl` envs.** ECML ships scenarios as pickled envs. We use
  the exact same primitive — `RailEnvPersister.load_new` — today for what-if
  forking in `backend/app/core/scenario_runner.py:319`. Loading an ECML scenario
  is *the same call*, just a different source.
- **Policy interface matches.** ECML policies implement
  `RailEnvPolicy.act(obs)` / `act_many(handles, observations)`; our
  `backend/app/policies/base.py` already implements that `act_many` and documents
  compatibility with `PolicyRunner.create_from_policy` / `TrajectoryEvaluator`.
  So (later) a challenge checkpoint can be wrapped as a policy in our registry.

## Verified: what a scenario `.pkl` carries

Loaded `level_0_scenario_1.pkl` from the starter kit with our own Flatland
(`RailEnvPersister.load_new`) and inspected it. **The full scenario persists —
including the train goals**, which was the open question:

- Grid **120×150**, 6 example lines (agents).
- Per agent: `initial_position`, `initial_direction`, **`target`** (final goal
  station), `earliest_departure`, `latest_arrival`, `speed_counter` (max speed).
- **`waypoints`** = the ordered **intermediate stops**, each as a set of
  acceptable cells — i.e. ECML's time-window/mandatory-stop structure comes
  along intact.
- Plus `malfunction` config, seeds, `distance_map`.

So loading a scenario reproduces the challenge instance exactly — network,
traffic, goals, intermediate stops, timetable, malfunctions. Nothing is
regenerated or approximated. That is precisely what "same scenarios" needs, and
why the loaded env should stay **non-editable** (any edit breaks comparability).

## Scope decision — which scenes? (answers "all 5 vs. 1 and 5")

**Code effort is flat**: build the loader once, then each extra scene is just
"drop a `.pkl` fixture + one registry entry". The real constraint is
**availability of public `.pkl` files**, not code:

- **Publicly available now:** the `level_0_scenario_1` sample, plus the starter
  kit's `example_curriculum.zip`. Its env list covers **scenes 1, 4, 5** only
  (`_scene_1_`, `_scene_4_`, `_scene_5_` × line-loads × agent counts).
- **Not public:** scenes **2 and 3** are absent from the example curriculum, and
  the exact competition scenarios are hidden server-side.

Therefore:

- **Start = scenes 1 and 5** → **easy**, both exist as public prebuilt `.pkl`s.
  This is the recommended first step.
- **All 5** → scenes 2 & 3 must be **self-generated** from `stations.pkl` + line
  generation on those regions (extra work, and not identical to the hidden eval
  instances) — do this only if experiments need those regions.

Recommendation: ship **scene 1 (level 0) first** as the minimal, then add scene 5;
treat scenes 2/3 as a later "generate if needed" item.

## Experiment-design idea: scene scale ↔ interaction mode (danib)

The scenes are **different-sized regions**, so their scale can *drive* which mode
makes sense — the automation level of each mode matches the density at which that
automation is the only workable option:

| Scene (scale) | Mode | Rationale |
| --- | --- | --- |
| **1** (smallest — ~8 agents at L0) | **Recommendation** (WP3.1) | Few trains → human can inspect each AI suggestion and decide per-decision. |
| **3 or 4** (mid) | **Co-Learning** (WP3.3) | Too many for per-decision review → human focuses on the *important* decisions, reflects, runs what-ifs. |
| **5** (largest — 28 at L0, **532 at L6**) | **Director** (WP3.4) | Human *cannot* act per-train → sets high-level direction, AI runs autonomously, human supervises. |

This is well grounded: within a single level the per-scene agent count already
rises across scenes 1→5 (L0: 8, 11, 14, 26, 28), and **level 6 runs entirely on
scene 5 with 532 agents** — scene 5 is the natural dense/Director end. It also fits
our framing that the 3 modes are **automation levels** for experiments (memory:
`colearning-crosscutting-layer`): here the scenario's scale *forces* the level
rather than merely allowing it.

**Two knobs, not one.** Density is primarily the **level** (agent count) and
secondarily the **scene** (spatial extent). Using the *scene* as the mode knob
(as above) also varies the *map*, giving visual variety; alternatively fix the
scene and scale via level. The scene knob is likely the more interesting one for
a human study.

**Availability caveat for 1/3/5:** scene 3 is **not** in the public example
curriculum (only 1, 4, 5). For the mode mapping, start with **1 / 4 / 5** (all
public) and treat scene 3 as "self-generate if the mid tier specifically needs
region 3". Keep the level low (L0–L1) so agent counts stay HMI-manageable except
where high density is the point (Director).

## How ECML models disruptions (verified from the `.pkl`)

Inspected the sample scenario's generators. Disruptions are
**parametrised-stochastic and seeded** — not hand-scripted, not free-random each
run:

- **Malfunctions** via `FileMalfunctionGen` with
  `MalfunctionParameters(rate=0.00185, min_duration=20, max_duration=50)` —
  a Poisson-like per-step breakdown probability, random duration in [20,50].
- **Reproducible:** the `.pkl` stores `random_seed`,
  `malfunction_cached_random_state`, `np_random_state`, `seed_history`, so the
  *same* disruptions replay identically every run (essential for a study — every
  participant faces the same operational situation).
- **Two effect types** via `MultiEffectsGeneratorWrapped`:
  `MalfunctionEffectsGenerator` (train breaks down) +
  `IntermediateStopMalfunctionEffectsGenerator` (disruptions at intermediate
  stops).
- **Intensity = the level axis:** levels 0–2 none, level 3 introduces
  breakdowns, 4–5 add departure delays, 6 max.

**What Flatland does *not* model natively** (relevant to our config wishlist):
"trains fail" = malfunctions ✓; "new trains arrive" = staggered
`earliest_departure` (agents activate later — ECML uses this) ✓; but
**weather / demand / external environment events are NOT native** — agents are
fixed at scenario-build time. Those would be **our** modelling layer (via the
`effects_generator` seam or scenario-swapping), not something ECML/Flatland gives
for free. Don't assume it's all there.

## Config-model direction (danib) — Basic / Advanced, layered

Rethink the flat config (`backend/app/models/session.py SessionCreateRequest` is
one flat bag today) into **two families**:

- **Preset / bundle** — pick a finished scenario (ECML, or saved own). Network +
  traffic + disruptions come together, non-editable. (This is Weg A / the loader
  below.)
- **Compose** — build it yourself, in three layers:

| Layer | You choose | Today's fields |
| --- | --- | --- |
| **Network** (infrastructure) | map / topology | `infrastructure_scene` |
| **Traffic** | lines/timetable → **implies agent count**, staggered departures (= "new trains"), speeds | `number_of_agents`, `line_length`, `speed_profile`, `latest_departure_max` |
| **Disruptions / Betriebslage** | breakdowns, delays, (our) external events | `malfunction_rate/min/max_duration` |

- **Basic** = one preset or a difficulty dial per layer (Disruptions:
  off / light / heavy).
- **Advanced** = expose the raw params — essentially today's flat
  `SessionCreateRequest`, grouped under "Advanced" instead of one wall of fields.

Layer-3 naming is open: "Störungen" is too narrow (only breakdowns); candidates
**Disruptions & Events**, **Betriebslage**, or **Perturbations** since it also
covers delays / new trains / external events. This is a real refactor (config is
flat today) — team decision, decoupled from the loader first step.

## Wording decision needed (surfaced during this work)

Our current two terms conflate three layers. The map-builder Scene adapter
(`backend/app/core/infrastructure_scene_adapter.py`) already emits **both**
`rail_generator` (network) **and** `line_generator` (traffic), so
"Infrastructure" today already means network+traffic ≈ a whole **scenario** —
which is why it "feels like scenarios". Proposed rename (team to confirm):

| Today | Really is | Proposed name |
| --- | --- | --- |
| **Layout** (`layout-designer`) | arrangement of HMI panels/widgets | **Interface** |
| **Infrastructure** (Scene) — network part | tracks, switches, stations | **Network** |
| **Infrastructure** (Scene) — traffic part | lines, timetable, agents, goals | **Traffic / Timetable** |
| (no name) network + traffic together | one runnable instance | **Scenario** |

This matches Flatland/ECML vocabulary ("topology", "scenario", "scene") and makes
the ECML loader conceptually clean: **ECML delivers a full Scenario as one
`.pkl`**. Minimal alternative: just rename Layout→Interface and
Infrastructure→Scenario (accept the bundling). Kept as an explicit open item so
it isn't lost.

## Approach (Weg A — prebuilt-scenario loader)

1. **Fixtures.** Add ECML `.pkl`s (scene 1, then 5) + `stations.pkl` under a
   backend fixtures dir (e.g. `backend/app/fixtures/ecml2026/`).
2. **Loader path** in `backend/app/core/env_factory.py`: a third env source
   ("prebuilt scenario") next to procedural-generate and Scene-adapter, using
   `RailEnvPersister.load_new`. Additive — does **not** touch the existing
   generate / Scene paths.
3. **Rewards option.** Expose `flatland.envs.rewards.ECML2026Rewards` as a
   selectable reward (already in our venv) for faithful scoring.
4. **UI.** Surface ECML scenes as **presets** in the scenario/Infrastructure
   picker ("ECML 2026 — Scene 1 (Level 0)"), alongside procedural + builder maps.
   Non-editable by design; bypasses the Infrastructure Builder.
5. **(Later, orthogonal) Results reuse (goal b).** If/when challenge policies are
   published, wrap a checkpoint as a Policy in `backend/app/policies/registry.py`
   — separate from map loading, not part of this plan's core.

## Explicitly out of scope / do-not-touch

- **No competition submission** — no Docker build, no `competition.flatland.cloud`.
- Do **not** convert the `.pkl` back into an editable Builder Scene (reverse of
  the Scene adapter) — unnecessary and it would break scenario comparability.
- Do **not** change trajectory compression (`session.store.ts _recordTrajectory`)
  or scenario-refresh throttling — the ECML env is a new *source*, not a pipeline
  change (guardrails, CLAUDE.md §6).

## Open questions for the team

- Adopt the scene↔mode mapping (Recommendation=1, Co-Learning=3/4, Director=5)?
  If yes and the mid tier must be region 3 specifically, we self-generate scene 3;
  otherwise start with the all-public **1 / 4 / 5**.
- Adopt the precise 3-layer rename (Interface / Network / Traffic / Scenario) or
  the minimal one (Interface / Scenario)?
- Which level(s) for experiments? Level 0 (8–28 agents) is HMI-manageable; higher
  levels (up to 532 agents) are likely too dense for a human dispatcher study.
- Goal (b): which challenge results do we actually want, and when do they become
  available (after 2026-06-29 end / 2026-07-06 announcement, and only if teams
  open their forks)?
