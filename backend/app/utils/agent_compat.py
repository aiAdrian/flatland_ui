"""Compatibility accessors for flatland-rl>=4.3's EnvAgent configuration API.

flatland-rl 4.3.0 removed EnvAgent.position/.direction/.old_position/
.old_direction/.initial_position/.initial_direction/.target and replaced them
with optional (position, direction) configuration tuples
(current_configuration / old_configuration / initial_configuration) plus a
`targets` set (an agent may have several direction alternatives at its target
cell). These helpers restore the old flat access pattern used throughout this
codebase without touching flatland internals at every call site.
"""
from typing import Optional, Tuple

Position = Tuple[int, int]


def agent_position(agent) -> Optional[Position]:
    return agent.current_configuration[0] if agent.current_configuration is not None else None


def agent_direction(agent) -> Optional[int]:
    return agent.current_configuration[1] if agent.current_configuration is not None else None


def agent_old_position(agent) -> Optional[Position]:
    return agent.old_configuration[0] if agent.old_configuration is not None else None


def agent_old_direction(agent) -> Optional[int]:
    return agent.old_configuration[1] if agent.old_configuration is not None else None


def agent_initial_position(agent) -> Position:
    return agent.initial_configuration[0]


def agent_initial_direction(agent) -> int:
    return agent.initial_configuration[1]


def agent_target(agent) -> Position:
    """A single representative target position from `agent.targets`.

    `targets` holds (position, direction) arrival alternatives - callers here
    only ever need a `(row, col)` for display/distance purposes, so pick
    deterministically (sorted) rather than relying on set iteration order.
    """
    return sorted(agent.targets)[0][0]
