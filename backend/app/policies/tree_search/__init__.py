"""Tree search over railway states, with learned node evaluation.

The Director's planner. A search tree whose nodes are states of the railway
and whose branches are joint decisions; neural networks judge each state as
it stands — nothing is completed, no baseline is planned, nothing is
simulated ahead to score a node — and the search grows towards whatever
looks most promising. See `docs/agent-setup.html` for the design.

Modules, in the order they build on each other:

- `scenario`   — what never changes: graph, timetable, distances
- `simulator`  — the fast graph-level world; advances between decisions
- `actions`    — what a train may be asked, and how choices combine
- `metrics`    — what a finished run is worth, as utilities in [0, 1]
- `observation`— a state as the networks read it
- `net`        — the value network, one per metric
- `search`     — the anytime best-first tree
- `plan`       — a path through the tree as executable schedules
- `selfplay`   — search, execute, measure, label
- `train`      — fit the networks to those labels
"""
