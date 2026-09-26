"""Deterministic event-grid simulator. All latencies/energy here are declared models.

The controller gets delivered packets only; the guard gets a propagated prior and
known commands. Truth and fault labels are confined to plant generation/evaluation.
"""

from fractions import Fraction as Q

from .assurance import CommandSink, check
from .controller import Baseline
from .enclosure import inside, separated, step, terminal
from .plant import flow, observe
from .types import Command, ExecutionRecord, StateBox, Status, Uncertainty, identity, primitive

DT_MS = 10
CYCLE_MS = 500
SNAPSHOT_MS = 100
APPLY_OFFSET_MS = 200
MODEL_COMPUTE_MS = 50
EXTRA_ACQUIRE_DELAY_MS = 100


def run(fixture):
    truth = tuple(fixture.initial)
    prior = fixture.initial_box()
    if not prior.contains(truth):
        raise ValueError("Fixture truth is outside initial contract")
    evaluation = StateBox.around(fixture.initial, (0, 0, 0, 0))
    baseline = Baseline()
    initial = Uncertainty(prior, 0)
    bootstrap = Command((Q(0), Q(0)), 0, 200, "bootstrap")
    boot_check = check(initial, bootstrap, enabled=fixture.checker_enabled)
    sink = CommandSink(
        boot_check.valid_until_ms if boot_check.status == Status.BOUNDED_PREFIX else 0
    )
    records = []

    def log(t, event, **details):
        records.append(ExecutionRecord(t, event, details))

    log(0, "initial_contract", information=primitive(initial), bootstrap=primitive(boot_check))
    log(
        0,
        "resource_model",
        decision_mj=5,
        range_mj=0.2,
        bearing_mj=0.3,
        work_budget_mj=fixture.work_budget_mj,
        real_hardware_measurement=False,
        compute_ms=MODEL_COMPUTE_MS,
        processing_ms=10,
        proposal_ms=15,
        checking_ms=20,
        dispatch_ms=5,
    )
    packets = []
    inflight = []
    replies = []
    spent = Q(0)
    sensor_sequence = 0
    action = (Q(0), Q(0))
    action_status = "bootstrap"
    coverage_ms = 0
    complete_ms = 0
    max_dwell_ms = 0
    model_containment = True
    collision_free = True
    keepout_free = True
    assumptions_valid = True
    first_numerical_exit = None
    first_unresolved_tube = None
    all_dispatches = []
    all_decisions = []
    requested = {t + EXTRA_ACQUIRE_DELAY_MS for t in fixture.additional_request_ms}
    last_mode = None
    for t in range(0, fixture.horizon_ms + 1, DT_MS):
        if t:
            eta = fixture.effectiveness_after if t - DT_MS >= fixture.actuator_fault_ms else 1.0
            truth = flow(truth, action, DT_MS / 1000, effectiveness=eta)
            prior, _ = step(prior, action, DT_MS)
            evaluation, tube = step(evaluation, action, DT_MS, (Q(str(eta)), Q(str(eta))), Q(0))
            contained = inside(tube)
            if not contained and first_unresolved_tube is None:
                first_unresolved_tube = t - DT_MS
            model_containment &= contained
            collision_free &= separated(tube, Q(2))
            keepout_free &= separated(tube, Q(10))
            if first_numerical_exit is None and not (
                -8 <= truth[0] <= 8 and -60 <= truth[1] <= -30
            ):
                first_numerical_exit = t
            complete_ms = complete_ms + DT_MS if terminal(tube) else 0
            max_dwell_ms = max(max_dwell_ms, complete_ms)
            if eta < 0.8:
                assumptions_valid = False
            if action_status != "uncredited_output_after_protection_expiry" and eta >= 0.8:
                coverage_ms += DT_MS
        # Arrival precedes the decision snapshot; future packets never enter its interface.
        arrived = [p for p in inflight if p.available_ms == t]
        packets.extend(arrived)
        for p in arrived:
            log(t, "observation_available", packet=primitive(p))
        inflight = [p for p in inflight if p.available_ms > t]
        # Drop old packet storage to bound memory; raw receipts remain separate.
        packets = [p for p in packets if t - p.available_ms <= 2000]
        for cmd, checked, info, ready in [r for r in replies if r[3] == t]:
            outcome = sink.submit(cmd, checked, info, ready)
            log(t, "decision_arrival", command=primitive(cmd), check=primitive(checked), **outcome)
            all_dispatches.append(outcome)
        replies = [r for r in replies if r[3] > t]
        action, action_status, applied = sink.tick(t)
        if applied or last_mode != action_status:
            log(
                t,
                "applied_command",
                action=primitive(action),
                mode=action_status,
                request_id=applied,
                valid_until_ms=sink.valid_until_ms,
            )
        last_mode = action_status
        if t in fixture.additional_request_ms:
            log(
                t,
                "additional_observation_requested",
                acquire_ms=t + EXTRA_ACQUIRE_DELAY_MS,
                policy="fixed_engineering_schedule_not_information_optimisation",
            )
        if (t % CYCLE_MS == 0 or t in requested) and t < fixture.horizon_ms:
            if spent + Q(1, 2) <= fixture.work_budget_mj:
                spent += Q(1, 2)
                emitted, lost = observe(truth, t, sensor_sequence, fixture.faults)
                sensor_sequence += 1
                inflight.extend(p for p in emitted if p.available_ms > t)
                packets.extend(p for p in emitted if p.available_ms == t)
                log(
                    t,
                    "sensor_acquisition",
                    packet_ids=[p.packet_id for p in emitted],
                    engineering_injection_log=list(lost),
                    charged_mj="1/2",
                )
                for packet in emitted:
                    if packet.available_ms == t:
                        log(t, "observation_available", packet=primitive(packet))
            else:
                log(t, "acquisition_unavailable", reason="model_work_budget_exhausted")
        if t % CYCLE_MS == SNAPSHOT_MS and t + 100 < fixture.horizon_ms:
            cycle = t // CYCLE_MS
            if spent + 5 > fixture.work_budget_mj:
                log(t, "decision_missing", reason="model_work_budget_exhausted")
            else:
                spent += 5
                proposal = baseline.propose(
                    tuple(packets),
                    t,
                    cycle * CYCLE_MS + APPLY_OFFSET_MS,
                    (cycle + 1) * CYCLE_MS + APPLY_OFFSET_MS,
                )
                info = Uncertainty(prior, t)
                checked = check(info, proposal.command, action, enabled=fixture.checker_enabled)
                chosen = proposal.command
                # Rejected proposals may switch to a newly checked finite coast.
                if checked.status == Status.UNRESOLVED and any(chosen.acceleration):
                    coast = Command((Q(0), Q(0)), chosen.apply_ms, chosen.end_ms, chosen.request_id)
                    coast_check = check(info, coast, action, enabled=fixture.checker_enabled)
                    if coast_check.status == Status.BOUNDED_PREFIX:
                        chosen, checked = coast, coast_check
                ready = t + (400 if cycle in fixture.late_cycles else MODEL_COMPUTE_MS)
                detail = {
                    "proposal": primitive(proposal),
                    "chosen_command": primitive(chosen),
                    "check": primitive(checked),
                    "information": primitive(info),
                    "simulated_ready_ms": ready,
                    "truth_available_to_controller": False,
                    "measurement_set_update": "unsupported_in_SA01",
                    "response_lost": cycle in fixture.stalled_cycles,
                }
                log(t, "decision_snapshot", **detail)
                all_decisions.append(detail)
                if cycle not in fixture.stalled_cycles:
                    replies.append((chosen, checked, info, ready))
                else:
                    log(t, "decision_missing", reason="injected_response_loss")
        if t % 500 == 0 or t == fixture.horizon_ms:
            # Evaluation-only record. Not passed back to controller or guard.
            log(
                t,
                "evaluation",
                state=[round(x, 12) for x in truth],
                complete_dwell_lower_ms=max_dwell_ms,
                prior_contains_numeric_truth=prior.contains(truth),
                cumulative_model_containment=model_containment,
                assumptions_valid=assumptions_valid,
                work_spent_mj=str(spent),
            )
    summary = {
        "schema": "iaa-engineering-result/1",
        "fixture": fixture.name,
        "fixture_sha256": identity(fixture),
        "evidence_class": "deterministic_engineering_fixture",
        "horizon_ms": fixture.horizon_ms,
        "decision_count": len(all_decisions),
        "scheduled_decisions": sum(d["scheduled"] for d in all_dispatches),
        "late_rejections": sum("late" in d["reasons"] for d in all_dispatches),
        "lost_responses": sum(d["response_lost"] for d in all_decisions),
        "unsupported_decisions": sum(
            d["check"]["status"] == Status.UNSUPPORTED for d in all_decisions
        ),
        "model_containment_via_continuous_tubes": model_containment,
        "model_collision_avoidance_via_continuous_tubes": collision_free,
        "model_keepout_avoidance_via_continuous_tubes": keepout_free,
        "model_goal_dwell_lower_ms": max_dwell_ms,
        "model_mission_completed": max_dwell_ms >= 2000,
        "conditional_guard_coverage_ms": coverage_ms,
        "protection_gap_ms": fixture.horizon_ms - coverage_ms,
        "assumptions_valid": assumptions_valid,
        "first_unresolved_containment_tube_ms": first_unresolved_tube,
        "first_numerical_exit_ms": first_numerical_exit,
        "work_spent_model_mj": str(spent),
        "hardware_energy_measured": False,
        "physical_execution": False,
        "full_recovery_proved": False,
        "final_numeric_state": [round(x, 12) for x in truth],
    }
    return summary, tuple(records)
