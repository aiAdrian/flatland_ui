"""Overlay of the decision-point graph on the Flatland rail infrastructure.

Two render targets:

- `render_decision_point_graph_on_flatland` (default): draws the env with
  Flatland's own `RenderTool` (PILSVG — the same SVG tile set the UI map
  uses, trains included) and overlays the graph in pixel space.
- `render_decision_point_graph`: lightweight schematic fallback that draws
  the track segments straight from the transition map, no Flatland renderer
  needed.

Overlaid in both: station nodes, switch decision cells, the switch cells
they guard, and the edges connecting them — drawn as direct node-to-node
arrows by default (`follow_track=True` traces the rails instead).

Run standalone to produce a PNG, from a session-style env, a scenario
preset, or the small reproducible demo env:

    python -m app.policies.goal_based_policies.visualization out.png
    python -m app.policies.goal_based_policies.visualization out.png ecml2026-scene1-level0
    python -m app.policies.goal_based_policies.visualization out.png demo
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from flatland.envs.malfunction_generators import Malfunction, NoMalfunctionGen
from flatland.envs.rail_env import RailEnv

from app.core.station_aware_env import StationAwareRailEnv

from app.policies.goal_based_policies.infrastructure_graph import (
    DIRECTIONS,
    OPPOSITE,
    Cell,
    DecisionPointGraph,
    _get_transitions,
    build_decision_point_graph,
)

# Border midpoint of a cell (plot coords: x=col, y=row) per direction.
_SIDE_OFFSET: Dict[int, Tuple[float, float]] = {
    0: (0.0, -0.5),  # North
    1: (0.5, 0.0),   # East
    2: (0.0, 0.5),   # South
    3: (-0.5, 0.0),  # West
}


def _cell_track_segments(env: RailEnv, cell: Cell) -> List[Tuple[int, int]]:
    """Unique (entry_side, exit_side) pairs of track through a cell."""
    segments = set()
    for heading in DIRECTIONS:
        transitions = _get_transitions(env, cell, heading)
        for exit_dir in DIRECTIONS:
            if transitions[exit_dir]:
                entry_side = OPPOSITE[heading]
                pair = tuple(sorted((entry_side, exit_dir)))
                segments.add(pair)
    return sorted(segments)


def _draw_rail(ax, env: RailEnv) -> None:
    for r in range(env.height):
        for c in range(env.width):
            if int(env.rail.grid[r, c]) == 0:
                continue
            for side_a, side_b in _cell_track_segments(env, (r, c)):
                ax_a = (c + _SIDE_OFFSET[side_a][0], r + _SIDE_OFFSET[side_a][1])
                ax_b = (c + _SIDE_OFFSET[side_b][0], r + _SIDE_OFFSET[side_b][1])
                if side_a == side_b:
                    # Dead-end style stub: border midpoint to cell center.
                    xs, ys = [ax_a[0], c], [ax_a[1], r]
                else:
                    # Route through the cell center so turns render as bends.
                    xs = [ax_a[0], c, ax_b[0]]
                    ys = [ax_a[1], r, ax_b[1]]
                ax.plot(xs, ys, color="0.75", linewidth=1.2, zorder=1,
                        solid_capstyle="round")


_ToXY = Callable[[Cell], Tuple[float, float]]


def _grid_xy(cell: Cell) -> Tuple[float, float]:
    return (cell[1], cell[0])


def _label_travel_time(ax, position: Tuple[float, float], edge) -> None:
    """Small travel-time number next to an edge."""
    ax.annotate(
        str(edge.travel_time),
        xy=position,
        ha="center", va="center",
        fontsize=5.5, color="tab:blue", fontweight="bold", zorder=8,
        bbox=dict(
            boxstyle="round,pad=0.12", facecolor="white",
            edgecolor="none", alpha=0.7,
        ),
    )


def _draw_edges(
    ax,
    graph: DecisionPointGraph,
    to_xy: _ToXY = _grid_xy,
    follow_track: bool = False,
    annotate_travel_time: bool = True,
) -> None:
    """Draw graph edges, labelled with their travel time in steps.

    By default each edge is one straight arrow from node to node — the graph
    connection itself, which stays readable on dense networks. With
    `follow_track` the arrow traces the underlying cell path instead.
    """
    if follow_track:
        for edge in graph.edges:
            pts = [to_xy(cell) for cell in edge.path]
            ax.plot(
                [x for x, _ in pts], [y for _, y in pts],
                color="tab:blue", linewidth=2.0, alpha=0.45, zorder=2,
            )
            if len(pts) >= 2:
                mid = len(pts) // 2
                ax.annotate(
                    "",
                    xy=pts[mid], xytext=pts[mid - 1],
                    arrowprops=dict(
                        arrowstyle="-|>", color="tab:blue", alpha=0.6, lw=1.0,
                    ),
                    zorder=3,
                )
                if annotate_travel_time:
                    _label_travel_time(ax, pts[mid], edge)
        return

    # Curve opposite directions apart so A->B and B->A stay distinguishable.
    seen: set = set()
    for edge in graph.edges:
        start, end = to_xy(edge.from_cell), to_xy(edge.to_cell)
        if start == end:
            continue
        pair = (edge.from_cell, edge.to_cell)
        rad = 0.12 if (edge.to_cell, edge.from_cell) in seen else 0.0
        seen.add(pair)
        ax.annotate(
            "",
            xy=end, xytext=start,
            arrowprops=dict(
                arrowstyle="-|>", color="tab:blue", alpha=0.55,
                lw=1.4, shrinkA=3.5, shrinkB=4.5,
                connectionstyle=f"arc3,rad={rad}",
            ),
            zorder=3,
        )
        if annotate_travel_time:
            # Sit the label nearer the source than the midpoint: edges
            # between the same two clusters share a midpoint, so labels
            # would pile up there, while their sources differ.
            t = 0.3
            dx, dy = end[0] - start[0], end[1] - start[1]
            # matplotlib's arc3 is a quadratic Bezier whose control point is
            # chord midpoint + rad * perpendicular(chord).
            ctrl = (
                (start[0] + end[0]) / 2 + rad * dy,
                (start[1] + end[1]) / 2 - rad * dx,
            )
            _label_travel_time(
                ax,
                (
                    (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * ctrl[0] + t ** 2 * end[0],
                    (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * ctrl[1] + t ** 2 * end[1],
                ),
                edge,
            )


def _draw_nodes(
    ax, graph: DecisionPointGraph, annotate: bool, to_xy: _ToXY = _grid_xy
) -> None:
    switch_cells = [to_xy(c) for c in graph.switch_cells]
    if switch_cells:
        ax.scatter(
            [x for x, _ in switch_cells], [y for _, y in switch_cells],
            marker="D", s=18, color="0.45", zorder=4, label="switch (not a node)",
        )

    decision = [n for n in graph.nodes.values() if "switch_decision" in n.kinds]
    if decision:
        pts = [to_xy(n.cell) for n in decision]
        ax.scatter(
            [x for x, _ in pts], [y for _, y in pts],
            marker="o", s=55, facecolor="tab:orange", edgecolor="black",
            linewidth=0.6, zorder=5, label="switch decision cell",
        )

    stations = [n for n in graph.nodes.values() if "station" in n.kinds]
    if stations:
        pts = [to_xy(n.cell) for n in stations]
        ax.scatter(
            [x for x, _ in pts], [y for _, y in pts],
            marker="s", s=70, facecolor="tab:green", edgecolor="black",
            linewidth=0.6, zorder=6, label="station stop",
        )
        if annotate:
            # One label per station, at its first stop cell — a station may
            # span several platform cells.
            for station in graph.stations:
                stops = sorted(station.stop_cells)
                if not stops:
                    continue
                ax.annotate(
                    station.name,
                    xy=to_xy(stops[0]),
                    xytext=(4, -4), textcoords="offset points",
                    fontsize=7, fontweight="bold", zorder=7,
                )


def _rail_bounds(env: RailEnv, margin: int = 1) -> Tuple[int, int, int, int]:
    """Bounding box (row0, col0, row1, col1) of cells carrying rail.

    Sparse envs leave most of the grid empty; cropping to this box makes the
    graph fill the frame instead of floating in blank terrain.
    """
    rows = [
        r for r in range(env.height)
        if any(int(env.rail.grid[r, c]) for c in range(env.width))
    ]
    cols = [
        c for c in range(env.width)
        if any(int(env.rail.grid[r, c]) for r in range(env.height))
    ]
    if not rows or not cols:
        return 0, 0, env.height - 1, env.width - 1
    return (
        max(0, rows[0] - margin),
        max(0, cols[0] - margin),
        min(env.height - 1, rows[-1] + margin),
        min(env.width - 1, cols[-1] + margin),
    )


def render_decision_point_graph(
    env: RailEnv,
    graph: Optional[DecisionPointGraph] = None,
    *,
    ax=None,
    annotate_stations: bool = True,
    follow_track: bool = False,
    annotate_travel_time: bool = True,
    crop_to_rail: bool = True,
    title: Optional[str] = None,
):
    """Render the graph on top of the env's rail infrastructure.

    Returns (figure, axes). Builds the graph from the env if none is given.
    """
    import matplotlib.pyplot as plt

    if graph is None:
        graph = build_decision_point_graph(env)

    if crop_to_rail:
        row0, col0, row1, col1 = _rail_bounds(env)
    else:
        row0, col0, row1, col1 = 0, 0, env.height - 1, env.width - 1
    span_cols = col1 - col0 + 1
    span_rows = row1 - row0 + 1

    if ax is None:
        size = max(6.0, min(20.0, span_cols * 0.3))
        fig, ax = plt.subplots(
            figsize=(size, size * span_rows / max(1, span_cols))
        )
    else:
        fig = ax.figure

    _draw_rail(ax, env)
    _draw_edges(
        ax, graph, follow_track=follow_track,
        annotate_travel_time=annotate_travel_time,
    )
    _draw_nodes(ax, graph, annotate=annotate_stations)

    ax.set_xlim(col0 - 0.5, col1 + 0.5)
    ax.set_ylim(row1 + 0.5, row0 - 0.5)  # row 0 on top, matching the grid
    ax.set_aspect("equal")
    ax.set_xlabel("column")
    ax.set_ylabel("row")
    ax.set_title(
        title
        or f"Decision-point graph — {len(graph.nodes)} nodes, {len(graph.edges)} edges"
    )
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=3,
        fontsize=8, framealpha=0.9,
    )
    fig.tight_layout()
    return fig, ax


def render_decision_point_graph_on_flatland(
    env: RailEnv,
    graph: Optional[DecisionPointGraph] = None,
    *,
    px_per_cell: Optional[int] = None,
    annotate_stations: bool = True,
    follow_track: bool = False,
    annotate_travel_time: bool = True,
    crop_to_rail: bool = True,
    title: Optional[str] = None,
):
    """Overlay the graph on Flatland's own rendering of the env.

    Uses `RenderTool` with the PILSVG graphics layer — the same SVG tile set
    the UI map is built from, trains included — and draws the graph on top in
    pixel coordinates. Returns (figure, axes).
    """
    import matplotlib.pyplot as plt
    from flatland.utils.rendertools import RenderTool

    if graph is None:
        graph = build_decision_point_graph(env)

    if crop_to_rail:
        row0, col0, row1, col1 = _rail_bounds(env)
    else:
        row0, col0, row1, col1 = 0, 0, env.height - 1, env.width - 1
    span_cols = col1 - col0 + 1
    span_rows = row1 - row0 + 1

    if px_per_cell is None:
        # Keep the visible (cropped) area below ~4000 px on the long side.
        px_per_cell = max(10, min(40, 4000 // max(span_cols, span_rows)))

    renderer = RenderTool(
        env,
        gl="PILSVG",
        screen_width=env.width * px_per_cell,
        screen_height=env.height * px_per_cell,
    )
    renderer.render_env(show=False, show_observations=False, show_predictions=False)
    image = renderer.get_image()
    cell_px = renderer.gl.nPixCell  # tiles are drawn at (col*cell_px, row*cell_px)

    def to_xy(cell: Cell) -> Tuple[float, float]:
        return ((cell[1] + 0.5) * cell_px, (cell[0] + 0.5) * cell_px)

    size = max(6.0, min(20.0, span_cols * 0.3))
    fig, ax = plt.subplots(figsize=(size, size * span_rows / max(1, span_cols)))
    ax.imshow(image, zorder=0)
    _draw_edges(
        ax, graph, to_xy, follow_track=follow_track,
        annotate_travel_time=annotate_travel_time,
    )
    _draw_nodes(ax, graph, annotate=annotate_stations, to_xy=to_xy)

    ax.set_xlim(col0 * cell_px, (col1 + 1) * cell_px)
    ax.set_ylim((row1 + 1) * cell_px, row0 * cell_px)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        title
        or f"Decision-point graph — {len(graph.nodes)} nodes, {len(graph.edges)} edges"
    )
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=3,
        fontsize=8, framealpha=0.9,
    )
    fig.tight_layout()
    return fig, ax


def save_decision_point_graph(
    env: RailEnv,
    out_path: str,
    graph: Optional[DecisionPointGraph] = None,
    dpi: int = 150,
    on_flatland: bool = True,
    follow_track: bool = False,
    annotate_travel_time: bool = True,
) -> str:
    """Render and save the overlay as an image. Returns the path.

    `on_flatland=True` overlays on the real Flatland rendering; False uses
    the schematic transition-map drawing (no RenderTool required).
    `follow_track` draws edges along the rails instead of as direct arrows.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if on_flatland:
        fig, _ = render_decision_point_graph_on_flatland(
            env, graph, follow_track=follow_track,
            annotate_travel_time=annotate_travel_time,
        )
    else:
        fig, _ = render_decision_point_graph(
            env, graph, follow_track=follow_track,
            annotate_travel_time=annotate_travel_time,
        )
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


