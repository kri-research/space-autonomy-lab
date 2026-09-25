"""Deterministic fixed-output checks and write-once recording of their results."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from . import endpoint, matrix, stress

ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent
REPO = STUDY.parents[1]


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory():
    paths = list(ROOT.glob("*.py")) + [
        ROOT / x for x in ("SOURCE.json", "REFERENCE.json", "ENDPOINT_CONVENTION.md")
    ]
    return {p.name: digest(p.read_bytes()) for p in sorted(paths)}


def calculate():
    results = {
        "matrix": matrix.evaluate(),
        "stress": stress.evaluate(),
        "endpoint": endpoint.evaluate(),
    }
    refs = json.loads((ROOT / "REFERENCE.json").read_text())
    actual = {name: digest(canonical(value)) for name, value in results.items()}
    if actual != refs["scientific_result_sha256"]:
        raise ValueError("Fixed results differ from the supplied corrected reference")
    return results


def record(directory):
    directory = Path(directory)
    if directory.exists():
        raise ValueError("Recording requires a new output directory")
    sources = inventory()
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    for name, expected in sources.items():
        key = commit + ":" + (ROOT / name).relative_to(REPO).as_posix()
        raw = subprocess.check_output(["git", "-C", str(REPO), "show", key])
        if digest(raw) != expected:
            raise ValueError("Commit checked source before recording: " + name)
    results = calculate()
    directory.mkdir(parents=True)
    raw = canonical(results) + b"\n"
    (directory / "results.json").write_bytes(raw)
    manifest = {
        "schema": "sal-post-review-fixed-checks/1",
        "source_commit": commit,
        "source_sha256": sources,
        "result_sha256": digest(raw),
        "original_policy_executed": False,
        "original_results_changed": False,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return verify(directory)


def verify(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["source_sha256"] != inventory():
        raise ValueError("Fixed-check source differs")
    for name, expected in manifest["source_sha256"].items():
        key = manifest["source_commit"] + ":" + (ROOT / name).relative_to(REPO).as_posix()
        if digest(subprocess.check_output(["git", "-C", str(REPO), "show", key])) != expected:
            raise ValueError("Fixed-check generating source unavailable or different")
    raw = (directory / "results.json").read_bytes()
    if digest(raw) != manifest["result_sha256"]:
        raise ValueError("Fixed-check result bytes differ")
    results = calculate()
    if json.loads(raw) != results:
        raise ValueError("Fixed-check numerical reproduction differs")
    return {
        "passed": True,
        "nominal_and_shifted_pairs": 6,
        "joint_obstructions": 2,
        "stress_witnesses": len(results["stress"]["cases"]),
        "endpoint_example": True,
        "original_policy_executed": False,
        "original_results_changed": False,
        "scope": "Explicit construction and its simultaneous state shifts, not another full-campaign or physical study",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--record", type=Path)
    modes.add_argument("--verify", type=Path)
    a = p.parse_args()
    print(json.dumps(record(a.record) if a.record else verify(a.verify), indent=2))


if __name__ == "__main__":
    main()
