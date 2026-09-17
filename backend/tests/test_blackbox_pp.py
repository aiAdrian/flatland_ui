"""The vendored Prioritized Planning solver still solves the upstream cases.

Ported from AI4REALNET/flatland-blackbox `tests/test_solver.py` and
`tests/conftest.py` (MIT), PP only — CBS is not vendored.
"""
from types import SimpleNamespace

import networkx as nx

from app.planners.blackbox.pp import PrioritizedPlanningSolver
from app.planners.blackbox.utils import (
    add_proxy_nodes,
    check_no_collisions,
    filter_proxy_nodes,
    get_rail_subgraph,
)


def _agent(handle, start, goal):
    return SimpleNamespace(handle=handle, initial_position=start, target=goal, earliest_departure=0)


def _tiny_graph():
    G = nx.DiGraph()
    nA, nB = (0, 0, 1), (0, 1, 3)
    G.add_node(nA, type="rail")
    G.add_node(nB, type="rail")
    G.add_edge(nA, nB, type="dir", l=1)
    G.add_edge(nB, nA, type="dir", l=1)
    return G


def _cross_graph():
    G = nx.DiGraph()
    A, B1, B, A1 = (0, 0, 1), (0, 1, 3), (1, 0, 1), (1, 1, 3)
    for node in [A, B1, B, A1]:
        G.add_node(node, type="rail")
    for u, v in [(A, B1), (B1, A), (B, A1), (A1, B), (A, B), (B, A), (B1, A1), (A1, B1)]:
        G.add_edge(u, v, type="dir", l=1)
    return G


def _solve(graph, agents):
    solver = PrioritizedPlanningSolver(add_proxy_nodes(get_rail_subgraph(graph), agents))
    return filter_proxy_nodes(solver.solve(agents))


def test_single_agent_tiny():
    a0 = _agent(0, (0, 0), (0, 1))
    path = _solve(_tiny_graph(), [a0])[0]
    assert path
    last_node, _ = path[-1]
    assert (last_node[0], last_node[1]) == (0, 1)


def test_two_agents_cross_without_collision():
    a0 = _agent(0, (0, 0), (1, 1))
    a1 = _agent(1, (1, 0), (0, 1))
    solution = _solve(_cross_graph(), [a0, a1])
    assert (solution[0][-1][0][0], solution[0][-1][0][1]) == (1, 1)
    assert (solution[1][-1][0][0], solution[1][-1][0][1]) == (0, 1)
    check_no_collisions(solution)
