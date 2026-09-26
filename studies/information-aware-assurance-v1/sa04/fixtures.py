"""Exposed SA04 integration fixtures, distinct from prior stored outcomes."""

from copy import deepcopy
from fractions import Fraction as Q

from iaa.enclosure import inside, step
from iaa.plant import SensorFaults, flow, observe
from iaa.types import identity, primitive
from sa02.model import HistorySegment
from sa03.development import Case, clean_sensors
from sa03.model import Timing

from .compute import check_action, initial_arm, planner, proposal_action
from .gate import Gate
from .trace import audit, seal

METHODS = ("uncertainty_triggered", "decision_aware")
FAULTS = (
    "nominal",
    "sensor_loss",
    "late_planner",
    "planner_failure",
    "checker_failure",
    "late_checker",
    "checker_channel_corrupt",
    "missed_application_window",
    "window_jitter",
    "settings_changed",
    "acknowledgement_loss",
    "unsupported_sensor_clock",
    "unsafe_initial",
    "unmodelled_sensor_bias",
    "already_adequate",
    "actuator_saturation",
)


def initial_input(kind="ambiguity"):
    case = Case("sa04-context")
    if kind == "adequate":
        case = Case(
            "sa04-context",
            prior_radii=(Q(1, 100), Q(1, 100), Q(1, 10000), Q(1, 10000)),
            actual_initial=(0, -40, 0, 0),
        )
    elif kind == "unsafe":
        case = Case(
            "sa04-context",
            prior_centre=(0, Q(-3003, 100), 0, Q(1, 4)),
            prior_radii=(Q(1, 100000),) * 4,
            actual_initial=(0, Q(-3003, 100), 0, Q(1, 4)),
        )
    raw = dict(
        initial=primitive(case.initial_box()),
        sensors=primitive(clean_sensors()),
        packets=[],
        history=primitive((HistorySegment(0, 100, (0, 0)),)),
        at_ms=100,
        queued_action=["0", "0"],
        timing=primitive(Timing()),
    )
    return raw, case.actual_initial


def at_time(raw, now, receipts):
    result = deepcopy(raw)
    history = [HistorySegment(0, 100, (0, 0))]
    if now > 100:
        history.append(HistorySegment(100, min(now, 200), tuple(raw["queued_action"])))
    if now > 200:
        history.append(HistorySegment(200, now, (0, 0)))
    result.update(
        at_ms=now,
        history=primitive(history),
        packets=deepcopy(raw["packets"]) + primitive(receipts),
    )
    return result


def delivered_packet(raw, actual_initial, channel, fault="nominal"):
    if not channel or fault == "sensor_loss":
        return ()
    x = flow(actual_initial, (0, 0), 0.25)
    packets, _ = observe(
        x,
        250,
        1,
        SensorFaults(start_ms=0, range_bias_m=0.5 if fault == "unmodelled_sensor_bias" else 0),
    )
    from dataclasses import replace

    return tuple(
        replace(
            p,
            value=round(p.value, 12),
            timestamp_uncertainty_ms=100 if fault == "unsupported_sensor_clock" else 2,
        )
        for p in packets
        if p.channel == channel
    )


