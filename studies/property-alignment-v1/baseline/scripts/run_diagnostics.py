#!/usr/bin/env python3
"""Execute the sealed, additive ideal-information diagnostic and numerical checks."""

from __future__ import annotations
import csv
import hashlib
import json
import math
import platform
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import scipy
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.loader import config, originals, FilterHealth, SOURCES
from validation.properties import inside_union, union_excess, old_excess, inside_hold


def write_csv(path, rows):
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def relative_rhs(t, s, u, mu, R):
    """Independent circular-chief rotating-frame central-gravity equations.

    expm1/log1p avoids subtracting two nearly equal radial gravity values.
    This implementation calls none of the original dynamics functions.
    """
    x, y, z, vx, vy, vz = s
    n = math.sqrt(mu / R**3)
    delta = 2 * x / R + (x * x + y * y + z * z) / R**2
    inv_factor = math.exp(-1.5 * math.log1p(delta))
    radial_diff = -mu / R**2 * math.expm1(math.log1p(x / R) - 1.5 * math.log1p(delta))
    return [
        vx,
        vy,
        vz,
        radial_diff + 2 * n * vy + n * n * x + u[0],
        -mu / R**3 * y * inv_factor - 2 * n * vx + n * n * y + u[1],
        -mu / R**3 * z * inv_factor + u[2],
    ]


