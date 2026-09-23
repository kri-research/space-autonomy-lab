"""Bounded post-failure diagnostic plan; never invoke protected execution."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from .worker import PACKAGE, STUDY, read_protocol, atomic_new


def execute(output):
    output = Path(output).expanduser().absolute()
    if output.exists() or output.is_relative_to(STUDY.parents[1]):
        raise ValueError("Fresh private diagnostic directory required")
    output.mkdir(parents=True, exist_ok=False)
    protocol = read_protocol()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    env = dict(os.environ)
    inventory = {
        str(p.relative_to(PACKAGE)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(PACKAGE.rglob("*"))
        if p.suffix in (".py", ".json")
    }
    header = {
        "schema": "sal-task08A-diagnostic-run/1",
        "evidence_class": "post_failure_development_diagnosis",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": inventory,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "whole_limit_s": protocol["whole_diagnostic_wall_limit_s"],
        "candidate_outcomes": 0,
        "original_attempt_retried": False,
        "separate_diagnostic_reexecutions": True,
    }
    atomic_new(output / "run.json", header)
    start = time.perf_counter()
    receipts = []

    def launch(stage, index):
        label = f"{stage['stage']}__{index:05d}"
        mode = (
            "profile"
            if stage["stage"] == "serial_profile"
            else "trace"
            if stage["stage"] == "serial_trace"
            else "plain"
        )
        argv = [
            sys.executable,
            "-m",
            "runtime_diagnosis_v1.worker",
            "--index",
            str(index),
            "--mode",
            mode,
            "--output",
            str(output / label),
        ]
        log = (output / (label + ".log")).open("x")
        proc = subprocess.Popen(argv, cwd=STUDY, env=env, stdout=log, stderr=subprocess.STDOUT)
        return {
            "proc": proc,
            "log": log,
            "launched": time.perf_counter(),
            "label": label,
            "index": index,
            "stage": stage["stage"],
            "mode": mode,
            "limit_s": stage["case_wall_limit_s"],
            "load_before": list(os.getloadavg()),
        }

    def finish(job, timeout=False):
        proc = job["proc"]
        if timeout and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        code = proc.wait()
        job["log"].close()
        receipt = {k: v for k, v in job.items() if k not in ("proc", "log", "launched")}
        receipt.update(
            {
                "exit_code": code,
                "parent_wall_s": time.perf_counter() - job["launched"],
                "diagnostic_watchdog": timeout,
                "load_after": list(os.getloadavg()),
            }
        )
        p = output / job["label"] / "result.json"
        if p.exists():
            row = json.loads(p.read_text())
            receipt.update(
                {
                    "qualification_wall_s": row["qualification_wall_s"],
                    "qualification_cpu_s": row["qualification_cpu_s"],
                    "eligible": row["qualification"]["eligible"],
                    "result_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                }
            )
        atomic_new(output / (job["label"] + ".receipt.json"), receipt)
        receipts.append(receipt)
        print(json.dumps(receipt, allow_nan=False), flush=True)

    for stage in protocol["plan"]:
        todo = list(stage["indices"])
        active = []
        try:
            while todo or active:
                if time.perf_counter() - start > protocol["whole_diagnostic_wall_limit_s"]:
                    raise TimeoutError("Declared whole diagnostic budget exhausted")
                while todo and len(active) < stage.get("workers", 1):
                    active.append(launch(stage, todo.pop(0)))
                for job in list(active):
                    expired = time.perf_counter() - job["launched"] > job["limit_s"]
                    if job["proc"].poll() is not None or expired:
                        finish(job, expired)
                        active.remove(job)
                time.sleep(0.02)
        finally:
            for job in active:
                finish(job, True)
    atomic_new(
        output / "complete.json",
        {
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": time.perf_counter() - start,
            "receipts": receipts,
            "all_diagnostic_attempts_accounted": True,
            "original_campaign_valid": False,
            "no_repair_implemented": True,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    execute(args.output)


if __name__ == "__main__":
    main()
