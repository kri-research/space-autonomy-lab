"""Same bounded spawned coordinator for calibration and authorized replacement work.

No original runner is patched. Phase-specific failure receipts retain unknown
qualification and failed selected outcomes without resampling or retries.
"""

from collections import deque
from pathlib import Path
import fcntl
import json
import math
import multiprocessing as mp
import os
import time
from evaluation.safety import atomic_json, strict_json, safe_path, canonical_hash, utc_now
from .receipts import key, seal, validate, missing


def worker(payload, kind, destination, event_path, qualification=None, test_mode=None):
    started = time.perf_counter()

    def observe(event):
        with Path(event_path).open("a") as handle:
            handle.write(
                json.dumps(
                    {"case_key": key(payload), "wall_s": time.perf_counter() - started, **event},
                    allow_nan=False,
                )
                + "\n"
            )
            handle.flush()

    observe({"phase": "imports"})
    if test_mode is not None:
        if payload["namespace"] != "calibration":
            raise PermissionError("Test hooks cannot receive protected/development inputs")
        if test_mode == "crash":
            observe({"phase": "injected_crash"})
            raise RuntimeError("Deliberate calibration crash")
        if test_mode == "timeout":
            observe({"phase": "injected_wait"})
            time.sleep(10)
            return
        raise ValueError("Unknown test mode")
    from evaluation.runner import _information
    from qualification_repair_v1.core import qualify
    from qualification_repair_v1.recheck import recheck
    from evaluation.episode import run_case

    if kind == "qualification":
        result = qualify(_information(payload), observer=observe)
        observe({"phase": "qualification_recheck"})
        proof = (
            recheck(_information(payload), result)
            if result["eligible"] is not None
            else {"passed": False, "reason": "qualification_unknown"}
        )
        if not proof["passed"] and result["eligible"] is not None:
            result = {
                "status": "qualification_recheck_unresolved",
                "eligible": None,
                "physical_impossibility_claim": False,
                "original_qualification": result,
            }
        row = {
            "schema": "sal-replacement-qualification/1",
            "case_id": canonical_hash(payload),
            **{k: payload[k] for k in ("namespace", "stratum", "index", "generator_seed")},
            "qualification": result,
            "qualification_recheck": proof,
            "worker_wall_s": time.perf_counter() - started,
        }
    elif kind == "episode":
        if qualification is None or qualification.get("eligible") is not True:
            raise ValueError("Candidate cannot run before positive selection")
        observe({"phase": "candidate_episode"})
        row = run_case(payload, qualification_record=qualification)
        row["worker_wall_s"] = time.perf_counter() - started
    else:
        raise ValueError("Unknown job kind")
    row = seal(row)
    validate(row, payload, kind, qualification)
    observe({"phase": "publishing"})
    atomic_json(destination, row)


