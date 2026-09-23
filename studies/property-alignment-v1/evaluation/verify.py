"""Verify the frozen inputs without evaluating protected states or methods."""

from pathlib import Path
import argparse
import json
from .execute import verify_freeze
from .freeze import exact_command, RETIRED_INPUT_COUNT
from .generator import STRATA, case_payload
from .safety import strict_json, canonical_hash


def verify(path):
    path = Path(path)
    doc = strict_json(path)
    verify_freeze(path, doc["evaluation_id"])
    reserve = strict_json(path.parent / "protected_reserve.json")
    count = doc["design"]["reserve_per_stratum"]
    expected = [
        (s, i) for s in STRATA for i in range(RETIRED_INPUT_COUNT, RETIRED_INPUT_COUNT + count)
    ]
    actual = [(r["stratum"], r["index"]) for r in reserve["cases"]]
    if expected != actual:
        raise ValueError("Reserve order, membership or retired-input boundary differs")
    for entry in reserve["cases"]:
        payload = case_payload("protected", entry["stratum"], entry["index"])
        if canonical_hash(payload) != entry["payload_sha256"]:
            raise ValueError("Protected input bytes differ")
    if (path.parent / "amendments.jsonl").read_text():
        raise ValueError("Superseded freeze cannot be run; create a new identity")
    if doc["task08_execution_command"] != exact_command(doc["evaluation_id"]):
        raise ValueError("Execution command changed")
    return {
        "passed": True,
        "evaluation_id": doc["evaluation_id"],
        "protected_reserve_cases_checked": len(actual),
        "verification_scope": "input identity only; no qualification, policy, event or protected endpoint computed",
        "protected_outcomes_accessed": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(verify(a.freeze), indent=2))


if __name__ == "__main__":
    main()
