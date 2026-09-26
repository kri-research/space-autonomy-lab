"""Bounded JSON-line planner/checker service, no physical I/O."""

import argparse
import os
import platform
import resource
import secrets
import sys
from time import perf_counter_ns, process_time_ns, sleep

from iaa.types import identity

from .compute import check_action, planner
from .wire import MAX_BYTES, dumps, loads, validate_request


def peak_rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if platform.system() == "Darwin" else value * 1024)


def answer(req, role):
    validate_request(req)
    if req["operation"] != role:
        raise ValueError("Wrong worker role")
    start, cpu = perf_counter_ns(), process_time_ns()
    result, components = (planner if role == "plan" else check_action)(req["payload"])
    return dict(
        schema="iaa-execution-response/4",
        request_sha256=identity(req),
        session=req["session"],
        sequence=req["sequence"],
        role=role,
        result=result,
        result_sha256=identity(result),
        components_ns=components,
        worker_elapsed_ns=perf_counter_ns() - start,
        worker_cpu_ns=process_time_ns() - cpu,
        peak_rss_bytes=peak_rss_bytes(),
        physical_io=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("plan", "check"))
    parser.add_argument(
        "--fault", choices=("none", "stall", "exit", "truncate", "corrupt"), default="none"
    )
    args = parser.parse_args()
    session = secrets.token_hex(16)
    sys.stdout.buffer.write(
        dumps(dict(schema="iaa-worker-ready/4", role=args.role, session=session)) + b"\n"
    )
    sys.stdout.buffer.flush()
    last = -1
    while True:
        raw = sys.stdin.buffer.readline(MAX_BYTES + 2)
        if not raw:
            break
        if len(raw) > MAX_BYTES + 1 or not raw.endswith(b"\n"):
            return 2
        try:
            req = validate_request(loads(raw[:-1]))
            if req["session"] != session or req["sequence"] <= last:
                raise ValueError("Stale session or sequence")
            last = req["sequence"]
            if args.fault == "stall":
                sleep(2)
            if args.fault == "exit":
                os._exit(3)
            if args.fault == "truncate":
                sys.stdout.buffer.write(b'{"partial":')
                sys.stdout.buffer.flush()
                return 3
            response = answer(req, args.role)
            if args.fault == "corrupt":
                response["result_sha256"] = "0" * 64
        except Exception as exc:
            response = dict(schema="iaa-worker-error/4", error=type(exc).__name__)
        sys.stdout.buffer.write(dumps(response) + b"\n")
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