class _UncachedNoMalfunctionGen(NoMalfunctionGen):
    """`NoMalfunctionGen` without its 9 MB per-env random cache.

    Flatland's `ParamMalfunctionGen.generate` lazily caches
    `NBR_CHACHED_RAND` (1,000,000) draws — 8 MB of float64 plus 1 MB of
    bool — on an env's first step, and does so even when the malfunction
    probability is zero, which is what `NoMalfunctionGen` configures. Since
    every draw is then compared against a probability of 0.0, the whole
    cache exists to produce "no malfunction" a million times.

    Dataset generation builds up to two envs per scenario and tens of
    thousands of scenarios, so that cache is the dominant memory cost of
    generating at all: it churned gigabytes and drove the machine into
    swap. Returning the answer directly allocates nothing.

    This does not change any outcome. The malfunction generator is the only
    consumer of `env.np_random` during stepping (rail, line and timetable
    generation all draw during `reset`, before the first `generate` call),
    so not drawing here leaves infrastructure, timetables and rollouts
    identical — `tests/test_goal_based_evaluator.py` pins that.
    """

    def generate(self, np_random=None) -> Malfunction:
        return Malfunction(0)


def build_demo_env(
    seed: int = 7,
    width: int = 40,
    height: int = 40,
    number_of_agents: int = 2,
    max_num_cities: int = 2,
    line_length: int = 2,
    flexible_terminus: bool = False,
    malfunction_generator=None,
) -> RailEnv:
    """Small, sparse, reproducible env for legible example renders.

    Built directly rather than through `env_factory.create_env` because a
    pinned `RailEnv(random_seed=...)` is what makes generation reproducible,
    and the session factory deliberately leaves that unset — the same params
    give a different env on every call there. One rail pair per city and one
    track between cities keeps decision points far enough apart to read the
    graph.

    `line_length` is how many cities a train's line calls at. Flatland's
    default is 2 (origin and target only); the UI's `env_factory` uses 4, so
    pass 4 to generate the multi-stop lines that connections are defined on.
    Note Flatland caps it at the number of cities actually placed, so lines
    can be shorter than requested.

    `flexible_terminus` lets a train finish at *any* platform of its final
    city. Flatland decides arrival with `configuration in agent.targets`, so
    without this a train redirected to the other platform is never marked
    DONE and drifts. Intermediate stops need no such treatment — nothing at
    runtime reads `waypoints` at all — so this is only about the terminus.
    """
    import flatland.envs.timetable_generators as ttg
    from flatland.envs import line_generators as line_gen
    from flatland.envs import rail_generators as rail_gen

    env = StationAwareRailEnv(
        width=width,
        height=height,
        number_of_agents=number_of_agents,
        random_seed=seed,
        rail_generator=rail_gen.sparse_rail_generator(
            max_num_cities=max_num_cities,
            seed=seed,
            grid_mode=False,
            max_rails_between_cities=1,
            max_rail_pairs_in_city=1,
        ),
        line_generator=line_gen.sparse_line_generator(
            seed=seed, line_length=line_length
        ),
        timetable_generator=ttg.timetable_generator,
        # None means none: the default stays the cache-free no-op. The
        # safety calibration passes a ParamMalfunctionGen to disturb
        # otherwise identical episodes.
        malfunction_generator=(
            malfunction_generator if malfunction_generator is not None
            else _UncachedNoMalfunctionGen()
        ),
    )
    env.reset()
    if flexible_terminus:
        _widen_terminus_targets(env)
    return env


