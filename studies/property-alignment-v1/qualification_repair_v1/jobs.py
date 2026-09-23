"""Qualification-only spawned workers with attributed failures and immutable resume.

This validation runner rejects protected namespaces. A subsequent new freeze must
explicitly integrate the repair; the old evaluation.execute entrypoint is untouched.
"""

from pathlib import Path
from collections import deque
from datetime import datetime, timezone
import json
import os
import hashlib
import fcntl
import math
import multiprocessing as mp
import time
from evaluation.safety import atomic_json, strict_json, canonical_hash, safe_path
from .fixtures import information


def _last_event(path):
    last = {"phase": "worker_startup"}
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                event = json.loads(line)
                if isinstance(event, dict) and "phase" in event:
                    last = event
            except json.JSONDecodeError:
                pass  # A torn final progress line cannot invent a completed phase.
    return last


def _worker(payload, dest, event_file, mode):
    start = time.perf_counter()
    path = Path(event_file)

    def observe(event):
        entry = {
            "case_key": payload["key"],
            "wall_since_start_s": time.perf_counter() - start,
            **event,
        }
        with path.open("a") as stream:
            stream.write(json.dumps(entry, allow_nan=False) + "\n")
            stream.flush()

    observe({"phase": "imports"})
    if mode == "forced_crash":
        observe({"phase": "injected_test_failure"})
        raise RuntimeError("deliberate development worker crash")
    if mode == "forced_timeout":
        observe({"phase": "injected_test_wait"})
        time.sleep(10)
        return
    from .core import qualify

    info = information(payload)
    observe({"phase": "qualification_start"})
    result = qualify(info, observer=observe)
    atomic_json(
        dest,
        {
            "schema": "sal-repair-job/1",
            "key": payload["key"],
            "input_sha256": canonical_hash(payload),
            "namespace": payload["namespace"],
            "qualification": result,
            "worker_wall_s": time.perf_counter() - start,
        },
    )


def _missing(payload, reason, event_path, elapsed=None, exitcode=None):
    return {
        "schema": "sal-repair-job/1",
        "key": payload["key"],
        "input_sha256": canonical_hash(payload),
        "namespace": payload["namespace"],
        "qualification": {
            "status": reason,
            "eligible": None,
            "physical_impossibility_claim": False,
        },
        "worker_wall_s": None,
        "failure": {
            "reason": reason,
            "case_key": payload["key"],
            "phase": _last_event(event_path).get("phase"),
            "last_event": _last_event(event_path),
            "parent_wall_s": elapsed,
            "exit_code": exitcode,
            "retry_performed": False,
        },
    }


def _validate(row, payload):
    if row.get("key") != payload["key"] or row.get("input_sha256") != canonical_hash(payload):
        raise ValueError("Saved receipt input identity differs")
    if row.get("namespace") != payload["namespace"]:
        raise ValueError("Saved receipt namespace differs")
    q = row["qualification"]
    e = q.get("eligible")
    status = q.get("status")
    if e is not None and type(e) is not bool:
        raise ValueError("Eligibility is not Boolean/unknown")
    if (status == "qualified") != (e is True):
        raise ValueError("Qualification flag differs from status")
    if e is False and status not in ("not_certified_by_library", "proved_precommand_violation"):
        raise ValueError("Failure cannot silently become excluded/ineligible")
    if q.get("physical_impossibility_claim") is True and status != "proved_precommand_violation":
        raise ValueError("Unsupported physical claim")


