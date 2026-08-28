# Flatland 4.3.0 — measured upgrade trial

> **Status:** trial run 2026-08-20, **not applied**. The repo stays pinned to
> `flatland-rl==4.2.6`. Every number below was measured on this machine
> (macOS arm64, Python 3.14, `backend/.venv`), not estimated.
>
> **Verdict:** the code migration is about a day. The blocker is not code — it is
> that **seeded worlds change**, which is a study-planning decision (§4).

---

## 1. The three runs

| Run | Result | Duration |
|---|---|---|
| `4.2.6` (baseline) | 2 failed, 379 passed, 1 skipped | 19:33 |
| `4.3.0` as-is | **165 failed**, 188 passed, 29 errors | 4:58 |
| `4.3.0` + 5-line shim (§3) | **7 failed**, 374 passed, 1 skipped | 18:56 |

Two of the seven were **already red on 4.2.6** (§6). Net new breakage: **5 tests**,
all in one place (§5).

Reproduce:

```bash
cd backend && .venv/bin/python -m pytest -q
```

---

## 2. What 4.3.0 removed

`EnvAgent` lost its convenience accessors. Probed directly, not inferred:

| 4.2.6 | 4.3.0 |
|---|---|
| `agent.initial_position` | ✗ → `agent.initial_configuration[0]` |
| `agent.initial_direction` | ✗ → `agent.initial_configuration[1]` |
| `agent.position` | ✗ → `agent.current_configuration[0]` (may be `None`) |
| `agent.direction` | ✗ → `agent.current_configuration[1]` |
| `agent.target` | ✗ → `list(agent.targets)[0][0]` (`targets` is a **set**) |

We touch these at roughly **120 call sites across 26 files** (`app/` + `tests/`).

Also changed: `PolicyRunner.create_from_policy` **dropped `start_step` and
`fork_from_trajectory`**. We do not use either (our `start_step` hits are our own
`Policy` lifecycle hook), so this costs us nothing today — but trajectory forking
through that entry point is gone, which matters for
[`widget-b1-whatif-compare.md`](widget-b1-whatif-compare.md).

Everything else we import still exists, including the internal
`NBR_CHACHED_RAND` we depend on in the malfunction generator.

---

## 3. The shim that turns 165 failures into 7

```python
from flatland.envs.agent_utils import EnvAgent

if not hasattr(EnvAgent, "initial_position"):
    EnvAgent.initial_position  = property(lambda s: s.initial_configuration[0])
    EnvAgent.initial_direction = property(lambda s: s.initial_configuration[1])
    EnvAgent.position  = property(lambda s: s.current_configuration[0] if s.current_configuration else None)
    EnvAgent.direction = property(lambda s: s.current_configuration[1] if s.current_configuration else None)
    EnvAgent.target    = property(lambda s: list(s.targets)[0][0])
```

Verified working (`initial_position (21, 10)`, `target (5, 24)` on seed 42).

It is a bridge, not a destination: monkey-patching a third-party `attrs` class is
the kind of thing that breaks silently on the next release. Use it to get the
suite green, then migrate the call sites and delete it.

---

## 4. The actual blocker: seeded worlds change

