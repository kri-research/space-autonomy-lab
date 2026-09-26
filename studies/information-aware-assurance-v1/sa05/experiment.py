"""Matched finite-manoeuvre trial. Truth is confined to plant/sensor evaluation.

Planning and checks use existing code without modifying it. Clock durations are
explicit simulation assumptions. Measured compute duration does not retime physics.
"""

import math
import resource
import sys
from fractions import Fraction as Q
from time import perf_counter_ns, process_time_ns

from iaa.types import ObservationPacket, StateBox, identity, primitive
from sa02.intervals import Interval, interval
from sa02.model import FaultHypothesis, HistorySegment, SensorContract
from sa03.model import Context, Timing
from sa03.policy import decide
from sa04.compute import check_action, estimate, initial_arm, proposal_action
from sa04.fixtures import at_time
from sa04.gate import Gate

from .design import METHODS
from .dynamics import NUMERIC_POSITION_M, NUMERIC_VELOCITY_MPS, Plant, numerical_adjudication


def sensors(stratum):
    zero = interval(0)
    hypotheses = (FaultHypothesis("no_bias", (zero,) * 4),)
    if stratum != "nominal":
        full = (Interval(-Q(1, 2), Q(1, 2)),) * 2 + (
            Interval(-Q(2, 5), Q(2, 5)),
            Interval(-Q(1, 50), Q(1, 50)),
        )
        hypotheses += (FaultHypothesis("persistent_shared_and_channels", full),)
    return SensorContract(hypotheses=hypotheses, initial_splits=0)


def packet(case, state, channel, epoch):
    if channel is None or (epoch == 250 and case[channel + "_lost"]):
        return ()
    cx, cy, br, bb = map(lambda x: float(Q(x)), case["biases"])
    x, y = state[0] + cx, state[1] + cy
    noise = float(Q(case["measurement_noise"][f"{channel}-{epoch}"]))
    value = math.hypot(x, y) + br + noise if channel == "range" else math.atan2(y, x) + bb + noise
    if channel == "bearing":
        value = (value + math.pi) % (2 * math.pi) - math.pi
    # Quantization is deliberately below the declared total error, including encoding.
    value = round(value, 5 if channel == "range" else 8)
    return (
        ObservationPacket(
            f"{case['unit']}-{channel}-{epoch}",
            epoch,
            channel,
            value,
            epoch + (case["timestamp_offset_ms"] if epoch else 0),
            epoch + (40 if channel == "range" else 70),
            2,
            "m" if channel == "range" else "rad",
        ),
    )


def plan(raw, method):
    if method not in METHODS:
        raise ValueError("Unknown matched comparator")
    out, contract, timing, queue = estimate(raw)
    context = Context(
        out,
        contract,
        timing,
        queued_action=queue,
        resource_mj=500,
        max_operations=50000,
        max_nodes=255,
    )
    result = decide(context, method)
    cert = result["certificate"]
    proposal = dict(
        status=result["status"],
        channel=cert["channel"] if cert else None,
        fallback=cert["no_observation"]["action"] if cert else (Q(0), Q(0)),
        leaves=[],
        context_sha256=context.identity(),
        operations=result["operations"],
        model_cost_mj=result["modeled_cost_mj"],
    )
    if cert:
        proposal["leaves"] = [
            dict(low=x["reading"].lo, high=x["reading"].hi, action=x["result"]["action"])
            for x in cert["leaves"]
            if x["result"]
        ]
    return primitive(proposal), primitive(result), primitive(out)


