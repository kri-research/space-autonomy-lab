"""Bounded non-actuating host measurement using public integration inputs.

One warm-up and two measured repetitions per input, all retained. This describes
an originating-process host, not an external evaluation, spacecraft or WCET proof.
"""

import json
import platform
import resource
import sys
from pathlib import Path
from time import get_clock_info, perf_counter_ns, process_time_ns

from .api import assess
from .examples import examples
from .integrity import verify_installation


def run(output):
    output = Path(output).expanduser()
    if output.exists() or any((p / ".git").exists() for p in (output, *output.resolve().parents)):
        raise ValueError("New output outside checkouts required")
    provenance = verify_installation()
    design = dict(
        warmups=1,
        repetitions=2,
        input_names=[r["name"] for r in examples()],
        purpose="installation and bounded interface profiling",
        energy_measured=False,
    )
    record = dict(
        schema="kri-assurance-host/1",
        source_commit=provenance["source_commit"],
        development_build=provenance["development_build"],
        protocol=design,
        environment=dict(
            python=sys.version.split()[0],
            os=platform.system(),
            architecture=platform.machine(),
            clock=vars(get_clock_info("perf_counter")),
        ),
        samples=[],
        physical_validation=False,
        target_validation=False,
        external_replication=False,
        timings_are_WCET=False,
    )
    with output.open("x") as f:
        # Preserve complete or interrupted execution, without retrying failed cells.
        try:
            for repetition in range(-1, 2):
                for item in examples():
                    start, cpu = perf_counter_ns(), process_time_ns()
                    outcome = assess(item["request"])
                    cpu_ns, wall_ns = process_time_ns() - cpu, perf_counter_ns() - start
                    record["samples"].append(
                        dict(
                            name=item["name"],
                            repetition=repetition,
                            warmup=repetition < 0,
                            result=outcome,
                            elapsed_ns=wall_ns,
                            cpu_ns=cpu_ns,
                            expected_status_matched=outcome["status"] == item["expected_status"],
                            process_peak_rss_bytes=resource.getrusage(
                                resource.RUSAGE_SELF
                            ).ru_maxrss
                            * (1 if sys.platform == "darwin" else 1024),
                        )
                    )
            record["complete"] = True
        except Exception as exc:
            record["complete"] = False
            record["error"] = type(exc).__name__
            raise
        finally:
            json.dump(record, f, sort_keys=True, indent=2)
            f.write("\n")
    return record
