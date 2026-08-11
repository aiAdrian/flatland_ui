"""Run schedules in Flatland and label the outcome.

This is the ground truth the schedule evaluator is trained against: play a
scenario's schedules with `SchedulePlayer` and report whether every train
reached its goal and how much delay accumulated.

One env step is treated as one minute, so delays map onto the operational
delay buckets used in the evaluator's second output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Sequence, Set, Tuple

from flatland.envs.rail_env import RailEnv
from flatland.envs.step_utils.states import TrainState

from app.policies.goal_based_policies.infrastructure_graph import DecisionPointGraph
from app.policies.goal_based_policies.schedule import SchedulePlayer, TrainSchedule

# Upper bound (exclusive) of each delay bucket, in minutes. The last bucket
# is open ended: 0-4, 5-14, 15-29, 30-44, 45-59, 60+.
DELAY_BUCKET_BOUNDS: Tuple[int, ...] = (5, 15, 30, 45, 60)
DELAY_BUCKET_LABELS: Tuple[str, ...] = (
    "0-4", "5-14", "15-29", "30-44", "45-59", "60+",
)
NUM_DELAY_BUCKETS = len(DELAY_BUCKET_LABELS)


def delay_bucket(delay_minutes: float) -> int:
    """Index of the bucket a delay falls into."""
    for index, bound in enumerate(DELAY_BUCKET_BOUNDS):
        if delay_minutes < bound:
            return index
    return NUM_DELAY_BUCKETS - 1


@dataclass
class RolloutResult:
    """Outcome of playing one scenario's schedules."""
    all_arrived: bool
    total_delay: int
    max_delay: int
    arrivals: Dict[int, Optional[int]]  # handle -> arrival step, None if stranded
    delays: Dict[int, int]              # handle -> delay in minutes
    steps: int
    # handle -> watched cell -> (first step on it, last step on it). Empty
    # unless `watch_cells` was given. Used to recover when a train actually
    # called at a station, which is what connections are judged on.
    occupancy: Dict[int, Dict[Tuple[int, int], Tuple[int, int]]] = field(
        default_factory=dict
    )

    @property
    def bucket(self) -> int:
        return delay_bucket(self.total_delay)


def run_schedules(
    env: RailEnv,
    graph: DecisionPointGraph,
    schedules: Sequence[TrainSchedule],
    max_steps: Optional[int] = None,
    watch_cells: Optional[Iterable[Tuple[int, int]]] = None,
) -> RolloutResult:
    """Play the schedules to the end of the episode and label the outcome.

    Delay per train is `arrival_step - latest_arrival`, clamped at zero. A
    train that never arrives is charged the delay it had accrued when the
    episode ended, and flips `all_arrived` to False.

    `watch_cells` records, per train, the first and last step it stood on
    each of those cells. Pass the stations' platform cells to recover when
    each train actually called where — done inside this episode rather than
    by replaying, because dataset generation runs this tens of thousands of
    times. A train off the map (before departure, after arrival) has no
    position and is not recorded.
    """
    handles = [s.handle for s in schedules]
    player = SchedulePlayer(graph, env, schedules)

    limit = int(max_steps or getattr(env, "_max_episode_steps", 0) or 200)
    arrivals: Dict[int, Optional[int]] = {h: None for h in handles}
    watched: Set[Tuple[int, int]] = {
        (int(c[0]), int(c[1])) for c in (watch_cells or ())
    }
    occupancy: Dict[int, Dict[Tuple[int, int], Tuple[int, int]]] = {
        h: {} for h in handles
    }

    step = 0
    for step in range(1, limit + 1):
        env.step(player.act_many(handles))
        for handle in handles:
            agent = env.agents[handle]
            if watched:
                position = getattr(agent, "position", None)
                if position is not None:
                    cell = (int(position[0]), int(position[1]))
                    if cell in watched:
                        seen = occupancy[handle].get(cell)
                        occupancy[handle][cell] = (
                            (step, step) if seen is None else (seen[0], step)
                        )
            if arrivals[handle] is None and agent.state == TrainState.DONE:
                arrivals[handle] = step
        if all(arrivals[h] is not None for h in handles):
            break

    delays: Dict[int, int] = {}
    for handle in handles:
        latest = getattr(env.agents[handle], "latest_arrival", None)
        deadline = int(latest) if latest is not None else limit
        arrival = arrivals[handle]
        reference = arrival if arrival is not None else step
        delays[handle] = max(0, int(reference) - deadline)

    return RolloutResult(
        all_arrived=all(arrivals[h] is not None for h in handles),
        total_delay=sum(delays.values()),
        max_delay=max(delays.values()) if delays else 0,
        arrivals=arrivals,
        delays=delays,
        steps=step,
        occupancy=occupancy,
    )
