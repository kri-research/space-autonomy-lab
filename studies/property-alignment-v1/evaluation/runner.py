"""Write-once evaluation runner with resumable, deterministic case receipts."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import hashlib
import json
import os
import platform
import time

from .episode import run_case
from .generator import STRATA, case_payload
from .qualification import qualification
from candidate.information import Hypothesis, InformationSet
from fractions import Fraction as Q


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def read_json(path):
    return json.loads(Path(path).read_text())


def _information(payload):
    doc = payload["information"]
    return InformationSet(
        tuple(Hypothesis(tuple(x["lower"]), tuple(x["upper"])) for x in doc["hypotheses"]),
        age=doc["age"],
        delay=doc["delay"],
        queue=tuple(tuple(v for v in row) for row in doc["queue"]),
        authority=Q(doc["authority"]),
        effectiveness=tuple(Q(v) for v in doc["effectiveness"]),
        disturbance=Q(doc["disturbance"]),
        kind=doc["kind"],
        units=tuple(doc["units"]),
    )


def qualification_receipt(payload):
    return {
        "case_id": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "namespace": payload["namespace"],
        "stratum": payload["stratum"],
        "index": payload["index"],
        "qualification": qualification(_information(payload)),
    }


def _episode_worker(args):
    payload, include_native = args
    return run_case(payload, include_native_baselines=include_native)


def environment():
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "workers_environment": os.environ.get("SAL_EVAL_WORKERS"),
        "openblas_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
        "physical_validation": False,
    }


def _run_payloads(payloads, output, workers=1, include_native=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cases = output / "cases"
    cases.mkdir()
    started = time.perf_counter()
    results = []
    jobs = [(payload, include_native) for payload in payloads]
    if workers == 1:
        iterable = ((_episode_worker(job), job[0]) for job in jobs)
        for result, payload in iterable:
            path = cases / f"{payload['stratum']}__{payload['index']:05d}.json"
            write_json(path, result)
            results.append(result)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(_episode_worker, job): job[0] for job in jobs}
            for future in as_completed(future_map):
                payload = future_map[future]
                result = future.result()
                path = cases / f"{payload['stratum']}__{payload['index']:05d}.json"
                write_json(path, result)
                results.append(result)
    results.sort(key=lambda row: (STRATA.index(row["stratum"]), row["index"]))
    manifest = {
        path.relative_to(output).as_posix(): sha(path)
        for path in sorted(output.rglob("*.json"))
        if path.name not in {"manifest.json", "summary.json"}
    }
    write_json(output / "manifest.json", manifest)
    summary = {
        "schema": "sal-evaluation-run-summary/1",
        "cases": len(results),
        "eligible": sum(row["primary"]["eligible"] for row in results),
        "on_time_decisive_valid": sum(row["primary"]["on_time_decisive_valid"] for row in results),
        "statuses": {
            status: sum(row["candidate"]["status"] == status for row in results)
            for status in sorted({row["candidate"]["status"] for row in results})
        },
        "per_stratum": {
            stratum: {
                "cases": sum(row["stratum"] == stratum for row in results),
                "eligible": sum(
                    row["stratum"] == stratum and row["primary"]["eligible"] for row in results
                ),
                "on_time_decisive_valid": sum(
                    row["stratum"] == stratum and row["primary"]["on_time_decisive_valid"]
                    for row in results
                ),
            }
            for stratum in STRATA
        },
        "maximum_episode_wall_s": max((row["episode_wall_s"] for row in results), default=0.0),
        "total_wall_s": time.perf_counter() - started,
        "environment": environment(),
    }
    write_json(output / "summary.json", summary)
    return summary


def run_fixed_namespace(namespace, count_per_stratum, output, workers=1, include_native=True):
    payloads = [
        case_payload(namespace, stratum, index)
        for stratum in STRATA
        for index in range(count_per_stratum)
    ]
    return _run_payloads(payloads, output, workers=workers, include_native=include_native)
