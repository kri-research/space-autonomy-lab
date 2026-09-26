"""Planner proposals and a smaller realized-action checker with shared mathematics.

The checker reconstructs SA02 uncertainty from input receipts. It does not trust
planner trees, state boxes or certificate flags. The observer and rational flow
remain in the trusted computing base; process separation is not a new proof.
"""

from fractions import Fraction as Q
from time import perf_counter_ns

from iaa.enclosure import inside, separated, step
from iaa.types import Command, identity, millis, primitive, rational
from sa02.bridge import ALLOWED
from sa02.estimator import Observer
from sa02.model import validate_history
from sa03.model import Context
from sa03.policy import decide

from . import wire

ZERO = (Q(0), Q(0))
INPUT_KEYS = ("initial", "sensors", "packets", "history", "at_ms", "queued_action", "timing")


def unpack(raw):
    wire.exact(raw, INPUT_KEYS)
    box, sensor = wire.initial(raw["initial"]), wire.sensors(raw["sensors"])
    pk, hist, timing = (
        wire.packets(raw["packets"]),
        wire.history(raw["history"]),
        wire.timing(raw["timing"]),
    )
    now = millis(raw["at_ms"])
    if not 100 <= now <= 700:
        raise ValueError("Snapshot outside supported decision interval")
    validate_history(hist, now)
    queue = Command(
        tuple(wire.number(v) for v in raw["queued_action"]), 100, 200, "queue"
    ).acceleration
    # Applied history after the initial snapshot must agree with this loaded queue.
    for segment in hist:
        for a, b, u in ((100, 200, queue), (200, now, ZERO)):
            if max(a, segment.start_ms) < min(b, segment.end_ms) and segment.action != u:
                raise ValueError("Applied and queued command history disagree")
    if any(p.available_ms > now for p in pk):
        raise ValueError("Undelivered observation crossed execution boundary")
    return box, sensor, pk, hist, timing, queue


def estimate(raw):
    box, sensor, pk, hist, timing, queue = unpack(raw)
    out = Observer(box, sensor).update(pk, hist, raw["at_ms"])
    return out, sensor, timing, queue


def planner(payload):
    wire.exact(payload, ("input", "method"))
    raw = payload["input"]
    if raw["at_ms"] != 100 or payload["method"] not in ("uncertainty_triggered", "decision_aware"):
        raise ValueError("Planner snapshot or method")
    start = perf_counter_ns()
    out, sensors, timing, queue = estimate(raw)
    update_ns = perf_counter_ns() - start
    context = Context(out, sensors, timing, queued_action=queue)
    start = perf_counter_ns()
    result = decide(context, payload["method"])
    planning_ns = perf_counter_ns() - start
    cert = result["certificate"]
    # This is an untrusted proposal menu, not an exported authority token.
    proposal = dict(
        status=result["status"],
        channel=cert["channel"] if cert else None,
        fallback=cert["no_observation"]["action"] if cert else ZERO,
        leaves=[],
        context_sha256=context.identity(),
        initial_estimate_sha256=out.identity(),
        operations=result["operations"],
        model_cost_mj=result["modeled_cost_mj"],
    )
    if cert:
        proposal["leaves"] = [
            dict(low=x["reading"].lo, high=x["reading"].hi, action=x["result"]["action"])
            for x in cert["leaves"]
            if x["result"]
        ]
    return primitive(proposal), dict(uncertainty_update_ns=update_ns, planner_ns=planning_ns)


def proposal_action(proposal, receipts):
    """Only propose; the actual packet/history is rechecked by the checker."""
    selected = tuple(map(rational, proposal["fallback"]))
    matching = [p for p in receipts if p.channel == proposal["channel"]]
    if len(matching) == 1:
        value = rational(matching[0].value)
        for leaf in proposal["leaves"]:
            if rational(leaf["low"]) <= value <= rational(leaf["high"]):
                selected = tuple(map(rational, leaf["action"]))
                break
    Command(selected, 700, 1200, "proposal")
    return selected


def schedule_check(box, schedule):
    """Enclose continuous trajectories and arbitrary switching in the 10 ms band."""
    if not inside(box) or not separated(box):
        return False, 0
    steps = 0
    for start, end, action, eta in schedule:
        t = start
        while t < end:
            dt = min(50, end - t)
            box, tube = step(box, action, dt, eta)
            steps += 1
            if steps > 1000:
                raise ValueError("Checking work limit")
            if not inside(tube) or not separated(tube):
                return False, steps
            t += dt
    return True, steps


def future_schedule(now, queue, action):
    rows = []
    for start, end, u, eta in (
        (100, 200, queue, (Q(4, 5), Q(1))),
        (200, 700, ZERO, (Q(4, 5), Q(1))),
        (700, 710, action, (Q(0), Q(1))),
        (710, 1200, action, (Q(4, 5), Q(1))),
        (1200, 4200, ZERO, (Q(4, 5), Q(1))),
    ):
        if end > now:
            rows.append((max(start, now), end, u, eta))
    return rows


def initial_arm(raw):
    """Offline preload for a future simulated episode, never a live-state freeze."""
    box, _, _, hist, _, queue = unpack(raw)
    if raw["at_ms"] != 100:
        raise ValueError("Initial arming snapshot")
    rows = [(s.start_ms, s.end_ms, s.action, (Q(4, 5), Q(1))) for s in hist]
    rows += future_schedule(100, queue, ZERO)
    valid, steps = schedule_check(box, rows)
    return dict(
        schema="iaa-prearm/4",
        valid=valid,
        initial_input_sha256=identity(raw),
        model_sha256=identity(wire.MODEL),
        expires_ms=4200 if valid else 0,
        steps=steps,
        offline_simulation_initialization=True,
    )


def binding(payload):
    raw = payload["input"]
    return dict(
        payload_sha256=identity(payload),
        observations_sha256=identity(raw["packets"]),
        history_sha256=identity(raw["history"]),
        sensors_sha256=identity(raw["sensors"]),
        model_sha256=identity(wire.MODEL),
        input_sha256=identity(raw),
        at_ms=raw["at_ms"],
        action=primitive(payload["action"]),
        application_window_ms=[700, 710],
        command_end_ms=1200,
        expires_ms=4200,
    )


def check_action(payload):
    wire.exact(payload, ("input", "action"))
    raw = payload["input"]
    action = Command(
        tuple(wire.number(v) for v in payload["action"]), 700, 1200, "checked"
    ).acceleration
    start = perf_counter_ns()
    out, _, _, queue = estimate(raw)
    update_ns = perf_counter_ns() - start
    valid = out.status in ALLOWED and bool(out.cells)
    start = perf_counter_ns()
    safe, steps = (
        schedule_check(out.hull(), future_schedule(raw["at_ms"], queue, action))
        if valid
        else (False, 0)
    )
    check_ns = perf_counter_ns() - start
    result = dict(
        schema="iaa-action-check/4",
        binding=binding(payload),
        status="checked_window_prefix" if safe else "unresolved",
        uncertainty=primitive(out),
        uncertainty_sha256=out.identity(),
        steps=steps,
        scope="HCW_variable_start_fixed_end_three_second_coast",
        full_recovery=False,
        physical_validation=False,
    )
    return result, dict(uncertainty_update_ns=update_ns, checking_ns=check_ns)
