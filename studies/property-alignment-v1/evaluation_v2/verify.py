"""Check a replacement freeze without performing protected scientific work."""

import argparse
import json
from pathlib import Path
from .identity import verify
from evaluation.safety import strict_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--runtime", action="store_true")
    a = p.parse_args()
    doc = verify(a.freeze, runtime=a.runtime)
    reserve = strict_json(a.freeze.parent / "reserve.json")
    print(
        json.dumps(
            {
                "passed": True,
                "evaluation_id": doc["evaluation_id"],
                "target_total": doc["design"]["target_total"],
                "reserve_cases": len(reserve["cases"]),
                "identity_retirements": len(reserve["retired"]),
                "protected_scientific_evaluations": 0,
                "scope": "Input/source/design/integration identity checks only",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
