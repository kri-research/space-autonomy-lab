"""Calibrate the final execution path on exactly eight calibration cases only."""

from pathlib import Path
import argparse
import hashlib
from .generator import STRATA, case_payload
from .jobs import run_jobs
from .episode import scientific_signature
from .safety import atomic_json, strict_json, safe_path, canonical_hash


def signatures(path):
    rows = [strict_json(p) for p in path.glob("*.json")]
    return [
        scientific_signature(r)
        for r in sorted(rows, key=lambda r: (STRATA.index(r["stratum"]), r["index"]))
    ]


def calibrate(output):
    output = safe_path(output)
    study = Path(__file__).resolve().parents[1]
    if output.exists() or output.is_relative_to(study.parents[1]):
        raise ValueError("New private calibration output required")
    output.mkdir(parents=True)
    inputs = [case_payload("calibration", s, i) for s in STRATA for i in range(2)]
    atomic_json(output / "inputs.json", inputs)
    serial = run_jobs(inputs, output / "serial", kind="episode", workers=1)
    parallel = run_jobs(inputs, output / "parallel", kind="episode", workers=4)
    if not serial["complete"] or not parallel["complete"]:
        raise AssertionError("Calibration incomplete")
    if signatures(output / "serial") != signatures(output / "parallel"):
        raise AssertionError("Serial and parallel scientific outputs differ")
    first = run_jobs(inputs, output / "checkpoint", kind="episode", workers=4, max_new=3)
    first_hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (output / "checkpoint").glob("*.json")
    }
    second = run_jobs(inputs, output / "checkpoint", kind="episode", workers=4)
    if first["complete"] or not second["complete"]:
        raise AssertionError("Checkpoint path did not pause and resume")
    if signatures(output / "serial") != signatures(output / "checkpoint"):
        raise AssertionError("Checkpoint scientific output differs")
    for name, value in first_hashes.items():
        if hashlib.sha256((output / "checkpoint" / name).read_bytes()).hexdigest() != value:
            raise AssertionError("Completed receipt rewritten")
    interrupted = output / "interrupted"
    p = inputs[0]
    stem = f"{p['stratum']}__{p['index']:05d}.json"
    atomic_json(interrupted / "started" / stem, {"case_id": canonical_hash(p), "kind": "episode"})
    no_retry = run_jobs([p], interrupted, kind="episode", workers=1)
    failed = strict_json(interrupted / stem)
    if no_retry["new_attempts"] != 0 or failed["primary"]["on_time_decisive_valid"]:
        raise AssertionError("Interrupted started case was rerun or counted successful")
    timeout = run_jobs(
        [inputs[1]], output / "timeout", kind="episode", workers=1, case_limit_s=0.000001
    )
    tr = next((output / "timeout").glob("*.json"))
    if strict_json(tr)["primary"]["on_time_decisive_valid"]:
        raise AssertionError("Forced process timeout became a success")
    result = {
        "passed": True,
        "namespace": "calibration",
        "cases": len(inputs),
        "serial_wall_s": serial["wall_s"],
        "parallel_wall_s": parallel["wall_s"],
        "serial_parallel_scientific_equivalence": True,
        "checkpoint_first": first,
        "checkpoint_second": second,
        "completed_receipts_preserved": True,
        "interrupted_started_case_not_rerun": True,
        "forced_timeout_failure": timeout,
        "protected_case_evaluations": 0,
        "scope": "Same eight calibration inputs deliberately repeated for mechanics; no independent scientific replicates or worst-case runtime claim",
    }
    atomic_json(output / "result.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    import json

    print(json.dumps(calibrate(a.output), indent=2))


if __name__ == "__main__":
    main()
