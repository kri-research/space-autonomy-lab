"""Execute a sealed developmental matrix once, retaining all selected attempts."""

from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
import json
import os
import subprocess
import time
from .io import ROOT, PACKAGE, save_json, verify_seal, seal, new_output, manifest, environment, sha
from .experiment import run_cell, innovations, ARM_NAMES
from .qualification import classification_only, qualify


def matrix(protocol):
    return [
        (case, plant, arm)
        for case in protocol["cases"]
        for plant in protocol["plants"]
        for arm in protocol["arms"]
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seal", "run", "verify"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.action == "seal":
        print(json.dumps(seal(), indent=2))
        return
    sealed = verify_seal()
    if args.action == "verify":
        print("Protocol and source identities match")
        return
    if args.output is None or not 1 <= args.workers <= 4:
        parser.error("Fresh external output and 1-4 workers required")
    protocol = json.loads((PACKAGE / "protocol.json").read_text())
    if tuple(protocol["arms"]) != ARM_NAMES or len(matrix(protocol)) != 56:
        raise ValueError("Matrix drift")
    output = new_output(args.output)
    with (output / "execution.lock").open("x") as f:
        f.write(str(os.getpid()) + chr(10))
    save_json(output / "protocol.json", protocol)
    save_json(output / "seal.json", sealed)
    save_json(
        output / "innovations.json", {k: v.tolist() for k, v in innovations(protocol).items()}
    )
    record = {
        "schema": "sal-causal-execution/1",
        "kind": "developmental_mechanistic_not_confirmatory",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment(),
        "code_commit": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "protocol_sha256": sha(PACKAGE / "protocol.json"),
        "workers": args.workers,
        "selected_cells": 56,
        "status": "running",
        "results": [],
        "qualification": [],
        "no_historical_campaign": True,
        "no_task05_work": True,
        "automatic_retry": False,
    }
    started = time.perf_counter()
    save_json(output / "started.json", record)
    try:
        classification_only(output)
        print("Same-path classification complete", flush=True)
        for case in protocol["cases"]:
            if case["role"] == "ideal_main":
                for kind in protocol["plants"]:
                    q = qualify(case, kind, output, protocol)
                    record["qualification"].append(q)
                    print(
                        "Qualification",
                        case["id"],
                        kind,
                        q["finite_horizon_recoverability"],
                        flush=True,
                    )
        jobs = [(c, p, a, str(output), protocol) for c, p, a in matrix(protocol)]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_cell, j): j for j in jobs}
            for future in as_completed(futures):
                c, p, a, *_ = futures[future]
                try:
                    r = future.result()
                    record["results"].append(
                        {
                            "case": c["id"],
                            "plant": p,
                            "arm": a,
                            "execution_status": r["execution_status"],
                            "physical_status": r["physical_status"],
                        }
                    )
                    print(
                        c["id"],
                        p,
                        a,
                        r["execution_status"],
                        r["physical_status"],
                        r["overrides"],
                        r["changed_commands"],
                        flush=True,
                    )
                except Exception as exc:
                    failure = {
                        "case": c["id"],
                        "plant": p,
                        "arm": a,
                        "execution_status": "worker_failed",
                        "error": type(exc).__name__ + ":" + str(exc),
                    }
                    record["results"].append(failure)
                    save_json(output / f"worker_failure_{c['id']}_{p}_{a}.json", failure)
                    print("Worker failed", failure, flush=True)
        record["status"] = (
            "complete"
            if len(record["results"]) == 56
            and all(r["execution_status"] == "complete" for r in record["results"])
            else "incomplete"
        )
    except Exception as exc:
        record.update(status="incomplete", error=type(exc).__name__ + ":" + str(exc))
    verify_seal()
    record["elapsed_wall_s"] = time.perf_counter() - started
    record["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    save_json(output / "execution.json", record)
    manifest(output)
    print("Developmental execution", record["status"], len(record["results"]), flush=True)
    if record["status"] != "complete":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
