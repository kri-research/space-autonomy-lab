"""Declared developmental comparisons, not final or historical evaluations."""

from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
import os
import time
import numpy as np
from causal.native import Plant, components
from causal.experiment import ideal_snapshot, archival_call, evaluate_execution
from causal.screen import ControlledGate
from causal.qualification import reference
from .common import (
    Observation,
    observation_to_information,
    Tube,
    SENSOR,
    W_COMPONENT,
    MODEL_COMPONENT,
    NUMERIC_COMPONENT,
    AC,
    U_MAX,
)
from .predictive import PredictiveFilter, Decision
from .barrier import BarrierFilter

PACKAGE = Path(__file__).resolve().parent
ARMS = ("unprotected", "original", "aligned", "tracking", "predictive", "barrier")


def plain(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, np.generic):
        return x.item()
    raise TypeError(type(x).__name__)


def write(path, data):
    with Path(path).open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=plain, allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def innovations(protocol):
    rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([protocol["seed"], 5])))
    sensor = rng.uniform(-1, 1, (301, 4))
    process = rng.uniform(-1, 1, (1200, 2))
    return sensor, process


def tracker(estimate, initial, t):
    q, v, a = reference(initial, float(t), 180.0)
    u = a + 0.01 * (q - estimate[:2]) + 0.2 * (v - estimate[2:]) - (AC @ estimate)[2:]
    norm = np.linalg.norm(u)
    if norm > U_MAX:
        u = u * (U_MAX / norm)
    return u


def make_filter(arm, tube, config):
    if arm == "predictive":
        return PredictiveFilter(
            tube,
            horizon=config["horizon"],
            solver_time_limit=config["solver_time_limit"],
            decision_limit=config["decision_limit"],
        )
    if arm == "barrier":
        return BarrierFilter(
            tube,
            rates=tuple(config["rates"]),
            solver_time_limit=config["solver_time_limit"],
            decision_limit=config["decision_limit"],
        )
    return None


