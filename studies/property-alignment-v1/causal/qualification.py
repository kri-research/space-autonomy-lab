"""Predeclared feasibility witnesses and classification-only replay.
Witnesses concern explicit held inputs; they are not a tuned competing filter.
"""

from pathlib import Path
import json
import numpy as np
from .native import Plant, components
from .experiment import evaluate_execution, save_csv
from .screen import inspect_arcs
from .io import ROOT, save_json, manifest
from adjudication.flow import Model, propagate_schedule


def reference(initial, t, duration=180.0):
    q0 = np.asarray(initial[:2])
    v0 = np.asarray(initial[2:])
    target = np.array([0.0, -30.0])
    if t >= duration:
        return target, np.zeros(2), np.zeros(2)
    delta = target - q0
    c2 = (3 * delta - 2 * v0 * duration) / duration**2
    c3 = (-2 * delta + v0 * duration) / duration**3
    return (
        q0 + v0 * t + c2 * t * t + c3 * t**3,
        v0 + 2 * c2 * t + 3 * c3 * t * t,
        2 * c2 + 6 * c3 * t,
    )


def qualify(case, kind, output, protocol):
    dest = Path(output) / "qualification" / f"{case['id']}__{kind}"
    dest.mkdir(parents=True, exist_ok=False)
    plant = Plant(kind, case["initial"])
    cfg, *_ = components()
    state = np.array(case["initial"])
    states = [[0.0, *state.tolist()]]
    schedule = []
    status = "complete"
    error = None
    try:
        for k in range(300):
            q, v, a = reference(case["initial"], float(k))
            target_acceleration = a + 0.01 * (q - state[:2]) + 0.2 * (v - state[2:])
            n = cfg.mean_motion_rad_s
            u = target_acceleration - np.array(
                [3 * n * n * state[0] + 2 * n * state[3], -2 * n * state[2]]
            )
            if np.linalg.norm(u) > 0.02 + 1e-12:
                raise ArithmeticError("Qualification command outside bound; no retuning")
            for j in range(4):
                t = k + j / 4
                schedule.append((t, t + 0.25, u.tolist()))
                state = plant.step(u)
                states.append([t + 0.25, *state.tolist()])
    except Exception as exc:
        status = "failed"
        error = type(exc).__name__ + ":" + str(exc)
    save_csv(dest / "states.csv", ["time_s", "x_m", "y_m", "vx_mps", "vy_mps"], states)
    save_json(dest / "schedule.json", schedule)
    result, enclosure = (
        evaluate_execution(kind, case["initial"], schedule, states, protocol)
        if status == "complete"
        else ({"status": "unresolved"}, [])
    )
    if enclosure:
        save_csv(
            dest / "enclosures.csv",
            [
                "time_s",
                *[n + s for n in ("x_m", "y_m", "vx_mps", "vy_mps") for s in ("_lo", "_hi")],
            ],
            enclosure,
        )
    certified = (
        result["status"] == "validated_containment" and result.get("hold_acquired") == "satisfied"
    )
    record = {
        "case": case["id"],
        "plant": kind,
        "execution_status": status,
        "error": error,
        "finite_horizon_recoverability": "demonstrated_fixed_input_continuation"
        if certified
        else "unassessed",
        "scope": "Known initial state, ideal information, no disturbances, supplied held inputs on [0,300]. Neither robust/infinite-horizon recovery nor a competing baseline.",
        "adjudication": result,
        "selected_cases_changed": False,
    }
    save_json(dest / "result.json", record)
    manifest(dest)
    return record


def classification_only(output):
    doc = json.loads((ROOT / "adjudication/input_commands.json").read_text())
    schedule = [(k, k + 1, u) for k, u in enumerate(doc["commands_mps2"])]
    arcs = propagate_schedule(Model("nonlinear"), [0.0, -97.5, 0.0, 0.12], schedule)
    results = {
        p: inspect_arcs(arcs, p, 10.0, max_cells=100000) for p in ("in_band", "closed_union")
    }
    record = {
        "kind": "classification_only_same_fixed_path",
        "command_input": "adjudication/input_commands.json",
        "initial": [0.0, -97.5, 0.0, 0.12],
        "plant": "nonlinear",
        "predicate_tolerance_m": 1e-9,
        "shared_command_sequence": True,
        "shared_continuous_arcs": True,
        "control_modified": False,
        "outcomes_previously_known": True,
        "results": results,
    }
    save_json(Path(output) / "classification_only.json", record)
    return record
