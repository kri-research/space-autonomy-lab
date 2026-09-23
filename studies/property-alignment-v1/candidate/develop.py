"""Bounded Task06 development execution; no historical or protected campaign."""

from pathlib import Path
from fractions import Fraction as Q
from dataclasses import replace
from itertools import product
from datetime import datetime, timezone
from collections import Counter
import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import numpy as np
from candidate.scalar import ScalarBox, common_inputs, action_is_safe, held_duration_bracket
from candidate.information import Hypothesis, InformationSet
from candidate.fixtures import fixtures, PAIR_ACTIONS, SINGLE_BRAKES
from candidate.certify import decide, certify_action
from candidate.affine import obstruction, recheck_certificate
from candidate.comparators import compare
from candidate.heuristic import individual_wall_scores

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, Q):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write(path, data):
    with Path(path).open("x") as f:
        json.dump(data, f, indent=2, sort_keys=True, default=plain, allow_nan=False)
        f.write("\n")


def inventory():
    paths = []
    for directory in (
        "candidate",
        "specification",
        "adjudication",
        "protective",
        "causal",
        "baseline/validation",
    ):
        paths.extend((ROOT / directory).glob("*.py"))
    paths.extend(
        ROOT / p
        for p in (
            "specification/property_contract.json",
            "candidate/protocol.json",
            "protective/requirements.txt",
        )
    )
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths))}


def scalar_search():
    rows = []
    mismatches = []
    count = 0
    for seed in range(512):
        r = random.Random(60620260923 + seed)
        center = Q(r.randrange(-80, 81), 100)
        radius = Q(r.randrange(0, 11), 100)
        speed = Q(r.randrange(-40, 41), 100)
        ve = Q(r.randrange(0, 6), 100)
        box = ScalarBox(center - radius, center + radius, speed - ve, speed + ve)
        t = r.choice([Q(1, 4), Q(1, 2), Q(1), Q(2)])
        umax = Q(r.randrange(5, 51), 100)
        eta = (Q(r.randrange(0, 11), 10), Q(1))
        w = Q(r.randrange(0, 6), 100)
        kwargs = dict(authority=umax, effectiveness=eta, disturbance=w)
        result = common_inputs([box], t, **kwargs)
        checks = []
        for j in range(17):
            u = umax * Q(j - 8, 8)
            exact = action_is_safe([box], u, t, **kwargs)
            predicted = result["status"] == "exact_feasible_interval" and Q(
                result["lower"]
            ) <= u <= Q(result["upper"])
            count += 1
            checks.append(
                {"u": str(u), "exact_extrema_safe": exact, "interval_predicts_safe": predicted}
            )
            if predicted != exact:
                mismatches.append((seed, str(u)))
        rows.append(
            {
                "seed_offset": seed,
                "box": [str(getattr(box, k)) for k in ("qlo", "qhi", "vlo", "vhi")],
                "duration_s": str(t),
                "authority": str(umax),
                "effectiveness": list(map(str, eta)),
                "disturbance": str(w),
                "result": result,
                "checks": checks,
            }
        )
    pair = [ScalarBox(".9", ".9", ".2", ".2"), ScalarBox("-.9", "-.9", "-.2", "-.2")]
    return {
        "cases": rows,
        "command_checks": count,
        "mismatches": mismatches,
        "symmetric_pair_held_duration": held_duration_bracket(pair, 2),
        "exact_half_second": common_inputs(pair, Q(1, 2)),
    }


def grid_cases():
    cases = {}
    for i, (clearance, speed, eta) in enumerate(
        product((".0005", ".002", ".006", ".02"), ("-.01", "0", ".01", ".04"), ("1/2", "1"))
    ):
        # This product has32 cases; a second16-case bounded-information slice completes48.
        h = Hypothesis.point((0, -27 - Q(clearance), 0, Q(speed)))
        cases[f"exact-{i:02d}"] = InformationSet((h,), effectiveness=(Q(eta), Q(1)))
    for i, (clearance, speed) in enumerate(
        product((".0005", ".002", ".006", ".02"), ("-.01", "0", ".01", ".04"))
    ):
        h = Hypothesis(
            (0, -27 - Q(clearance) - Q("0.0001"), 0, Q(speed) - Q(".0001")),
            (0, -27 - Q(clearance) + Q("0.0001"), 0, Q(speed) + Q(".0001")),
        )
        cases[f"bounded-{i:02d}"] = InformationSet((h,), disturbance=Q("0.00001"))
    assert len(cases) == 48
    return cases


