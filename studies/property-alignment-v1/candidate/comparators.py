"""Preserved Task05 baselines with an explicit conservative information adapter.
No baseline control equation or certificate is modified. A hull representation
and a longer-horizon guarantee are genuine differences from a one-step test.
"""

from fractions import Fraction as Q
import time
import numpy as np
from adjudication.flow import Model, propagate_schedule
from adjudication.interval import Box, Interval
from protective.common import Information, Tube, NUMERIC_COMPONENT
from protective.predictive import PredictiveFilter
from protective.barrier import BarrierFilter
from .certify import realized, certify_action


def center_error(box):
    center = []
    error = []
    for v in box.coordinates:
        mid = float((Q(v.lo) + Q(v.hi)) / 2)
        radius = max(Q(mid) - Q(v.lo), Q(v.hi) - Q(mid))
        center.append(mid)
        error.append(float(Interval.point(radius).hi))
    return np.array(center), np.array(error)


def at_time(info, t):
    boxes = []
    for hypothesis in info.hypotheses:
        if t == 0:
            boxes.append(hypothesis.enclosure())
            continue
        segments = []
        for k, u in enumerate(info.queue[:t]):
            for j in range(4):
                a = Q(k) + Q(j, 4)
                segments.append((a, a + Q(1, 4), realized(info, u)))
        arcs = propagate_schedule(Model("hcw"), hypothesis.enclosure(), segments)
        boxes.append(arcs[-1].point(t))
    return Box(
        tuple(
            Interval(
                min(b.coordinates[j].lo for b in boxes), max(b.coordinates[j].hi for b in boxes)
            )
            for j in range(4)
        )
    )


def compare(info, proposal=(0.0, 0.0)):
    if info.effectiveness != (Q(1), Q(1)) or info.authority != Q(1, 50):
        return {"status": "unsupported_native_actuation_bounds", "not_a_baseline_failure": True}
    if info.kind != "declared_exact_information_set":
        return {"status": "unsupported_information_semantics", "not_a_baseline_failure": True}
    started = time.perf_counter()
    current = at_time(info, info.age)
    future = at_time(info, info.application_time)
    estimate, error = center_error(future)
    now, now_error = center_error(current)
    sensor_center, sensor = center_error(info.hull().enclosure())
    tube = Tube(sensor, float(info.disturbance) + NUMERIC_COMPONENT)
    pending = tuple(
        (j, j + 1, [float(x) for x in info.queue[j]])
        for j in range(info.age, info.application_time)
    )
    packet = Information(
        info.age, info.application_time, estimate, error, True, now, now_error, pending
    )
    adapter_s = time.perf_counter() - started
    rows = {}
    for name, method in [
        (
            "predictive",
            PredictiveFilter(tube, horizon=180, solver_time_limit=0.2, decision_limit=1.0),
        ),
        (
            "barrier",
            BarrierFilter(tube, rates=(0.04, 0.08), solver_time_limit=0.2, decision_limit=1.0),
        ),
    ]:
        start = time.perf_counter()
        result = method.decide(packet, np.asarray(proposal, float))
        rows[name] = {
            "status": result.status,
            "protected": bool(result.protected),
            "command": None if result.command is None else result.command.tolist(),
            "details": result.details,
            "policy_wall_s": time.perf_counter() - start,
            "setup_s": method.setup_wall_s,
            "terminal_domain_valid": bool(tube.valid_terminal),
        }
        if result.command is not None:
            rows[name]["separate_prefix_check"] = certify_action(
                info, tuple(map(float, result.command))
            )
    return {
        "status": "evaluated_with_declared_hull_adapter",
        "methods": rows,
        "adapter_s": adapter_s,
        "adapter_uses_truth": False,
        "incoming_exact_hypotheses": len(info.hypotheses),
        "native_information_error": error.tolist(),
        "scope": "single decision, unchanged native guarantees; prefix availability is not superiority over recovery certification",
    }
