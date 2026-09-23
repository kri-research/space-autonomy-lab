"""Read-only reconstruction of retained baseline decisions and matched evidence."""

from pathlib import Path
from collections import Counter
import argparse
import csv
import hashlib
import json
import math
import numpy as np
from .binding import verify_seal
from .common import (
    A,
    B,
    K,
    TARGET,
    H,
    BAND,
    ELLIPSE,
    ALPHA,
    U_MAX,
    CHORD_MARGIN,
    SENSOR,
    W_COMPONENT,
    MODEL_COMPONENT,
    NUMERIC_COMPONENT,
    Tube,
    pnorm,
)
from .run import innovations

PACKAGE = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(
        p.read_text(),
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON " + x)),
    )


def lines(p):
    return [
        json.loads(s, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        for s in p.read_text().splitlines()
        if s.strip()
    ]


def check_manifest(directory):
    directory = Path(directory)
    manifest = read(directory / "manifest.json")
    actual = {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p != directory / "manifest.json"
    }
    if actual != set(manifest):
        raise ValueError("Artifact membership differs")
    for name, expected in manifest.items():
        p = directory / name
        if p.is_symlink() or ".." in Path(name).parts or not p.is_file() or sha(p) != expected:
            raise ValueError("Artifact identity differs: " + name)
    return len(actual)


def plan_residual(plan, tube):
    u = np.asarray(plan["u"], dtype=float).T
    n = u.shape[1]
    switch = plan["switch"]
    r = tube.radii(plan["r0"], n)
    z = np.empty((4, n + 1))
    z[:, 0] = np.asarray(plan["initial_estimate"]) - TARGET
    for j in range(n):
        z[:, j + 1] = A @ z[:, j] + B @ u[:, j]
    if not np.all(np.isfinite(z)) or not np.all(np.isfinite(u)):
        raise ValueError("Nonfinite plan")
    residual = [
        float(
            np.max(np.linalg.norm(u, axis=0) + tube.support_U * r[:-1] + tube.input_error - U_MAX)
        ),
        float(np.max(np.linalg.norm(z[2:], axis=0) + tube.support_V * r - 2.0)),
        pnorm(z[:, -1]) + r[-1] - ALPHA,
    ]
    if switch > 0:
        q = z[:2, : switch + 1] + TARGET[:2, None]
        residual.append(
            float(
                np.max(
                    H @ q
                    - BAND[:, None]
                    + np.linalg.norm(H, axis=1)[:, None] * CHORD_MARGIN
                    + tube.support_A[:, None] * r[None, : switch + 1]
                )
            )
        )
    residual.append(
        float(
            np.max(
                np.linalg.norm(ELLIPSE @ z[:2, switch:], axis=0)
                + 0.5 * CHORD_MARGIN
                + tube.support_E * r[switch:]
                - 1
            )
        )
    )
    if max(residual) > 0 or np.max(np.abs(z[:, -1] - plan["terminal_z"])) > 1.0e-10:
        raise ValueError("Retained plan violates its declared tightened feasible set")
    return z, r, max(residual)


def verify_cell(directory, case, protocol):
    summary = read(directory / "summary.json")
    records = lines(directory / "commands.jsonl")
    plans = lines(directory / "plans.jsonl")
    states = np.array(
        [
            [float(r[k]) for k in ["time_s", "x_m", "y_m", "vx_mps", "vy_mps"]]
            for r in csv.DictReader((directory / "states.csv").open())
        ]
    )
    schedule = read(directory / "schedule.json")
    if summary["execution_error"] is not None:
        raise ValueError("Incomplete scientific execution retained separately")
    if len(records) != 300 or len(states) != 1201 or len(schedule) != 1200:
        raise ValueError("Episode incomplete")
    np.testing.assert_array_equal(states[:, 0], np.arange(1201) / 4)
    np.testing.assert_allclose(states[0, 1:], case["initial"], atol=0, rtol=0)
    noise, forces = innovations(protocol)
    noise_scale = np.zeros(4) if case["information"] == "ideal" else SENSOR
    d = 0.0 if case["information"] == "ideal" else W_COMPONENT
    tube = Tube(noise_scale, d + MODEL_COMPONENT + NUMERIC_COMPONENT)
    bytime = {p["decision_at"]: p for p in plans}
    if len(bytime) != len(plans):
        raise ValueError("Duplicated plans")
    latest = None
    max_plan = -math.inf
    policy_states = Counter()
    protected = external = 0
    for k, row in enumerate(records):
        measured = max(0, k - case["age"])
        if (
            row["decision_at"] != k
            or row["measured_at"] != measured
            or row["received_at"] != k
            or row["application_at"] != k + case["delay"]
        ):
            raise ValueError("Decision chronology differs")
        expected_observation = states[4 * measured, 1:] + noise_scale * noise[measured]
        np.testing.assert_allclose(row["observation"], expected_observation, rtol=0, atol=1.0e-12)
        u = np.array(row["selected"])
        applied = np.array(row["applied_this_tick"])
        if not np.all(np.isfinite(u)) or np.linalg.norm(u) > U_MAX + 1.0e-12:
            raise ValueError("Control bound")
        queued = (
            np.zeros(2) if k < case["delay"] else np.array(records[k - case["delay"]]["selected"])
        )
        np.testing.assert_array_equal(applied, queued)
        for j in range(4):
            index = 4 * k + j
            a, b, real = schedule[index]
            if a != index / 4 or b != (index + 1) / 4:
                raise ValueError("Physical segment extent")
            np.testing.assert_allclose(real, applied + d * forces[index], rtol=0, atol=1.0e-15)
            np.testing.assert_array_equal(real, row["realized_accelerations"][j])
        if type(row["protected"]) is not bool or type(row["external_tracking_guard"]) is not bool:
            raise ValueError("Non-Boolean decision status")
        if row["protected"] and row["external_tracking_guard"]:
            raise ValueError("External guard misreported as protection")
        protected += row["protected"]
        external += row["external_tracking_guard"]
        policy_states[row["status"]] += 1
        if not math.isfinite(row["policy_wall_s"]) or row["policy_wall_s"] < 0:
            raise ValueError("Timing")
        if row["status"] == "feasible_predictive_plan":
            if k not in bytime:
                raise ValueError("Missing retained feasible plan")
            p = bytime[k]
            z, r, res = plan_residual(p, tube)
            max_plan = max(max_plan, res)
            np.testing.assert_array_equal(u, p["u"][0])
            latest = (p, z, r)
            if not any(
                a.get("passed") and a.get("optimality_residual_check")
                for a in row["details"]["attempts"]
            ):
                raise ValueError("Unverified solver result")
        if row["status"] in ("stored_tube_feedback", "terminal_feedback"):
            if latest is None:
                raise ValueError("Backup without prior plan")
            p, z, r = latest
            i = row["application_at"] - p["application_at"]
            expected = (
                K @ (np.asarray(row["application_estimate"]) - TARGET)
                if i >= len(p["u"])
                else np.asarray(p["u"][i])
                + K @ (np.asarray(row["application_estimate"]) - TARGET - z[:, i])
            )
            np.testing.assert_allclose(u, expected, rtol=0, atol=1.0e-10)
        if row["status"] == "robust_sampled_barrier":
            viable = [
                a
                for a in row["details"]["attempts"]
                if a.get("component") == row["details"]["component"] and a.get("checked_feasible")
            ]
            if (
                len(viable) != 1
                or not viable[0]["optimality_residual_check"]
                or min(viable[0]["psi2_lower"]) < 0
            ):
                raise ValueError("Barrier condition missing")
    if (
        protected != summary["protected_decisions"]
        or external != summary["external_guard_decisions"]
        or dict(policy_states) != summary["statuses"]
    ):
        raise ValueError("Aggregate decision count differs")
    physical = read(directory / "adjudication.json")
    if physical != summary["adjudication"]:
        raise ValueError("Physical evidence mismatch")
    if physical["status"] == "validated_containment" and (
        not physical.get("complete_range_coverage")
        or physical["components"]["containment"] != "satisfied"
    ):
        raise ValueError("Unresolved incorrectly scored safe")
    if physical.get("simulator_agreement") != "within_predeclared_comparison_limit":
        raise ValueError("Independent numerical comparison failed")
    return {
        "case": case["id"],
        "plant": summary["plant"],
        "arm": summary["arm"],
        "commands": 300,
        "states": 1201,
        "plans": len(plans),
        "maximum_plan_constraint_residual": None if not plans else max_plan,
        "protected_decisions": protected,
        "external_guard_decisions": external,
        "physical_status": physical["status"],
        "hold_status": physical["hold_acquired"],
    }


def verify(directory, expected_action=None):
    directory = Path(directory)
    files = check_manifest(directory)
    protocol = read(directory / "protocol.json")
    source_seal = verify_seal()
    if read(directory / "seal.json") != source_seal or protocol != read(PACKAGE / "protocol.json"):
        raise ValueError("Protocol/core source binding")
    report = read(directory / "results.json")
    action = expected_action or report["action"]
    if action != report["action"]:
        raise ValueError("Wrong evidence class")
    expected = protocol["tuning_count"] if action == "tune" else protocol["comparison_count"]
    cells = sorted(p for p in directory.iterdir() if p.is_dir())
    if len(cells) != expected or report["count"] != expected:
        raise ValueError("Wrong selected population")
    results = []
    identities = []
    for cell in cells:
        summary = read(cell / "summary.json")
        case = next(c for c in protocol["cases"] if c["id"] == summary["case"])
        results.append(verify_cell(cell, case, protocol))
        identities.append((summary["case"], summary["plant"], summary["arm"]))
    if action == "compare":
        expected_cells = {
            (c["id"], p, a)
            for c in protocol["cases"]
            for p in protocol["plants"]
            for a in protocol["arms"]
        }
        if set(identities) != expected_cells or len(identities) != len(set(identities)):
            raise ValueError("Missing or duplicate factorial cell")
    if action == "tune":
        selection = read(directory / "selection.json")
        for family in ("predictive", "barrier"):
            family_rows = [r for r in report["rows"] if r["arm"] == family]
            configurations = sorted(
                json.dumps(r["configuration"], sort_keys=True) for r in family_rows
            )
            expected_configurations = sorted(
                json.dumps(c, sort_keys=True) for c in protocol["tuning"][family]
            )
            if configurations != expected_configurations:
                raise ValueError("Tuning budget or settings changed")

            def ranking(r):
                return (
                    r["physical_status"] == "validated_containment",
                    r["all_filter_decisions_protected"],
                    r["hold_status"] == "satisfied",
                    -r["effort_integral"],
                )

            winner = max(family_rows, key=ranking)
            if selection["selected"][family] != winner["configuration"]:
                raise ValueError("Declared tuning ranking changed")
    else:
        selected = read(directory / "selection.json")["selected"]
        if any(
            r["configuration"] != selected[r["arm"]] for r in report["rows"] if r["arm"] in selected
        ):
            raise ValueError("Comparison tuning was changed between cases")
    return {
        "schema": "sal-protective-record-verification/1",
        "passed": True,
        "action": action,
        "cells": len(results),
        "files": files,
        "decisions": sum(r["commands"] for r in results),
        "states": sum(r["states"] for r in results),
        "plans": sum(r["plans"] for r in results),
        "results": results,
        "scope": "Read-only recomputation and exact record identities; no new trial, prevalence or physical claim",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.directory)
    if args.output:
        with args.output.open("x") as f:
            json.dump(report, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
