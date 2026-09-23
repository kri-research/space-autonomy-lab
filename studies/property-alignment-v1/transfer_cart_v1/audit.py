"""Read-only complete-case accounting. Never reruns a controller."""

from pathlib import Path
from collections import Counter
import argparse
import csv
import io
import json
import math
from .schema import ROOT, STRATA, read, digest, validate, rational
from .freeze import verify, sha

METHODS = (
    "lag_aware_common_command",
    "robust_predictive_prefix",
    "third_order_barrier",
    "mean_only_prefix",
    "instantaneous_actuator_ablation",
)


def verify_row(case, row):
    validate(case)
    if type(row.get("index")) is not int:
        raise ValueError("Noninteger case index")
    if row.get("case_id") != digest(case) or any(
        row.get(k) != case[k] for k in ("stratum", "index", "namespace")
    ):
        raise ValueError("Transfer input identity mismatch")
    if "execution_failure" in row:
        if row["execution_failure"].get("retry") is not False:
            raise ValueError("Failure retried")
        return
    if set(row.get("methods", {})) != set(METHODS):
        raise ValueError("Incomplete method accounting")

    def prediction(pred):
        if pred["status"] not in ("prefix", "obstruction", "unresolved", "budget_miss"):
            raise ValueError("Unknown decision")
        if type(pred["on_time"]) is not bool or pred["recovery_claim"] is not False:
            raise ValueError("Invalid type or recovery claim")
        w = pred["wall_s"]
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0:
            raise ValueError("Invalid policy timing")
        if pred["on_time"] != (w <= 1.0):
            raise ValueError("Timing threshold differs")
        if pred["status"] in ("prefix", "obstruction") and not pred["on_time"]:
            raise ValueError("Late certificate delivered")
        if pred["status"] == "prefix":
            u = tuple(map(rational, pred["action"]))
            if len(u) != 2 or sum(x * x for x in u) > rational(case["authority"]) ** 2:
                raise ValueError("Input norm violated")
        elif pred["action"] is not None:
            raise ValueError("Nonpositive result has applied action")

    for entry in row["methods"].values():
        prediction(entry["prediction"])
    for entry in row["proper_subsets"]:
        prediction(entry["prediction"])
    expected_subsets = 0 if len(case["boxes"]) == 1 else 2 if len(case["boxes"]) == 2 else 6
    if len(row["proper_subsets"]) != expected_subsets:
        raise ValueError("Subset accounting differs")
    if row["physical_validation"] or row["full_recovery_or_mission_utility_evaluated"]:
        raise ValueError("Unsupported evidence class")


def primary(entry):
    pred, ref = entry["prediction"], entry["reference"]
    if pred["status"] == "prefix":
        return (
            "verified_prefix"
            if ref.get("status") == "contained"
            else "contradicted_prefix"
            if ref.get("status") == "violation"
            else "unverified_prefix"
        )
    if pred["status"] == "obstruction":
        return "verified_obstruction" if ref.get("proved") is True else "unverified_obstruction"
    return pred["status"]