def recovery(name, hypothesis, brake, model, output):
    from causal.native import Plant, components
    from causal.qualification import reference
    from causal.experiment import evaluate_execution, save_csv

    initial = list(map(float, hypothesis.lower))
    plant = Plant(model, initial)
    cfg, *_ = components()
    n = cfg.mean_motion_rad_s
    states = [[0.0, *initial]]
    schedule = []
    commands = []
    origin = None
    error = None
    state = np.array(initial)
    try:
        for k in range(300):
            if k == 0:
                u = np.array(list(map(float, brake)))
            else:
                if origin is None:
                    origin = state.copy()
                q, v, a = reference(origin, k - 1.0, duration=180.0)
                u = (
                    a
                    + 0.01 * (q - state[:2])
                    + 0.2 * (v - state[2:])
                    - np.array([3 * n * n * state[0] + 2 * n * state[3], -2 * n * state[2]])
                )
                norm = np.linalg.norm(u)
                if norm > 0.02:
                    u *= 0.02 / norm
            if sum(Q(float(value)) ** 2 for value in u) > Q(1, 50) ** 2:
                u *= 0.02 * (1.0 - 1.0e-12) / np.linalg.norm(u)
            if sum(Q(float(value)) ** 2 for value in u) > Q(1, 50) ** 2:
                raise ArithmeticError("Represented control exceeds exact authority")
            commands.append([k, *u.tolist()])
            for j in range(4):
                t = k + j / 4
                schedule.append((t, t + 0.25, u.tolist()))
                state = plant.step(u)
                states.append([t + 0.25, *state.tolist()])
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
    dest = output / "recovery" / f"{name}__{model}"
    dest.mkdir(parents=True, exist_ok=False)
    save_csv(dest / "states.csv", ["time_s", "x_m", "y_m", "vx_mps", "vy_mps"], states)
    save_csv(dest / "commands.csv", ["time_s", "ax_mps2", "ay_mps2"], commands)
    judged, enclosures = (
        evaluate_execution(model, hypothesis.enclosure(), schedule, states, {})
        if error is None
        else ({"status": "unresolved", "reason": error}, [])
    )
    if enclosures:
        save_csv(
            dest / "enclosures.csv",
            [
                "time_s",
                *[
                    key + suffix
                    for key in ("x_m", "y_m", "vx_mps", "vy_mps")
                    for suffix in ("_lo", "_hi")
                ],
            ],
            enclosures,
        )
    result = {
        "case": name,
        "model": model,
        "initial": initial,
        "initial_exact": list(map(str, hypothesis.lower)),
        "validation_initial": "outward enclosure of exact rational hypothesis",
        "first_brake": list(map(str, brake)),
        "commands": len(commands),
        "error": error,
        "adjudication": judged,
        "evidence": "individual known-state fixed-input existence witness, not shared-policy recovery",
    }
    write(dest / "result.json", result)
    return result


