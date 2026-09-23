"""Read-only reconstruction of the complete developmental execution records."""

from pathlib import Path, PurePosixPath
from collections import Counter
import argparse
import csv
import json
import math
import numpy as np
from .io import sha, save_json
from .experiment import hash_array


def strict_json(path):
    def invalid(value):
        raise ValueError("Nonfinite JSON token: " + value)

    return json.loads(Path(path).read_text(), parse_constant=invalid)


def verify_manifest(directory):
    directory = Path(directory).resolve()
    catalog = strict_json(directory / "manifest.json")
    actual = {
        str(p.relative_to(directory))
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if set(catalog) != actual:
        raise ValueError("Artifact membership mismatch")
    for name, digest in catalog.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
            raise ValueError("Invalid artifact path")
        path = directory / name
        if any(p.is_symlink() for p in [path, *path.parents]) or sha(path) != digest:
            raise ValueError("Artifact content mismatch: " + name)
    return len(catalog)


def jsonlines(path):
    def invalid(value):
        raise ValueError("Nonfinite JSON token: " + value)

    return [json.loads(s, parse_constant=invalid) for s in Path(path).read_text().splitlines()]


def validate_cell(folder, case, innovations):
    folder = Path(folder)
    verify_manifest(folder)
    summary = strict_json(folder / "summary.json")
    commands = jsonlines(folder / "commands.jsonl")
    packets = jsonlines(folder / "packets.jsonl")
    schedule = strict_json(folder / "applied_schedule.json")
    with (folder / "states.csv").open() as f:
        states = list(csv.DictReader(f))
    if (
        summary["execution_status"] != "complete"
        or len(commands) != 300
        or len(states) != 1201
        or len(schedule) != 1200
    ):
        raise ValueError("Incomplete cell")
    motion = np.array(
        [[float(r[k]) for k in ["time_s", "x_m", "y_m", "vx_mps", "vy_mps"]] for r in states]
    )
    if not np.all(np.isfinite(motion)) or not np.array_equal(motion[:, 0], np.arange(1201) / 4):
        raise ValueError("Invalid sampled time coverage")
    np.testing.assert_array_equal(motion[0, 1:], case["initial"])
    actual_inputs = []
    for k, row in enumerate(commands):
        if (
            row["time_s"] != k
            or row["decision_at_s"] != k
            or row["applied_at_s"] != k
            or row["input_delay_s"] != 0
        ):
            raise ValueError("Command chronology mismatch")
        selected = np.array(row["selected"])
        proposed = np.array(row["proposed"])
        if (
            selected.shape != (2,)
            or not np.all(np.isfinite(selected))
            or np.linalg.norm(selected) > 0.02 + 1e-12
        ):
            raise ValueError("Command bound mismatch")
        if row["command_changed"] != (not np.array_equal(selected, proposed)):
            raise ValueError("Changed-command flag mismatch")
        if row["overridden"] != (row["reason"] != "accepted"):
            raise ValueError("Override flag mismatch")
        if row["geometry_evaluated"] != ("geometry" in row["visited_branches"]):
            raise ValueError("Visited branch mismatch")
        if row["reason"] == "NUMERICAL_UNRESOLVED" and row["screen"]["status"] != "unresolved":
            raise ValueError("Numerical-rejection reason mismatch")
        if row["reason"] == "accepted":
            np.testing.assert_array_equal(selected, proposed)
        for ch in ("primary", "monitor"):
            snap = row[ch]
            if np.asarray(snap["mean"]).shape != (4,) or np.asarray(snap["covariance"]).shape != (
                4,
                4,
            ):
                raise ValueError("Invalid snapshot dimensions")
            if case["information"] == "ideal":
                np.testing.assert_array_equal(snap["mean"], motion[4 * k, 1:])
                assert snap["health"] == "valid" and snap["prediction_only_age_s"] == 0
        for j, item in enumerate(row["physically_applied"]):
            t = k + j / 4
            if item["start_s"] != t or item["end_s"] != t + 0.25 or item["effectiveness"] != 1:
                raise ValueError("Applied input chronology mismatch")
            expected = selected + np.array(item["process"]) + np.array(item["actuator_error"])
            np.testing.assert_array_equal(expected, item["acceleration"])
            if schedule[4 * k + j] != [t, t + 0.25, item["acceleration"]]:
                raise ValueError("Schedule mismatch")
            if case["information"] == "estimator":
                np.testing.assert_array_equal(
                    item["process"], innovations["process_acceleration"][4 * k + j]
                )
                np.testing.assert_array_equal(
                    item["actuator_error"], innovations["actuator_error"][k]
                )
            else:
                np.testing.assert_array_equal(item["process"], [0, 0])
                np.testing.assert_array_equal(item["actuator_error"], [0, 0])
            actual_inputs.append(item["acceleration"])
        if len(row["physically_applied"]) != 4:
            raise ValueError("Missing applied intervals")
        for n in ("decision_wall_s", "decision_cpu_s"):
            if not math.isfinite(row[n]) or row[n] < 0:
                raise ValueError("Invalid measured compute cost")
    reasons = dict(Counter(r["reason"] for r in commands))
    if summary["reasons"] != reasons:
        raise ValueError("Reason aggregate mismatch")
    for field, key in [
        ("overrides", "overridden"),
        ("changed_commands", "command_changed"),
        ("geometry_checks", "geometry_evaluated"),
    ]:
        if summary[field] != sum(r[key] for r in commands):
            raise ValueError("Count mismatch: " + field)
    checks = {
        "motion_sha256": hash_array(motion),
        "selected_command_sha256": hash_array([r["selected"] for r in commands]),
        "applied_command_sha256": hash_array(actual_inputs),
    }
    if any(summary[k] != v for k, v in checks.items()):
        raise ValueError("Motion/command digest mismatch")
    if case["information"] == "ideal":
        if packets:
            raise ValueError("Ideal fixture must not claim measurement packets")
    else:
        if len(packets) != 602:
            raise ValueError("Wrong packet population")
        for i, packet in enumerate(packets):
            k = i // 2
            ch = ("primary", "monitor")[i % 2]
            if packet["time_s"] != k or packet["channel"] != ch:
                raise ValueError("Packet chronology mismatch")
            noise = np.array(innovations[ch + "_noise"][k])
            np.testing.assert_array_equal(noise, packet["noise_innovation"])
            active = (
                ch == "primary"
                and case["fault"] != "none"
                and 100 <= k < (130 if case["fault"] == "bias" else 106)
            )
            if packet["fault_window_active"] != active:
                raise ValueError("Fault timing mismatch")
            if active and case["fault"] == "dropout":
                if packet["packet"] is not None or packet["disposition"] != "dropout":
                    raise ValueError("Missing dropout")
            else:
                quantum = np.array([0.02, 0.02, 0.002, 0.002])
                value = np.rint((motion[4 * k, 1:] + noise) / quantum) * quantum
                if active and case["fault"] == "bias":
                    value = value + np.array([8.0, 0.0, 0.0, 0.0])
                np.testing.assert_array_equal(value, packet["packet"])
        dispositions = dict(Counter(p["disposition"] for p in packets if p["fault_window_active"]))
        if summary["fault_packet_dispositions"] != dispositions:
            raise ValueError("Fault acceptance aggregate mismatch")
    if summary["adjudication"] != strict_json(folder / "adjudication.json"):
        raise ValueError("Endpoint aggregate mismatch")
    return {
        "commands": len(commands),
        "states": len(states),
        "packet_opportunities": len(packets),
        "applied_segments": len(schedule),
    }


def verify(directory):
    directory = Path(directory).resolve()
    file_count = verify_manifest(directory)
    protocol = strict_json(directory / "protocol.json")
    innovations = strict_json(directory / "innovations.json")
    expected = {
        f"{c['id']}__{m}__{a}": c
        for c in protocol["cases"]
        for m in protocol["plants"]
        for a in protocol["arms"]
    }
    if {p.name for p in (directory / "cells").iterdir() if p.is_dir()} != set(expected):
        raise ValueError("Run matrix mismatch")
    totals = Counter()
    for name, case in expected.items():
        totals.update(validate_cell(directory / "cells" / name, case, innovations))
    return {
        "schema": "sal-causal-record-verification/1",
        "passed": True,
        "execution_manifest_sha256": sha(directory / "manifest.json"),
        "files": file_count,
        "cells": len(expected),
        "reconstructed_counts": dict(totals),
        "scope": "record, pairing and source identities; no new simulation execution or independent physical validation",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execution", type=Path, required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = verify(args.execution)
    if args.output:
        save_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
