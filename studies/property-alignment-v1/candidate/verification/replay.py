"""Recheck saved actions and recovery inputs without generating new policies.

This is post-execution numerical validation, not a repeat of the developmental
experiment. Budgets, original verdicts, failed attempts and timings stay intact.
"""

from pathlib import Path
from fractions import Fraction as Q
import argparse
import csv
import json
import os
import time
from candidate.artifact import verify, strict, load_information, sha
from candidate.certify import certify_action
from candidate.information import Hypothesis
from adjudication.flow import Model, propagate_schedule
from adjudication.engine import adjudicate
from specification.contract import load_property


def positive_checks(directory):
    """All reported on-time positives, plus fixed-pair and baseline checks."""
    fixtures = {
        k: load_information(v) for k, v in strict(directory / "fixture_inputs.json").items()
    }
    checks = []
    for row in strict(directory / "fixtures.json") + strict(directory / "grid.json"):
        info = load_information(row["input"]) if "input" in row else fixtures[row["case"]]
        candidate = row["candidate"]
        if candidate["status"] == "certified_common_prefix":
            checks.append((row["case"], "candidate", info, candidate["positive"]))
        for key in ("fixed_pair_action", "nonlinear_same_action"):
            old = row.get(key)
            if old and old["status"] == "certified_common_prefix":
                checks.append((row["case"], key, info, old))
    for case in strict(directory / "comparisons.json"):
        for name, method in case.get("methods", {}).items():
            if method["protected"]:
                old = method["separate_prefix_check"]
                if old["status"] != "certified_common_prefix":
                    raise ValueError("Recorded baseline certificate lacks a positive check")
                checks.append((case["case"], name, fixtures[case["case"]], old))
    return checks


def prefix_replay(directory):
    rows = []
    for name, kind, info, old in positive_checks(directory):
        started = time.perf_counter()
        if old["information_sha256"] != info.identity():
            raise ValueError("Wrong saved prefix input")
        fresh = certify_action(info, tuple(Q(x) for x in old["action"]), old["model"])
        if fresh["status"] != "certified_common_prefix":
            raise ValueError("Saved prefix failed revalidation: " + name + "/" + kind)
        if fresh["all_terminal_members"] != old["all_terminal_members"]:
            raise ValueError("Terminal membership changed")
        rows.append(
            {
                "case": name,
                "kind": kind,
                "model": old["model"],
                "status": fresh["status"],
                "wall_s": time.perf_counter() - started,
            }
        )
    return rows


def recovery_replay(directory):
    rows = []
    for old in strict(directory / "recoveries.json"):
        started = time.perf_counter()
        file = directory / "recovery" / (old["case"] + "__" + old["model"]) / "commands.csv"
        with file.open() as handle:
            commands = list(csv.DictReader(handle))
        if len(commands) != 300 or [Q(c["time_s"]) for c in commands] != list(range(300)):
            raise ValueError("Incomplete or reordered recovery commands")
        schedule = []
        for k, command in enumerate(commands):
            u = [float(command["ax_mps2"]), float(command["ay_mps2"])]
            if sum(Q(v) ** 2 for v in u) > Q(1, 50) ** 2:
                raise ValueError("Saved command exceeds exact authority")
            for j in range(4):
                a = Q(k) + Q(j, 4)
                schedule.append((a, a + Q(1, 4), u))
        initial = Hypothesis.point(old["initial_exact"]).enclosure()
        arcs = propagate_schedule(Model(old["model"]), initial, schedule)
        fresh = adjudicate(arcs, load_property(), required_events=[a for a, b, u in schedule])
        for key in ("status", "components", "hold_acquired", "nominal_goal"):
            if fresh[key] != old["adjudication"][key]:
                raise ValueError("Saved recovery disagrees: " + old["case"] + "/" + key)
        rows.append(
            {
                "case": old["case"],
                "model": old["model"],
                "status": fresh["status"],
                "hold_acquired": fresh["hold_acquired"],
                "command_sha256": sha(file),
                "wall_s": time.perf_counter() - started,
            }
        )
    return rows


def run(directory, output):
    directory = Path(directory).expanduser().resolve()
    raw = Path(output).expanduser().absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError("Symlink in verification output path")
    output = raw.resolve()
    study = Path(__file__).resolve().parents[2]
    protected = (study.parents[1], Path(os.environ["SAL_EVIDENCE_ROOT"]).resolve(), directory)
    if any(output.is_relative_to(p) for p in protected):
        raise ValueError("Verification output must be outside all source repositories")
    verify(directory)
    original_hash = sha(directory / "manifest.json")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "sal-candidate-fixed-input-revalidation/1",
        "evidence_class": "post_execution_fixed_input_numerical_revalidation",
        "input_manifest_sha256": original_hash,
        "original_outcomes_changed": False,
        "policy_regenerated": False,
        "protected_evaluation_accessed": False,
    }
    try:
        report["prefixes"] = prefix_replay(directory)
        report["recoveries"] = recovery_replay(directory)
        verify(directory)
        if sha(directory / "manifest.json") != original_hash:
            raise ValueError("Original artifact changed during revalidation")
        report["passed"] = True
    except Exception as exc:
        report.update(passed=False, error=type(exc).__name__ + ":" + str(exc))
        raise
    finally:
        report["verifier_sha256"] = sha(Path(__file__))
        with (output / "verification.json").open("x") as handle:
            json.dump(report, handle, indent=2, allow_nan=False)
    print(
        json.dumps(
            {
                "passed": True,
                "prefix_rechecks": len(report["prefixes"]),
                "recovery_rechecks": len(report["recoveries"]),
                "new_comparative_trials": 0,
            },
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.directory, args.output)
