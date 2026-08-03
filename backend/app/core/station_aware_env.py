"""Keep Flatland's station grouping, which `RailEnv` discards.

`sparse_rail_generator` knows which platform cells belong to which city: it
returns `agents_hints` with `city_positions`, `city_orientations` and
`train_stations` — the latter a list indexed by city, each holding that
city's platform cells as `((row, col), track_nr)`. Two adjacent cells with
track numbers 0 and 1 are two platforms of one station.

`RailEnv.reset` keeps only what it needs from those hints (`distance_map`,
`level_free_positions`) and lets the rest fall out of scope, and
`RailEnvPersister` never writes them. So by the time anyone holds an env,
the grouping is gone and stations can only be guessed at from train
missions — which yields one single-cell "station" per origin/target, with
platforms of the same city split apart.

Two pieces recover it without touching Flatland:

- `StationAwareRailEnv` overrides `_call_rail_generator` — the seam
  `AbstractRailEnv` declares and `RailEnv` itself overrides — to keep the
  hints on the env.
- `remember_station_hints` / `station_hints_for` additionally index them by
  grid content, because a *forked* env loses the attribute: what-if
  branching (`scenario_runner`) goes through
  `RailEnvPersister.save` → `load_new`, which reconstructs a plain
  `RailEnv`. The fork's grid is value-identical to its parent's, so the
  hints can be found by content instead. Note the grid comes back as
  `int64` where it was `uint16`, so the key normalises dtype — hashing raw
  bytes would miss.

The registry is process-local and deliberately simple: it is a cache for
envs built in this process, not a persistence format. A miss is not an
error — callers fall back to the other station sources.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional, Tuple

import numpy as np
from flatland.envs.rail_env import RailEnv

# Grid fingerprint -> the generator's agents_hints.
_HINTS: Dict[Tuple[str, Tuple[int, int]], Dict[str, Any]] = {}


def fingerprint_grid(grid) -> Optional[Tuple[str, Tuple[int, int]]]:
    """Content key for a rail grid, stable across persistence.

    Normalises the dtype because `RailEnvPersister.load_new` rebuilds the
    grid as `int64` from a `uint16` original; the cell values are identical,
    so the fingerprint has to be taken on the values, not the raw buffer.
    """
    if grid is None:
        return None
    normalised = np.asarray(grid).astype(np.int64, copy=False)
    digest = hashlib.sha1(normalised.tobytes()).hexdigest()
    return digest, tuple(int(n) for n in normalised.shape)


def grid_fingerprint(env: RailEnv) -> Optional[Tuple[str, Tuple[int, int]]]:
    """Content key for an env's rail grid."""
    return fingerprint_grid(getattr(getattr(env, "rail", None), "grid", None))


def remember_station_hints(grid, hints: Dict[str, Any]) -> None:
    """Index generator hints by grid content so forks can find them."""
    if not hints or "train_stations" not in hints:
        return
    key = fingerprint_grid(grid)
    if key is not None:
        _HINTS[key] = hints


def station_hints_for(env: RailEnv) -> Optional[Dict[str, Any]]:
    """The generator hints for this env, or None if it was not built here.

    Checks the attribute first (the env itself), then the registry (a fork
    or reload of an env built in this process).
    """
    own = getattr(env, "station_hints", None)
    if own:
        return own
    key = grid_fingerprint(env)
    return _HINTS.get(key) if key is not None else None


def forget_station_hints() -> None:
    """Drop the registry. For tests that assert the fallback behaviour."""
    _HINTS.clear()


class StationAwareRailEnv(RailEnv):
    """`RailEnv` that keeps the generator's station grouping.

    Overrides the same method `RailEnv` overrides from `AbstractRailEnv`, so
    this is the class hierarchy's own extension point rather than a patch.
    Behaviour is otherwise unchanged: the hints are recorded and passed on
    untouched.
    """

    def __init__(self, *args, **kwargs):
        # Set before super().__init__, which may reset() and populate it.
        self.station_hints: Optional[Dict[str, Any]] = None
        super().__init__(*args, **kwargs)

    def _call_rail_generator(self, optionals):
        optionals, rail = super()._call_rail_generator(optionals)
        if optionals and "agents_hints" in optionals:
            hints = optionals["agents_hints"]
            if hints and "train_stations" in hints:
                self.station_hints = hints
                # Fingerprint the grid the generator just produced: `self.rail`
                # is not assigned until reset() returns from this call.
                remember_station_hints(getattr(rail, "grid", None), hints)
        return optionals, rail


__all__ = [
    "StationAwareRailEnv",
    "fingerprint_grid",
    "forget_station_hints",
    "grid_fingerprint",
    "remember_station_hints",
    "station_hints_for",
]
