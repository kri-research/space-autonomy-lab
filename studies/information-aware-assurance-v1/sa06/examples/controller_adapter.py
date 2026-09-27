"""Minimal consumer of the public API, running outside the source checkout.

Replace propose() with another team's controller. Its output is always rechecked.
This example establishes interface use, not controller superiority or external use.
"""

import json
from fractions import Fraction

from kri_assurance_eval.api import assess, estimate_snapshot
from kri_assurance_eval.examples import examples


def propose(snapshot):
    observation = estimate_snapshot(snapshot)
    cells = observation["uncertainty"]["cells"]
    if not cells:
        return ["0", "0"]
    # An intentionally simple heuristic. The envelope checker supplies the finite check.
    y = (
        min(Fraction(c["bounds"][1]["lo"]) for c in cells)
        + max(Fraction(c["bounds"][1]["hi"]) for c in cells)
    ) / 2
    return ["0", "1/50" if y < -40 else "-1/50" if y > -40 else "0"]


def main():
    request = examples()[0]["request"]
    request["proposed_action"] = propose(request["current_input"])
    result = assess(request)
    assert result["status"] == "supported_prefix"
    assert not result["physical_actuation"] and not result["conformance_claim"]
    print(
        json.dumps(
            dict(
                status=result["status"],
                proposed=request["proposed_action"],
                internal_integration=True,
                external_replication=False,
            )
        )
    )


if __name__ == "__main__":
    main()