def main():
    protocol_path = ROOT / "data/diagnostic_protocol.json"
    raw = protocol_path.read_bytes()
    protocol = json.loads(raw)
    expected = (ROOT / "data/diagnostic_protocol.sha256").read_text().split()[0]
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Diagnostic protocol changed after sealing")
    c = config()
    d4, d5, g4, g5, ctrl = originals(expanded_cache=True)
    controller = ctrl.DeterministicHoldController(c)
    initial = np.array(protocol["initial_state_planar"], float)
    if not inside_union(initial):
        raise ValueError("Selected initial state must be in S")
    mu, R = c.gravitational_parameter_m3_s2, c.reference_radius_m
    chief = d5.circular_chief_state(mu, R)
    rho0 = np.array([initial[0], initial[1], 0.0, initial[2], initial[3], 0.0])
    covariance = np.diag(protocol["snapshot_covariance_diagonal"])
    results = {}
    all_states = []
    all_commands = []
    paths = {}
    commands_by_plant = {}
    for plant in ["HCW", "nonlinear"]:
        monitor = ctrl.EstimatedGeometryMonitor(c, controller, controller.controller_identity)
        state = initial.copy() if plant == "HCW" else d5.pair_from_relative(chief, rho0)
        planar = initial.copy()
        states = []
        commands = []

        def record(t, planar):
            row = {
                "plant": plant,
                "time_s": float(t),
                **dict(zip(["x_m", "y_m", "vx_mps", "vy_mps"], map(float, planar))),
                "separation_m": float(np.linalg.norm(planar[:2])),
                "inside_union": inside_union(planar),
                "union_excess_m": union_excess(planar),
                "old_excess_m": old_excess(planar),
                "inside_hold": inside_hold(planar),
            }
            states.append(row)

        record(0.0, planar)
        for k in range(protocol["horizon_s"]):
            snap = SimpleNamespace(
                time_s=float(k),
                mean=planar.copy(),
                covariance=covariance.copy(),
                health=FilterHealth.VALID,
                prediction_only_age_s=0.0,
                consecutive_innovation_rejections=0,
            )
            proposal = controller.decide(ctrl.observation_from_snapshot(snap))
            decision = monitor.gate(snap, proposal)
            u = decision.executed_acceleration_mps2.copy()
            row = {
                "plant": plant,
                "time_s": float(k),
                "proposed_ax_mps2": float(proposal.acceleration_mps2[0]),
                "proposed_ay_mps2": float(proposal.acceleration_mps2[1]),
                "applied_ax_mps2": float(u[0]),
                "applied_ay_mps2": float(u[1]),
                "overridden": bool(decision.overridden),
                "command_changed": not np.array_equal(u, proposal.acceleration_mps2),
                "reason": decision.reason or "accepted",
                "following_interval_s": 1.0,
            }
            commands.append(row)
            for j in range(4):
                if plant == "HCW":
                    state = d4.propagate_exact(state, u, c.mean_motion_rad_s, 0.25)
                    planar = state.copy()
                else:
                    state = d5.propagate_fixed(state, np.r_[u, 0.0], mu, 0.25, 0.1)
                    rho = d5.pair_to_relative(state)
                    planar = rho[[0, 1, 3, 4]]
                if not np.all(np.isfinite(planar)):
                    raise ArithmeticError("Nonfinite trajectory")
                record(k + (j + 1) / 4, planar)
        paths[plant] = np.array(
            [[r[a] for a in ["x_m", "y_m", "vx_mps", "vy_mps"]] for r in states]
        )
        commands_by_plant[plant] = np.array(
            [[r["applied_ax_mps2"], r["applied_ay_mps2"]] for r in commands]
        )
        outside = [i for i, r in enumerate(states) if not r["inside_union"]]
        first = outside[0] if outside else None
        # Sample-based hold duration; no claim of between-sample membership.
        longest = 0.0
        run_start = None
        first_hold_observed = None
        for r in states:
            if r["inside_hold"]:
                if run_start is None:
                    run_start = r["time_s"]
                longest = max(longest, r["time_s"] - run_start)
                if first_hold_observed is None and r["time_s"] - run_start >= 60:
                    first_hold_observed = r["time_s"]
            else:
                run_start = None
        results[plant] = {
            "command_decisions": len(commands),
            "state_observations": len(states),
            "initial_inside_union": bool(states[0]["inside_union"]),
            "sampled_outside_observations": len(outside),
            "first_observed_violation_bracket_s": None
            if first is None
            else [states[first - 1]["time_s"], states[first]["time_s"]],
            "minimum_sampled_separation_m": min(r["separation_m"] for r in states),
            "maximum_sampled_union_excess_m": max(r["union_excess_m"] for r in states),
            "maximum_sampled_old_excess_m": max(r["old_excess_m"] for r in states),
            "override_decisions": sum(r["overridden"] for r in commands),
            "changed_commands": sum(r["command_changed"] for r in commands),
            "maximum_sampled_hold_run_s": longest,
            "first_60s_sampled_hold_completion_s": first_hold_observed,
            "first_observed_violation_command": None
            if first is None
            else commands[min(299, int(states[first]["time_s"]))],
        }
        all_states.extend(states)
        all_commands.extend(commands)
        print(plant, results[plant], flush=True)
    write_csv(ROOT / "data/diagnostic_states.csv", all_states)
    write_csv(ROOT / "data/diagnostic_commands.csv", all_commands)
    # Fixed-command convergence, not a newly tuned closed loop at each step size.
    u_seq = commands_by_plant["nonlinear"]
    replays = {0.1: paths["nonlinear"]}
    convergence = []
    for h in [0.05, 0.025]:
        state = d5.pair_from_relative(chief, rho0)
        trace = [initial.copy()]
        for u in u_seq:
            for _ in range(4):
                state = d5.propagate_fixed(state, np.r_[u, 0.0], mu, 0.25, h)
                rho = d5.pair_to_relative(state)
                trace.append(rho[[0, 1, 3, 4]])
        replays[h] = np.array(trace)
    rho = rho0.copy()
    independent = [initial.copy()]
    for u in u_seq:
        out = solve_ivp(
            relative_rhs,
            (0.0, 1.0),
            rho,
            method="DOP853",
            t_eval=[0.25, 0.5, 0.75, 1.0],
            args=(np.r_[u, 0.0], mu, R),
            rtol=1e-11,
            atol=1e-12,
        )
        if not out.success:
            raise ArithmeticError(out.message)
        independent.extend(out.y[[0, 1, 3, 4], :].T)
        rho = out.y[:, -1]
    independent = np.array(independent)
    for h, trace in replays.items():
        delta = trace - independent
        convergence.append(
            {
                "maximum_rk4_step_s": h,
                "max_position_difference_to_independent_m": float(
                    np.max(np.linalg.norm(delta[:, :2], axis=1))
                ),
                "max_velocity_difference_to_independent_mps": float(
                    np.max(np.linalg.norm(delta[:, 2:], axis=1))
                ),
                "sampled_membership_disagreements": sum(
                    inside_union(a) != inside_union(b) for a, b in zip(trace, independent)
                ),
                "max_position_difference_to_production_m": float(
                    np.max(np.linalg.norm(trace[:, :2] - replays[0.1][:, :2], axis=1))
                ),
            }
        )
    write_csv(ROOT / "data/integration_comparison.csv", convergence)
    write_csv(
        ROOT / "data/independent_relative_trace.csv",
        [
            {"time_s": i * 0.25, **dict(zip(["x_m", "y_m", "vx_mps", "vy_mps"], map(float, row)))}
            for i, row in enumerate(independent)
        ],
    )
    results["integration_comparison"] = convergence
    results["matched_closed_loop_plant_difference"] = {
        "max_position_difference_m": float(
            np.max(np.linalg.norm(paths["HCW"][:, :2] - paths["nonlinear"][:, :2], axis=1))
        ),
        "max_velocity_difference_mps": float(
            np.max(np.linalg.norm(paths["HCW"][:, 2:] - paths["nonlinear"][:, 2:], axis=1))
        ),
    }
    results["provenance"] = {
        "kind": "New deterministic ideal-information diagnostic, not historical replay",
        "protocol_sha256": expected,
        "controller_identity": controller.controller_identity,
        "lqr_gain": controller.gain.tolist(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "source_git_blobs": SOURCES,
        "command_count_excludes_terminal_observation": True,
    }
    (ROOT / "data/diagnostic_results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        (ROOT / "logs/diagnostic_failure.txt").write_text(traceback.format_exc())
        raise