def run(case, method):
    start, cpu_start = perf_counter_ns(), process_time_ns()
    truth = tuple(Q(x) for x in case["initial_state"])
    initial = StateBox.around(
        tuple(Q(x) for x in case["prior_center"]), tuple(Q(x) for x in case["prior_radii"])
    )
    if not initial.contains(truth):
        raise ValueError("Latent truth outside supplied initial prior")
    plant = Plant(
        truth, float(Q(case["effectiveness"])), tuple(float(Q(x)) for x in case["disturbance"])
    )
    warm = packet(case, plant.state(), case["warm_channel"], 0)
    raw = dict(
        initial=primitive(initial),
        sensors=primitive(sensors(case["stratum"])),
        packets=primitive(warm),
        history=primitive((HistorySegment(0, 100, (0, 0)),)),
        at_ms=100,
        queued_action=["0", "0"],
        timing=primitive(Timing()),
    )
    prearm_start = perf_counter_ns()
    arm = initial_arm(raw)
    prearm_ns = perf_counter_ns() - prearm_start
    gate = Gate(raw, arm)
    plant.advance(100)
    plan_start = perf_counter_ns()
    proposal, full_policy, initial_estimate = plan(raw, method)
    plan_ns = perf_counter_ns() - plan_start
    plan_ok = (
        case["planner_ready_ms"] <= 150 and arm["valid"] and full_policy["certificate"] is not None
    )
    channel = proposal["channel"] if plan_ok else None
    acquisition_state = plant.advance(250)
    generated = packet(case, acquisition_state, channel, 250)
    plant.advance(650)
    delivered = tuple(p for p in generated if p.available_ms <= 650)
    chosen = proposal_action(proposal, delivered) if plan_ok else (Q(0), Q(0))
    payload = dict(input=at_time(raw, 650, delivered), action=primitive(chosen))
    check_start = perf_counter_ns()
    checked, components = check_action(payload)
    check_ns = perf_counter_ns() - check_start
    # Account all observed algorithmic work, including failed planning/checking.
    # Both workers have fixed caps: <=100001 observer operations, <=50001 plan
    # operations and <=1000 propagation steps. Together with modeled fixed/sensor
    # charges these fit the common 500 mJ envelope. This is not measured energy.
    work = (
        full_policy["operations"]
        + initial_estimate["diagnostics"]["operations"]
        + checked["uncertainty"]["diagnostics"]["operations"]
        + checked["steps"]
    )
    warm_cost = (
        Q(1, 5) if case["warm_channel"] == "range" else Q(3, 10) if case["warm_channel"] else Q(0)
    )
    sensor_cost = Q(1, 5) if channel == "range" else Q(3, 10) if channel else Q(0)
    used_energy = Q(10) + Q(work, 1000) + warm_cost + sensor_cost
    budget_ok = used_energy <= 500
    admitted = (
        gate.admit(checked, payload, case["checker_ready_ms"])
        if plan_ok and budget_ok
        else dict(scheduled=False, reasons=["no_timely_supported_plan_or_resource_budget"])
    )
    # Each phase is stepped at its actual simulated time, never its measured host duration.
    application_state = plant.advance(case["application_ms"])
    emitted = gate.tick(case["application_ms"], live_binding_sha256=identity(payload))
    action = tuple(Q(x) for x in emitted["action"])
    plant.advance(1200, action)
    plant.advance(4200)
    final_state = plant.state()
    adjudicated = numerical_adjudication(plant.rows)
    estimated = checked["uncertainty"]
    state_at_check = next(r["state"] for r in plant.rows if r["at_ms"] == 650)
    # Definitely outside every projected box, beyond the numerical allowance.
    margins = (NUMERIC_POSITION_M,) * 2 + (NUMERIC_VELOCITY_MPS,) * 2
    excluded = bool(estimated["cells"]) and not any(
        all(
            float(Q(c["bounds"][j]["lo"])) - margins[j]
            <= state_at_check[j]
            <= float(Q(c["bounds"][j]["hi"])) + margins[j]
            for j in range(4)
        )
        for c in estimated["cells"]
    )
    initial_v = float(truth[0]) ** 2 + (float(truth[1]) + 40) ** 2
    final_v = final_state[0] ** 2 + (final_state[1] + 40) ** 2
    row = dict(
        schema="iaa-sa05-result/1",
        unit=case["unit"],
        stratum=case["stratum"],
        method=method,
        input_sha256=identity(case),
        status="completed",
        policy_status=proposal["status"],
        task_band=case["task_band"],
        outside_type=case["outside_type"],
        modeled_assumptions=case["stratum"] != "outside_assumptions",
        initial_protection=arm["valid"],
        planning_supported=plan_ok,
        observation_requests=int(channel is not None),
        requested_channel=channel,
        delivered_requests=len(delivered),
        planner_clock_late=case["planner_ready_ms"] > 150,
        checker_clock_late=case["checker_ready_ms"] > 700,
        command_admitted=admitted["scheduled"],
        candidate_applied=emitted["newly_applied"],
        nonzero_intervention=bool(emitted["newly_applied"] and any(action)),
        missed_application_window=case["application_ms"] > 710,
        application_ms=case["application_ms"] if emitted["newly_applied"] else None,
        action=primitive(action),
        command_end_ms=1200,
        finite_expiry_ms=4200,
        protective_continuation_used=bool(arm["valid"] and not emitted["newly_applied"]),
        unresolved_decision=proposal["status"] not in ("checked_tree", "checked_action")
        or checked["status"] == "unresolved",
        unsafe_admission_observed=bool(
            emitted["credited"] and adjudicated["constraint_status"] == "violated"
        ),
        nonempty_information_exclusion=excluded,
        unnecessary_abstention_established=None,
        abstention_reference_scope=(
            "No oracle establishes necessity or real-time feasibility of an alternative"
        ),
        modeled_energy_mj=round(float(used_energy), 9),
        modeled_budget_mj=500,
        modeled_budget_exhausted=not budget_ok,
        total_counted_work_units=work,
        planner_observer_work_units=initial_estimate["diagnostics"]["operations"],
        checker_observer_work_units=checked["uncertainty"]["diagnostics"]["operations"],
        planner_work_units=proposal["operations"],
        checker_steps=checked["steps"],
        task_potential_change_m2=round(final_v - initial_v, 9),
        initial_task_potential_m2=round(initial_v, 9),
        final_task_potential_m2=round(final_v, 9),
        **adjudicated,
        energy_measured=False,
        real_time_feasibility=False,
    )
    timing = dict(
        unit=case["unit"],
        method=method,
        prearm_ns=prearm_ns,
        planner_ns=plan_ns,
        checker_ns=check_ns,
        checker_components_ns=components,
        complete_offline_trial_ns=perf_counter_ns() - start,
        process_cpu_ns=process_time_ns() - cpu_start,
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        planner_over_50ms=plan_ns > 50_000_000,
        checker_over_50ms=check_ns > 50_000_000,
        actual_physical_latency_measured=False,
    )
    evidence = dict(
        initial_input=raw,
        initial_estimate=initial_estimate,
        prearm=arm,
        full_policy=full_policy,
        proposal=proposal,
        delivered_receipts=primitive(delivered),
        requested_channel=channel,
        acquisition_state_evaluation_only=acquisition_state,
        checker_payload=payload,
        checked=checked,
        admission=admitted,
        emitted=emitted,
        application_state_evaluation_only=application_state,
        trajectory=[
            dict(at_ms=r["at_ms"], state=[round(x, 12) for x in r["state"]]) for r in plant.rows
        ],
        simulated_acknowledgement=emitted["newly_applied"],
        simulated_clock=dict(
            planner_ready=case["planner_ready_ms"], checker_ready=case["checker_ready_ms"]
        ),
        protection_ends_ms=4200,
    )
    return row, primitive(evidence), timing
