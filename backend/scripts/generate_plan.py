#!/usr/bin/env python
"""Record a scenario under a policy and write the result as a plan file.

The cheapest of the plan sources: a run produced by an existing policy is
feasible by construction, so it is a usable plan on the first try and a
golden reference for the replay — running the plan back with no disturbances
must reproduce the recording exactly (asserted in
`tests/test_plan_and_disturbances.py`). The richer sources, for later, are
`goal_based_policies.schedule.plan_shortest_path` plus a conflict-resolution
pass, and the consortium CBS/PP solver in `flatland-blackbox`.

    cd backend
    .venv/bin/python scripts/generate_plan.py pf-ch-wn-wal-conflict \\
        --policy deadlock_avoidance \\
        --out app/fixtures/pf_ch/pf-ch-wn-wal-conflict.plan.json

Re-run it whenever the scene changes; a plan is only valid for the scene it
was recorded on.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flatland.envs.step_utils.states import TrainState  # noqa: E402

from app.core.env_factory import create_env  # noqa: E402
from app.core.plans import (  # noqa: E402
    plan_to_dict,
    trainruns_from_marey_history,
    validate_plan,
)
from app.policies.registry import create_runtime_policy  # noqa: E402


def _snapshot(env, step: int) -> dict:
    """One Marey-history row: every on-map train's cell and heading."""
    agents = {}
    for handle, agent in enumerate(env.agents):
        if agent.position is None or agent.direction is None:
            continue
        agents[str(handle)] = {
            "pos": [int(agent.position[0]), int(agent.position[1])],
            "dir": int(agent.direction),
            "state": getattr(agent.state, "name", str(agent.state)),
        }
    return {"step": step, "agents": agents}


def record(preset_id: str, policy_id: str, max_steps: int | None) -> tuple[dict, dict]:
    env = create_env(scenario_preset_id=preset_id)
    policy = create_runtime_policy(policy_id, env)

    limit = int(max_steps or getattr(env, "_max_episode_steps", 0) or 300)
    snapshots = [_snapshot(env, 0)]

    for step in range(1, limit + 1):
        if all(a.state == TrainState.DONE for a in env.agents):
            break
        policy.start_step()
        actions = policy.act_many(env.get_agent_handles(), env.obs_dict or {})
        env.step(actions)
        policy.end_step()
        snapshots.append(_snapshot(env, step))

    arrived = sum(1 for a in env.agents if a.state == TrainState.DONE)
    stats = {
        "steps": len(snapshots) - 1,
        "arrived": arrived,
        "total": len(env.agents),
    }
    return trainruns_from_marey_history(snapshots), stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preset_id")
    parser.add_argument("--policy", default="deadlock_avoidance")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    trainruns, stats = record(args.preset_id, args.policy, args.max_steps)
    validate_plan(trainruns)

    if stats["arrived"] < stats["total"]:
        print(
            f"WARNING: only {stats['arrived']}/{stats['total']} trains arrived — "
            f"the plan does not get every train home.",
            file=sys.stderr,
        )

    body = plan_to_dict(
        trainruns,
        plan_id=f"{args.preset_id}.plan.v1",
        scenario=args.preset_id,
        generated_by=args.policy,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    print(
        f"{args.out}: {len(trainruns)} trainruns, "
        f"{sum(len(r) for r in trainruns.values())} waypoints, "
        f"{stats['steps']} steps, {stats['arrived']}/{stats['total']} arrived"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
