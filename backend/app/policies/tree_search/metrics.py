"""The metrics a run is judged by, as utilities in [0, 1].

One function per metric, each turning a finished run into a single number
where 1 is perfect. These are the *labels* the value networks are trained
against and the exact quantities their outputs are estimates of, so they
live in one place rather than being restated at every call site.

Punctuality ships first (see the setup document, §5); connections and
stability are added here as further entries, and the search picks up the
new axis without changing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

from app.policies.tree_search.simulator import Outcome

# Upper bound (exclusive) of each delay band, in minutes — one env step is
# one minute. The last band is open ended.
DELAY_BANDS: Tuple[int, ...] = (5, 15, 30, 45, 60)
DELAY_BAND_LABELS: Tuple[str, ...] = (
    "0-4", "5-14", "15-29", "30-44", "45-59", "60+",
)
# What landing in each band is worth, best to worst.
BAND_VALUES: Tuple[float, ...] = (1.0, 0.8, 0.6, 0.4, 0.2, 0.0)

# How much of the punctuality utility is carried by trains arriving at all;
# the rest is how late the ones that did were. Both failure modes have to
# stay visible: a run that is punctual for the two trains that made it is
# not a good run.
ARRIVAL_SHARE = 0.5

# The metrics the search knows about, in the order the weights are given.
METRICS: Tuple[str, ...] = ("punctuality",)


@dataclass(frozen=True)
class DirectorWeights:
    """The user's three dials.

    All three are accepted and reported; only the metrics that actually
    have a network behind them steer anything (see `METRICS`). Keeping the
    other dials in the type rather than dropping them means the HMI, the
    API and the stored session state need no change when the next metric
    lands.
    """
    punctuality: float = 1.0
    connections: float = 1.0
    stability: float = 1.0

    def __post_init__(self) -> None:
        values = (self.punctuality, self.connections, self.stability)
        if any(value < 0 for value in values):
            raise ValueError(f"weights must be non-negative, got {values}")
        if sum(values) <= 0:
            raise ValueError("at least one weight must be positive")

    def as_metrics(self) -> Dict[str, float]:
        """Just the dials the search can act on."""
        every = {
            "punctuality": self.punctuality,
            "connections": self.connections,
            "stability": self.stability,
        }
        active = {name: every[name] for name in METRICS if name in every}
        return active or {"punctuality": 1.0}

    def unimplemented(self) -> Tuple[str, ...]:
        """Dials that are set but have no network behind them yet — the
        honest answer to "why did turning this up change nothing"."""
        every = {
            "punctuality": self.punctuality,
            "connections": self.connections,
            "stability": self.stability,
        }
        return tuple(
            name for name, value in every.items()
            if name not in METRICS and value > 0
        )


def delay_band(total_delay: float) -> int:
    """Which band a total delay falls into."""
    for index, bound in enumerate(DELAY_BANDS):
        if total_delay < bound:
            return index
    return len(BAND_VALUES) - 1


def punctuality(outcome: Outcome) -> float:
    """Did the trains arrive, and were they on time?"""
    return (
        ARRIVAL_SHARE * float(outcome.arrived_fraction)
        + (1.0 - ARRIVAL_SHARE) * BAND_VALUES[delay_band(outcome.total_delay)]
    )


def utilities(outcome: Outcome) -> Dict[str, float]:
    """Every metric of a finished run, keyed by name."""
    return {"punctuality": punctuality(outcome)}


def combine(values: Dict[str, float], weights: Dict[str, float]) -> float:
    """The weighted sum the search maximises.

    Weights are normalised here, so the dials need no coupling in the UI and
    a metric that is not yet implemented can simply be absent.
    """
    active = {
        name: max(0.0, float(weights.get(name, 0.0))) for name in values
    }
    total = sum(active.values())
    if total <= 0:
        # No usable weights: every metric counts the same rather than the
        # score collapsing to zero.
        return sum(values.values()) / max(1, len(values))
    return sum(values[name] * weight for name, weight in active.items()) / total


def normalised_weights(
    weights: Dict[str, float], names: Sequence[str] = METRICS
) -> Dict[str, float]:
    """The weights actually in force, for reporting alongside a score."""
    active = {name: max(0.0, float(weights.get(name, 0.0))) for name in names}
    total = sum(active.values())
    if total <= 0:
        return {name: 1.0 / len(names) for name in names}
    return {name: value / total for name, value in active.items()}


__all__ = [
    "ARRIVAL_SHARE",
    "DirectorWeights",
    "BAND_VALUES",
    "DELAY_BANDS",
    "DELAY_BAND_LABELS",
    "METRICS",
    "combine",
    "delay_band",
    "normalised_weights",
    "punctuality",
    "utilities",
]
