"""Readiness and independent-metrology checks; no actuation or device transport."""

from fractions import Fraction as Q
import argparse
import json
from pathlib import Path

REQUIRED = (
    "device_id",
    "processor_model",
    "sensor_model",
    "actuator_model",
    "independent_metrology_model",
    "operator_id",
    "safety_supervisor_id",
    "trial_specific_approval_artifact",
    "emergency_stop_test_artifact",
    "parameter_identification_artifact",
    "metrology_calibration_artifact",
    "clock_alignment_artifact",
    "frozen_source_commit",
    "frozen_initial_states_artifact",
    "frozen_analysis_artifact",
    "session_plan_artifact",
)
NUMERIC = (
    "position_uncertainty_m",
    "velocity_uncertainty_mps",
    "actuator_state_uncertainty_mps2",
    "clock_alignment_bound_s",
    "sensor_latency_upper_s",
    "actuation_latency_upper_s",
    "reset_tolerance_m",
)


def readiness(config):
    missing = [k for k in REQUIRED if not isinstance(config.get(k), str) or not config[k].strip()]
    for k in NUMERIC:
        value = config.get(k)
        try:
            if isinstance(value, bool) or value is None or Q(str(value)) < 0:
                raise ValueError()
        except (ValueError, TypeError, ZeroDivisionError):
            missing.append(k)
    if config.get("metrology_independent_of_controller") is not True:
        missing.append("metrology_independent_of_controller")
    if config.get("model_assumptions_reviewed") is not True:
        missing.append("model_assumptions_reviewed")
    return {
        "structural_readiness": not missing,
        "missing": missing,
        "authorization_verified": False,
        "physical_driver_implemented": False,
        "may_energize_equipment": False,
        "scope": "Checklist completeness does not authenticate approvals or prove safe operation",
    }


def _q(value):
    if isinstance(value, bool):
        raise ValueError("Boolean physical value")
    return Q(str(value))


def metrology_adjudicate(
    samples,
    *,
    position_error_m,
    alignment_error_s,
    speed_bound_mps,
    maximum_gap_s,
    expected_start_s,
    expected_end_s,
    guard_events=(),
):
    """Closed triangle check under SUPPLIED deterministic metrology and speed bounds.

    Returned containment is conditional on those externally established bounds.
    Unknown sampling gaps or uncertain boundary signs are never counted safe.
    Guard events are retained regardless of the position verdict.
    """
    error, align, speed, gap = map(
        _q, (position_error_m, alignment_error_s, speed_bound_mps, maximum_gap_s)
    )
    start, end = map(_q, (expected_start_s, expected_end_s))
    if min(error, align, speed) < 0 or gap <= 0 or end <= start:
        raise ValueError("Invalid metrology bounds")
    normal = ((Q(1), Q(0)), (Q(-3, 5), Q(4, 5)), (Q(-3, 5), Q(-4, 5)))
    if not samples:
        return {"status": "unresolved", "reason": "no_samples", "guard_events": list(guard_events)}
    ts = [_q(s["time_s"]) for s in samples]
    if ts != sorted(set(ts)) or ts[0] != start or ts[-1] != end:
        raise ValueError("Missing or unordered time coverage")
    radii = [sum(abs(c) for c in n) * error + speed * align for n in normal]
    bounds = []
    for s in samples:
        xy = tuple(_q(v) for v in s["position_m"])
        if len(xy) != 2:
            raise ValueError("Planar position required")
        bounds.append(
            [
                (
                    sum(c * x for c, x in zip(n, xy, strict=True)) - e,
                    sum(c * x for c, x in zip(n, xy, strict=True)) + e,
                )
                for n, e in zip(normal, radii, strict=True)
            ]
        )
    witnesses = [
        {"sample": i, "face": j, "projection_lower": str(lo)}
        for i, row in enumerate(bounds)
        for j, (lo, hi) in enumerate(row)
        if lo > 1
    ]
    reasons = []
    if any(b - a > gap for a, b in zip(ts[:-1], ts[1:], strict=True)):
        reasons.append("metrology_gap")
    for i in range(len(ts) - 1):
        # A bounded-speed curve is within v*dt/2 of its nearest sampled endpoint.
        pad = speed * (ts[i + 1] - ts[i]) / 2
        if any(max(bounds[i][j][1], bounds[i + 1][j][1]) + pad > 1 for j in range(3)):
            reasons.append("continuous_boundary_uncertainty")
    return {
        "status": "violation" if witnesses else "unresolved" if reasons else "contained",
        "witnesses": witnesses,
        "reasons": sorted(set(reasons)),
        "guard_events": list(guard_events),
        "physical_validation_claimed": False,
        "scope": "conditional on supplied independent metrology/speed/error bounds; origin authentication is external",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("configuration", type=Path)
    a = parser.parse_args()
    result = readiness(json.loads(a.configuration.read_text()))
    print(json.dumps(result, indent=2))
    if not result["structural_readiness"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
