"""Supplemental fixed-output proof transcripts without changing the frozen auditor.

A read-only Python profile callback observes accepted leaf enclosures during a
separately labelled replay. It neither changes a local variable nor substitutes
a function. The returned original result must be byte-value equal to the first
audit result. Transcript checks reconstruct each enclosure from original boxes.
"""

from fractions import Fraction as Q
import sys
from independent_hcw_audit_v1 import certificates as core
from independent_hcw_audit_v1.arithmetic import Interval, SCALE
from independent_hcw_audit_v1.hcw import state_range
from independent_hcw_audit_v1.schema import identity, require

TRACE_SCHEMA = "sal-hcw-proof-transcript/1"


def geometric_margin(box):
    x, y = box[:2]
    corridor = (-100 - y, y + 30, 10 * x + y, -10 * x + y)
    if all(v.hi <= 0 for v in corridor):
        return {
            "component": "corridor",
            "slack_lower": str(Q(-max(v.hi for v in corridor), SCALE)),
            "slack_unit": "m_in_scaled_halfspace_inequalities",
        }
    ellipse = 9 * x.square() + 4 * (y + 30).square() - 36
    require(ellipse.hi <= 0, "Recorded leaf not contained in either region component")
    return {
        "component": "ellipse",
        "slack_lower": str(Q(-ellipse.hi, SCALE)),
        "slack_unit": "m^2_in_scaled_ellipse_inequality",
    }


def encode_box(box):
    return [[str(x.lo), str(x.hi)] for x in box]


def trace_prefix(info, command, expected, settings):
    require(sys.getprofile() is None, "Existing profiler would be displaced")
    leaves = []

    def observe(frame, event, returned):
        if event == "return" and frame.f_code is core.geometry.__code__ and returned == "contained":
            caller = frame.f_back
            if caller is not None and caller.f_code is core.check_prefix.__code__:
                value = caller.f_locals
                box = frame.f_locals["box"]
                leaves.append(
                    {
                        "hypothesis": value["index"],
                        "time_s": [str(value["a"]), str(value["b"])],
                        "state_endpoints_dyadic": encode_box(box),
                        **geometric_margin(box),
                    }
                )

    try:
        sys.setprofile(observe)
        result = core.check_prefix(
            info,
            command,
            max_cells=settings["max_cells_per_prefix"],
            min_width=Q(settings["minimum_time_width_s"]),
        )
    finally:
        sys.setprofile(None)
    require(result == expected, "Transcript replay differs from the first frozen audit result")
    trace = {
        "schema": TRACE_SCHEMA,
        "information_sha256": info.identity(),
        "command": list(map(str, command)),
        "queue_sha256": identity(info.payload()["queue"]),
        "settings": settings,
        "endpoint_scale": "2^-192",
        "state_units": ["m", "m", "m/s", "m/s"],
        "input_event_times_s": [str(Q(k, 4)) for k in range(4 * (info.D + 1) + 1)],
        "frozen_result_sha256": identity(expected),
        "frozen_result_status": expected["status"],
        "leaves": leaves,
        "first_audit_result_changed": False,
        "scope": "Fixed-output transcript expansion of unchanged R02 core; not a new policy, third numerical implementation or physical robustness margin",
    }
    verify_trace(info, command, expected, settings, trace)
    return trace


def verify_trace(info, command, expected, settings, trace):
    require(
        trace.get("schema") == TRACE_SCHEMA and trace.get("information_sha256") == info.identity(),
        "Trace input binding",
    )
    require(
        trace.get("command") == list(map(str, command))
        and trace.get("queue_sha256") == identity(info.payload()["queue"]),
        "Trace command or queue changed",
    )
    require(
        trace.get("settings") == settings
        and trace.get("frozen_result_sha256") == identity(expected)
        and trace.get("frozen_result_status") == expected["status"],
        "Trace result or settings changed",
    )
    require(
        trace.get("endpoint_scale") == "2^-192"
        and trace.get("state_units") == ["m", "m", "m/s", "m/s"],
        "Trace units",
    )
    events = [Q(k, 4) for k in range(4 * (info.D + 1) + 1)]
    require(trace.get("input_event_times_s") == list(map(str, events)), "Trace event coverage")
    seq = core.schedule(info, command)
    leaves = trace.get("leaves")
    require(type(leaves) is list and len(leaves) <= settings["max_cells_per_prefix"], "Leaf count")
    intervals = {i: [] for i in range(len(info.hypotheses))}
    for leaf in leaves:
        i = leaf.get("hypothesis")
        require(type(i) is int and i in intervals, "Leaf hypothesis index")
        a, b = map(Q, leaf["time_s"])
        require(
            leaf["time_s"] == [str(a), str(b)] and any(c <= a < b <= d for c, d, _ in seq),
            "Leaf crosses an event or has invalid time",
        )
        raw = leaf.get("state_endpoints_dyadic")
        require(
            type(raw) is list
            and len(raw) == 4
            and all(
                type(v) is list
                and len(v) == 2
                and all(type(s) is str and str(int(s)) == s for s in v)
                for v in raw
            ),
            "Noncanonical state enclosure",
        )
        claimed = tuple(Interval(int(lo), int(hi)) for lo, hi in raw)
        rebuilt = state_range(info.hypotheses[i].intervals(), seq, a, b)
        require(claimed == rebuilt, "Leaf is not the original-box full-input enclosure")
        require(
            {k: leaf.get(k) for k in ("component", "slack_lower", "slack_unit")}
            == geometric_margin(rebuilt),
            "Leaf margin differs",
        )
        intervals[i].append((a, b))
    for i, times in intervals.items():
        ordered = sorted(times)
        require(ordered == times and len(set(times)) == len(times), "Unordered/duplicate leaf")
        if expected["status"] == "verified_prefix":
            require(
                bool(times) and times[0][0] == 0 and times[-1][1] == info.D + 1,
                "Missing hypothesis coverage",
            )
            require(
                all(b == c for (_, b), (c, _) in zip(times[:-1], times[1:], strict=True)),
                "Continuous coverage gap or overlap",
            )
            report = expected["hypotheses"][i]
            require(
                report["hypothesis"] == i
                and report["complete"] is True
                and report["continuous_cells"] == len(times),
                "Original leaf accounting changed",
            )
    require(trace.get("first_audit_result_changed") is False, "Trace changes original audit")
    return {"leaves": len(leaves), "complete_containment": expected["status"] == "verified_prefix"}
