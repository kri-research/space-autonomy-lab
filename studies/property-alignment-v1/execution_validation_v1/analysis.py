"""Descriptive host timing and an explicit separation from physical delay bounds."""

from pathlib import Path
from collections import Counter
import json
from .protocol import identity, delay_compatibility


def stats(xs):
    if not xs:
        return {"n": 0}
    if any(type(x) is not int or x < 0 for x in xs):
        raise ValueError("Nanosecond samples must be nonnegative integers")
    ys = sorted(xs)

    def q(p):
        pos = (len(ys) - 1) * p
        i = int(pos)
        j = min(i + 1, len(ys) - 1)
        return ys[i] + (pos - i) * (ys[j] - ys[i])

    return {
        "n": len(xs),
        "minimum_ns": min(xs),
        "median_ns": q(0.5),
        "p95_ns": q(0.95),
        "maximum_ns": max(xs),
        "mean_ns": sum(xs) / len(xs),
        "inverse_mean_roundtrip_hz": 1e9 / (sum(xs) / len(xs)) if sum(xs) > 0 else None,
        "maximum_is_wcet": False,
    }


def validate_sample(row):
    req = row["request"]
    reply = row["response"]
    pt = row["parent_timing"]
    ct = reply["timing"]
    if reply["request_sha256"] != identity(req) or reply["id"] != req["id"]:
        raise ValueError("Sample binding")
    times = [
        pt["request_start_ns"],
        pt["encoded_ns"],
        pt["written_ns"],
        pt["received_ns"],
        pt["validated_ns"],
    ]
    service = [
        ct[k] for k in ("service_start_ns", "policy_start_ns", "policy_end_ns", "service_end_ns")
    ]
    if (
        any(type(x) is not int or x < 0 for x in times + service)
        or times != sorted(times)
        or service != sorted(service)
    ):
        raise ValueError("Clock sample order")
    if not times[0] <= service[0] <= service[-1] <= times[-1]:
        raise ValueError("Same-host clock order")
    if pt["roundtrip_ns"] != times[-1] - times[0]:
        raise ValueError("Roundtrip mismatch")
    if row["delay_assessment"] != delay_compatibility(pt["roundtrip_ns"], reply["model_delay_ns"]):
        raise ValueError("Delay meaning changed")
    if row["host_service_budget_exceeded"] is not (pt["roundtrip_ns"] > 1000000000):
        raise ValueError("Budget mismatch")
    if row["physical_actuation"] is not False or row["evidence_level"] != "host_computer_timing":
        raise ValueError("Unsupported evidence level")
    return row


def summarize_directory(output, frozen):
    from .harness import requests

    output = Path(output)
    allrows = []
    groups = []
    clocks = []
    for session in range(frozen["plan"]["sessions"]):
        dest = output / f"session{session:02d}"
        schedule = requests(frozen["plan"], session)
        expected = {x["request"]["id"] + ".json" for x in schedule}
        if {p.name for p in (dest / "samples").glob("*.json")} != expected:
            raise ValueError("Incomplete planned membership")
        rows = [
            validate_sample(
                json.loads((dest / "samples" / (x["request"]["id"] + ".json")).read_text())
            )
            for x in schedule
        ]
        for row, spec in zip(rows, schedule, strict=True):
            if any(row[k] != v for k, v in spec.items()):
                raise ValueError("Session scheduling changed")
        allrows += rows
        clock = json.loads((dest / "clock.json").read_text())
        clocks.append(
            {
                "session": session,
                **{k: v for k, v in clock.items() if k != "back_to_back_ns"},
                "clock_pair_diagnostics": stats(clock["back_to_back_ns"]),
            }
        )
        for a in frozen["plan"]["adapters"]:
            subset = [
                r
                for r in rows
                if r["phase"] == "measured" and all(r["request"][k] == v for k, v in a.items())
            ]
            values = [r["parent_timing"]["roundtrip_ns"] for r in subset]
            groups.append(
                {
                    "session": session,
                    **a,
                    "roundtrip": stats(values),
                    "policy": stats(
                        [
                            r["response"]["timing"]["policy_end_ns"]
                            - r["response"]["timing"]["policy_start_ns"]
                            for r in subset
                        ]
                    ),
                    "statuses": dict(Counter(r["response"]["result"]["status"] for r in subset)),
                    "service_overruns": sum(r["host_service_budget_exceeded"] for r in subset),
                    "application_window_shortfalls": sum(
                        r["delay_assessment"]["status"] == "incompatible_host_lower_bound"
                        for r in subset
                    ),
                    "unknown_physical_timing": len(subset),
                }
            )
    measured = [r for r in allrows if r["phase"] == "measured"]
    if (
        len(measured) != frozen["plan"]["measured_requests"]
        or len(allrows) - len(measured) != frozen["plan"]["warmup_requests"]
    ):
        raise ValueError("Planned denominator")
    return {
        "schema": "sal-host-measurement-summary/1",
        "id": frozen["id"],
        "sessions": len(clocks),
        "warmup_samples": len(allrows) - len(measured),
        "measured_samples": len(measured),
        "groups": groups,
        "clock_diagnostics": clocks,
        "all_requests_accounted_for": True,
        "timing_contradictions_to_zero_or_short_application_windows": sum(
            r["delay_assessment"]["status"] == "incompatible_host_lower_bound" for r in measured
        ),
        "host_service_budget_misses": sum(r["host_service_budget_exceeded"] for r in measured),
        "physical_sensor_delays_measured": False,
        "physical_actuator_delays_measured": False,
        "physical_trials": 0,
        "external_reviews": 0,
        "uncertainty": "Repeated host rounds are correlated; clock resolution is not calibrated accuracy. No timing error bound from an independent time reference is available. No IID uncertainty interval or flight inference.",
        "interpretation": "A literal zero queued interval cannot include positive measured software latency. Longer windows remain conditional on unmeasured sensor/actuator/alignment bounds. Early replies must be queued until the modeled application instant; no early or late physical application is authorized.",
    }
