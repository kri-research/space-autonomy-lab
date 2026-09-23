"""Independent fixed-command/proof reproduction in a standard-library-only export."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import platform
import sys
import time
from .schema import read, subset
from .reference import action_check, dual_check


def replay(data, output):
    data, output = Path(data), Path(output)
    if output.exists():
        raise ValueError("Reproduction receipt exists")
    cases = read(data / "inputs.json")
    rows = [json.loads(line) for line in (data / "cases.jsonl").read_text().splitlines()]
    comparisons = []
    started = time.perf_counter()

    def check(case, entry, label, tau=None):
        pred = entry["prediction"]
        expected = entry["reference"]
        if pred["status"] == "prefix":
            actual = action_check(case, pred["action"], actual_tau=tau)
        elif pred["status"] == "obstruction" and tau is None:
            actual = dual_check(case, pred["details"]["obstruction"]["weights"])
        else:
            return
        comparisons.append({"label": label, "matches": actual == expected})

    for c, row in zip(cases, rows, strict=True):
        if "methods" not in row:
            continue
        for m, entry in row["methods"].items():
            check(c, entry, row["case_id"] + "/" + m)
        for entry in row["proper_subsets"]:
            check(
                subset(c, entry["indices"]),
                entry,
                row["case_id"] + "/subset/" + str(entry["indices"]),
            )
        st = row.get("lag_mismatch_stress", {})
        for m, ref in st.get("fixed_command_rechecks", {}).items():
            check(
                c,
                {"prediction": row["methods"][m]["prediction"], "reference": ref},
                row["case_id"] + "/lag_stress/" + m,
                st["actual_tau"],
            )
    forbidden = [
        name
        for name in sys.modules
        if name.startswith(
            (
                "numpy",
                "scipy",
                "transfer_cart_v1.policies",
                "transfer_cart_v1.lag",
                "candidate",
                "adjudication",
                "protective",
                "evaluation",
            )
        )
    ]
    result = {
        "schema": "sal-transfer-cleanroom/1",
        "passed": all(x["matches"] for x in comparisons) and not forbidden,
        "comparisons": len(comparisons),
        "mismatches": [x for x in comparisons if not x["matches"]],
        "forbidden_modules_loaded": forbidden,
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "elapsed_s": time.perf_counter() - started,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": {
            n: hashlib.sha256((Path(__file__).parent / n).read_bytes()).hexdigest()
            for n in ("__init__.py", "schema.py", "reference.py", "cleanroom.py")
        },
        "scope": "Isolated source export and fresh interpreter environment; same researcher/specification; no independent laboratory or policy-timing replication",
    }
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = replay(a.data, a.output)
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