def run(output):
    before = inventory()
    expected = json.loads((PACKAGE / "seal.json").read_text())
    if before != expected["source_sha256"]:
        raise ValueError("Source changed after developmental seal")
    raw = output.expanduser().absolute()
    if any(p.is_symlink() for p in (raw, *raw.parents)):
        raise ValueError("No symlink output")
    output = raw.resolve()
    evidence = Path(os.environ["SAL_EVIDENCE_ROOT"]).resolve()
    if output.is_relative_to(ROOT.parents[1]) or output.is_relative_to(evidence):
        raise ValueError("Output must be outside both repositories")
    output.mkdir(parents=True, exist_ok=False)
    write(
        output / "inputs.json",
        {
            "protocol": json.loads((PACKAGE / "protocol.json").read_text()),
            "seal": expected,
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    cases = fixtures()
    write(output / "fixture_inputs.json", {name: info.payload() for name, info in cases.items()})
    scalar = scalar_search()
    write(output / "scalar.json", scalar)
    results = []
    comparisons = []
    for name, info in cases.items():
        result = decide(info)
        if result.get("negative", {}).get("status") == "proved_no_common_held_command":
            assert recheck_certificate(info, result["negative"])["proved"]
        fixed = certify_action(info, PAIR_ACTIONS[name]) if name in PAIR_ACTIONS else None
        nonlinear = (
            certify_action(info, tuple(Q(x) for x in result["action"]), "nonlinear")
            if result.get("action")
            else None
        )
        row = {
            "case": name,
            "candidate": result,
            "fixed_pair_action": fixed,
            "nonlinear_same_action": nonlinear,
        }
        results.append(row)
        write(output / (name + ".json"), row)
        comparison = compare(info)
        comparison["individual_stopping_heuristic"] = individual_wall_scores(info)
        comparisons.append({"case": name, **comparison})
        print(name, result["status"], comparison["status"], flush=True)
    write(output / "fixtures.json", results)
    write(output / "comparisons.json", comparisons)
    grid = []
    for name, info in grid_cases().items():
        result = decide(info)
        grid.append({"case": name, "input": info.payload(), "candidate": result})
    write(output / "grid.json", grid)
    # Removing the all-hypotheses quantifier is a deliberately invalid shortcut.
    mean_rows = []
    for name in ("opposed_radial", "three_face_conflict", "correlated_union"):
        info = cases[name]
        points = np.array(
            [
                [float((a + b) / 2) for a, b in zip(h.lower, h.upper, strict=True)]
                for h in info.hypotheses
            ]
        )
        mean = InformationSet((Hypothesis.point(tuple(map(float, points.mean(axis=0)))),))
        choice = decide(mean)
        actual = (
            certify_action(info, tuple(Q(v) for v in choice["action"]))
            if choice.get("action")
            else None
        )
        mean_rows.append(
            {
                "case": name,
                "mean_only": choice,
                "full_set_recheck": actual,
                "shortcut_is_valid": False,
            }
        )
    write(output / "mean_ablation.json", mean_rows)
    hull = replace(
        cases["correlated_union"],
        hypotheses=(cases["correlated_union"].hull(),),
        kind="outer_enclosure_only",
    )
    write(
        output / "representation_ablation.json",
        {
            "union_zero": certify_action(cases["correlated_union"], (0, 0)),
            "hull_zero": certify_action(hull, (0, 0)),
            "hull_negative": obstruction(hull),
        },
    )
    recoveries = []
    for name, brake in SINGLE_BRAKES.items():
        for model in ("hcw", "nonlinear"):
            result = recovery(name, cases[name].hypotheses[0], brake, model, output)
            recoveries.append(result)
            print("recovery", name, model, result["adjudication"]["status"], flush=True)
    write(output / "recoveries.json", recoveries)
    if inventory() != before:
        raise RuntimeError("Scientific source changed during execution")
    positive = sum(row["candidate"]["status"] == "certified_common_prefix" for row in results)
    negative = sum(row["candidate"]["status"] == "proved_no_common_held_command" for row in results)
    summary = {
        "schema": "sal-candidate-development-result/1",
        "status": "completed",
        "named_cases": len(results),
        "named_positive": positive,
        "named_negative": negative,
        "named_unresolved": len(results) - positive - negative,
        "grid_cases": len(grid),
        "grid_statuses": dict(Counter(x["candidate"]["status"] for x in grid)),
        "scalar_checks": scalar["command_checks"],
        "scalar_disagreements": len(scalar["mismatches"]),
        "individual_recovery_runs": len(recoveries),
        "recovery_statuses": dict(Counter(x["adjudication"]["status"] for x in recoveries)),
        "baseline_protected_prefix_checks_unresolved": sum(
            v.get("protected", False)
            and v.get("separate_prefix_check", {}).get("status") != "certified_common_prefix"
            for c in comparisons
            for v in c.get("methods", {}).values()
        ),
        "source_sha256": before,
        "python": platform.python_version(),
        "platform": platform.system(),
        "protected_evaluation_accessed": False,
        "physical_validation": False,
        "broad_novelty_established": False,
        "limit": "Finite common prefixes and necessary HCW obstructions; no invented general recovery or superiority claim",
    }
    write(output / "summary.json", summary)
    write(
        output / "manifest.json",
        {
            p.relative_to(output).as_posix(): digest(p)
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
