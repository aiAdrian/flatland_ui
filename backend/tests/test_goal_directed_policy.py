"""The Director planner as a registry policy: planning, caching, re-planning."""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

import app.policies.goal_directed_policy as module  # noqa: E402
from app.policies.goal_directed_policy import (  # noqa: E402
    GoalDirectedPolicy,
    director_weights,
    plan_info,
    plan_schedules,
    set_director_weights,
)
from app.policies.registry import (  # noqa: E402
    create_runtime_policy,
    get_policy_spec,
    policy_ids,
    scenario_policy_factories,
)

BUDGET = 120  # enough to find a plan on these small networks, fast in CI


def _env(seed=2001, agents=4, size=30):
    from app.policies.goal_based_policies.visualization import build_demo_env

    return build_demo_env(
        seed=seed, width=size, height=size, number_of_agents=agents,
        max_num_cities=2, line_length=2,
    )


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    """Every test plans from scratch, with the default dials, and quickly."""
    monkeypatch.setattr(module, "_PLAYERS", type(module._PLAYERS)())
    monkeypatch.setattr(module, "_PLAN_INFO", type(module._PLAN_INFO)())
    monkeypatch.setattr(module, "_SCHEDULES", type(module._SCHEDULES)())
    monkeypatch.setattr(module, "_SCENARIOS", type(module._SCENARIOS)())
    monkeypatch.setattr(module, "_ENV_WEIGHTS", type(module._ENV_WEIGHTS)())
    monkeypatch.setattr(module, "_REPLAN_STATE", type(module._REPLAN_STATE)())
    monkeypatch.setattr(module, "_WEIGHTS", (1.0, 1.0, 1.0))
    monkeypatch.setattr(module, "PLANNING_BUDGET", BUDGET)


@pytest.fixture(scope="module")
def env():
    return _env()


def test_the_policy_is_registered_and_gated_like_the_others():
    assert "goal_directed" in policy_ids()
    spec = get_policy_spec("goal_directed")
    assert spec.show_in_ui
    assert not spec.is_default  # DLA stays the default
    # Planning costs seconds; what-if branching forks envs freely, so the
    # policy must not be offered there until planning is cheap enough.
    assert "goal_directed" not in scenario_policy_factories()


def test_weights_are_validated_and_take_effect_for_new_plans():
    set_director_weights(2, 0, 1)
    assert director_weights() == (2.0, 0.0, 1.0)
    with pytest.raises(ValueError, match="non-negative"):
        set_director_weights(-1, 1, 1)
    with pytest.raises(ValueError, match="positive"):
        set_director_weights(0, 0, 0)


def test_the_search_plans_without_any_checkpoint(monkeypatch, env):
    """A missing value network costs plan quality, not planning: the
    search still runs, it just has nothing to prefer with."""
    from app.policies.tree_search import director

    monkeypatch.setattr(director, "_LOADED", {})
    monkeypatch.setattr(director, "MODEL_DIR", "/nonexistent")
    policy = create_runtime_policy("goal_directed", env)
    info = plan_info(env)
    assert info["source"].startswith("search")
    assert info["search"]["models"] == []
    actions = {h: policy.act_for_handle(h) for h in range(len(env.agents))}
    assert all(int(a) in range(5) for a in actions.values())


def test_the_plan_carries_the_provenance_the_hmi_shows(env):
    """The info payload is what the HMI reads: where the plan came from,
    what it scores, how much of the search went into it — and which of the
    dials nothing acts on yet."""
    set_director_weights(1, 1, 1)
    create_runtime_policy("goal_directed", env)
    info = plan_info(env)

    assert info["weights"] == [1.0, 1.0, 1.0]
    assert 0.0 <= info["weighted"] <= 1.0
    assert set(info["utilities"]) == {"punctuality"}
    # Dials with no network behind them are named rather than silently
    # ignored — otherwise "I turned it up and nothing changed" has no answer.
    assert set(info["unimplemented_weights"]) == {"connections", "stability"}
    assert info["search"]["nodes"] > 1
    assert info["decisions"] >= 0


def test_the_plan_is_a_playable_schedule(env):
    """What the search commits has to be drivable by the player: every
    train gets entries, and stepping them raises nothing."""
    policy = create_runtime_policy("goal_directed", env)
    schedules = plan_schedules(env)
    assert schedules is not None
    assert len(schedules) == len(env.agents)
    assert all(schedule.entries for schedule in schedules)

    handles = list(range(len(env.agents)))
    for _ in range(15):
        env.step({h: policy.act_for_handle(h) for h in handles})


def test_the_plan_and_its_progress_survive_policy_rebuilds(env):
    """Session APIs rebuild the policy object on every request; the plan
    and the player's position along it must live with the env."""
    GoalDirectedPolicy(env)
    first_player = module._PLAYERS[env]
    GoalDirectedPolicy(env)  # a later request's fresh policy object
    assert module._PLAYERS[env] is first_player


def test_a_malfunction_triggers_a_residual_replan(monkeypatch):
    """A fresh malfunction of consequence makes the next action request
    re-plan from the current state, once — the cooldown absorbs the
    next outage."""
    import time

    from app.policies.tree_search import director

    # A short re-plan budget so the background search finishes well inside
    # the episode; the trigger and the splice are what is under test, not
    # how deeply the search thinks.
    monkeypatch.setattr(director, "REPLAN_BUDGET", 40)

    fresh = _env(agents=6, size=40)
    policy = GoalDirectedPolicy(fresh)
    handles = list(range(len(fresh.agents)))
    for _ in range(5):
        fresh.step({h: policy.act_for_handle(h) for h in handles})

    running = next(a for a in fresh.agents if a.position is not None)
    running.malfunction_handler._set_malfunction_down_counter(10)
    # The trigger starts a *background* re-plan; the committed plan keeps
    # driving while the search runs, and a later action request applies
    # the result re-anchored to wherever the trains are by then.
    deadline = time.time() + 20
    replans: list = []
    while time.time() < deadline and not replans:
        if fresh.dones.get("__all__"):
            # The episode outran the search. Give the job a moment and ask
            # once more — a finished episode still records the event.
            time.sleep(0.2)
            for handle in handles:
                policy.act_for_handle(handle)
            replans = plan_info(fresh).get("replans") or []
            break
        fresh.step({h: policy.act_for_handle(h) for h in handles})
        replans = plan_info(fresh).get("replans") or []
        time.sleep(0.02)
    assert len(replans) == 1
    assert replans[0]["reason"].startswith(
        f"malfunction on train {running.handle}")
    assert replans[0]["source"] in ("research", "continue")

    # A second outage inside the cooldown does not re-plan again.
    if not fresh.dones.get("__all__"):
        fresh.step({h: policy.act_for_handle(h) for h in handles})
    other = next(a for a in fresh.agents if a.handle != running.handle)
    other.malfunction_handler._set_malfunction_down_counter(10)
    for h in handles:
        policy.act_for_handle(h)
    assert len(plan_info(fresh).get("replans") or []) == 1
