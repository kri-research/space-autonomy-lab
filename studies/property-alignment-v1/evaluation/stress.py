"""Fixed assumption-handling checks, excluded from the protected denominator."""

from pathlib import Path
import argparse
import json
from candidate.certify import decide
from candidate.comparators import compare
from .generator import stress_cases
from .safety import atomic_json, safe_path


def check_stress(output):
    output = safe_path(output)
    if output.exists():
        raise ValueError("Stress receipt is write-once")
    result = {
        "schema": "sal-evaluation-stress/1",
        "in_primary_denominator": False,
        "protected_inputs_accessed": False,
        "cases": {},
    }
    for name, info in stress_cases().items():
        candidate = decide(info, budget_s=1.0)
        native = compare(info)
        result["cases"][name] = {"input": info.payload(), "candidate": candidate, "native": native}
    covariance = result["cases"]["covariance_only"]["candidate"]
    assert covariance.get("action") is None and covariance["status"] not in (
        "certified_common_prefix",
        "proved_no_common_held_command",
    )
    assert (
        result["cases"]["reduced_effectiveness"]["native"]["status"]
        == "unsupported_native_actuation_bounds"
    )
    assert (
        result["cases"]["outer_enclosure_only"]["candidate"]["status"]
        != "proved_no_common_held_command"
    )
    result["passed"] = True
    atomic_json(output, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    r = check_stress(a.output)
    print(
        json.dumps(
            {
                "passed": r["passed"],
                "cases": {k: v["candidate"]["status"] for k, v in r["cases"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
