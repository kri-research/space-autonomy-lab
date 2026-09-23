"""Eligibility and fixed diagnostic shortcuts for the frozen evaluation."""

from dataclasses import replace
from fractions import Fraction as Q
from itertools import combinations

from candidate.certify import certify_action, decide
from candidate.information import Hypothesis, InformationSet

# Chosen before pilot outcomes. All norms are strictly below 0.02 m/s^2.
QUALIFICATION_ACTIONS = (
    (0, 0),
    ("0.005", 0),
    ("-0.005", 0),
    (0, "0.005"),
    (0, "-0.005"),
    ("0.01", 0),
    ("-0.01", 0),
    (0, "0.01"),
    (0, "-0.01"),
    ("0.019", 0),
    ("-0.019", 0),
    (0, "0.019"),
    (0, "-0.019"),
)


def singleton_information(info, hypothesis):
    if not isinstance(info, InformationSet) or not isinstance(hypothesis, Hypothesis):
        raise ValueError("Explicit information set and hypothesis required")
    return replace(info, hypotheses=(hypothesis,))


def qualification(info):
    """Require every hidden hypothesis to admit a validated one-second prefix.

    This is deliberately weaker than full recovery and is labelled as such.
    It prevents a common-action obstruction being driven by a state that is
    already individually unable to survive the next held interval.
    """
    rows = []
    for index, hypothesis in enumerate(info.hypotheses):
        single = singleton_information(info, hypothesis)
        accepted = None
        attempts = []
        for action in QUALIFICATION_ACTIONS:
            result = certify_action(single, tuple(Q(str(x)) for x in action), model="hcw")
            attempts.append({"action": list(map(str, action)), "status": result["status"]})
            if result["status"] == "certified_common_prefix":
                accepted = list(map(str, action))
                break
        rows.append(
            {
                "hypothesis": index,
                "qualified": accepted is not None,
                "witness_action": accepted,
                "attempts": attempts,
            }
        )
    return {
        "eligible": all(row["qualified"] for row in rows),
        "criterion": "every hypothesis has a validated one-second HCW prefix under fixed action library",
        "full_recovery_claim": False,
        "hypotheses": rows,
    }


def pairwise_shortcut(info, budget_s=1.0):
    """Deliberately incomplete shortcut: pairwise compatibility only."""
    if len(info.hypotheses) < 3:
        return {"applicable": False, "declares_compatible": None, "pairs": []}
    rows = []
    for i, j in combinations(range(len(info.hypotheses)), 2):
        pair = replace(info, hypotheses=(info.hypotheses[i], info.hypotheses[j]))
        result = decide(pair, budget_s=budget_s)
        rows.append({"pair": [i, j], "status": result["status"]})
    compatible = all(row["status"] == "certified_common_prefix" for row in rows)
    return {
        "applicable": True,
        "declares_compatible": compatible,
        "pairs": rows,
        "shortcut_is_sound_for_full_set": False,
    }
