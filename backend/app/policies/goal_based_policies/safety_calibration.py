"""Does the static safety score predict damage under disturbance?

The measure's null hypothesis: "this score is
decoration — it does not predict how a plan degrades when something goes
wrong." This module tests it and fits the free parameters:

- Held-out scenarios, three plans each with genuinely different safety
  (the conflict-blind lines plan, the avoidance plan, a wait-perturbed
  variant).
- Per plan: the static safety score, one nominal episode, and several
  *disturbed* episodes — same rail, same schedule, different malfunction
  draws (`ParamMalfunctionGen`; the generators' own seeds pin the
  infrastructure while `reset(random_seed=k)` re-seeds the malfunction
  stream).
- Damage = mean extra delay over the disturbed episodes vs nominal, and
  the rate at which a nominally-arriving plan loses trains.
- Verdict = rank correlation of `1 - safety` with damage, side by side
  with the obvious confounds (train count, nominal delay). The measure
  earns its place only if it beats them.

`fitted_params` derives the disturbance-scale parameters from the
malfunction distribution itself (tau_deadlock / window / delta = the mean
malfunction duration) — the "fit from the distribution, not by hand"
half of the calibration. The study scores both parameter sets so the fit
has to prove itself on the same data.
"""
from __future__ import annotations

import json
import random
from typing import Dict, List, Optional, Sequence

import numpy as np

