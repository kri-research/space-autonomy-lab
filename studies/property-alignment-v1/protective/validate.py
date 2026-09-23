"""Bounded deterministic backup and matrix validation, separate from tuning."""

from pathlib import Path
from collections import Counter
import argparse
import json
import numpy as np
from .binding import verify_seal
from .certificates import check_constants
from .common import (
    Observation,
    observation_to_information,
    Tube,
    MODEL_COMPONENT,
    NUMERIC_COMPONENT,
)
from .predictive import PredictiveFilter
from .run import write, prepare_output, digest
from causal.native import Plant, components
from causal.experiment import evaluate_execution, save_csv


def validate_backup(output):
    cfg, ctrl, *_ = components()
    initial = [0.0, -97.5, 0.0, 0.12]
    primary = ctrl.DeterministicHoldController(cfg)
    from causal.experiment import ideal_snapshot

    f = PredictiveFilter(Tube(np.zeros(4), MODEL_COMPONENT + NUMERIC_COMPONENT), 160)
    plant = Plant("hcw", initial)
    state = np.array(initial)
    history = {}
    schedule = []
    commands = []
    states = [[0.0, *initial]]
    for k in range(300):
        i = observation_to_information(
            Observation(k, k, tuple(state), (0.0, 0.0, 0.0, 0.0), "ideal"), k, k, history
        )
        proposal = primary.decide(
            ctrl.observation_from_snapshot(ideal_snapshot(state, k))
        ).acceleration_mps2
        decision = f.decide(i, proposal, force_solver_failure=k > 0)
        if decision.command is None or not decision.protected:
            raise ArithmeticError("Stored/terminal backup failed")
        u = decision.command
        history[k] = u
        commands.append(
            {
                "tick": k,
                "status": decision.status,
                "selected": u.tolist(),
                "forced_solver_failure": k > 0,
            }
        )
        for j in range(4):
            t = k + j / 4
            schedule.append((t, t + 0.25, u.tolist()))
            state = plant.step(u)
            states.append([t + 0.25, *state.tolist()])
    physical, enclosures = evaluate_execution("hcw", initial, schedule, states, {})
    if physical["status"] != "validated_containment" or physical["hold_acquired"] != "satisfied":
        raise ArithmeticError("Backup fixed-input validation failed")
    write(output / "backup_commands.json", commands)
    write(output / "backup_schedule.json", schedule)
    save_csv(output / "backup_states.csv", ["time_s", "x_m", "y_m", "vx_mps", "vy_mps"], states)
    save_csv(
        output / "backup_enclosures.csv",
        ["time_s", *[n + s for n in ("x_m", "y_m", "vx_mps", "vy_mps") for s in ("_lo", "_hi")]],
        enclosures,
    )
    return {
        "kind": "single_initial_plan_with299_forced_solver_failures",
        "initial": initial,
        "horizon": 160,
        "decisions": len(commands),
        "statuses": dict(Counter(r["status"] for r in commands)),
        "adjudication": physical,
        "selected_input_bound": max(float(np.linalg.norm(r["selected"])) for r in commands),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    seal = verify_seal()
    out = prepare_output(args.output)
    constant = check_constants()
    if not constant["passed"]:
        raise ArithmeticError("Baseline constants failed independent checks")
    write(out / "constants.json", constant)
    backup = validate_backup(out)
    write(
        out / "results.json",
        {
            "status": "passed",
            "backup": backup,
            "source_seal": seal,
            "comparison_or_tuning": False,
            "scope": "One declared ideal-state software/numerical fixture, not a robustness population or hardware run",
        },
    )
    write(out / "manifest.json", {p.name: digest(p) for p in sorted(out.iterdir()) if p.is_file()})
    print(
        json.dumps(
            {
                "constants": "passed",
                "backup_statuses": backup["statuses"],
                "physical": backup["adjudication"]["status"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
