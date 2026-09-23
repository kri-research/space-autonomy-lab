"""Adaptive conservative episode adjudication from checked continuous arcs.

Failure, missing time coverage, unbounded numerical error and exhausted refinement
are explicit unresolved results. No endpoint sampling establishes interval safety.
"""

from fractions import Fraction as Q
from specification.contract import Verdict as V, HoldCoverage as H
from .interval import Interval, rational_bounds
from .geometry import bounds
from .flow import TaylorArc
from .polynomial import PolynomialArc

KEYS = ("containment", "collision_free", "keep_out_free")


def all_status(values):
    values = tuple(values)
    if not values or any(not isinstance(v, V) for v in values):
        raise ValueError("Nonempty typed component verdicts required")
    if any(v == V.VIOLATED for v in values):
        return V.VIOLATED
    if any(v == V.UNRESOLVED for v in values):
        return V.UNRESOLVED
    return V.SATISFIED


def failure(reason):
    return {
        "status": "unresolved",
        "reason": reason,
        "components": dict.fromkeys(KEYS, V.UNRESOLVED),
        "hold_acquired": V.UNRESOLVED,
        "nominal_goal": V.UNRESOLVED,
        "first_exit_bracket_s": None,
        "validated_containment": False,
    }


def adjudicate(
    arcs,
    prop,
    *,
    end=None,
    minimum_width=Q(1, 4096),
    max_cells=100000,
    required_events=(),
    aborted=False,
):
    horizon = Q(prop.horizon if end is None else end)
    width = Q(minimum_width)
    if (
        not 0 < horizon <= Q(prop.horizon)
        or width <= 0
        or type(max_cells) is not int
        or max_cells < 1
    ):
        raise ValueError("Invalid adjudication window or refinement budget")
    if type(aborted) is not bool:
        raise ValueError("Abort flag must be Boolean")
    arcs = tuple(arcs)
    if not arcs:
        return failure("missing_trajectory")
    cursor = Q(0)
    previous = None
    try:
        for arc in arcs:
            if not isinstance(arc, (TaylorArc, PolynomialArc)):
                return failure("no_supported_continuous_enclosure")
            if Q(arc.start) != cursor or Q(arc.end) <= cursor or Q(arc.end) > horizon:
                return failure("gap_overlap_or_wrong_extent")
            initial = arc.point(arc.start)
            if previous is not None and previous != initial:
                return failure("unjustified_state_reset_at_segment_boundary")
            previous = arc.point(arc.end)
            cursor = Q(arc.end)
        if cursor != horizon:
            return failure("incomplete_trajectory")
        splits = {Q(a.start) for a in arcs} | {horizon}
        if any(Q(t) not in splits for t in required_events):
            return failure("required_time_event_not_split")
    except (ArithmeticError, ValueError, TypeError, OverflowError):
        return failure("invalid_continuous_enclosure")
    leaves = []
    witness_times = {k: [] for k in KEYS}
    unresolved_reasons = set()
    nodes = 0
    minimum_lower = None
    minimum_upper = None
    complete_range_coverage = True
    for arc in arcs:
        stack = [(Q(arc.start), Q(arc.end))]
        while stack:
            a, b = stack.pop()
            nodes += 1
            try:
                if nodes > max_cells:
                    raise ArithmeticError("refinement_budget_exhausted")
                metrics = bounds(arc.range(a, b), prop)
                points = [(t, bounds(arc.point(t), prop)) for t in (a, (a + b) / 2, b)]
                lo = metrics["separation_squared_m2"][0]
                hi = min(p["separation_squared_m2"][1] for _, p in points)
                minimum_lower = lo if minimum_lower is None else min(lo, minimum_lower)
                minimum_upper = hi if minimum_upper is None else min(hi, minimum_upper)
                need_split = (
                    any(metrics[k] == V.UNRESOLVED for k in KEYS) or metrics["hold"] == H.UNRESOLVED
                )
                if need_split and b - a > width and nodes + len(stack) + 2 <= max_cells:
                    mid = (a + b) / 2
                    stack.extend([(mid, b), (a, mid)])
                    continue
                statuses = {k: metrics[k] for k in KEYS}
                for k in KEYS:
                    witnessed = [t for t, p in points if p[k] == V.VIOLATED]
                    if witnessed:
                        statuses[k] = V.VIOLATED
                        witness_times[k].extend(witnessed)
                if need_split:
                    unresolved_reasons.add("boundary_or_range_overlap_at_resolution_limit")
                leaves.append((a, b, statuses, metrics["hold"]))
            except (ArithmeticError, ValueError, TypeError, OverflowError) as exc:
                complete_range_coverage = False
                unresolved_reasons.add(type(exc).__name__ + ":" + str(exc))
                leaves.append((a, b, dict.fromkeys(KEYS, V.UNRESOLVED), H.UNRESOLVED))
    components = {k: all_status([s[k] for _, _, s, _ in leaves]) for k in KEYS}
    physical = all_status(components.values())
    run_certain = run_possible = max_certain = max_possible = Q(0)
    for a, b, _, hold in leaves:
        run_certain = run_certain + b - a if hold == H.ALL_ELIGIBLE else Q(0)
        run_possible = run_possible + b - a if hold != H.NONE_ELIGIBLE else Q(0)
        max_certain = max(max_certain, run_certain)
        max_possible = max(max_possible, run_possible)
    dwell = Q(prop.hold_dwell)
    hold_status = (
        V.SATISFIED
        if max_certain >= dwell
        else V.VIOLATED
        if max_possible < dwell
        else V.UNRESOLVED
    )
    # The earliest non-proved-inside interval precedes the first valid outside witness.
    # This cannot skip a narrower excursion because the prefix uses range enclosures.
    bracket = None
    initial = bounds(arcs[0].point(0), prop)["containment"]
    if initial == V.SATISFIED and witness_times["containment"]:
        earliest = min(witness_times["containment"])
        lower = next((a for a, b, s, h in leaves if s["containment"] != V.SATISFIED), Q(0))
        if lower <= earliest:
            bracket = [rational_bounds(lower)[0], rational_bounds(earliest)[1]]
    status = {
        V.SATISFIED: "validated_containment",
        V.VIOLATED: "validated_violation",
        V.UNRESOLVED: "unresolved",
    }[physical]
    result = {
        "status": status,
        "scope": "complete_episode" if horizon == Q(prop.horizon) else "bounded_window",
        "enclosure_kinds": sorted({a.evidence_kind for a in arcs}),
        "model_kinds": sorted(
            {
                a.model_kind if isinstance(a, TaylorArc) else "declared_polynomial_curve"
                for a in arcs
            }
        ),
        "components": components,
        "hold_acquired": hold_status,
        "nominal_goal": V.VIOLATED if aborted else all_status([physical, hold_status]),
        "initial_containment": initial,
        "first_exit_bracket_s": bracket,
        "first_exit_is_exact_time": False,
        "guaranteed_dwell_s": str(max_certain),
        "possible_dwell_upper_s": str(max_possible),
        "aborted": aborted,
        "leaf_intervals": len(leaves),
        "range_evaluations": nodes,
        "ambiguous_intervals": sum(
            any(s[k] == V.UNRESOLVED for k in KEYS) or h == H.UNRESOLVED for _, _, s, h in leaves
        ),
        "unresolved_reasons": sorted(unresolved_reasons),
        "witness_times_s": {k: float(min(v)) if v else None for k, v in witness_times.items()},
        "validated_containment": physical == V.SATISFIED,
        "complete_range_coverage": complete_range_coverage,
        "conditions": "stated ODE/polynomial, supplied inputs, outward arithmetic, no physical-validation claim",
    }
    if complete_range_coverage and minimum_lower is not None and minimum_upper is not None:
        interval = Interval(
            rational_bounds(minimum_lower)[0], rational_bounds(minimum_upper)[1]
        ).sqrt()
        result["minimum_separation_enclosure_m"] = [interval.lo, interval.hi]
    return result


def adjudicate_execution(
    model,
    initial,
    segments,
    prop,
    *,
    maximum_step=0.25,
    event_times=(),
    minimum_width=Q(1, 4096),
    order=8,
):
    """Fail-closed entry point for a complete explicitly split executed schedule."""
    from .flow import propagate_schedule

    try:
        events = tuple(event_times)
        arcs = propagate_schedule(
            model, initial, segments, maximum_step=maximum_step, event_times=events, order=order
        )
        return adjudicate(arcs, prop, minimum_width=minimum_width, required_events=events)
    except Exception as exc:
        return failure("propagation_or_adjudication_failed:" + type(exc).__name__ + ":" + str(exc))