def run(fault="nominal", method="uncertainty_triggered"):
    if fault not in FAULTS or method not in METHODS:
        raise ValueError("Unknown fixed engineering fixture")
    raw, truth0 = initial_input(
        "unsafe"
        if fault == "unsafe_initial"
        else "adequate"
        if fault == "already_adequate"
        else "ambiguity"
    )
    arm = initial_arm(raw)
    gate = Gate(raw, arm)
    events = []

    def log(t, event, data):
        events.append(dict(at_ms=t, event=event, data=primitive(data)))

    log(100, "initial", dict(input=raw, arm=arm))
    plan, _ = planner(dict(input=raw, method=method))
    ready = 151 if fault == "late_planner" else 145
    plan_ok = ready <= 150 and fault != "planner_failure" and arm["valid"]
    log(ready, "planner", dict(proposal=plan, accepted_for_sensing=plan_ok, measured=False))
    channel = plan["channel"] if plan_ok else None
    receipts = delivered_packet(raw, truth0, channel, fault)
    if channel:
        log(150, "sensor_request", dict(channel=channel, acquire_ms=250, assumed_delay=True))
    for p in receipts:
        log(p.available_ms, "observation", primitive(p))
    payload = dict(
        input=at_time(raw, 650, receipts), action=primitive(proposal_action(plan, receipts))
    )
    result, _ = check_action(payload)
    check_ready = 701 if fault == "late_checker" else 675
    if plan_ok and fault != "checker_failure":
        log(650, "check_input", payload)
        log(check_ready, "check_result", result)
        # The channel status is supplied by the actual transport wrapper in host use.
        ok = fault != "checker_channel_corrupt"
        outcome = dict(scheduled=False, reasons=["not_yet_arrived"])
    else:
        outcome = dict(scheduled=False, reasons=["planner_or_checker_unavailable"])
        log(650, "component_failure", dict(reason=outcome["reasons"][0]))
    invalidation_at = (
        690 if fault == "settings_changed" else 701 if fault == "acknowledgement_loss" else None
    )
    if fault == "actuator_saturation":
        invalidation_at = 705
    ticks = list(range(100, 4301, 10))
    if fault == "window_jitter":
        ticks.remove(700)
        ticks.append(705)
    if fault == "missed_application_window":
        ticks.remove(700)
        ticks.remove(710)
    if invalidation_at is not None:
        ticks.append(invalidation_at)
    if plan_ok and fault != "checker_failure":
        ticks.append(check_ready)
    last_t, truth, evaluation, last_action = 0, tuple(truth0), None, (Q(0), Q(0))
    from iaa.types import StateBox

    evaluation = StateBox.around(truth0, (0, 0, 0, 0))
    contained, ticks_out = True, []
    for t in sorted(set(ticks)):
        remaining = t - last_t
        while remaining:
            dt = min(10, remaining)
            truth = flow(truth, last_action, dt / 1000)
            evaluation, tube = step(evaluation, last_action, dt, (Q(1), Q(1)), Q(0))
            contained &= inside(tube)
            remaining -= dt
        if t == check_ready and plan_ok and fault != "checker_failure":
            outcome = gate.admit(result, payload, t, checker_channel_ok=ok)
            log(t, "admission", dict(outcome=outcome, checker_channel_ok=ok))
        if t == invalidation_at:
            gate.invalidate()
            log(t, "invalidate", dict(reason=fault))
        tick = gate.tick(
            t,
            live_binding_sha256=identity(payload)
            if t >= 650 and plan_ok and fault != "checker_failure"
            else None,
        )
        ticks_out.append(tick)
        log(t, "command", tick)
        if tick["newly_applied"]:
            log(
                t,
                "acknowledgement",
                dict(
                    action=tick["action"], physical=False, received=fault != "acknowledgement_loss"
                ),
            )
        last_action = tuple(Q(v) for v in tick["action"])
        last_t = t
        if t % 100 == 0:
            log(
                t,
                "consequence",
                dict(
                    state=[round(v, 12) for v in truth],
                    physical_feedback=False,
                    evaluator_only=True,
                    continuous_model_containment=bool(contained),
                ),
            )
    log(4300, "end", dict(after_protection_expiry=True))
    trace = seal(events)
    errors = audit(trace)
    if errors:
        raise ValueError("Trace self-audit failed: " + str(errors))
    summary = dict(
        fault=fault,
        method=method,
        initial_protection=arm["valid"],
        candidate_admitted=outcome["scheduled"],
        request=channel,
        applied_times=[r["at_ms"] for r in ticks_out if r["newly_applied"]],
        continuous_realized_model_containment=bool(contained),
        terminal_uncredited=not ticks_out[-1]["credited"],
        observation_contract_deliberately_violated=fault == "unmodelled_sensor_bias",
        trace_terminal=trace["terminal"],
        simulation_only=True,
        physical_validation=False,
    )
    return summary, trace