def run_case(case, kind, arm, config, protocol, output, *, tuning=False):
    dest = Path(output)
    dest.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    cfg, ctrl, *_ = components()
    controller = ctrl.DeterministicHoldController(cfg)
    gate = (
        ctrl.EstimatedGeometryMonitor(cfg, controller, controller.controller_identity)
        if arm == "original"
        else ControlledGate(controller, "closed_union")
        if arm == "aligned"
        else None
    )
    sensor_scale = np.zeros(4) if case["information"] == "ideal" else SENSOR.copy()
    disturbance = 0.0 if case["information"] == "ideal" else W_COMPONENT
    tube = Tube(sensor_scale, disturbance + MODEL_COMPONENT + NUMERIC_COMPONENT)
    f = make_filter(arm, tube, config)
    sensor_noise, force_noise = innovations(protocol)
    plant = Plant(kind, case["initial"])
    states = [[0.0, *case["initial"]]]
    ticks = [np.array(case["initial"], dtype=float)]
    delay = case["delay"]
    age = case["age"]
    history = {0: np.zeros(2)} if delay else {}
    schedule = []
    records = []
    plan_records = []
    tracking_initial = None
    error = None
    with (
        (dest / "commands.jsonl").open("x") as command_log,
        (dest / "plans.jsonl").open("x") as plan_log,
    ):
        try:
            for k in range(300):
                measured = max(0, k - age)
                observation = ticks[measured] + sensor_scale * sensor_noise[measured]
                packet = Observation(
                    measured,
                    k,
                    tuple(observation),
                    tuple(sensor_scale),
                    "ideal" if case["information"] == "ideal" else "deterministic_interval",
                )
                info = observation_to_information(
                    packet, k, k + delay, history, disturbance + MODEL_COMPONENT + NUMERIC_COMPONENT
                )
                if tracking_initial is None:
                    tracking_initial = observation.copy()
                snap = ideal_snapshot(info.estimate, k + delay)
                snap.covariance = np.diag(np.maximum(info.error / 3, 1.0e-8) ** 2)
                proposal = controller.decide(ctrl.observation_from_snapshot(snap))
                begin = time.perf_counter()
                cpu = time.process_time()
                if f is not None:
                    decision = f.decide(info, proposal.acceleration_mps2)
                elif arm == "unprotected":
                    decision = Decision(proposal.acceleration_mps2, "unprotected", False, {})
                elif arm == "tracking":
                    decision = Decision(
                        tracker(info.estimate, tracking_initial, k + delay),
                        "bounded_tracking_control",
                        False,
                        {},
                    )
                else:
                    g, details = (
                        archival_call(gate, snap, proposal)
                        if arm == "original"
                        else gate.gate(snap, proposal)
                    )
                    decision = Decision(
                        g.executed_acceleration_mps2,
                        g.reason or "accepted",
                        False,
                        {"overridden": bool(g.overridden), **details},
                    )
                policy_wall = time.perf_counter() - begin
                policy_cpu = time.process_time() - cpu
                unavailable = decision.command is None
                selected = (
                    tracker(info.estimate, tracking_initial, k + delay)
                    if unavailable
                    else np.asarray(decision.command)
                )
                if not np.all(np.isfinite(selected)) or np.linalg.norm(selected) > U_MAX + 1.0e-12:
                    raise ArithmeticError("Selected input bound")
                history[k + delay] = selected.copy()
                applied = np.asarray(history[k])
                if (
                    f is not None
                    and arm == "predictive"
                    and decision.status == "feasible_predictive_plan"
                ):
                    p = f.plan
                    saved = {
                        "decision_at": k,
                        "application_at": k + delay,
                        "initial_estimate": info.estimate.tolist(),
                        "r0": float(p["radii"][0]),
                        "switch": p["switch"],
                        "u": p["u"].T.tolist(),
                        "terminal_z": p["z"][:, -1].tolist(),
                    }
                    plan_log.write(
                        json.dumps(saved, default=plain, allow_nan=False, separators=(",", ":"))
                        + "\n"
                    )
                    plan_records.append(saved)
                row = {
                    "decision_at": k,
                    "measured_at": measured,
                    "received_at": k,
                    "application_at": k + delay,
                    "observation": observation.tolist(),
                    "current_estimate": info.current_estimate.tolist(),
                    "application_estimate": info.estimate.tolist(),
                    "application_error": info.error.tolist(),
                    "current_error": info.current_error.tolist(),
                    "pending": info.pending,
                    "proposal": proposal.acceleration_mps2.tolist(),
                    "selected": selected.tolist(),
                    "applied_this_tick": applied.tolist(),
                    "status": decision.status,
                    "protected": decision.protected,
                    "external_tracking_guard": unavailable,
                    "policy_wall_s": policy_wall,
                    "policy_cpu_s": policy_cpu,
                    "details": decision.details,
                    "realized_accelerations": [],
                }
                for j in range(4):
                    force = disturbance * force_noise[4 * k + j]
                    realized = applied + force
                    schedule.append((k + j / 4, k + (j + 1) / 4, realized.tolist()))
                    row["realized_accelerations"].append(realized.tolist())
                    s = plant.step(realized)
                    states.append([k + (j + 1) / 4, *s.tolist()])
                ticks.append(np.array(states[-1][1:]))
                command_log.write(
                    json.dumps(row, default=plain, allow_nan=False, separators=(",", ":")) + "\n"
                )
                command_log.flush()
                records.append(row)
        except Exception as exc:
            error = type(exc).__name__ + ":" + str(exc)
    from causal.experiment import save_csv

    save_csv(dest / "states.csv", ["time_s", "x_m", "y_m", "vx_mps", "vy_mps"], states)
    write(dest / "schedule.json", schedule)
    if error is None:
        physical, enclosures = evaluate_execution(kind, case["initial"], schedule, states, protocol)
    else:
        physical, enclosures = {"status": "unresolved", "reason": "incomplete_execution"}, []
    if enclosures:
        save_csv(
            dest / "enclosures.csv",
            [
                "time_s",
                *[n + s for n in ("x_m", "y_m", "vx_mps", "vy_mps") for s in ("_lo", "_hi")],
            ],
            enclosures,
        )
    write(dest / "adjudication.json", physical)
    protected = sum(r["protected"] for r in records)
    summary = {
        "case": case["id"],
        "plant": kind,
        "arm": arm,
        "configuration": config,
        "tuning": tuning,
        "case_role": case["role"],
        "information": case["information"],
        "initial": case["initial"],
        "age_s": age,
        "delay_s": delay,
        "commands": len(records),
        "states": len(states),
        "execution_error": error,
        "protected_decisions": protected,
        "external_guard_decisions": sum(r["external_tracking_guard"] for r in records),
        "statuses": dict(Counter(r["status"] for r in records)),
        "changed_commands": sum(not np.array_equal(r["proposal"], r["selected"]) for r in records),
        "max_selected_norm": max(
            (float(np.linalg.norm(r["selected"])) for r in records), default=0
        ),
        "effort_integral": sum(float(np.linalg.norm(r["applied_this_tick"])) for r in records),
        "policy_wall_max": max((r["policy_wall_s"] for r in records), default=0),
        "policy_wall_median": float(np.median([r["policy_wall_s"] for r in records]))
        if records
        else None,
        "policy_cpu_total": sum(r["policy_cpu_s"] for r in records),
        "setup_wall_s": getattr(f, "setup_wall_s", 0),
        "stored_plans": len(plan_records),
        "physical_status": physical["status"],
        "hold_status": physical.get("hold_acquired"),
        "all_filter_decisions_protected": arm in ("predictive", "barrier") and protected == 300,
        "adjudication": physical,
        "terminal_tube_valid": tube.valid_terminal,
        "steady_error_P_radius": tube.steady_radius,
        "seed": protocol["seed"],
        "noise_hash": hashlib.sha256(sensor_noise.tobytes() + force_noise.tobytes()).hexdigest(),
        "runtime_s": time.perf_counter() - start,
        "physical_validation": False,
        "scope": "selected development; fixed-input continuous adjudication, conditional method guarantees, no exact numerical-feedback theorem",
    }
    write(dest / "summary.json", summary)
    write(
        dest / "manifest.json", {p.name: digest(p) for p in sorted(dest.iterdir()) if p.is_file()}
    )
    print(
        case["id"],
        kind,
        arm,
        config.get("horizon", config.get("rates")),
        physical["status"],
        physical.get("hold_acquired"),
        protected,
        summary["external_guard_decisions"],
        flush=True,
    )
    return summary


