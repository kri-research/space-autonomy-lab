"""Descriptive developmental summaries; no population inference or new execution."""

from pathlib import Path
import argparse
import csv
import json
from .artifact import verify, read, sha
from .run import write


def analyze(directory, output):
    directory = Path(directory)
    output = Path(output)
    if output.exists():
        raise FileExistsError("Retain previous analysis; choose a new directory")
    checked = verify(directory, "compare")
    rows = read(directory / "results.json")["rows"]
    output.mkdir(parents=True)
    summary = []
    for arm in ("unprotected", "original", "aligned", "tracking", "predictive", "barrier"):
        selected = [
            r for r in rows if r["arm"] == arm and r["case_role"] != "proved_unrecoverable_control"
        ]
        controls = [
            r for r in rows if r["arm"] == arm and r["case_role"] == "proved_unrecoverable_control"
        ]
        summary.append(
            {
                "arm": arm,
                "admissible_cases": len(selected),
                "contained": sum(r["physical_status"] == "validated_containment" for r in selected),
                "violated": sum(r["physical_status"] == "validated_violation" for r in selected),
                "unresolved": sum(r["physical_status"] == "unresolved" for r in selected),
                "hold_acquired": sum(r["hold_status"] == "satisfied" for r in selected),
                "entirely_filter_protected": sum(
                    r["all_filter_decisions_protected"] for r in selected
                ),
                "external_guard_decisions": sum(r["external_guard_decisions"] for r in selected),
                "infeasible_control_violations": sum(
                    r["physical_status"] == "validated_violation" for r in controls
                ),
                "maximum_policy_call_s": max(r["policy_wall_max"] for r in selected),
            }
        )
    comparisons = []
    for case in sorted({r["case"] for r in rows}):
        for plant in ("hcw", "nonlinear"):
            members = {r["arm"]: r for r in rows if r["case"] == case and r["plant"] == plant}
            if len({r["noise_hash"] for r in members.values()}) != 1:
                raise ValueError("Exogenous noise unpaired")
            comparisons.append(
                {
                    "case": case,
                    "plant": plant,
                    "role": members["predictive"]["case_role"],
                    "reference_status": members["unprotected"]["physical_status"],
                    "predictive_status": members["predictive"]["physical_status"],
                    "predictive_fully_protected": members["predictive"][
                        "all_filter_decisions_protected"
                    ],
                    "barrier_status": members["barrier"]["physical_status"],
                    "barrier_fully_protected": members["barrier"]["all_filter_decisions_protected"],
                    "barrier_external_guard_decisions": members["barrier"][
                        "external_guard_decisions"
                    ],
                }
            )
    report = {
        "schema": "sal-protective-development-analysis/1",
        "execution_manifest_sha256": sha(directory / "manifest.json"),
        "source_seal_sha256": sha(directory / "seal.json"),
        "selected_tuning": read(directory / "selection.json")["selected"],
        "counts": {
            "cells": len(rows),
            "decisions": checked["decisions"],
            "states": checked["states"],
            "plans": checked["plans"],
        },
        "arms": summary,
        "paired_comparisons": comparisons,
        "infrastructure_failures": sum(r["execution_error"] is not None for r in rows),
        "scope": "Selected developmental contexts; no inferential denominator, general superiority, novel controller or physical validation",
        "external_guard_policy": "Continuation after uncertified output is retained, not credited to the filter.",
        "timing_scope": "Policy calls exclude shared observation/proposal preparation, external continuation, and offline adjudication.",
    }
    write(output / "results.json", report)
    write(output / "verification.json", checked)
    for name, values in [("arms.csv", summary), ("comparisons.csv", comparisons)]:
        with (output / name).open("x", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(values[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(values)
    write(
        output / "manifest.json", {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    )
    print(json.dumps({"counts": report["counts"], "arms": summary}, indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.directory, args.output)