def summarize(cases, rows):
    if len(cases) != len(rows) or len({digest(c) for c in cases}) != len(cases):
        raise ValueError("Incomplete or duplicate cases")
    for case, row in zip(cases, rows, strict=True):
        verify_row(case, row)
    result = {
        "schema": "sal-cart-transfer-summary/1",
        "cases": len(cases),
        "physical_validation": False,
        "operational_prevalence_or_superiority_inference": False,
        "methods": {},
        "by_stratum": {},
        "all_individually_certified_obstructions": 0,
        "all_pairs_certified_joint_obstructions": 0,
        "implementation_failures": sum("execution_failure" in r for r in rows),
        "scope": "Prospective actuator-lag simulation transfer of finite shared-input criterion, not complete recovery or unchanged orbital controller portability.",
    }
    for method in METHODS:
        entries = [r["methods"][method] for r in rows if "methods" in r]
        counts = Counter(primary(e) for e in entries)
        result["methods"][method] = {
            "outcomes": dict(counts),
            "total": len(entries),
            "max_policy_wall_s": max((e["prediction"]["wall_s"] for e in entries), default=None),
            "exceptions": sum("exception" in e["prediction"]["details"] for e in entries),
        }
    for s in STRATA:
        group = [r for r in rows if r["stratum"] == s and "methods" in r]
        result["by_stratum"][s] = {
            "cases": sum(c["stratum"] == s for c in cases),
            "methods": {m: dict(Counter(primary(r["methods"][m]) for r in group)) for m in METHODS},
        }
    ids = []
    for row in rows:
        if (
            "methods" not in row
            or primary(row["methods"]["lag_aware_common_command"]) != "verified_obstruction"
        ):
            continue
        singles = [e for e in row["proper_subsets"] if len(e["indices"]) == 1]
        pairs = [e for e in row["proper_subsets"] if len(e["indices"]) == 2]
        individual = bool(singles) and all(primary(e) == "verified_prefix" for e in singles)
        pairwise = bool(pairs) and all(primary(e) == "verified_prefix" for e in pairs)
        result["all_individually_certified_obstructions"] += individual
        result["all_pairs_certified_joint_obstructions"] += pairwise
        ids.append(
            {
                "case_id": row["case_id"],
                "stratum": row["stratum"],
                "index": row["index"],
                "all_singletons_certified": individual,
                "all_pairs_certified": pairwise,
            }
        )
    result["obstruction_mechanisms"] = ids
    stress = [r for r in rows if r.get("lag_mismatch_stress")]
    result["lag_mismatch_stress"] = {
        "cases": len(stress),
        "outside_assumptions": True,
        "methods": {
            m: dict(
                Counter(
                    r["lag_mismatch_stress"]["fixed_command_rechecks"][m]["status"]
                    for r in stress
                    if m in r["lag_mismatch_stress"]["fixed_command_rechecks"]
                )
            )
            for m in METHODS
        },
    }
    protected = result["methods"]["lag_aware_common_command"]
    result["supported_conditional_criterion"] = (
        not result["implementation_failures"]
        and not protected["exceptions"]
        and not any(
            protected["outcomes"].get(k, 0)
            for k in ("contradicted_prefix", "unverified_prefix", "unverified_obstruction")
        )
    )
    result["no_general_new_controller_advantage_claim"] = True
    return result


def table(result):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    columns = [
        "stratum",
        "method",
        "cases",
        "verified_prefix",
        "verified_obstruction",
        "unresolved",
        "budget_miss",
        "contradicted_prefix",
        "unverified_prefix",
        "unverified_obstruction",
    ]
    w.writerow(columns)
    for s, g in result["by_stratum"].items():
        for m, counts in g["methods"].items():
            w.writerow([s, m, g["cases"], *[counts.get(k, 0) for k in columns[3:]]])
    return buf.getvalue()


def archive(run, output):
    from .experiment import atomic

    run, output = Path(run), Path(output)
    if output.exists():
        raise ValueError("Artifact already exists")
    done = read(run / "completion.json")
    cases = read(run / "inputs.json")
    for name, h in done["files"].items():
        if sha(run / name) != h:
            raise ValueError("Raw receipt changed " + name)
    rows = [read(run / "cases" / f"{c['stratum']}__{c['index']:04d}.json") for c in cases]
    summary = summarize(cases, rows)
    output.mkdir()
    atomic(output / "inputs.json", cases)
    atomic(output / "summary.json", summary)
    atomic(output / "execution.json", done)
    with (output / "cases.jsonl").open("x") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n")
    (output / "results.csv").write_text(table(summary))
    atomic(
        output / "manifest.json",
        {
            "files": {f.name: sha(f) for f in sorted(output.iterdir())},
            "source_raw_sha256": done["files"],
            "raw_results_preserved": True,
        },
    )
    return summary


def verify_artifact(output):
    output = Path(output)
    manifest = read(output / "manifest.json")
    actual = {p.name: sha(p) for p in output.iterdir() if p.is_file() and p.name != "manifest.json"}
    if actual != manifest["files"]:
        raise ValueError("Transfer artifact changed")
    cases = read(output / "inputs.json")
    rows = [json.loads(line) for line in (output / "cases.jsonl").read_text().splitlines()]
    result = summarize(cases, rows)
    if (
        result != read(output / "summary.json")
        or table(result) != (output / "results.csv").read_text()
    ):
        raise ValueError("Transfer reporting changed")
    frozen = verify(ROOT / "frozen/freeze.json")
    if (
        cases != read(ROOT / "frozen/inputs.json")
        or read(output / "execution.json")["transfer_id"] != frozen["transfer_id"]
    ):
        raise ValueError("Results are not from frozen inputs")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--run", type=Path)
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    result = verify_artifact(a.output) if a.verify else archive(a.run, a.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
