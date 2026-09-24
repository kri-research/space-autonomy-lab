"""Retained calibration using only identified, already exposed development inputs."""

from pathlib import Path
from collections import Counter
import time
import hashlib
import platform
import resource
from .schema import strict_json, identity
from .jobs import execute

ROOT = Path(__file__).resolve().parent
SETTINGS = {"max_cells_per_prefix": 16384, "minimum_time_width_s": "1/65536"}


def run():
    jobs = strict_json((ROOT / "development_cases.json").read_bytes())
    rows = []
    started = time.perf_counter()
    for job in jobs:
        before, cpu = time.perf_counter(), time.process_time()
        result = execute(job, SETTINGS)
        rows.append(
            {
                "job": job["key"],
                "input_sha256": identity(job),
                "result": result,
                "wall_s": time.perf_counter() - before,
                "cpu_s": time.process_time() - cpu,
            }
        )
    failures = [
        r["job"]
        for r in rows
        if r["result"]["claim"]["status"] in ("binding_invalid_evidence", "contradicted_prefix")
    ]
    return {
        "schema": "sal-independent-hcw-development/1",
        "passed": not failures,
        "jobs": len(rows),
        "rows": rows,
        "statuses": dict(Counter(r["result"]["claim"]["status"] for r in rows)),
        "hard_failures": failures,
        "maximum_job_wall_s": max(r["wall_s"] for r in rows),
        "total_wall_s": time.perf_counter() - started,
        "maximum_rss_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "platform": platform.system() + " " + platform.machine(),
        "python": platform.python_version(),
        "settings": SETTINGS,
        "input_sha256": hashlib.sha256((ROOT / "development_cases.json").read_bytes()).hexdigest(),
        "protected_cases_numerically_audited": 0,
        "timings_are_not_wcet": True,
    }
