"""Matched closed-loop cells and independent fixed-execution adjudication."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fractions import Fraction as Q
from collections import Counter
import csv
import hashlib
import json
import math
import time
import numpy as np
from specification.contract import load_property, State
from adjudication.flow import Model, propagate_schedule
from adjudication.engine import adjudicate
from .io import save_json, manifest
from .native import components, Plant
from .screen import ControlledGate

ARM_NAMES = ("no_gate", "original_gate", "controlled_in_band", "controlled_union")


def innovations(protocol):
    seed = protocol["estimator"]["seed_master"]

    def draws(stream, shape):
        return np.random.Generator(
            np.random.PCG64DXSM(np.random.SeedSequence([seed, 1, stream]))
        ).normal(size=shape)

    sigma = np.array(protocol["estimator"]["measurement_sigma"])
    return {
        "primary_noise": draws(1, (301, 4)) * sigma,
        "monitor_noise": draws(2, (301, 4)) * sigma,
        "process_acceleration": np.clip(draws(3, (1200, 2)), -3.0, 3.0) * 0.0005,
        "actuator_error": draws(4, (300, 2)) * 0.0002,
    }


def hash_array(array):
    return hashlib.sha256(np.ascontiguousarray(array, dtype="<f8").tobytes()).hexdigest()


def ideal_snapshot(state, time_s):
    cfg, ctrl, *_ = components()
    return SimpleNamespace(
        time_s=float(time_s),
        mean=np.array(state, copy=True),
        covariance=np.diag([0.01, 0.01, 0.0001, 0.0001]),
        health=ctrl.FilterHealth.VALID,
        prediction_only_age_s=0.0,
        consecutive_innovation_rejections=0,
    )


def snapshot_record(s):
    return {
        "mean": s.mean.tolist(),
        "covariance": s.covariance.tolist(),
        "health": s.health.value,
        "prediction_only_age_s": s.prediction_only_age_s,
        "consecutive_innovation_rejections": s.consecutive_innovation_rejections,
    }


def archival_call(gate, snapshot, proposal):
    cfg, ctrl, *_ = components()
    geometry = ctrl.evaluate_segment
    events = []

    def observe_geometry(*args, **kwargs):
        events.append("geometry")
        return geometry(*args, **kwargs)

    fallback = gate._fallback

    def observe_fallback(*args, **kwargs):
        events.append("fallback")
        return fallback(*args, **kwargs)

    with (
        patch.object(ctrl, "evaluate_segment", observe_geometry),
        patch.object(gate, "_fallback", observe_fallback),
    ):
        result = gate.gate(snapshot, proposal)
    prefix = ["controller_identity"]
    for reason, label in [
        ("CONTROLLER_INTEGRITY", "estimator_divergence"),
        ("ESTIMATOR_DIVERGED", "estimator_quality"),
        ("ESTIMATOR_QUALITY", "command_bound"),
    ]:
        if result.reason == reason:
            break
        prefix.append(label)
    return result, {
        "visited_branches": prefix + events,
        "geometry_evaluated": "geometry" in events,
        "branch_logging": "early prefix from frozen control flow; geometry and fallback invocations directly observed",
        "screen": None,
        "predicate": "original_in_band",
        "fallback_verified_safe": False,
    }


def packet_update(filters, case, state, k, noise, protocol):
    cfg, _, _, _, _, measurements = components()
    fault_kind = case.get("fault", "none")
    onset = 100.0 if fault_kind != "none" else None
    end = (130.0 if fault_kind == "bias" else 106.0) if fault_kind != "none" else None
    fault = measurements.MeasurementFault(
        fault_kind,
        "primary" if fault_kind != "none" else "none",
        onset,
        end,
        (8.0, 0.0, 0.0, 0.0) if fault_kind == "bias" else None,
    )
    logs = []
    for channel, flt in zip(("primary", "monitor"), filters, strict=True):
        innovation = noise[channel + "_noise"][k]
        packet = measurements.navigation_packet(
            sequence_id=k,
            measured_at_s=float(k),
            received_at_s=float(k),
            latent_state=state,
            measurement_noise=innovation,
            quantization=np.array(cfg.measurement_quantization),
            nominal_covariance=cfg.nominal_measurement_covariance,
            channel=channel,
            fault=fault,
            previous_packet=None,
        )
        diagnostic = flt.ingest(packet) if packet is not None else None
        logs.append(
            {
                "time_s": k,
                "channel": channel,
                "measurement_time_s": k,
                "receipt_time_s": k,
                "fault_window_active": fault.active(k, channel),
                "fault_kind": fault_kind if fault.active(k, channel) else "none",
                "noise_innovation": innovation.tolist(),
                "packet": None if packet is None else packet.measurement.tolist(),
                "disposition": "dropout" if packet is None else diagnostic.disposition.value,
                "nis": None if diagnostic is None else diagnostic.nis,
                "filter_innovation": None if diagnostic is None else diagnostic.innovation,
            }
        )
    return [f.snapshot() for f in filters], logs


def evaluate_execution(kind, initial, schedule, states, protocol):
    prop = load_property()
    started = time.perf_counter()
    try:
        arcs = propagate_schedule(Model(kind), initial, schedule, maximum_step=0.25, order=8)
        result = adjudicate(
            arcs,
            prop,
            minimum_width=Q(1, 4096),
            required_events=[i / 4 for i in range(1201)],
            max_cells=100000,
        )
        discrepancy = np.zeros(4)
        enclosure = []
        for i, (t, box) in enumerate(
            [(Q(0), arcs[0].point(0))] + [(a.end, a.point(a.end)) for a in arcs]
        ):
            actual = np.array(states[i][1:5], dtype=float)
            low = np.array([v.lo for v in box.coordinates])
            high = np.array([v.hi for v in box.coordinates])
            discrepancy = np.maximum(
                discrepancy, np.maximum(np.maximum(low - actual, actual - high), 0.0)
            )
            enclosure.append([float(t), *[v for c in box.coordinates for v in (c.lo, c.hi)]])
        result["max_simulator_distance_outside_enclosure_components"] = discrepancy.tolist()
        result["reference_comparison_scope"] = (
            "Original approximate plant versus enclosed intended ODE; includes represented frame-initial differences, not a simulator error certificate."
        )
        result["feedback_sequence_certified"] = False
        result["scope_of_validated_result"] = (
            "Intended mathematical model under the exact recorded input schedule; feedback generator is not interval-certified."
        )
        result["simulator_agreement"] = (
            "outside_predeclared_comparison_limit"
            if max(discrepancy[:2]) > 1e-5 or max(discrepancy[2:]) > 1e-8
            else "within_predeclared_comparison_limit"
        )
    except Exception as exc:
        result = {
            "status": "unresolved",
            "reason": type(exc).__name__ + ":" + str(exc),
            "components": dict.fromkeys(
                ("containment", "collision_free", "keep_out_free"), "unresolved"
            ),
            "hold_acquired": "unresolved",
            "nominal_goal": "unresolved",
        }
        enclosure = []
    result["adjudication_wall_s"] = time.perf_counter() - started
    return result, enclosure


def save_csv(path, headers, rows):
    with Path(path).open("x", newline="") as handle:
        writer = csv.writer(handle, lineterminator=chr(10))
        writer.writerow(headers)
        writer.writerows(rows)


def run_cell(job):
    case, kind, arm, output, protocol = job
    dest = Path(output) / "cells" / f"{case['id']}__{kind}__{arm}"
    dest.mkdir(parents=True, exist_ok=False)
    cfg, ctrl, _, _, estimator, _ = components()
    controller = ctrl.DeterministicHoldController(cfg)
    gate = (
        ctrl.EstimatedGeometryMonitor(cfg, controller, controller.controller_identity)
        if arm == "original_gate"
        else ControlledGate(
            controller, "in_band" if arm == "controlled_in_band" else "closed_union"
        )
        if arm.startswith("controlled_")
        else None
    )
    initial = case["initial"]
    plant = Plant(kind, initial)
    prop = load_property()
    filters = (
        [estimator.PlanarNavigationFilter(cfg), estimator.PlanarNavigationFilter(cfg)]
        if case["information"] == "estimator"
        else None
    )
    noise = innovations(protocol) if filters else None
    states = []
    commands = []
    schedules = []
    packet_rows = []
    time_started = time.perf_counter()
    status = "running"
    error = None

    def record_state(t, s):
        c = prop.classify(State(*map(float, s)))
        states.append(
            [
                t,
                *map(float, s),
                c["inside_union"],
                c["collision"],
                c["keep_out_entry"],
                c["hold_eligible"],
            ]
        )

    record_state(0.0, initial)
    try:
        with (
            (dest / "commands.jsonl").open("x") as command_file,
            (dest / "packets.jsonl").open("x") as packet_file,
        ):
            for k in range(301):
                s = np.array(initial, float) if k == 0 else plant.observed_state()
                if filters:
                    snaps, packets = packet_update(filters, case, s, k, noise, protocol)
                    for p in packets:
                        packet_file.write(
                            json.dumps(p, allow_nan=False, separators=(",", ":")) + chr(10)
                        )
                    packet_rows.extend(packets)
                else:
                    snaps = [ideal_snapshot(s, k), ideal_snapshot(s, k)]
                if k == 300:
                    break
                primary, monitor = snaps
                start = time.perf_counter()
                cpu = time.process_time()
                proposal = controller.decide(ctrl.observation_from_snapshot(primary))
                if arm == "no_gate":
                    decision = ctrl.GateDecision(
                        proposal.acceleration_mps2, proposal.acceleration_mps2, False, None, None
                    )
                    details = {
                        "visited_branches": [],
                        "geometry_evaluated": False,
                        "screen": None,
                        "predicate": None,
                        "fallback_verified_safe": False,
                    }
                elif arm == "original_gate":
                    decision, details = archival_call(gate, monitor, proposal)
                else:
                    decision, details = gate.gate(monitor, proposal)
                wall = time.perf_counter() - start
                elapsed_cpu = time.process_time() - cpu
                u = decision.executed_acceleration_mps2.copy()
                if (
                    not np.all(np.isfinite(u))
                    or np.linalg.norm(u) > cfg.max_acceleration_mps2 + 1e-12
                ):
                    raise ArithmeticError("Selected command invalid")
                row = {
                    "time_s": k,
                    "decision_at_s": k,
                    "applied_at_s": k,
                    "input_delay_s": 0.0,
                    "primary": snapshot_record(primary),
                    "monitor": snapshot_record(monitor),
                    "proposed": proposal.acceleration_mps2.tolist(),
                    "selected": u.tolist(),
                    "overridden": bool(decision.overridden),
                    "command_changed": not np.array_equal(u, proposal.acceleration_mps2),
                    "reason": decision.reason or "accepted",
                    "conservative_radius_m": decision.conservative_keep_out_radius_m,
                    **details,
                    "decision_wall_s": wall,
                    "decision_cpu_s": elapsed_cpu,
                    "physically_applied": [],
                }
                for j in range(4):
                    disturbance = (
                        np.zeros(2) if noise is None else noise["process_acceleration"][4 * k + j]
                    )
                    actuator = np.zeros(2) if noise is None else noise["actuator_error"][k]
                    applied = u + disturbance + actuator
                    t = k + j / 4
                    schedules.append((t, t + 0.25, applied.tolist()))
                    row["physically_applied"].append(
                        {
                            "start_s": t,
                            "end_s": t + 0.25,
                            "acceleration": applied.tolist(),
                            "effectiveness": 1.0,
                            "process": disturbance.tolist(),
                            "actuator_error": actuator.tolist(),
                        }
                    )
                    record_state(t + 0.25, plant.step(applied))
                if filters:
                    for flt in filters:
                        flt.advance(u, float(k + 1))
                commands.append(row)
                command_file.write(
                    json.dumps(row, allow_nan=False, separators=(",", ":")) + chr(10)
                )
                command_file.flush()
        status = "complete"
    except Exception as exc:
        status = "failed"
        error = type(exc).__name__ + ":" + str(exc)
    save_csv(
        dest / "states.csv",
        [
            "time_s",
            "x_m",
            "y_m",
            "vx_mps",
            "vy_mps",
            "sampled_inside_union",
            "sampled_collision",
            "sampled_keep_out",
            "sampled_hold_eligible",
        ],
        states,
    )
    save_json(dest / "applied_schedule.json", schedules)
    if status == "complete":
        physical, enclosure = evaluate_execution(kind, initial, schedules, states, protocol)
    else:
        physical = {"status": "unresolved", "reason": "incomplete_execution"}
        enclosure = []
    if enclosure:
        save_csv(
            dest / "enclosures.csv",
            [
                "time_s",
                *[n + s for n in ("x_m", "y_m", "vx_mps", "vy_mps") for s in ("_lo", "_hi")],
            ],
            enclosure,
        )
    save_json(dest / "adjudication.json", physical)
    reasons = Counter(r["reason"] for r in commands)
    summary = {
        "case": case["id"],
        "information": case["information"],
        "case_role": case["role"],
        "plant": kind,
        "arm": arm,
        "execution_status": status,
        "error": error,
        "initial": initial,
        "initial_recovery_status": case["recovery_status"],
        "commands": len(commands),
        "states": len(states),
        "packet_opportunities": len(packet_rows),
        "overrides": sum(r["overridden"] for r in commands),
        "changed_commands": sum(r["command_changed"] for r in commands),
        "geometry_checks": sum(r["geometry_evaluated"] for r in commands),
        "reasons": dict(reasons),
        "geometry_rejections": reasons["UNCERTAINTY_AWARE_GEOMETRY"],
        "numerically_unresolved_decisions": reasons["NUMERICAL_UNRESOLVED"],
        "control_effort_integral_mps": sum(float(np.linalg.norm(r["selected"])) for r in commands),
        "control_energy_integral_m2ps3": sum(
            float(np.dot(r["selected"], r["selected"])) for r in commands
        ),
        "max_selected_norm_mps2": max(
            (float(np.linalg.norm(r["selected"])) for r in commands), default=0.0
        ),
        "sampled_minimum_separation_m": min(math.hypot(r[1], r[2]) for r in states),
        "sampled_outside_count": sum(not r[5] for r in states),
        "abort_requested": False,
        "decision_cpu_total_s": sum(r["decision_cpu_s"] for r in commands),
        "decision_wall_max_s": max((r["decision_wall_s"] for r in commands), default=0.0),
        "wall_runtime_s": time.perf_counter() - time_started,
        "physical_status": physical["status"],
        "adjudication": physical,
        "controller_identity": controller.controller_identity,
        "innovation_sha256": {} if noise is None else {k: hash_array(v) for k, v in noise.items()},
        "fault_packet_dispositions": dict(
            Counter(p["disposition"] for p in packet_rows if p["fault_window_active"])
        ),
        "motion_sha256": hash_array(np.array([r[:5] for r in states])),
        "selected_command_sha256": hash_array(np.array([r["selected"] for r in commands])),
        "applied_command_sha256": hash_array(np.array([u for a, b, u in schedules])),
    }
    save_json(dest / "summary.json", summary)
    manifest(dest)
    return summary
