"""Exact post-hoc necessary goal-entry screen of the unchanged SA05 inputs.

No policy, trajectory solver, primary analysis or estimator is imported.
"""

import argparse
import hashlib
import json
from collections import Counter
from fractions import Fraction as Q
from pathlib import Path

INPUT_SHA256 = "72b8c3ed9552804c48e23f825aea5d99e9f8bf23a6765e61cb1f9e2c7f39a6e0"
INPUT_COMMIT = "9d921566a919ee81cc4fb2b5391069b545667ff2"
N = Q(11, 10000)
HORIZON = Q(21, 5)
DWELL = Q(2)
LATEST_ENTRY = HORIZON - DWELL
START, END = Q(7, 10), Q(6, 5)
AUTHORITY = Q(1, 50)
INITIAL_SPEED = Q(21, 500)
BOOTSTRAP_SPEED = Q(1, 5)
DISTURBANCE = Q(1, 100000)
DRIFT = 3 * N**2 * 8 + 2 * N * BOOTSTRAP_SPEED + DISTURBANCE
GOAL = ((-Q(7, 20), Q(7, 20)), (-Q(807, 20), -Q(793, 20)))


def deviation(t):
    """Absolute controlled pulse plus drift contribution at time t, exactly."""
    t = Q(t)
    if not 0 <= t <= HORIZON:
        raise ValueError("Time outside the conditional analysis horizon")
    duration = max(Q(0), min(t, END) - START)
    pulse = AUTHORITY * (duration**2 / 2 + duration * max(Q(0), t - END))
    return pulse + DRIFT * t**2 / 2


def coordinate_range(position, velocity, t=LATEST_ENTRY):
    """Whole-time range from convex upper and concave lower envelopes."""
    position, velocity, t = Q(position), Q(velocity), Q(t)
    error = deviation(t)
    return min(position, position + velocity * t - error), max(
        position, position + velocity * t + error
    )


def classify(state):
    z = tuple(Q(v) for v in state)
    if len(z) != 4 or max(map(abs, z[2:])) > INITIAL_SPEED:
        raise ValueError("Unsupported initial component speed")
    if not (-8 <= z[0] <= 8 and -60 <= z[1] <= -30):
        raise ValueError("Initial point outside the successful-trajectory geometry")
    if INITIAL_SPEED + (AUTHORITY + DRIFT) * HORIZON >= BOOTSTRAP_SPEED:
        raise ValueError("First-hitting-time bootstrap does not close")
    ranges = [coordinate_range(z[j], z[j + 2]) for j in range(2)]
    gaps = [
        max(Q(0), goal[0] - hi, lo - goal[1]) for (lo, hi), goal in zip(ranges, GOAL, strict=True)
    ]
    eligible = (
        all(lo <= z[j] <= hi for j, (lo, hi) in enumerate(GOAL))
        and z[2] ** 2 + z[3] ** 2 <= Q(1, 20) ** 2
    )
    excluded = max(gaps) > 0
    if eligible and excluded:
        raise ArithmeticError("Entry at zero cannot be excluded for an eligible point")
    return dict(
        initially_eligible_exact=eligible,
        entry_excluded=excluded,
        non_exclusion_establishes_feasibility=False,
        coordinate_ranges_m=[[str(lo), str(hi)] for lo, hi in ranges],
        coordinate_gaps_m=list(map(str, gaps)),
        separating_gap_m=str(max(gaps)),
    )


def analyze(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != INPUT_SHA256:
        raise ValueError("Input is not the fixed SA05 population")
    cases = json.loads(raw)
    if len(cases) != 112 or len({c["unit"] for c in cases}) != 112:
        raise ValueError("Wrong population membership")
    if Counter(c["stratum"] for c in cases) != dict(
        nominal=48, bounded_faults=48, outside_assumptions=16
    ):
        raise ValueError("Wrong stratum accounting")
    rows = []
    for case in cases:
        if case["stratum"] == "outside_assumptions":
            continue
        if (
            case["split"] != "held_out"
            or not Q(4, 5) <= Q(case["effectiveness"]) <= 1
            or not 700 <= case["application_ms"] <= 710
            or any(abs(Q(v)) > DISTURBANCE for v in case["disturbance"])
        ):
            raise ValueError("Unsupported in-model actuation or disturbance")
        rows.append(
            dict(unit=case["unit"], stratum=case["stratum"], **classify(case["initial_state"]))
        )
    summary = {}
    for stratum in ("nominal", "bounded_faults"):
        group = [r for r in rows if r["stratum"] == stratum]
        summary[stratum] = dict(
            units=len(group),
            initially_eligible=sum(r["initially_eligible_exact"] for r in group),
            entry_excluded=sum(r["entry_excluded"] for r in group),
            initially_ineligible_not_excluded=[
                r["unit"]
                for r in group
                if not r["initially_eligible_exact"] and not r["entry_excluded"]
            ],
        )
    gaps = [Q(r["separating_gap_m"]) for r in rows if r["entry_excluded"]]
    return dict(
        schema="kri-sa05-posthoc-attainability/1",
        analysis_date="2026-09-28",
        post_hoc=True,
        new_experiment=False,
        input_sha256=INPUT_SHA256,
        input_commit=INPUT_COMMIT,
        scope="Necessary contained-trajectory condition; non-exclusion does not prove feasibility",
        constants=dict(
            mean_motion=str(N),
            horizon_s=str(HORIZON),
            dwell_s=str(DWELL),
            latest_entry_s=str(LATEST_ENTRY),
            pulse_start_s=str(START),
            pulse_end_s=str(END),
            authority_mps2=str(AUTHORITY),
            drift_mps2=str(DRIFT),
            velocity_bootstrap_mps=str(INITIAL_SPEED + (AUTHORITY + DRIFT) * HORIZON),
            extra_at_latest_entry_m=str(deviation(LATEST_ENTRY)),
        ),
        summary=summary,
        minimum_exclusion_gap_m=str(min(gaps)) if gaps else None,
        checked_in_model_units=len(rows),
        not_analyzed_outside_assumption_units=16,
        initially_ineligible=sum(not r["initially_eligible_exact"] for r in rows),
        excluded_initially_ineligible=sum(r["entry_excluded"] for r in rows),
        checks=rows,
        original_denominators_unchanged=True,
        original_outcomes_unchanged=True,
        physical_validation=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.inputs)
    with args.output.open("x") as file:
        json.dump(result, file, indent=2, sort_keys=True)
        file.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "checks"}, sort_keys=True))
