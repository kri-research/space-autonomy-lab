"""Bounded subprocess jobs with start markers, immutable receipts and honest resume.

Each case runs in a new spawned process. Only processes created here can be
terminated. Calibration exercises this same path; no protected inputs are
needed to test checkpointing, timeouts, or concurrency.
"""

from collections import deque
from pathlib import Path
import multiprocessing as mp
import time
from .safety import atomic_json, strict_json, canonical_hash, check_receipt, utc_now


def _perform(payload, kind, output, qualification_record=None):
    from .runner import qualification_receipt
    from .episode import run_case

    if kind == "qualification":
        row = qualification_receipt(payload)
    elif kind == "episode":
        row = run_case(payload, qualification_record=qualification_record)
    else:
        raise ValueError("Unknown job kind")
    atomic_json(output, row)


def _validate(row, payload, kind):
    if row.get("case_id") != canonical_hash(payload):
        raise ValueError("Receipt input identity changed")
    for key in ("namespace", "stratum", "index"):
        if row.get(key) != payload[key]:
            raise ValueError("Receipt metadata changed")
    if kind == "episode":
        check_receipt(row, payload)
    elif type(row["qualification"]["eligible"]) is not bool:
        raise ValueError("Qualification must be resolved; infrastructure errors block selection")


def run_jobs(
    payloads,
    output,
    *,
    kind,
    workers=4,
    case_limit_s=15.0,
    wall_limit_s=1800.0,
    qualification_records=None,
    max_new=None,
):
    if (
        kind not in ("qualification", "episode")
        or type(workers) is not int
        or not 1 <= workers <= 4
    ):
        raise ValueError("Bounded declared job kind and workers required")
    if not 0 < case_limit_s <= 60 or not 0 < wall_limit_s <= 3600:
        raise ValueError("Invalid bounded execution limits")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    markers = output / "started"
    markers.mkdir(exist_ok=True)
    payloads = list(payloads)
    if len({canonical_hash(p) for p in payloads}) != len(payloads):
        raise ValueError("Repeated input")
    pending = deque()
    preserved = 0
    for p in payloads:
        stem = f"{p['stratum']}__{p['index']:05d}"
        dest, marker = output / (stem + ".json"), markers / (stem + ".json")
        if dest.exists():
            _validate(strict_json(dest), p, kind)
            preserved += 1
        elif marker.exists():
            if strict_json(marker)["case_id"] != canonical_hash(p):
                raise ValueError("Start marker belongs to another input")
            if kind == "qualification":
                raise RuntimeError(
                    "Interrupted qualification blocks selection; no eligibility substitution"
                )
            from .execute import _missing_episode

            atomic_json(dest, _missing_episode(p, "interrupted_started_case_no_retry"))
            preserved += 1
        else:
            pending.append((p, dest, marker))
    ctx = mp.get_context("spawn")
    active = []
    started_at = time.perf_counter()
    new = 0
    stopped = False
    try:
        while pending or active:
            if time.perf_counter() - started_at >= wall_limit_s:
                stopped = True
                break
            if sum(p.stat().st_size for p in output.glob("*.json")) > 512 * 1024 * 1024:
                raise RuntimeError("Fixed receipt disk budget exceeded")
            while pending and len(active) < workers and (max_new is None or new < max_new):
                payload, dest, marker = pending.popleft()
                atomic_json(
                    marker,
                    {"case_id": canonical_hash(payload), "kind": kind, "started_at_utc": utc_now()},
                )
                qual = (
                    None
                    if qualification_records is None
                    else qualification_records[canonical_hash(payload)]
                )
                process = ctx.Process(target=_perform, args=(payload, kind, str(dest), qual))
                process.start()
                active.append((process, payload, dest, time.perf_counter()))
                new += 1
            if not active:
                break
            for job in list(active):
                process, payload, dest, launched = job
                timed_out = process.is_alive() and time.perf_counter() - launched >= case_limit_s
                if timed_out:
                    process.terminate()
                    process.join(2)
                    if process.is_alive():
                        process.kill()
                        process.join(2)
                if not process.is_alive():
                    process.join()
                    active.remove(job)
                    if not dest.exists():
                        reason = (
                            "worker_wall_timeout"
                            if timed_out
                            else "worker_failed_exit_" + str(process.exitcode)
                        )
                        if kind == "qualification":
                            raise RuntimeError("Qualification failure blocks selection: " + reason)
                        from .execute import _missing_episode

                        atomic_json(dest, _missing_episode(payload, reason))
                    _validate(strict_json(dest), payload, kind)
            time.sleep(0.01)
    finally:
        for process, _, _, _ in active:
            if process.is_alive():
                process.terminate()
                process.join(2)
                if process.is_alive():
                    process.kill()
                    process.join(2)
    complete = all((output / f"{p['stratum']}__{p['index']:05d}.json").exists() for p in payloads)
    return {
        "complete": complete,
        "new_attempts": new,
        "preserved_receipts": preserved,
        "expected": len(payloads),
        "wall_limit_reached": stopped,
        "wall_s": time.perf_counter() - started_at,
        "process_model": "fresh spawned process per case; at most four concurrently",
    }
