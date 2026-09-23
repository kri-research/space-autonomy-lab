"""One-attempt bounded transfer execution with prospective case membership."""

from pathlib import Path
from datetime import datetime, timezone
from itertools import combinations
import argparse
import json
import os
import subprocess
import sys
import time
from .schema import ROOT, STRATA, make_case, digest, read, subset, observe, rational


def atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    temp = path.with_name("." + path.name + ".tmp-" + str(os.getpid()))
    try:
        with temp.open("xb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.link(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def checked(case, result, actual_tau=None):
    from .reference import action_check, dual_check

    if result["status"] == "prefix":
        return action_check(case, result["action"], actual_tau=actual_tau)
    if result["status"] == "obstruction" and actual_tau is None:
        return dual_check(case, result["details"]["obstruction"]["weights"])
    return {"status": "not_applicable", "reason": "no_delivered_certificate"}


def one(case):
    from .policies import METHODS, decide

    started = time.perf_counter()
    packets = [observe(case, b["lower"]) for b in case["boxes"]]
    if any(p != packets[0] for p in packets):
        raise ValueError("Measurement leaks the true hypothesis")
    results = {}
    for method in METHODS:
        prediction = decide(case, method)
        observed = checked(case, prediction)
        results[method] = {"prediction": prediction, "reference": observed}
    proper = []
    if len(case["boxes"]) > 1:
        for size in range(1, len(case["boxes"])):
            for indices in combinations(range(len(case["boxes"])), size):
                c = subset(case, indices)
                prediction = decide(c)
                proper.append(
                    {
                        "indices": list(indices),
                        "prediction": prediction,
                        "reference": checked(c, prediction),
                    }
                )
    stress = {}
    if case["namespace"] == "protected" and case["stratum"] == "single_face" and case["index"] < 16:
        actual_tau = str(4 * rational(case["tau"]))
        stress = {
            "actual_tau": actual_tau,
            "declared_tau": case["tau"],
            "outside_assumptions": True,
            "fixed_command_rechecks": {
                m: checked(case, v["prediction"], actual_tau)
                for m, v in results.items()
                if v["prediction"]["status"] == "prefix"
            },
        }
    return {
        "schema": "sal-cart-transfer-outcome/1",
        "case_id": digest(case),
        "namespace": case["namespace"],
        "stratum": case["stratum"],
        "index": case["index"],
        "measurement_packets": packets,
        "methods": results,
        "proper_subsets": proper,
        "lag_mismatch_stress": stress,
        "episode_wall_s": time.perf_counter() - started,
        "physical_validation": False,
        "full_recovery_or_mission_utility_evaluated": False,
    }


def execute(output, calibration=False, freeze_path=None, authorize=False):
    from .freeze import verify
    import fcntl

    output = Path(output).resolve()
    repo = ROOT.parents[2]
    if output.is_relative_to(repo):
        raise ValueError("Raw execution must be outside the repository")
    if calibration:
        count = 2
        namespace = "calibration"
        identity = "calibration-" + digest(read(ROOT / "design.json"))
        cases = [make_case(namespace, s, i) for s in STRATA for i in range(count)]
    else:
        if not authorize:
            raise PermissionError("Explicit Task09 execution required")
        doc = verify(freeze_path, runtime=True)
        identity = doc["transfer_id"]
        namespace = "protected"
        cases = read(Path(freeze_path).parent / "inputs.json")
    if output.exists():
        raise ValueError("Attempt already exists; preserve it rather than rerunning")
    output.mkdir(parents=True)
    registry = output.parent / "identities"
    registry.mkdir(exist_ok=True)
    if not calibration:
        atomic(registry / (identity + ".json"), {"transfer_id": identity, "output": str(output)})
    atomic(output / "inputs.json", cases)
    atomic(
        output / "header.json",
        {
            "schema": "sal-cart-run/1",
            "transfer_id": identity,
            "namespace": namespace,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "workers": 1,
            "case_limit_s": 60,
            "phase_limit_s": 1800,
            "source_sha256": __import__(
                "transfer_cart_v1.freeze", fromlist=["inventory"]
            ).inventory(),
        },
    )
    (output / "cases").mkdir()
    (output / "started").mkdir()
    (output / "process_logs").mkdir()
    total = time.perf_counter()
    timings = []
    active = None
    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            for c in cases:
                if time.perf_counter() - total > 1800:
                    raise TimeoutError("Declared transfer phase budget")
                name = f"{c['stratum']}__{c['index']:04d}"
                inp = output / "started" / (name + ".json")
                dest = output / "cases" / (name + ".json")
                atomic(inp, c)
                command = [
                    sys.executable,
                    "-m",
                    "transfer_cart_v1.experiment",
                    "worker",
                    "--input",
                    str(inp),
                    "--output",
                    str(dest),
                ]
                begin = time.perf_counter()
                with (output / "process_logs" / (name + ".txt")).open("xb") as log:
                    active = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                    try:
                        code = active.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        active.terminate()
                        try:
                            active.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            active.kill()
                            active.wait()
                        code = -9
                active = None
                if code != 0 or not dest.exists():
                    if dest.exists():
                        raise RuntimeError("Worker failure after receipt publication")
                    atomic(
                        dest,
                        {
                            "schema": "sal-cart-transfer-outcome/1",
                            "case_id": digest(c),
                            "namespace": namespace,
                            "stratum": c["stratum"],
                            "index": c["index"],
                            "execution_failure": {
                                "exit_code": code,
                                "reason": "timeout" if code == -9 else "worker_failure",
                                "retry": False,
                            },
                            "physical_validation": False,
                        },
                    )
                row = read(dest)
                if row["case_id"] != digest(c):
                    raise ValueError("Wrong returned input")
                timings.append(
                    {"case_id": digest(c), "exit_code": code, "wall_s": time.perf_counter() - begin}
                )
        finally:
            if active is not None and active.poll() is None:
                active.terminate()
                active.wait(timeout=3)
    atomic(
        output / "completion.json",
        {
            "transfer_id": identity,
            "cases": len(cases),
            "elapsed_s": time.perf_counter() - total,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "attempts": timings,
            "files": {
                f.relative_to(output).as_posix(): __import__("hashlib")
                .sha256(f.read_bytes())
                .hexdigest()
                for f in sorted(output.rglob("*"))
                if f.is_file() and f.name != "run.lock"
            },
        },
    )
    return {
        "completed": len(cases),
        "failed": sum(t["exit_code"] != 0 for t in timings),
        "elapsed_s": time.perf_counter() - total,
        "transfer_id": identity,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["calibration", "execute", "worker"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--authorize-task09", action="store_true")
    a = parser.parse_args()
    if a.mode == "worker":
        atomic(a.output, one(read(a.input)))
    else:
        print(
            json.dumps(
                execute(a.output, a.mode == "calibration", a.freeze, a.authorize_task09), indent=2
            )
        )


if __name__ == "__main__":
    main()