4.3 changed the sparse rail generator ("one link per gate-gate pair according to
data model", "ban inter-city fibre search from cutting through inner-city
tracks", "fix city naming overflow and drop redundant path search"). Measured
effect — SHA-256 of the rail grid and of the agent origins/targets:

| Seed | grid 4.2.6 | grid 4.3.0 | agents 4.2.6 | agents 4.3.0 | same |
|---|---|---|---|---|---|
| 1 | `24e85fb310b31028` | `c0872d33b0ad5b21` | `8ba258e755543440` | `ed9579cb5a22f68c` | **no** |
| 7 | `ab31aa78a7adc30d` | `da691f9b2014905f` | `a6d390e96c32d06f` | `09440298f63d50e8` | **no** |
| 42 | `ef793003c5386edb` | `0dfddf5f635bf414` | `744b1122ecb017da` | `9afbdccd65620913` | **no** |
| 123 | `2b8cf7c9d23208db` | `adba6cbe6395a038` | `259780bbeea974bc` | `71a76caeb7af7a73` | **no** |

Every seed produces a different topology **and** different agent placement.
Consequences:

- Every study scenario defined by a seed becomes a different scenario.
- Sessions recorded before and after the upgrade are **not comparable** — which
  is exactly what [`interaction-logging-plan.md`](interaction-logging-plan.md)
  is trying to make possible.
- 33 of our 44 test files use seeds.

**Therefore: upgrade before a study, never during one.** If a study is running or
imminent, stay on 4.2.6 and revisit after.

---

## 5. The five genuine failures

All five share one root cause — the Director's evaluation-set generator yields
**zero scenarios** under 4.3:

```
assert {s.mix for s in samples} == {"control", "long"}
E   AssertionError: assert set() == {'control', 'long'}
    ValueError: need at least one array to stack
```

- `test_goal_based_eval_set.py` — 2 tests
- `test_goal_based_evaluator.py` — 3 tests

Same origin as §4: the generator changed, and the selection criteria in
`app/policies/goal_based_policies/eval_set.py` no longer match anything. Two
files, but a content question (which scenarios do we still want?), not a
mechanical rename.

---

## 6. Two tests are already red on 4.2.6

Independent of this upgrade, on `explore_db`, reproducing in 0.65 s:

- **`test_hmi_marey_api_contract.py::test_hmi_marey_data_forecast_still_matches_enrichment_contract`**
  — `/hmi/marey-data` returns `{'agents': {}, 'cached': False}`; the test expects
  `cached is True` with enriched agents. The scenario cache is not being reused.
- **`test_infrastructure_scene_session.py::test_infrastructure_scene_switch_visuals_match_builder_canvas`**
  — tile resolution mismatch: `Weiche_horizontal_oben_rechts.svg @180` where
  `Weiche_horizontal_unten_links.svg @0` is expected. The backend tile resolver
  and the builder canvas have drifted apart.

Both violate the CLAUDE.md guardrail "keep existing tests green" and should be
fixed regardless of the version decision.

---

## 7. Packaging: 4.3.0 needs a compiler

| | 4.2.6 | 4.3.0 |
|---|---|---|
| PyPI artifacts | universal wheel (`py2.py3-none-any`) + sdist | **sdist only** |
| Build deps | — | `cython>=3.2.9` |

The build succeeds here in about 30 seconds and produces a platform wheel
(`flatland_rl-4.3.0-cp314-cp314-macosx_26_0_arm64.whl`), but **every target
platform now needs a toolchain**. `backend/Dockerfile` and CI need checking
before anyone upgrades — and this affects the other consortium partners too, not
just us.

---

## 8. What 4.3 would buy us

Not nothing — this is why the question is worth revisiting:

- **`stations_links.py`** — a real data model (`Station` with `gates`,
  `stopping_points`, `Link` with `fibres`). Supersedes most of
  [`cities-stations-plan.md`](cities-stations-plan.md), and models
  multi-track and station capacity natively.
- **`graph/graph_simplification.py`** — an upstream `DecisionPointGraph` with
  edge `len`, overlapping our `infrastructure_graph.py`. Worth de-duplicating.
- **Link-map fixes** (double slips, edge cases) — relevant to
  [`widget-linkmap-zwl.md`](widget-linkmap-zwl.md).
- **Delay rewards** and ECML2026 fine-grained rewards.
- Cython state machine → bigger grids stay affordable.

---

## 9. Recommended order, if we do it

1. Fix the two pre-existing failures first, so "green" means something (§6).
2. Decide the study question (§4). Nothing else matters until that is settled.
3. Land the shim (§3) plus the migration of the ~120 call sites, in one PR.
4. Fix the eval-set selection (§5).
5. Check `Dockerfile` / CI for the build toolchain (§7).
6. Only then consider adopting `stations_links` (§8), which is its own piece of work.
