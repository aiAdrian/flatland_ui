"""What an option changes against the plan that is driving.

Drawing each option's full planned routes was unusable: nearly every train gets
re-planned, and the deviating stretches measured 19–96 cells, so the map filled
with long near-identical dashed lines. `_divergence` reduces that to the part
that carries information.
"""
import warnings

warnings.filterwarnings("ignore")

from app.api.sessions import _divergence  # noqa: E402


def pts(*cells, start=0):
    """Path points from (row, col) pairs, one step apart."""
    return [
        {"step": start + i, "row": r, "col": c} for i, (r, c) in enumerate(cells)
    ]


def test_identical_routes_change_nothing():
    path = pts((0, 0), (0, 1), (0, 2))
    assert _divergence(path, path) is None


def test_a_missing_option_path_changes_nothing():
    assert _divergence(pts((0, 0), (0, 1)), None) is None
    assert _divergence(pts((0, 0), (0, 1)), []) is None


def test_same_route_but_later_is_reported_as_a_hold():
    """A wait cannot be drawn as a route — the difference is in time, so the
    caller marks the place instead of drawing a line."""
    current = pts((0, 0), (0, 1), (0, 2), start=10)
    option = pts((0, 0), (0, 1), (0, 2), start=14)
    diff = _divergence(current, option)
    assert diff == {"kind": "hold", "steps": 4, "row": 0, "col": 0}


def test_an_earlier_arrival_is_not_a_hold():
    current = pts((0, 0), (0, 1), start=14)
    option = pts((0, 0), (0, 1), start=10)
    assert _divergence(current, option) is None


def test_a_detour_returns_only_the_deviating_stretch():
    """The whole point: not the full route, just where it differs — with one cell
    of context on each side so it visibly branches off and rejoins."""
    current = pts((0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5))
    option = pts((0, 0), (0, 1), (1, 2), (1, 3), (0, 4), (0, 5))
    diff = _divergence(current, option)
    assert diff["kind"] == "reroute"
    cells = [(p["row"], p["col"]) for p in diff["points"]]
    # Context (0,1) … deviation (1,2), (1,3) … context (0,4).
    assert cells == [(0, 1), (1, 2), (1, 3), (0, 4)]
    # Full route was six cells; the informative part is four.
    assert len(diff["points"]) < len(option)


def test_the_branch_point_is_the_first_differing_cell():
    """What the map marks by default — one mark per train instead of a line."""
    current = pts((0, 0), (0, 1), (0, 2), (0, 3))
    option = pts((0, 0), (0, 1), (1, 2), (1, 3))
    diff = _divergence(current, option)
    assert diff["branch"]["row"] == 1
    assert diff["branch"]["col"] == 2


def test_a_route_that_never_rejoins_is_cut_at_its_end():
    current = pts((0, 0), (0, 1), (0, 2))
    option = pts((0, 0), (5, 1), (5, 2))
    diff = _divergence(current, option)
    cells = [(p["row"], p["col"]) for p in diff["points"]]
    assert cells[0] == (0, 0)  # the shared cell before the split
    assert cells[-1] == (5, 2)


def test_the_same_route_continued_further_is_not_a_reroute():
    """The option follows the identical cells and simply goes on further — the
    train takes the same way, so marking the extra tail as a "deviation" would
    claim a route change that did not happen."""
    current = pts((0, 0), (0, 1))
    option = pts((0, 0), (0, 1), (0, 2), (0, 3))
    assert _divergence(current, option) is None


def test_a_one_cell_difference_is_not_drawable():
    """A stretch of fewer than two cells cannot be a line; nothing is returned
    rather than a degenerate path."""
    assert _divergence(pts((0, 0)), pts((1, 0))) is None