from app.policies.goal_based_policies.dataset import (
    Layout,
    build_layout_env,
    perturb_waits,
    plan_all_lines,
)
from app.policies.goal_based_policies.eval_set import mixes_by_name
from app.policies.goal_based_policies.infrastructure_graph import (
    build_decision_point_graph,
)
from app.policies.goal_based_policies.rollout import run_schedules
from app.policies.goal_based_policies.safety import (
    SafetyParams,
    assess_safety,
)
from app.policies.goal_based_policies.schedule import plan_avoiding_overlaps
from app.policies.goal_based_policies.visualization import (
    _widen_terminus_targets,
    build_demo_env,
)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Rank correlation, ties by average rank. NaN-free by construction:
    constant inputs return 0.0 (no ranking information either way)."""
    def ranks(values: Sequence[float]) -> np.ndarray:
        order = np.argsort(values, kind="stable")
        result = np.empty(len(values), dtype=np.float64)
        position = 0
        values = np.asarray(values, dtype=np.float64)
        while position < len(order):
            end = position
            while (end + 1 < len(order)
                   and values[order[end + 1]] == values[order[position]]):
                end += 1
            rank = (position + end) / 2.0
            for index in order[position:end + 1]:
                result[index] = rank
            position = end + 1
        return result

    if len(xs) < 2:
        return 0.0
    rx, ry = ranks(xs), ranks(ys)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return 0.0
    return float(((rx - rx.mean()) * (ry - ry.mean())).mean() / (sx * sy))


def fitted_params(min_duration: int, max_duration: int) -> SafetyParams:
    """Disturbance-scale parameters set from the malfunction distribution:
    a meet faces a whole malfunction, a blockage lasts one, and the
    reference cascade disturbance is one — so all three get its mean."""
    mean_duration = (min_duration + max_duration) / 2.0
    return SafetyParams(
        tau_deadlock=mean_duration,
        window=mean_duration,
        delta=mean_duration,
    )


def _disturbed_env(layout: Layout, trains: int, rate: float,
                   min_duration: int, max_duration: int, episode_seed: int,
                   horizon: Optional[int] = None):
    from flatland.envs.malfunction_generators import (
        MalfunctionParameters,
        ParamMalfunctionGen,
    )

    env = build_demo_env(
        seed=layout.seed, width=layout.size, height=layout.size,
        number_of_agents=trains, max_num_cities=layout.cities,
        line_length=layout.line_length, flexible_terminus=True,
        malfunction_generator=ParamMalfunctionGen(MalfunctionParameters(
            malfunction_rate=rate, min_duration=min_duration,
            max_duration=max_duration,
        )),
    )
    # Keep the rail and the schedule (a full re-seeded reset regenerates
    # a *different* network); re-seed only the env's randomness stream,
    # which is what the malfunction generator draws from. Reset rebuilds
    # agent state, so the flexible terminus must be re-applied.
    env.reset(regenerate_rail=False, regenerate_schedule=False,
              random_seed=episode_seed)
    _widen_terminus_targets(env)
    if horizon is not None:
        # The env refuses to step past its own cap, so the extended
        # horizon has to be written onto it (same move the session
        # manager makes for max_episode_steps overrides).
        env._max_episode_steps = int(horizon)
    return env


def run_study(
    scenarios: int = 12,
    seed: int = 5,
    episodes: int = 4,
    rate: float = 1 / 150,
    min_duration: int = 10,
    max_duration: int = 30,
    horizon_factor: int = 4,
    verbose: bool = True,
) -> Dict[str, object]:
    """See the module docstring.

    `horizon_factor` extends both the nominal and the disturbed episodes
    beyond Flatland's own cap. Measured necessity, not a tweak: at the
    default cap (~45 steps here) every non-arriving train is charged
    "cap minus deadline" *regardless of malfunctions*, so damage clips
    to zero and no measure could validate. With room to arrive late,
    lateness exists and can be attributed.
    """
    mix = mixes_by_name(["control"])[0]
    rng = random.Random(seed)
    default_params = SafetyParams()
    fitted = fitted_params(min_duration, max_duration)

    points: List[Dict[str, float]] = []
    attempts = 0
    while len({p["scenario"] for p in points}) < scenarios and attempts < scenarios * 6:
        attempts += 1
        layout = Layout(
            index=attempts, seed=rng.randint(*mix.seed_range),
            size=rng.choice(mix.sizes), cities=rng.choice(mix.cities),
            line_length=mix.line_length,
        )
        # Few trains on purpose: plans that nominally *arrive* are the
        # ones on which malfunction damage is measurable at all. Dense
        # conflict-blind plans fail by permanent blocking with or
        # without a malfunction, which saturates any delay-based damage
        # signal (measured — the first study drew exactly that blank).
        trains = rng.randint(2, 5)
        try:
            env = build_layout_env(layout, trains)
            graph = build_decision_point_graph(env)
            base = plan_all_lines(env, graph)
        except Exception:
            continue
        if base is None:
            continue
        avoided = plan_avoiding_overlaps(
            env, graph, base, safety=1, max_total_wait=200,
            max_iterations=2000)
        plans = {
            "lines": base,
            "avoidance": avoided,
            "noisy": perturb_waits(avoided, rng),
        }
        for name, schedules in plans.items():
            report = assess_safety(env, graph, schedules,
                                   params=default_params)
            report_fitted = assess_safety(env, graph, schedules,
                                          params=fitted)

            nominal_env = build_layout_env(layout, trains)
            nominal_graph = build_decision_point_graph(nominal_env)
            horizon = horizon_factor * int(
                getattr(nominal_env, "_max_episode_steps", 0) or 200)
            nominal_env._max_episode_steps = horizon
            nominal = run_schedules(
                nominal_env, nominal_graph, schedules, max_steps=horizon)

            extras, failures = [], []
            for episode in range(episodes):
                disturbed = _disturbed_env(
                    layout, trains, rate, min_duration, max_duration,
                    episode_seed=seed * 10_007 + episode,
                    horizon=horizon,
                )
                disturbed_graph = build_decision_point_graph(disturbed)
                result = run_schedules(
                    disturbed, disturbed_graph, schedules, max_steps=horizon)
                extras.append(result.total_delay - nominal.total_delay)
                failures.append(
                    1.0 if (nominal.all_arrived and not result.all_arrived)
                    else 0.0)

            points.append({
                "scenario": layout.seed, "plan": name, "trains": trains,
                "safety": report.safety,
                "safety_fitted": report_fitted.safety,
                "slack": report.slack_score,
                "deadlock": report.deadlock_score,
                "track": report.track_score,
                "cascade": report.cascade_score,
                "nominal_delay": nominal.total_delay,
                "nominal_arrived": bool(nominal.all_arrived),
                "extra_mean": float(np.mean(extras)),
                "extra_max": float(np.max(extras)),
                "failure_rate": float(np.mean(failures)),
            })
        if verbose:
            done = len({p["scenario"] for p in points})
            print(f"  scenario {done}/{scenarios}", flush=True)

    def correlate(subset: List[Dict[str, float]]) -> Dict[str, float]:
        def against_damage(key: str, damage: str = "extra_mean") -> float:
            return spearman(
                [1 - p[key] if key not in ("trains", "nominal_delay")
                 else p[key] for p in subset],
                [p[damage] for p in subset],
            )

        return {
            "safety_default": against_damage("safety"),
            "safety_fitted": against_damage("safety_fitted"),
            "component_slack": against_damage("slack"),
            "component_deadlock": against_damage("deadlock"),
            "component_track": against_damage("track"),
            "component_cascade": against_damage("cascade"),
            "confound_trains": against_damage("trains"),
            "confound_nominal_delay": against_damage("nominal_delay"),
            "deadlock_vs_failures": spearman(
                [1 - p["deadlock"] for p in subset],
                [p["failure_rate"] for p in subset],
            ),
            "safety_vs_failures": spearman(
                [1 - p["safety"] for p in subset],
                [p["failure_rate"] for p in subset],
            ),
        }

    arrived = [p for p in points if p["nominal_arrived"]]
    correlations = correlate(points)
    correlations_arrived = correlate(arrived) if len(arrived) >= 6 else {}
    return {
        "points": points,
        "correlations": correlations,
        "correlations_nominally_arriving": correlations_arrived,
        "config": {
            "scenarios": scenarios, "episodes": episodes, "rate": rate,
            "min_duration": min_duration, "max_duration": max_duration,
            "fitted_params": {
                "tau_deadlock": fitted.tau_deadlock,
                "window": fitted.window, "delta": fitted.delta,
            },
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=run_study.__doc__)
    parser.add_argument("--scenarios", type=int, default=12)
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument(
        "--rate", type=float, default=None,
        help="malfunction rate per train per step "
             "(default: run_study's own default)",
    )
    parser.add_argument("--min-duration", type=int, default=10)
    parser.add_argument("--max-duration", type=int, default=30)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    kwargs = dict(
        scenarios=args.scenarios, seed=args.seed, episodes=args.episodes,
        min_duration=args.min_duration, max_duration=args.max_duration,
    )
    if args.rate is not None:
        kwargs["rate"] = args.rate
    payload = run_study(**kwargs)
    print("\nrank correlation with mean extra delay under disturbance")
    print("(positive = the signal predicts damage; the measure must beat")
    print("the confounds to earn its place):")
    for name, value in payload["correlations"].items():
        print(f"  {name:<24} {value:+.3f}")
    if payload["correlations_nominally_arriving"]:
        arrived = sum(1 for p in payload["points"] if p["nominal_arrived"])
        print(f"\nsame, restricted to nominally-arriving plans "
              f"({arrived} points — where damage is well-defined):")
        for name, value in payload["correlations_nominally_arriving"].items():
            print(f"  {name:<24} {value:+.3f}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"written: {args.out}")
    return 0


__all__ = ["fitted_params", "run_study", "spearman"]


if __name__ == "__main__":
    raise SystemExit(main())
