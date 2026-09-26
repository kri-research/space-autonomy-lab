"""Predeclared engineering cases and small-reference comparisons, not a campaign."""

from dataclasses import replace
from fractions import Fraction as Q
from statistics import median

from iaa.fixtures import Fixture
from iaa.plant import SensorFaults
from iaa.types import primitive

from .intervals import Interval, contract_linear
from .model import SensorContract
from .oracle import hull, scalar_history, vertices
from .runtime import run


def cases():
    default = SensorContract()
    return (
        (Fixture("sa02_nominal"), default),
        (
            Fixture(
                "sa02_delayed_and_out_of_order",
                horizon_ms=8000,
                faults=SensorFaults(range_delay_ms=200, bearing_delay_ms=400, dropout_bearing=True),
            ),
            default,
        ),
        (
            Fixture(
                "sa02_shared_and_channel_bias",
                horizon_ms=12000,
                faults=SensorFaults(
                    common_position_bias_m=(0.4, 0.2), range_bias_m=0.3, bearing_bias_rad=0.01
                ),
            ),
            default,
        ),
        (Fixture("sa02_bounded_actuator", horizon_ms=10000, effectiveness_after=0.8), default),
        (
            Fixture("sa02_outside_actuator_model", horizon_ms=10000, effectiveness_after=0.2),
            default,
        ),
        (
            Fixture(
                "sa02_late_and_lost",
                horizon_ms=16000,
                late_cycles=(8, 9),
                stalled_cycles=tuple(range(14, 25)),
            ),
            default,
        ),
        (
            Fixture(
                "sa02_invalid_sensor_packets",
                horizon_ms=12000,
                faults=SensorFaults(stamp_offset_ms=1000, invalid_range=True),
            ),
            default,
        ),
        (Fixture("sa02_packet_capacity", horizon_ms=4000), replace(default, max_packets=4)),
        (
            Fixture(
                "sa02_coarse_representation",
                horizon_ms=12000,
                faults=SensorFaults(
                    common_position_bias_m=(0.4, 0.2), range_bias_m=0.3, bearing_bias_rad=0.01
                ),
            ),
            replace(default, max_cells=4, initial_splits=2),
        ),
        (
            Fixture(
                "sa02_outside_sensor_model", horizon_ms=12000, faults=SensorFaults(range_bias_m=2.0)
            ),
            default,
        ),
    )


def evaluate(fixture, contract):
    from .intervals import sincos

    sincos.cache_clear()
    summary, events, timings = run(fixture, contract)
    decisions = [e for e in events if e.event == "decision_snapshot"]
    width_ratios = []
    point_errors = []
    nonempty_exclusions = 0
    unavailable = 0
    comparison = []
    # Evaluation-only numeric truth is copied from its separately logged
    # decision record; it never enters the observer.
    for event in decisions:
        d = event.details
        est = d["observation_set"]
        cells = est["cells"]
        prior = est["prior_at_decision"]
        if not cells:
            unavailable += 1
            continue
        nonempty_exclusions += not d["observed_true_state_in_outer_set"]
        widths = [
            max(Q(c["bounds"][j]["hi"]) for c in cells)
            - min(Q(c["bounds"][j]["lo"]) for c in cells)
            for j in range(4)
        ]
        pw = [Q(b) - Q(a) for a, b in zip(prior["lower"], prior["upper"], strict=True)]
        ratio = (widths[0] * widths[1]) / (pw[0] * pw[1]) if pw[0] * pw[1] else None
        if ratio is not None:
            width_ratios.append(float(ratio))
        point = d["proposal"]["nominal_state"]
        truth = d["evaluation_only_state_at_snapshot"]
        if point:
            point_errors.append(sum((point[j] - truth[j]) ** 2 for j in (0, 1)) ** 0.5)
        comparison.append(
            {
                "at_ms": event.at_ms,
                "status": est["status"],
                "position_widths_m": [str(w) for w in widths[:2]],
                "velocity_widths_mps": [str(w) for w in widths[2:]],
                "outer_hull_area_over_unconditioned_prior": None if ratio is None else str(ratio),
                "true_state_retained": d["observed_true_state_in_outer_set"],
                "baseline_point_available": point is not None,
                "retained_hypotheses": est["diagnostics"]["hypotheses"],
                "operation_count": est["diagnostics"]["operations"],
            }
        )
    summary.update(
        nonempty_outer_exclusions_observed=nonempty_exclusions,
        unavailable_set_updates=unavailable,
        position_area_ratio_min=round(min(width_ratios), 9) if width_ratios else None,
        position_area_ratio_max=round(max(width_ratios), 9) if width_ratios else None,
        baseline_point_position_error_max_m=round(max(point_errors), 9) if point_errors else None,
        contract=primitive(contract),
        outside_sensor_model=not injected_offset_schedule_covered(fixture, contract),
        injected_offsets_have_exact_family_member=injected_offset_schedule_covered(
            fixture, contract
        ),
        sensor_bound_validation="assumed_not_hardware_calibrated",
        sensor_model_diagnosis_provided=False,
        outside_actuator_model=fixture.effectiveness_after < 0.8,
    )
    timing = {
        "fixture": fixture.name,
        "observer_update_ns": list(timings),
        "count": len(timings),
        "median_ns": median(timings) if timings else None,
        "max_ns": max(timings) if timings else None,
        "over_50ms_modeled_whole_path": sum(t > 50000000 for t in timings),
        "scope": "one host invocation; observer only, not worst-case execution or hardware energy",
    }
    return summary, events, comparison, timing


