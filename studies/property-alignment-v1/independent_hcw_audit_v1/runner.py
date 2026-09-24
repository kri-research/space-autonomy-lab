"""Serial offline certificate audit with immutable, non-retrying checkpoints."""

from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from contextlib import contextmanager
import argparse
import json
import hashlib
import math
import os
import subprocess
import sys
import time
import fcntl
from .schema import require, strict_json, identity
from .reader import load_dataset, safe_name

ROOT = Path(__file__).resolve().parent


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def safe_output(output):
    output = Path(output).expanduser().absolute()
    require(not any(p.is_symlink() for p in (output, *output.parents)), "Symlink output")
    require(not output.is_relative_to(ROOT), "Output must be outside auditor source")
    require(
        not any((parent / ".git").exists() for parent in (output, *output.parents)),
        "Output overlaps a Git evidence checkout",
    )
    return output


@contextmanager
def exclusive(output):
    with (output / "audit.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def verify_freeze(path, audit_id):
    from .protocol import validate_document

    return validate_document(strict_json(Path(path).read_bytes()), audit_id)


def run_jobs(
    jobs,
    settings,
    output,
    audit_id,
    *,
    resume=False,
    max_new=None,
    job_timeout_s=30,
    phase_timeout_s=1800,
):
    """Only unstarted jobs resume; starts without results are retained as interrupted.

    max_new provides a development-only controlled checkpoint. The campaign CLI
    does not expose it. Original policy outcomes are never recomputed or changed.
    """
    output = safe_output(output)
    require(
        type(job_timeout_s) in (int, float)
        and math.isfinite(job_timeout_s)
        and job_timeout_s > 0
        and type(phase_timeout_s) in (int, float)
        and math.isfinite(phase_timeout_s)
        and phase_timeout_s > 0,
        "Invalid watchdog",
    )
    require(max_new is None or (type(max_new) is int and max_new >= 0), "Invalid checkpoint count")
    require(
        type(jobs) is list and bool(jobs) and all(type(j) is dict for j in jobs),
        "Job list required",
    )
    expected = {
        "audit_id": audit_id,
        "jobs": {j["key"]: identity(j) for j in jobs},
        "settings": settings,
        "job_timeout_s": job_timeout_s,
        "phase_timeout_s": phase_timeout_s,
    }
    require(len(expected["jobs"]) == len(jobs), "Duplicate job key")
    for job in jobs:
        require(safe_name(job["key"]) == job["key"] and "/" not in job["key"], "Unsafe job key")
    if output.exists():
        require(
            resume and strict_json((output / "header.json").read_bytes()) == expected,
            "Existing header differs",
        )
    else:
        output.mkdir(parents=True)
        write_new(output / "header.json", expected)
    with exclusive(output):
        return _run(jobs, settings, output, audit_id, max_new, job_timeout_s, phase_timeout_s)


def validate_worker_result(result, job):
    require(type(result) is dict and result.get("key") == job["key"], "Worker response binding")
    require(result.get("schema") == "sal-independent-hcw-case-audit/1", "Worker result schema")
    claim = result.get("claim")
    require(type(claim) is dict, "Missing numerical claim outcome")
    require(
        claim.get("status")
        in {
            "verified_prefix",
            "verified_obstruction",
            "numerically_unresolved",
            "binding_invalid_evidence",
            "unsupported_assumptions",
            "contradicted_prefix",
            "no_on_time_certificate",
        },
        "Unknown numerical outcome",
    )
    trace = result.get("dependency_trace")
    require(
        type(trace) is dict
        and trace.get("nonstdlib_dependencies") == []
        and trace.get("isolated_python") is True
        and trace.get("site_disabled") is True
        and trace.get("external_imports_blocked_before_execution") is True,
        "Worker dependency boundary missing",
    )
    return result


def worker_artifacts(output, key):
    result = {}
    for suffix in (".json", ".stderr"):
        path = output / "worker-output" / (key + suffix)
        if path.exists():
            require(path.is_file() and not path.is_symlink(), "Unsafe worker output")
            result[path.relative_to(output).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def _run(jobs, settings, output, audit_id, max_new, job_timeout_s, phase_timeout_s):
    started, new, summary = time.monotonic(), 0, []
    receipts = output / "receipts"
    if receipts.exists():
        require(
            {p.name for p in receipts.iterdir()} <= {j["key"] + ".json" for j in jobs},
            "Unexpected audit receipt",
        )
    for job in jobs:
        key = job["key"]
        receipt, marker = receipts / (key + ".json"), output / "started" / (key + ".json")
        binding = {"audit_id": audit_id, "job_sha256": identity(job), "key": key}
        if receipt.exists():
            row = strict_json(receipt.read_bytes())
            require(
                row.get("binding") == binding
                and row.get("receipt_sha256")
                == identity({k: v for k, v in row.items() if k != "receipt_sha256"}),
                "Existing receipt differs",
            )
            require(
                marker.is_file()
                and not marker.is_symlink()
                and strict_json(marker.read_bytes()).get("binding") == binding,
                "Receipt without matching start",
            )
            require(
                row.get("worker_artifacts") == worker_artifacts(output, key),
                "Worker evidence changed",
            )
            if row["result"]["claim"]["status"] not in (
                "audit_interrupted",
                "audit_timeout",
                "audit_execution_failure",
            ):
                validate_worker_result(row["result"], job)
                raw = strict_json((output / "worker-output" / (key + ".json")).read_bytes())
                require(row["result"] == raw, "Receipt differs from original worker result")
            summary.append(row)
            continue
        if marker.exists():
            require(strict_json(marker.read_bytes())["binding"] == binding, "Prior start differs")
            result = {
                "key": key,
                "claim": {
                    "status": "audit_interrupted",
                    "reason": "started_without_completed_receipt_no_retry",
                },
            }
            elapsed = None
        else:
            if (
                max_new is not None and new >= max_new
            ) or time.monotonic() - started > phase_timeout_s:
                break
            packet = output / "jobs" / (key + ".json")
            if packet.exists():
                require(
                    strict_json(packet.read_bytes()) == {"job": job, "settings": settings},
                    "Incomplete staged input differs",
                )
            else:
                write_new(packet, {"job": job, "settings": settings})
            write_new(
                marker,
                {"binding": binding, "started_at_utc": datetime.now(timezone.utc).isoformat()},
            )
            before = time.monotonic()
            stdout, stderr = (
                output / "worker-output" / (key + ".json"),
                output / "worker-output" / (key + ".stderr"),
            )
            stdout.parent.mkdir(exist_ok=True)
            try:
                with stdout.open("xb") as out, stderr.open("xb") as log:
                    process = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-S",
                            "-B",
                            str(ROOT / "worker.py"),
                            "--job",
                            str(packet),
                        ],
                        stdout=out,
                        stderr=log,
                        timeout=job_timeout_s,
                        check=False,
                    )
                if process.returncode == 0:
                    result = validate_worker_result(strict_json(stdout.read_bytes()), job)
                else:
                    result = {
                        "key": key,
                        "claim": {
                            "status": "audit_execution_failure",
                            "returncode": process.returncode,
                        },
                    }
            except subprocess.TimeoutExpired:
                result = {
                    "key": key,
                    "claim": {"status": "audit_timeout", "limit_s": job_timeout_s, "retry": False},
                }
            except (ValueError, OSError) as exc:
                result = {
                    "key": key,
                    "claim": {
                        "status": "audit_execution_failure",
                        "error_type": type(exc).__name__,
                    },
                }
            elapsed = time.monotonic() - before
            new += 1
        row = {
            "binding": binding,
            "result": result,
            "cold_process_elapsed_s": elapsed,
            "original_policy_executed": False,
            "worker_artifacts": worker_artifacts(output, key),
        }
        row["receipt_sha256"] = identity(row)
        write_new(receipt, row)
        summary.append(row)
    return {
        "audit_id": audit_id,
        "expected": len(jobs),
        "completed": len(summary),
        "complete": len(summary) == len(jobs),
        "new_jobs": new,
        "statuses": dict(Counter(r["result"]["claim"]["status"] for r in summary)),
        "qualification_witnesses": sum(
            len(r["result"].get("qualification_witnesses", [])) for r in summary
        ),
        "no_original_results_changed": True,
        "no_original_policy_executed": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--study", type=Path, default=ROOT.parent)
    parser.add_argument("--authorize-R03", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    require(args.authorize_R03, "Full campaign audit requires explicit R03 execution")
    doc = verify_freeze(args.freeze, args.audit_id)
    cases, _ = load_dataset(args.study, doc["original_files_sha256"])
    require(
        [{"key": c["key"], **c["bindings"]} for c in cases] == doc["case_bindings"],
        "Original cases differ",
    )
    jobs = [
        {
            "kind": "recorded_episode",
            "key": c["key"],
            "payload": c["payload"],
            "episode": c["episode"],
            "qualification": c["qualification"],
        }
        for c in cases
    ]
    protocol = doc["protocol"]
    result = run_jobs(
        jobs,
        protocol["numerical"],
        args.output,
        args.audit_id,
        resume=args.resume,
        job_timeout_s=protocol["job_timeout_s"],
        phase_timeout_s=protocol["phase_timeout_s"],
    )
    verify_freeze(args.freeze, args.audit_id)
    load_dataset(args.study, doc["original_files_sha256"])
    if result["complete"]:
        target = args.output / "completion.json"
        stable = {k: v for k, v in result.items() if k != "new_jobs"}
        if target.exists():
            require(strict_json(target.read_bytes()) == stable, "Completion differs")
        else:
            write_new(target, stable)
    print(json.dumps(result, indent=2))
    if not result["complete"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
