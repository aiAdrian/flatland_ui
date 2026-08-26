"""The Director planner as a registry policy: gating, fallback, caching."""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

import app.policies.goal_directed_policy as module  # noqa: E402
from app.policies.goal_directed_policy import (  # noqa: E402
    GoalDirectedPolicy,
    director_weights,
    plan_info,
    set_director_weights,
)
from app.policies.registry import (  # noqa: E402
    create_runtime_policy,
    get_policy_spec,
    policy_ids,
    scenario_policy_factories,
)


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    """Every test plans from scratch, with the default dials."""
    monkeypatch.setattr(module, "_PLAYERS", type(module._PLAYERS)())
    monkeypatch.setattr(module, "_PLAN_INFO", type(module._PLAN_INFO)())
    monkeypatch.setattr(module, "_SCHEDULES", type(module._SCHEDULES)())
    monkeypatch.setattr(module, "_ENV_WEIGHTS", type(module._ENV_WEIGHTS)())
    monkeypatch.setattr(module, "_REPLAN_STATE", type(module._REPLAN_STATE)())
    monkeypatch.setattr(module, "_MODELS", None)
    monkeypatch.setattr(module, "_MODELS_FAILED", False)
    monkeypatch.setattr(module, "_WEIGHTS", (1.0, 1.0, 1.0))


@pytest.fixture(scope="module")
def env():
    from app.policies.goal_based_policies.dataset import (
        Layout, build_layout_env,
    )

    return build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)


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


def test_without_checkpoints_the_policy_degrades_to_avoidance(monkeypatch, env):
    """No models must never mean no service: the fallback plans with
    `plan_avoiding_overlaps` and says so in the plan info."""
    monkeypatch.setattr(module, "DEFAULT_EVALUATOR", "/nonexistent.ckpt")
    policy = create_runtime_policy("goal_directed", env)
    info = plan_info(env)
    assert info["source"] == "avoidance (no models)"
    actions = {h: policy.act_for_handle(h) for h in range(4)}
    assert all(int(a) in range(5) for a in actions.values())


def test_with_models_the_plan_carries_director_provenance(monkeypatch, env, tmp_path):
    """With checkpoints present the plan comes from the portfolio search,
    and the info payload is the HMI's provenance: source, score,
    utilities, the weights in force."""
    import torch

    from app.policies.goal_based_policies.connection_model import (
        ConnectionTransformer,
    )
    from app.policies.goal_based_policies.evaluator import ScheduleEvaluator

    torch.manual_seed(0)
    evaluator = tmp_path / "evaluator.ckpt"
    connection = tmp_path / "connection.ckpt"
    ScheduleEvaluator(
        hidden=16, rounds=1, trunk_layers=1, sequence_layers=1
    ).save(evaluator)
    ConnectionTransformer(
        hidden=16, rounds=1, layers=1, heads=2, dropout=0.0
    ).save(connection)
    monkeypatch.setattr(module, "DEFAULT_EVALUATOR", str(evaluator))
    monkeypatch.setattr(module, "DEFAULT_CONNECTION_MODEL", str(connection))
    set_director_weights(0, 0, 1)

    policy = create_runtime_policy("goal_directed", env)
    info = plan_info(env)
    assert info["source"] in {"search", "lines", "avoidance"}
    assert info["weights"] == [0.0, 0.0, 1.0]
    assert 0.0 <= info["weighted"] <= 1.0
    assert set(info["utilities"]) == {
        "punctuality", "connections", "stability"}
    assert policy.act_for_handle(0) is not None


def test_the_plan_and_its_progress_survive_policy_rebuilds(monkeypatch, env):
    """Session APIs rebuild the policy object on every request; the plan
    and the player's position along it must live with the env."""
    monkeypatch.setattr(module, "DEFAULT_EVALUATOR", "/nonexistent.ckpt")
    GoalDirectedPolicy(env)
    first_player = module._PLAYERS[env]
    GoalDirectedPolicy(env)  # a later request's fresh policy object
    assert module._PLAYERS[env] is first_player


def test_a_malfunction_triggers_a_residual_replan(monkeypatch, tmp_path):
    """A fresh malfunction of consequence makes the next action request
    re-plan from the current state, once — the cooldown absorbs the
    next outage."""
    import torch

    from app.policies.goal_based_policies.connection_model import (
        ConnectionTransformer,
    )
    from app.policies.goal_based_policies.dataset import (
        Layout, build_layout_env,
    )
    from app.policies.goal_based_policies.evaluator import ScheduleEvaluator

    torch.manual_seed(0)
    evaluator = tmp_path / "evaluator.ckpt"
    connection = tmp_path / "connection.ckpt"
    ScheduleEvaluator(
        hidden=16, rounds=1, trunk_layers=1, sequence_layers=1
    ).save(evaluator)
    ConnectionTransformer(
        hidden=16, rounds=1, layers=1, heads=2, dropout=0.0
    ).save(connection)
    monkeypatch.setattr(module, "DEFAULT_EVALUATOR", str(evaluator))
    monkeypatch.setattr(module, "DEFAULT_CONNECTION_MODEL", str(connection))

    fresh = build_layout_env(Layout(index=0, seed=2001, size=30, cities=2), 4)
    policy = GoalDirectedPolicy(fresh)
    handles = list(range(4))
    for _ in range(5):
        fresh.step({h: policy.act_for_handle(h) for h in handles})

    import time

    running = next(a for a in fresh.agents if a.position is not None)
    running.malfunction_handler._set_malfunction_down_counter(10)
    # The trigger starts a *background* re-plan; the committed plan keeps
    # driving while the search runs, and a later action request applies
    # the result re-anchored to wherever the trains are by then.
    deadline = time.time() + 15
    replans: list = []
    while time.time() < deadline and not replans:
        fresh.step({h: policy.act_for_handle(h) for h in handles})
        replans = plan_info(fresh).get("replans") or []
        time.sleep(0.02)
    assert len(replans) == 1
    assert replans[0]["reason"].startswith(
        f"malfunction on train {running.handle}")
    assert replans[0]["source"] in ("research", "continue")

    # A second outage inside the cooldown does not re-plan again.
    fresh.step({h: policy.act_for_handle(h) for h in handles})
    other = next(
        a for a in fresh.agents if a.handle != running.handle
    )
    other.malfunction_handler._set_malfunction_down_counter(10)
    for h in handles:
        policy.act_for_handle(h)
    assert len(plan_info(fresh).get("replans") or []) == 1