def run_batch(
    payloads,
    output,
    *,
    kind,
    context_id,
    workers=4,
    case_limit_s=15.0,
    phase_limit_s=1800.0,
    qualifications=None,
    authorize_task08d=False,
    max_new=None,
    test_mode=None,
):
    payloads = list(payloads)
    if (
        kind not in ("qualification", "episode")
        or type(workers) is not int
        or not 1 <= workers <= 4
    ):
        raise ValueError("Invalid execution phase/resources")
    if not isinstance(context_id, str) or not context_id:
        raise ValueError("Execution context identity required")
    for value, upper in ((case_limit_s, 60), (phase_limit_s, 1800)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 < value <= upper
        ):
            raise ValueError("Invalid bounded runtime")
    if max_new is not None and (type(max_new) is not int or max_new < 0):
        raise ValueError("Invalid checkpoint limit")
    if not payloads or len({key(p) for p in payloads}) != len(payloads):
        raise ValueError("Nonempty unique case keys required")
    if len({p["namespace"] for p in payloads}) != 1:
        raise ValueError("Mixed namespaces")
    protected = payloads[0]["namespace"] == "protected"
    if protected and (authorize_task08d is not True or test_mode is not None):
        raise PermissionError(
            "Protected jobs require explicit Task08D authorization and real execution"
        )
    if test_mode not in (None, "crash", "timeout") or (
        test_mode is not None and payloads[0]["namespace"] != "calibration"
    ):
        raise ValueError("Calibration-only failure injection")
    if kind == "episode":
        if qualifications is None or set(qualifications) != {canonical_hash(p) for p in payloads}:
            raise ValueError("Exact selection qualifications required")
        if any(q.get("eligible") is not True for q in qualifications.values()):
            raise ValueError("Unknown or ineligible selection")
    output = safe_path(output)
    repo = Path(__file__).resolve().parents[3]
    evidence = os.environ.get("SAL_EVIDENCE_ROOT")
    if output.is_relative_to(repo) or (evidence and output.is_relative_to(safe_path(evidence))):
        raise ValueError("Cannot write execution to either repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = safe_path(output.parent / ("." + output.name + ".batch.lock"))
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _locked(
            payloads,
            output,
            kind,
            context_id,
            workers,
            case_limit_s,
            phase_limit_s,
            qualifications,
            max_new,
            test_mode,
        )


def _locked(
    payloads,
    output,
    kind,
    context_id,
    workers,
    case_limit_s,
    phase_limit_s,
    qualifications,
    max_new,
    test_mode,
):
    qmap = {} if qualifications is None else qualifications
    header = {
        "schema": "sal-replacement-batch/1",
        "context_id": context_id,
        "kind": kind,
        "inputs": [canonical_hash(p) for p in payloads],
        "workers": workers,
        "case_limit_s": case_limit_s,
        "phase_limit_s": phase_limit_s,
        "test_mode": test_mode,
        "qualifications": {k: canonical_hash(v) for k, v in qmap.items()},
    }
    output.mkdir(parents=True, exist_ok=True)
    if (output / "header.json").exists():
        if strict_json(output / "header.json") != header:
            raise ValueError("Batch identity changed")
    else:
        if list(output.iterdir()):
            raise ValueError("Unowned output directory")
        atomic_json(output / "header.json", header)
    cases, markers, events = (output / name for name in ("cases", "started", "events"))
    for p in (cases, markers, events):
        p.mkdir(exist_ok=True)
    expected = {key(p) + ".json" for p in payloads}
    if {p.name for p in cases.glob("*.json")} - expected or {
        p.name for p in markers.glob("*.json")
    } - expected:
        raise ValueError("Unexpected execution receipt/start marker")
    pending = deque()
    preserved = 0
    for p in payloads:
        stem = key(p)
        dest = cases / (stem + ".json")
        marker = markers / (stem + ".json")
        ep = events / (stem + ".jsonl")
        qual = qmap.get(canonical_hash(p))
        if dest.exists():
            validate(strict_json(dest), p, kind, qual)
            preserved += 1
        elif marker.exists():
            saved = strict_json(marker)
            if saved.get("case_id") != canonical_hash(p) or saved.get("kind") != kind:
                raise ValueError("Interrupted start binding differs")
            atomic_json(dest, missing(p, kind, "interrupted_started_case_no_retry", ep, qual))
            preserved += 1
        else:
            pending.append(p)
    ctx = mp.get_context("spawn")
    active = []
    new = 0
    started = time.perf_counter()
    stopped = False

    def stop(child):
        if child.is_alive():
            child.terminate()
            child.join(2)
            if child.is_alive():
                child.kill()
                child.join(2)
        child.join()

    try:
        while pending or active:
            if time.perf_counter() - started >= phase_limit_s:
                stopped = True
                break
            if sum(p.stat().st_size for p in output.rglob("*") if p.is_file()) > 512 * 1024**2:
                raise RuntimeError("Receipt budget exceeded")
            while pending and len(active) < workers and (max_new is None or new < max_new):
                p = pending.popleft()
                stem = key(p)
                dest = cases / (stem + ".json")
                ep = events / (stem + ".jsonl")
                atomic_json(
                    markers / (stem + ".json"),
                    {"case_id": canonical_hash(p), "kind": kind, "started_at_utc": utc_now()},
                )
                qual = qmap.get(canonical_hash(p))
                child = ctx.Process(
                    target=worker, args=(p, kind, str(dest), str(ep), qual, test_mode)
                )
                launch = time.perf_counter()
                child.start()
                active.append((child, p, dest, ep, launch))
                new += 1
            if not active:
                break
            for job in list(active):
                child, p, dest, ep, launch = job
                elapsed = time.perf_counter() - launch
                timeout = child.is_alive() and elapsed >= case_limit_s
                if timeout:
                    stop(child)
                if not child.is_alive():
                    child.join()
                    active.remove(job)
                    if not dest.exists():
                        atomic_json(
                            dest,
                            missing(
                                p,
                                kind,
                                "worker_wall_timeout"
                                if timeout
                                else "worker_failed_exit_" + str(child.exitcode),
                                ep,
                                qmap.get(canonical_hash(p)),
                                elapsed,
                                child.exitcode,
                            ),
                        )
                    validate(strict_json(dest), p, kind, qmap.get(canonical_hash(p)))
            time.sleep(0.005)
    finally:
        for child, p, dest, ep, launch in active:
            stop(child)
            if not dest.exists():
                atomic_json(
                    dest,
                    missing(
                        p,
                        kind,
                        "phase_interruption_no_retry",
                        ep,
                        qmap.get(canonical_hash(p)),
                        time.perf_counter() - launch,
                        child.exitcode,
                    ),
                )
    rows = [
        strict_json(cases / (key(p) + ".json"))
        for p in payloads
        if (cases / (key(p) + ".json")).exists()
    ]
    for p in payloads:
        if (cases / (key(p) + ".json")).exists():
            validate(strict_json(cases / (key(p) + ".json")), p, kind, qmap.get(canonical_hash(p)))
    return {
        "complete": len(rows) == len(payloads),
        "expected": len(payloads),
        "completed": len(rows),
        "blockers": sum(r["qualification"]["eligible"] is None for r in rows)
        if kind == "qualification"
        else 0,
        "new_attempts": new,
        "preserved_receipts": preserved,
        "phase_limit_reached": stopped,
        "wall_s": time.perf_counter() - started,
        "kind": kind,
        "workers": workers,
    }