def prepare_output(path):
    path = Path(path).expanduser().absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Symlink output")
    roots = [PACKAGE.parents[2], Path(os.environ["SAL_EVIDENCE_ROOT"]).resolve()]
    if any(path.is_relative_to(p) for p in roots):
        raise ValueError("Execution output must be outside both repositories")
    path.mkdir(parents=True, exist_ok=False)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["tune", "compare"])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--selection", type=Path)
    args = parser.parse_args()
    from .binding import verify_seal

    verified_seal = verify_seal()
    protocol = json.loads((PACKAGE / "protocol.json").read_text())
    out = prepare_output(args.output)
    write(out / "protocol.json", protocol)
    write(out / "seal.json", verified_seal)
    write(out / "source.json", {p.name: digest(p) for p in sorted(PACKAGE.glob("*.py"))})
    start = time.perf_counter()
    rows = []
    if args.action == "tune":
        case = protocol["cases"][0]
        for family in ("predictive", "barrier"):
            for index, config in enumerate(protocol["tuning"][family]):
                rows.append(
                    run_case(
                        case,
                        "hcw",
                        family,
                        config,
                        protocol,
                        out / (family + "-" + str(index)),
                        tuning=True,
                    )
                )
        selected = {}
        for family in ("predictive", "barrier"):
            candidates = [r for r in rows if r["arm"] == family]

            # Success, uninterrupted certification, utility, then lower intervention effort.
            def rank(r):
                return (
                    r["physical_status"] == "validated_containment",
                    r["all_filter_decisions_protected"],
                    r["hold_status"] == "satisfied",
                    -r["effort_integral"],
                )

            winner = max(candidates, key=rank)
            selected[family] = winner["configuration"]
        write(
            out / "selection.json",
            {"selected": selected, "rule": protocol["selection_rule"], "all_attempts": rows},
        )
    else:
        if args.selection is None:
            raise ValueError("Tuning selection required")
        selected = json.loads(args.selection.read_text())["selected"]
        write(out / "selection.json", json.loads(args.selection.read_text()))
        for case in protocol["cases"]:
            for kind in ("hcw", "nonlinear"):
                for arm in ARMS:
                    config = selected.get(arm, {})
                    rows.append(
                        run_case(
                            case,
                            kind,
                            arm,
                            config,
                            protocol,
                            out / (case["id"] + "__" + kind + "__" + arm),
                        )
                    )
    write(
        out / "results.json",
        {
            "action": args.action,
            "rows": rows,
            "count": len(rows),
            "elapsed_s": time.perf_counter() - start,
            "final_evaluation": False,
        },
    )
    write(
        out / "manifest.json",
        {str(p.relative_to(out)): digest(p) for p in sorted(out.rglob("*")) if p.is_file()},
    )


if __name__ == "__main__":
    main()
