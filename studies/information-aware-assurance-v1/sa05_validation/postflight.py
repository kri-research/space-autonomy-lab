"""Read-only independent relative-ODE and endpoint analysis of every stored cell.

This audit imports the separately written ODE reference, not the Basilisk plant,
its adjudicator, the planner or the source of primary summary calculations.
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


def main():
    study, directory, destination = map(Path, sys.argv[1:4])
    if destination.exists():
        raise ValueError("New audit output required")
    sys.path.insert(0, str(study))
    from fractions import Fraction

    from sa05.reference import nonlinear

    def q(x):
        return float(Fraction(x))

    cases = {c["unit"]: c for c in json.loads((directory / "inputs.json").read_text())}
    rows = json.loads((directory / "results.json").read_text())
    checks = []
    for row in rows:
        if row["status"] != "completed":
            checks.append(
                dict(
                    unit=row["unit"],
                    method=row["method"],
                    status="not_replayed_incomplete_source_cell",
                )
            )
            continue
        c = cases[row["unit"]]
        evidence = json.loads(
            (directory / "cases" / (row["unit"] + "--" + row["method"] + ".json")).read_text()
        )["evidence"]
        initial = tuple(map(q, c["initial_state"]))
        eta, disturbance = q(c["effectiveness"]), tuple(map(q, c["disturbance"]))
        action = tuple(map(q, row["action"]))
        apply = c["application_ms"] / 1000
        times = [t["at_ms"] / 1000 for t in evidence["trajectory"]]
        reference = nonlinear(
            initial,
            [
                (apply, (0, 0), eta, disturbance),
                (1.2, action, eta, disturbance),
                (4.2, (0, 0), eta, disturbance),
            ],
            times,
        )
        states = [np.asarray(p) for _, p in reference]
        recorded = np.asarray([x["state"] for x in evidence["trajectory"]])
        errors = np.abs(np.asarray(states) - recorded)
        if len(states) != len(recorded):
            raise ValueError("Reference sample membership")
        violated = any(
            abs(p[0]) > 8 + 1e-5
            or p[1] < -60 - 1e-5
            or p[1] > -30 + 1e-5
            or math.hypot(p[0], p[1]) < 10 - 1e-5
            for p in states
        )
        clear = all(math.hypot(p[0], p[1]) < 100 and max(abs(p[2]), abs(p[3])) < 1 for p in states)
        dwell = longest = 0
        for j in range(len(states) - 1):
            a, b = states[j], states[j + 1]
            dt = times[j + 1] - times[j]
            ppad = 0.1 * dt * dt / 8 + 1e-5
            vpad = 0.1 * dt / 2 + 1e-7
            lows = [min(a[k], b[k]) - (ppad if k < 2 else vpad) for k in range(4)]
            highs = [max(a[k], b[k]) + (ppad if k < 2 else vpad) for k in range(4)]
            nearest = [
                0 if lows[k] <= 0 <= highs[k] else min(abs(lows[k]), abs(highs[k]))
                for k in range(2)
            ]
            clear &= (
                lows[0] >= -8
                and highs[0] <= 8
                and lows[1] >= -60
                and highs[1] <= -30
                and sum(v * v for v in nearest) > 100
            )
            goal = (
                lows[0] >= -0.35
                and highs[0] <= 0.35
                and lows[1] >= -40.35
                and highs[1] <= -39.65
                and sum(max(abs(lows[k]), abs(highs[k])) ** 2 for k in (2, 3)) <= 0.05**2
            )
            dwell = dwell + round(1000 * dt) if goal else 0
            longest = max(longest, dwell)
        before = states[0]
        initial_goal = (
            abs(before[0]) <= 0.35
            and abs(before[1] + 40) <= 0.35
            and math.hypot(before[2], before[3]) <= 0.05
        )
        category = "violated" if violated else "numerically_contained" if clear else "ambiguous"
        acquisition = bool(clear and longest >= 2000 and not initial_goal)
        final = states[-1]
        change = final[0] ** 2 + (final[1] + 40) ** 2 - initial[0] ** 2 - (initial[1] + 40) ** 2
        good = (
            errors[:, :2].max() < 1e-5
            and errors[:, 2:].max() < 1e-7
            and category == row["constraint_status"]
            and longest == row["dwell_lower_ms"]
            and acquisition == row["acquired_goal"]
            and abs(change - row["task_potential_change_m2"]) < 5e-5
        )
        checks.append(
            dict(
                unit=row["unit"],
                method=row["method"],
                status="matched" if good else "mismatch",
                samples=len(states),
                max_position_error_m=float(errors[:, :2].max()),
                max_velocity_error_mps=float(errors[:, 2:].max()),
                recomputed_constraint_status=category,
                recomputed_dwell_lower_ms=longest,
                recomputed_acquired_goal=acquisition,
                potential_difference_m2=float(change - row["task_potential_change_m2"]),
            )
        )
    result = dict(
        schema="iaa-sa05-independent-numerical-audit/1",
        audit_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        reference_source_sha256=hashlib.sha256(
            (study / "sa05/reference.py").read_bytes()
        ).hexdigest(),
        original_manifest_sha256=hashlib.sha256(
            (directory / "manifest.json").read_bytes()
        ).hexdigest(),
        checked_cells=sum(r["status"] == "matched" for r in checks),
        mismatches=sum(r["status"] == "mismatch" for r in checks),
        unexecuted_cells=sum(r["status"].startswith("not_replayed") for r in checks),
        checks=checks,
        physical_validation=False,
        external_replication=False,
        limitation=(
            "Same model constants and numerical allowances; separately expressed ODE, "
            "force frame and adjudication. Numerical corroboration, "
            "not a formal roundoff proof."
        ),
    )
    destination.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}))
    return int(result["mismatches"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
