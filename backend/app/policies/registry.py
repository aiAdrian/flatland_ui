"""Central policy registry for runtime creation + UI metadata.

Single source of truth for:
- available policy ids
- policy labels/descriptions for /policies
- runtime construction for step/play/scenario APIs
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from flatland.envs.rail_env import RailEnv

from app.policies.base import Policy
from app.policies.deadlock_avoidance_policy import DeadLockAvoidancePolicy
from app.policies.shortest_path_policy import ShortestPathPolicy
from app.policies.forward_only_policy import ForwardOnlyPolicy
from app.policies.do_nothing_policy import DoNothingPolicy
from app.policies.random_policy import RandomPolicy


PolicyFactory = Callable[[RailEnv], Policy]
PolicyBranchFactory = Callable[[], Policy]


@dataclass(frozen=True)
class PolicySpec:
    id: str
    label: str
    description: str
    is_default: bool
    show_in_ui: bool
    supports_scenarios: bool
    runtime_factory: PolicyFactory
    branch_factory: PolicyBranchFactory


def _mk_deadlock(env: RailEnv) -> Policy:
    return DeadLockAvoidancePolicy()


def _mk_shortest(env: RailEnv) -> Policy:
    return ShortestPathPolicy(env)


def _mk_random(env: RailEnv) -> Policy:
    try:
        action_size = int(env.action_space[0])
    except Exception:
        action_size = 5
    return RandomPolicy(action_size=action_size)


def _mk_forward(env: RailEnv) -> Policy:
    return ForwardOnlyPolicy()


def _mk_do_nothing(env: RailEnv) -> Policy:
    return DoNothingPolicy()


_REGISTRY: dict[str, PolicySpec] = {
    "deadlock_avoidance": PolicySpec(
        id="deadlock_avoidance",
        label="DLA (Default)",
        description="Avoids deadlocks proactively by checking opponent paths.",
        is_default=True,
        show_in_ui=True,
        supports_scenarios=True,
        runtime_factory=_mk_deadlock,
        branch_factory=DeadLockAvoidancePolicy,
    ),
    "shortest_path": PolicySpec(
        id="shortest_path",
        label="Shortest Path",
        description="Each agent picks the action that minimises distance to its target.",
        is_default=False,
        show_in_ui=True,
        supports_scenarios=True,
        runtime_factory=_mk_shortest,
        branch_factory=ShortestPathPolicy,
    ),
    "random": PolicySpec(
        id="random",
        label="Random",
        description="Picks a random valid action per agent.",
        is_default=False,
        show_in_ui=True,
        supports_scenarios=True,
        runtime_factory=_mk_random,
        branch_factory=RandomPolicy,
    ),
    "forward_only": PolicySpec(
        id="forward_only",
        label="Forward Only",
        description="Always MOVE_FORWARD; ignores switches.",
        is_default=False,
        show_in_ui=False,
        supports_scenarios=False,
        runtime_factory=_mk_forward,
        branch_factory=ForwardOnlyPolicy,
    ),
    "do_nothing": PolicySpec(
        id="do_nothing",
        label="Do Nothing",
        description="All agents stay still (DO_NOTHING).",
        is_default=False,
        show_in_ui=False,
        supports_scenarios=False,
        runtime_factory=_mk_do_nothing,
        branch_factory=DoNothingPolicy,
    ),
}


def policy_ids(*, include_hidden: bool = True) -> list[str]:
    if include_hidden:
        return list(_REGISTRY.keys())
    return [pid for pid, spec in _REGISTRY.items() if spec.show_in_ui]


def policy_specs(*, include_hidden: bool = True) -> list[PolicySpec]:
    if include_hidden:
        return list(_REGISTRY.values())
    return [spec for spec in _REGISTRY.values() if spec.show_in_ui]


def get_policy_spec(policy_id: str) -> PolicySpec | None:
    return _REGISTRY.get(policy_id)


def create_runtime_policy(policy_id: str, env: RailEnv) -> Policy:
    spec = get_policy_spec(policy_id)
    if spec is None:
        raise KeyError(policy_id)
    policy = spec.runtime_factory(env)
    policy.reset(env)
    return policy


def scenario_policy_factories() -> dict[str, PolicyBranchFactory]:
    return {
        spec.id: spec.branch_factory
        for spec in _REGISTRY.values()
        if spec.supports_scenarios
    }