def reference_cases():
    rows = []
    for number in range(12):
        bounds = [(-2, 2), (-1, 1)]
        constraints = [((1, 1), Q(number - 6, 10), Q(number + 2, 10)), ((2, -1), Q(-3, 2), Q(3, 2))]
        points = vertices(bounds, constraints)
        exact = hull(points)
        outer = tuple(Interval(*b) for b in bounds)
        for _ in range(4):
            for a, low, high in constraints:
                outer = contract_linear(outer, a, Interval(low, high))
        excess = [outer[j].width - (exact[j][1] - exact[j][0]) for j in range(2)]
        rows.append(
            {
                "case": number,
                "reference_vertices": primitive(points),
                "exact_hull": primitive(exact),
                "production_outer_hull": primitive(outer),
                "width_excess": primitive(excess),
                "all_reference_vertices_retained": all(
                    all(c.contains(v) for c, v in zip(outer, p, strict=True)) for p in points
                ),
            }
        )
    dynamic = scalar_history(
        [(-2, 2), (-Q(1, 10), Q(1, 10)), (-Q(1, 2), Q(1, 2))],
        [(0, Q(1, 4), Q(1, 10), 0), (2, Q(9, 20), Q(1, 10), 0)],
        3,
    )
    from iaa.types import StateBox

    from .estimator import advance
    from .model import Budget, HistorySegment
    from .oracle import hcw_point_bounds

    dynamic_outer = (Interval(-2, 2), Interval(-Q(1, 10), Q(1, 10)), Interval(-Q(1, 2), Q(1, 2)))
    for _ in range(5):
        dynamic_outer = contract_linear(dynamic_outer, (1, 0, 1), Interval(Q(3, 20), Q(7, 20)))
        dynamic_outer = contract_linear(dynamic_outer, (1, 2, 1), Interval(Q(7, 20), Q(11, 20)))
    dynamic_position = dynamic_outer[0] + dynamic_outer[1] * 3
    dynamic["production_initial_outer"] = primitive(dynamic_outer)
    dynamic["production_decision_position_outer"] = primitive(dynamic_position)
    dynamic["all_reference_vertices_retained"] = all(
        all(c.contains(v) for c, v in zip(dynamic_outer, p, strict=True))
        for p in dynamic["vertices"]
    )
    hcw = []
    initial = (Q(1, 2), Q(-45), Q(1, 100), Q(-1, 50))
    action = (Q(1, 100), Q(-1, 100))
    for duration in (Q(1, 100), Q(1, 5), Q(1), Q(3)):
        for eta in (Q(4, 5), Q(1)):
            reference = hcw_point_bounds(
                initial, action, duration, eta, (Q(1, 100000), Q(-1, 100000))
            )
            box = StateBox.around(initial, (Q(1, 10000),) * 4)
            ms = int(duration * 1000)
            outer, _ = advance(box, (HistorySegment(0, ms, action),), 0, ms, Budget(1000))
            hcw.append(
                {
                    "duration_s": str(duration),
                    "effectiveness": str(eta),
                    "reference_point_bounds": primitive(reference),
                    "production_outer": primitive(outer),
                    "reference_interval_contained": all(
                        a <= lo <= hi <= b
                        for a, (lo, hi), b in zip(outer.lower, reference, outer.upper, strict=True)
                    ),
                }
            )
    return {
        "linear_cases": rows,
        "scalar_constant_velocity_history": primitive(dynamic),
        "hcw_constant_input_reference": hcw,
        "scope": (
            "exact small linear oracle and independent rational HCW point bounds; "
            "not a second full nonlinear observer"
        ),
    }


def injected_offset_schedule_covered(fixture, contract):
    """Evaluation-only exact family membership, never fault diagnosis.

    Checks the configured latent offset signal, before measurement encoding.
    False is not itself proof that no observation history can satisfy the bounds.
    """
    offsets = tuple(
        map(
            lambda x: Q(str(x)),
            (
                *fixture.faults.common_position_bias_m,
                fixture.faults.range_bias_m,
                fixture.faults.bearing_bias_rad,
            ),
        )
    )
    for hypothesis in contract.hypotheses:
        limits = list(hypothesis.biases)
        cuts = {0, fixture.horizon_ms}
        cuts.update(
            t
            for t in (fixture.faults.start_ms, fixture.faults.end_ms)
            if 0 < t < fixture.horizon_ms
        )
        if hypothesis.active_window_ms is not None:
            cuts.update(t for t in hypothesis.active_window_ms if 0 < t < fixture.horizon_ms)
        possible = True
        ordered_cuts = sorted(cuts)
        for a, b in zip(ordered_cuts[:-1], ordered_cuts[1:], strict=True):
            t = Q(a + b, 2)
            actual_on = fixture.faults.start_ms <= t < fixture.faults.end_ms
            assumed_on = (
                hypothesis.active_window_ms is None
                or hypothesis.active_window_ms[0] <= t < hypothesis.active_window_ms[1]
            )
            for j, offset in enumerate(offsets):
                actual = offset if actual_on else Q(0)
                if assumed_on:
                    limits[j] = limits[j].intersect(Interval(actual, actual))
                    if limits[j] is None:
                        possible = False
                        break
                elif actual:
                    possible = False
                    break
            if not possible:
                break
        if possible:
            return True
    return False
