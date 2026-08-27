"""What the reflection agent claims has to match what it counted.

Two things were wrong before and are pinned down here: the evidence numbers were
counted against the most frequent strategy rather than against the learning the
card actually proposes, and a single earlier decision was phrased as a tendency.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fake_reflection_agent import FakeReflectionAgent  # noqa: E402
from strategies import CASE_PATTERN_DEVIATION  # noqa: E402


def _case(counts, expected, selected, sample=None):
    by_strategy = {
        strategy: [{"decision_id": f"D-{strategy}-{i}", "time_label": f"08:0{i}"}
                   for i in range(n)]
        for strategy, n in counts.items()
    }
    return {
        "case_type": CASE_PATTERN_DEVIATION,
        "decision_id": "D-ref",
        "pattern": {
            "expected_strategy": expected,
            "counts": counts,
            "sample_size": sample if sample is not None else sum(counts.values()),
            "confidence": 0.6,
            "decisions_by_strategy": by_strategy,
        },
        "episode": {
            "decision_id": "D-ref",
            "context": {"critical_connection": True, "time_label": "08:30"},
            "user_decision": {"selected_strategy": selected},
            "outcome": {},
        },
    }


def test_evidence_counts_against_the_learnings_own_target():
    """A learning pointing away from past behaviour must show that as conflict."""
    agent = FakeReflectionAgent()
    case = _case({"protect_critical_connection": 3, "minimize_delay": 1},
                 expected="protect_critical_connection",
                 selected="stabilize_network")
    # the answer steers the learning toward stabilize_network
    learning = agent.propose_learning(
        case, {"selected_options": ["Network stability was more important"],
               "free_text": ""},
    )
    evidence = learning["evidence"]
    assert learning["conditions"]["target_strategy"] == "stabilize_network"
    assert evidence["target_strategy"] == "stabilize_network"
    # none of the 4 comparable decisions support stabilising
    assert evidence["supporting_decisions"] == 0
    assert evidence["contradictory_decisions"] == 4
    assert len(evidence["contradictory_examples"]) == 4


def test_evidence_supports_a_learning_that_matches_past_behaviour():
    agent = FakeReflectionAgent()
    case = _case({"protect_critical_connection": 3, "minimize_delay": 1},
                 expected="protect_critical_connection",
                 selected="protect_critical_connection")
    learning = agent.propose_learning(case, {"selected_options": [], "free_text": ""})
    evidence = learning["evidence"]
    assert evidence["target_strategy"] == "protect_critical_connection"
    assert evidence["supporting_decisions"] == 3
    assert evidence["contradictory_decisions"] == 1


def test_without_comparable_decisions_confidence_is_not_faked():
    """Zero supporting and zero contradictory must not read as 'no objections'."""
    agent = FakeReflectionAgent()
    case = _case({}, expected=None, selected="minimize_delay")
    learning = agent.propose_learning(case, {"selected_options": [], "free_text": ""})
    evidence = learning["evidence"]
    assert evidence["evidence_basis"] == "no_comparable_decisions"
    assert learning["confidence"] == "Unproven"


def test_a_single_earlier_decision_is_not_called_a_tendency():
    agent = FakeReflectionAgent()
    one = agent.generate_reflection_question(
        _case({"protect_critical_connection": 1},
              expected="protect_critical_connection",
              selected="stabilize_network")
    )
    assert "mostly" not in one["question"]
    assert "one similar situation" in one["question"]

    many = agent.generate_reflection_question(
        _case({"protect_critical_connection": 3},
              expected="protect_critical_connection",
              selected="stabilize_network")
    )
    assert "mostly" in many["question"]
    assert "3 similar situations" in many["question"]
