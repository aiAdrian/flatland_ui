"""Tests for ScenarioBuilder policy-based scenarios."""
import warnings
warnings.filterwarnings("ignore")

import pytest
from flatland.core.env_observation_builder import DummyObservationBuilder
from flatland.envs.line_generators import sparse_line_generator
from flatland.envs.rail_env import RailEnv
from flatland.envs.rail_generators import sparse_rail_generator

from app.core.scenario_builder import (
    ScenarioBuilder, ScoringWeights, score_branch, tag_for,
)
from app.core.scenario_runner import BranchResult
from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.forward_only_policy import ForwardOnlyPolicy
from app.policies.do_nothing_policy import DoNothingPolicy
from app.utils.agent_compat import agent_position


def _make_env(num_agents: int = 2, seed: int = 42) -> RailEnv:
    e = RailEnv(
        width=25, height=25, number_of_agents=num_agents, random_seed=seed,
        rail_generator=sparse_rail_generator(max_num_cities=2, seed=seed),
        line_generator=sparse_line_generator(),
        obs_builder_object=DummyObservationBuilder(),
    )
    e.reset()
    return e


def _builder(env: RailEnv) -> ScenarioBuilder:
    return ScenarioBuilder(env, "deadlock_avoidance", DeadLockAvoidancePolicy)


def _candidates():
    return [
        ("forward_only", ForwardOnlyPolicy),
        ("do_nothing", DoNothingPolicy),
    ]


def test_score_perfect_run():
    perfect = BranchResult(
        total_agents=3, success_count=3,
        kpis={"total_delay": 0, "num_blocked_events": 0,
              "num_swap_attempts": 0, "num_deadlock_cycles": 0},
    )
    assert score_branch(perfect) >= 0.7


def test_score_terrible_run():
    bad = BranchResult(
        total_agents=3, success_count=0,
        kpis={"total_delay": 200, "num_blocked_events": 10,
              "num_swap_attempts": 5, "num_deadlock_cycles": 1},
    )
    assert score_branch(bad) < 0.3


def test_score_partial_run_in_middle():
    partial = BranchResult(
        total_agents=2, success_count=1,
        kpis={"total_delay": 10, "num_blocked_events": 1,
              "num_swap_attempts": 0, "num_deadlock_cycles": 0},
    )
    s = score_branch(partial)
    assert -0.5 < s < 0.7


def test_tag_avoid_for_deadlocks():
    bad = BranchResult(
        total_agents=2, success_count=2,
        kpis={"num_deadlock_cycles": 1},
    )
    assert tag_for(0.9, 0.0, bad) == "avoid"


def test_tag_recommended_only_when_better_than_baseline():
    good = BranchResult(total_agents=2, success_count=2, kpis={})
    assert tag_for(0.85, 0.70, good) == "recommended"
    assert tag_for(0.50, 0.45, good) is None
    assert tag_for(0.10, 0.30, good) == "avoid"


def test_builder_generate_scenarios_shape():
    env = _make_env()
    scenarios = _builder(env).generate_scenarios(_candidates(), horizon=20)

    assert len(scenarios) == 3
    assert scenarios[0].name == "baseline"
    assert scenarios[0].policy_id == "deadlock_avoidance"
    assert {s.policy_id for s in scenarios} == {
        "deadlock_avoidance", "forward_only", "do_nothing"
    }


def test_builder_returns_baseline_first_then_candidates_sorted():
    env = _make_env()
    scenarios = _builder(env).generate_scenarios(_candidates(), horizon=50)
    assert scenarios[0].name == "baseline"
    candidate_scores = [s.score for s in scenarios[1:]]
    assert candidate_scores == sorted(candidate_scores, reverse=True)


def test_builder_at_most_one_recommended():
    env = _make_env()
    scenarios = _builder(env).generate_scenarios(_candidates(), horizon=50)
    n_rec = sum(1 for s in scenarios if s.tag == "recommended")
    assert n_rec <= 1


def test_builder_skips_candidate_equal_to_baseline():
    env = _make_env()
    scenarios = _builder(env).generate_scenarios([
        ("deadlock_avoidance", DeadLockAvoidancePolicy),
        ("forward_only", ForwardOnlyPolicy),
    ], horizon=20)
    assert [s.policy_id for s in scenarios].count("deadlock_avoidance") == 1


def test_builder_does_not_modify_base_env():
    env = _make_env()
    elapsed_before = env._elapsed_steps
    pos_before = [agent_position(a) for a in env.agents]

    _builder(env).generate_scenarios(_candidates(), horizon=15)

    assert env._elapsed_steps == elapsed_before
    assert [agent_position(a) for a in env.agents] == pos_before


def test_builder_scenarios_serialise():
    env = _make_env()
    scenarios = _builder(env).generate_scenarios(_candidates(), horizon=15)
    for s in scenarios:
        d = s.to_dict()
        assert {"name", "policy_id", "score", "tag", "result"} <= d.keys()
        assert "success_rate" in d["result"]
        assert "kpis" in d["result"]
