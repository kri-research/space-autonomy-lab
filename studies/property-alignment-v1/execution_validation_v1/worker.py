"""Portable line-delimited JSON service with no physical device access."""

import sys
import time
from .protocol import strict_load, encode, identity, validate_request
from .adapters import prepare, decide_prepared, validate_prediction


def service(req):
    start = time.perf_counter_ns()
    cpu_start = time.process_time_ns()
    value, delay, authority = prepare(req)
    policy_start = time.perf_counter_ns()
    prediction = decide_prepared(req, value)
    policy_end = time.perf_counter_ns()
    result = validate_prediction(req, prediction, authority)
    finish = time.perf_counter_ns()
    return {
        "schema": "sal-execution-response/1",
        "id": req["id"],
        "sequence": req["sequence"],
        "request_sha256": identity(req),
        "domain": req["domain"],
        "method": req["method"],
        "model_delay_ns": int(delay * 1000000000),
        "result": result,
        "timing": {
            "service_start_ns": start,
            "policy_start_ns": policy_start,
            "policy_end_ns": policy_end,
            "service_end_ns": finish,
            "process_cpu_ns": time.process_time_ns() - cpu_start,
        },
        "clock": "perf_counter_ns",
        "evidence_level": "host_computer_timing",
        "physical_actuation": False,
    }


def main():
    # Import both adapters before the ready handshake; cold startup is separately measured.

    print(
        encode(
            {"ready": True, "schema": "sal-execution-service/1", "physical_backend": False}
        ).decode(),
        flush=True,
    )
    last = -1
    for raw in sys.stdin.buffer:
        try:
            req = validate_request(strict_load(raw))
            if req["sequence"] <= last:
                raise ValueError("Nonincreasing request sequence")
            last = req["sequence"]
            response = service(req)
        except Exception as exc:
            response = {
                "schema": "sal-execution-error/1",
                "error_type": type(exc).__name__,
                "physical_actuation": False,
            }
        sys.stdout.buffer.write(encode(response) + b"\n")
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
