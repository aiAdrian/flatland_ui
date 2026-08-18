"""Central definitions for strategies, confirmation modes and reason tags.

Everything here is domain vocabulary that both the UI and the (fake) reflection
agent rely on. Strategy IDs are always semantic -- never store bare "A"/"B"/"C".
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Strategies
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    short: str  # short letter shown on the card (A/B/C ...) purely cosmetic
    description: str


STRATEGIES: dict[str, Strategy] = {
    "minimize_delay": Strategy(
        id="minimize_delay",
        name="Minimize Delay",
        short="A",
        description="Keep trains moving. Prioritise the lowest possible added delay.",
    ),
    "protect_critical_connection": Strategy(
        id="protect_critical_connection",
        name="Protect Critical Connection",
        short="B",
        description="Hold or reorder so a critical passenger connection is kept.",
    ),
    "stabilize_network": Strategy(
        id="stabilize_network",
        name="Stabilize Network",
        short="C",
        description="Trade local delay for overall network stability and headroom.",
    ),
    "avoid_follow_up_conflicts": Strategy(
        id="avoid_follow_up_conflicts",
        name="Avoid Follow-up Conflicts",
        short="D",
        description="Choose the option that minimises downstream cascading conflicts.",
    ),
    "maintain_current_plan": Strategy(
        id="maintain_current_plan",
        name="Maintain Current Plan",
        short="E",
        description="Do not intervene. Keep the existing dispatching plan.",
    ),
}


def strategy_name(strategy_id: str | None) -> str:
    if strategy_id is None:
        return "-"
    strat = STRATEGIES.get(strategy_id)
    return strat.name if strat else strategy_id


# --------------------------------------------------------------------------- #
# Confirmation modes & rationale modes
# --------------------------------------------------------------------------- #

CONFIRMATION_QUICK_ACCEPT = "quick_accept"
CONFIRMATION_INFORMED_ACCEPT = "informed_accept"
CONFIRMATION_REASONED_ACCEPT = "reasoned_accept"
CONFIRMATION_OVERRIDE = "manual_override"
# Live mode: the decision deadline passed and the AI acted by default.
CONFIRMATION_DEFERRED = "deferred_to_ai"

RATIONALE_NONE = "none"
RATIONALE_REASON_TAGS = "reason_tags"
RATIONALE_FREE_TEXT = "free_text"

# Reason tags offered when a user gives a reason (accept or override)
REASON_TAGS = [
    "Critical Connection",
    "Low Ripple Risk",
    "Limited Additional Delay",
    "Passenger Impact",
    "Avoid Follow-up Conflicts",
    "Current Goals",
    "Other",
]

# Reasons shown in the confirmation reflection card (after clicking Let it run /
# Adjust). "Just following recommendation" marks a *passive* accept that is NOT
# counted as confirmed preference evidence; "Other" opens free text.
CONFIRM_REASON_JUST_FOLLOWING = "Just following recommendation"
CONFIRM_REASON_OTHER = "Other"
CONFIRM_REASONS = [
    "Critical connection",
    "Low ripple risk",
    "Limited additional delay",
    "Matches current goals",
    "Avoid follow-up conflicts",
    CONFIRM_REASON_JUST_FOLLOWING,
    CONFIRM_REASON_OTHER,
]

# --------------------------------------------------------------------------- #
# Operational pressure
# --------------------------------------------------------------------------- #

PRESSURE_LEVELS = ["LOW", "MEDIUM", "HIGH", "STRESS"]
PRESSURE_ORDER = {level: i for i, level in enumerate(PRESSURE_LEVELS)}


# --------------------------------------------------------------------------- #
# Reflection case types
# --------------------------------------------------------------------------- #

CASE_PATTERN_DEVIATION = "pattern_deviation"
CASE_PATTERN_CONFIRMATION = "pattern_confirmation"
CASE_UNEXPECTED_OUTCOME = "unexpected_outcome"
CASE_LEARNING_ADJUSTED = "learning_adjusted"
CASE_QUICK_ACCEPT = "quick_accept_pattern"
CASE_OVERRIDE = "override"