def _widen_terminus_targets(env: RailEnv) -> None:
    """Accept any platform of a train's final city as its arrival.

    Applied after `reset`, because reset rebuilds `targets` from the line and
    prunes them against the rail. `is_valid_configuration` drops the
    orientations the track cannot actually be entered from, so only real
    approaches survive.
    """
    from flatland.core.grid.grid4 import Grid4TransitionsEnum

    from app.policies.goal_based_policies.stations import resolve_stations

    stations = resolve_stations(env)
    cell_to_station = {c: s for s in stations for c in s.stop_cells}
    for agent in env.agents:
        target = (int(agent.target[0]), int(agent.target[1]))
        station = cell_to_station.get(target)
        if station is None:
            continue
        widened = set(agent.targets)
        for cell in station.stop_cells:
            widened |= {((int(cell[0]), int(cell[1])), d)
                        for d in Grid4TransitionsEnum}
        agent.targets = {
            t for t in widened if env.rail.is_valid_configuration(t)
        }


if __name__ == "__main__":
    import sys

    from app.core.env_factory import create_env

    out = sys.argv[1] if len(sys.argv) > 1 else "decision_point_graph.png"
    target = sys.argv[2] if len(sys.argv) > 2 else None

    if target == "demo":
        env, preset = build_demo_env(), None
    elif target:
        env, preset = create_env(scenario_preset_id=target), target
    else:
        env, preset = create_env(), None
    graph = build_decision_point_graph(env, scenario_preset_id=preset)
    print(
        f"graph: {len(graph.nodes)} nodes "
        f"({sum(1 for n in graph.nodes.values() if 'station' in n.kinds)} stations, "
        f"{sum(1 for n in graph.nodes.values() if 'switch_decision' in n.kinds)} "
        f"switch decision cells), {len(graph.edges)} edges, "
        f"{len(graph.switch_cells)} switches"
    )
    print(f"saved: {save_decision_point_graph(env, out, graph)}")
