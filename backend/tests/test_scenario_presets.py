"""Scenario presets: what the picker offers, and that a preset really is the
scenario it claims to be.

A preset exists because procedural generation is *not* reproducible
(`env_factory` leaves `RailEnv(random_seed=...)` unset, so identical params
give a different env every call). Persisting the env is therefore the only way
to hand the same instance to two people — which is worth nothing unless the
file still reproduces its source scenario exactly.
"""
import os
import warnings

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from flatland.envs.step_utils.states import TrainState  # noqa: E402

from app.core.env_factory import create_env, load_preset_env  # noqa: E402
from app.core.scenario_presets import list_presets  # noqa: E402
from app.policies.goal_based_policies.visualization import (  # noqa: E402
    build_demo_env,
)
from app.policies.registry import get_policy_spec  # noqa: E402

STRESS = "stress-bottleneck-30x30-7t"
# The generator call the stress preset was built from.
STRESS_SOURCE = dict(seed=9, width=30, height=30, number_of_agents=7,
                     max_num_cities=2, line_length=4, flexible_terminus=False)
MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models", "goal_directed",
)


def _fingerprint(env):
    """Everything that makes this scenario *this* scenario."""
    return {
        "rail": np.asarray(env.rail.grid).astype(np.int64).tobytes(),
        "starts": [(int(a.initial_position[0]), int(a.initial_position[1]),
                    int(a.initial_direction)) for a in env.agents],
        "targets": [(int(a.target[0]), int(a.target[1])) for a in env.agents],
        "departures": [int(getattr(a, "earliest_departure", 0) or 0)
                       for a in env.agents],
        "arrivals": [int(getattr(a, "latest_arrival", 0) or 0)
                     for a in env.agents],
    }


def _arrivals_under(env, policy_id: str) -> int:
    """How many trains a stock policy actually gets home."""
    handles = list(range(len(env.agents)))
    policy = get_policy_spec(policy_id).runtime_factory(env)
    policy.reset(env)
    for _ in range(int(getattr(env, "_max_episode_steps", 0) or 200)):
        policy.start_step()
        env.step(policy.act_many(handles, None))
        policy.end_step()
        if all(env.agents[h].state == TrainState.DONE for h in handles):
            break
    return sum(1 for h in handles
               if env.agents[h].state == TrainState.DONE)


def test_the_picker_lists_presets_without_leaking_paths():
    listed = {preset["id"]: preset for preset in list_presets()}
    assert STRESS in listed
    entry = listed[STRESS]
    assert (entry["width"], entry["height"], entry["agents"]) == (30, 30, 7)
    assert "path" not in entry, "the filesystem path must not reach the UI"


def test_the_stress_preset_reproduces_its_source_scenario():
    """The whole point of a preset: the file *is* the scenario, so the
    instance one person benchmarks is the instance another one loads."""
    loaded = load_preset_env(STRESS)
    assert (loaded.width, loaded.height, len(loaded.agents)) == (30, 30, 7)
    assert _fingerprint(loaded) == _fingerprint(build_demo_env(**STRESS_SOURCE))


def test_a_session_built_from_the_preset_ignores_the_generator_params():
    """`create_env` short-circuits to the file: grid, traffic and timetable
    come from the preset, not from whatever the session request asked for."""
    env = create_env(width=99, height=99, number_of_agents=2,
                     scenario_preset_id=STRESS)
    assert (env.width, env.height, len(env.agents)) == (30, 30, 7)
    assert _fingerprint(env) == _fingerprint(build_demo_env(**STRESS_SOURCE))


@pytest.mark.integration
def test_the_stress_preset_is_hard_for_the_stock_policies():
    """It is shipped *because* the default policy cannot solve it — if a
    stock policy ever brings everyone home, it stopped being a stress test
    and the numbers in `scenario_presets` are stale."""
    assert _arrivals_under(load_preset_env(STRESS), "deadlock_avoidance") < 7
    assert _arrivals_under(load_preset_env(STRESS), "shortest_path") < 7


@pytest.mark.integration
def test_the_stress_preset_is_solvable_by_the_director():
    """Hard is only useful if it is winnable: the Director's plan must get
    more trains home than the reactive baselines do, and it must still do
    so when replayed on a pristine copy — the search plans in its own fast
    model of the railway, and this is where that model is held to the real
    environment's verdict."""
    from app.policies.goal_based_policies.infrastructure_graph import (
        build_decision_point_graph,
    )
    from app.policies.goal_based_policies.stations import resolve_stations
    from app.policies.tree_search import director
    from app.policies.tree_search.verify import verify_plan

    env = load_preset_env(STRESS)
    plan = director.plan(
        env, weights=director.DirectorWeights(1, 1, 1), budget=800)

    fresh = load_preset_env(STRESS)
    verified = verify_plan(fresh, build_decision_point_graph(fresh),
                           resolve_stations(fresh), plan.schedules)
    # The preset is calibrated so the reactive policies strand trains
    # (the assertions above); planning ahead has to beat that.
    assert verified["arrived"] >= 7, verified