def _run_jobs(
    payloads,
    output,
    *,
    workers=4,
    case_limit_s=15.0,
    phase_limit_s=600.0,
    max_new=None,
    test_mode=None,
):
    payloads = list(payloads)
    output = safe_path(output)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("One to four workers required")
    for value in (case_limit_s, phase_limit_s):
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError("Finite positive budget required")
    if case_limit_s > 60 or phase_limit_s > 1800:
        raise ValueError("Declared maximum development budget exceeded")
    if max_new is not None and (type(max_new) is not int or max_new < 0):
        raise ValueError("Invalid start limit")
    if test_mode not in (None, "forced_crash", "forced_timeout"):
        raise ValueError("Unknown development test mode")
    for p in payloads:
        information(p)
        if (
            not isinstance(p["key"], str)
            or not p["key"]
            or any(
                c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for c in p["key"]
            )
        ):
            raise ValueError("Unsafe case key")
    if len({p["key"] for p in payloads}) != len(payloads) or not payloads:
        raise ValueError("Nonempty unique inputs required")
    repo = Path(__file__).resolve().parents[3]
    if output.is_relative_to(repo):
        raise ValueError("Execution output cannot enter the scientific repository")
    header = {
        "schema": "sal-repair-batch/1",
        "inputs": [canonical_hash(p) for p in payloads],
        "workers": workers,
        "case_limit_s": case_limit_s,
        "phase_limit_s": phase_limit_s,
        "test_mode": test_mode,
        "source_sha256": {
            name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
            for name in ("core.py", "jobs.py", "fixtures.py")
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    if (output / "header.json").exists():
        if strict_json(output / "header.json") != header:
            raise ValueError("Resume header drift")
    else:
        if list(output.iterdir()):
            raise ValueError("Existing unowned output refused")
        atomic_json(output / "header.json", header)
    cases = output / "cases"
    markers = output / "started"
    events = output / "events"
    for p in (cases, markers, events):
        p.mkdir(exist_ok=True)
    pending = deque()
    preserved = 0
    expected = {p["key"] + ".json" for p in payloads}
    if {p.name for p in cases.glob("*.json")} - expected:
        raise ValueError("Unexpected receipt")
    for p in payloads:
        dest = cases / (p["key"] + ".json")
        marker = markers / (p["key"] + ".json")
        if dest.exists():
            _validate(strict_json(dest), p)
            preserved += 1
        elif marker.exists():
            if strict_json(marker).get("input_sha256") != canonical_hash(p):
                raise ValueError("Start marker drift")
            atomic_json(
                dest, _missing(p, "interrupted_qualification", events / (p["key"] + ".jsonl"))
            )
            preserved += 1
        else:
            pending.append(p)
    context = mp.get_context("spawn")
    active = []
    start = time.perf_counter()
    new = 0
    phase_stopped = False
    try:
        while pending or active:
            if time.perf_counter() - start >= phase_limit_s:
                phase_stopped = True
                break
            while pending and len(active) < workers and (max_new is None or new < max_new):
                p = pending.popleft()
                dest = cases / (p["key"] + ".json")
                ep = events / (p["key"] + ".jsonl")
                atomic_json(
                    markers / (p["key"] + ".json"),
                    {
                        "input_sha256": canonical_hash(p),
                        "key": p["key"],
                        "phase": "qualification",
                        "started_at_utc": datetime.now(timezone.utc).isoformat(),
                    },
                )
                child = context.Process(target=_worker, args=(p, str(dest), str(ep), test_mode))
                launched = time.perf_counter()
                child.start()
                active.append((child, p, dest, ep, launched))
                new += 1
            if not active:
                break
            for job in list(active):
                child, p, dest, ep, launched = job
                elapsed = time.perf_counter() - launched
                timeout = child.is_alive() and elapsed >= case_limit_s
                if timeout:
                    child.terminate()
                    child.join(2)
                    if child.is_alive():
                        child.kill()
                        child.join(2)
                if not child.is_alive():
                    child.join()
                    active.remove(job)
                    if not dest.exists():
                        atomic_json(
                            dest,
                            _missing(
                                p,
                                "qualification_timeout"
                                if timeout
                                else "qualification_process_failure",
                                ep,
                                elapsed,
                                child.exitcode,
                            ),
                        )
                    _validate(strict_json(dest), p)
            time.sleep(0.005)
    finally:
        for child, p, dest, ep, launched in active:
            if child.is_alive():
                child.terminate()
                child.join(2)
                if child.is_alive():
                    child.kill()
                    child.join(2)
            if not dest.exists():
                atomic_json(
                    dest,
                    _missing(
                        p,
                        "qualification_phase_interruption",
                        ep,
                        time.perf_counter() - launched,
                        child.exitcode,
                    ),
                )
    rows = [
        strict_json(cases / (p["key"] + ".json"))
        for p in payloads
        if (cases / (p["key"] + ".json")).exists()
    ]
    return {
        "complete": len(rows) == len(payloads),
        "expected": len(payloads),
        "completed": len(rows),
        "blockers": sum(r["qualification"]["eligible"] is None for r in rows),
        "new_attempts": new,
        "preserved_receipts": preserved,
        "phase_limit_reached": phase_stopped,
        "wall_s": time.perf_counter() - start,
        "workers": workers,
        "scope": "developmental qualification only; not a protected campaign",
    }


def run_jobs(payloads, output, **kwargs):
    """One owner per batch. Never mistake another live writer for an interrupted job."""
    output = safe_path(output)
    repo = Path(__file__).resolve().parents[3]
    evidence = os.environ.get("SAL_EVIDENCE_ROOT")
    if output.is_relative_to(repo) or (evidence and output.is_relative_to(safe_path(evidence))):
        raise ValueError("Execution output cannot enter either scientific repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = safe_path(output.parent / ("." + output.name + ".qualification.lock"))
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run_jobs(payloads, output, **kwargs)
