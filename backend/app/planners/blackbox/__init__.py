"""Vendored solver code from AI4REALNET/flatland-blackbox.

Source: https://github.com/AI4REALNET/flatland-blackbox (MIT, see LICENSE here),
the canonical CBS/PP solver that `Tokener` and `T3.4-with-HMI` both vendor.

Why vendored and not installed: the package pins `flatland-rl==4.0.3` and pulls
`torch`, and its `utils.py` imports `flatland.graphs` at module load, which
Flatland 4.2.6 no longer ships. The solvers themselves only need `networkx`.

- `pp.py`   — `flatland_blackbox/solvers/pp.py`, unchanged apart from the import path.
- `utils.py` — the pure graph helpers from `flatland_blackbox/utils.py` that the
  solver and its tests use; bodies unchanged, the environment set-up and rendering
  half left out.
"""
