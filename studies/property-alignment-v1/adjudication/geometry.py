"""Independent rational inequality bounds for the declared physical property.

The online gate and historical excess functions are not imported. Rational
arithmetic on interval endpoints removes geometric rounding from sign decisions.
The nonconvex position set is treated as OR, never as an intersection.
"""

from fractions import Fraction as Q
from specification.contract import Verdict as V, HoldCoverage as H, Property
from .interval import Box, Interval, rational_bounds


def square_bounds(lo, hi):
    return (Q(0) if lo <= 0 <= hi else min(lo * lo, hi * hi), max(lo * lo, hi * hi))


def linear_bounds(a, xy, constant=0):
    low = high = Q(constant)
    for c, (lo, hi) in zip(a, xy, strict=True):
        ends = Q(c) * lo, Q(c) * hi
        low += min(ends)
        high += max(ends)
    return low, high


def bounds(box: Box, prop: Property):
    if not isinstance(box, Box) or not isinstance(prop, Property):
        raise ValueError("Explicit state enclosure and property required")
    xy = [(Q(v.lo), Q(v.hi)) for v in box.coordinates]
    slope = (Q(prop.inner_width) - Q(prop.outer_width)) / (Q(prop.upper_y) - Q(prop.lower_y))
    intercept = Q(prop.outer_width) - slope * Q(prop.lower_y)
    # Four halfspaces of the closed trapezoid, exact in represented constants.
    approach = [
        linear_bounds(a, xy[:2], c)
        for a, c in (
            ((0, -1), prop.lower_y),
            ((0, 1), -prop.upper_y),
            ((1, -slope), -intercept),
            ((-1, -slope), -intercept),
        )
    ]
    ellipse = [
        square_bounds((a - Q(c)) / Q(h), (b - Q(c)) / Q(h))
        for (a, b), c, h in zip(xy[:2], prop.center, prop.halfwidth, strict=True)
    ]
    ell = (sum(v[0] for v in ellipse) - 1, sum(v[1] for v in ellipse) - 1)
    positions = [square_bounds(*v) for v in xy[:2]]
    velocities = [square_bounds(*v) for v in xy[2:]]
    r2 = (sum(v[0] for v in positions), sum(v[1] for v in positions))
    v2 = (sum(v[0] for v in velocities), sum(v[1] for v in velocities))
    a_in = all(hi <= 0 for lo, hi in approach)
    a_out = any(lo > 0 for lo, hi in approach)
    contained = (
        V.SATISFIED if a_in or ell[1] <= 0 else V.VIOLATED if a_out and ell[0] > 0 else V.UNRESOLVED
    )
    exclusion = {}
    for name, radius in [
        ("collision_free", prop.collision_radius),
        ("keep_out_free", prop.keep_out_radius),
    ]:
        r = Q(radius) ** 2
        exclusion[name] = V.SATISFIED if r2[0] > r else V.VIOLATED if r2[1] <= r else V.UNRESOLVED
    speed = Q(prop.hold_speed) ** 2
    hold = (
        H.ALL_ELIGIBLE
        if ell[1] <= 0 and v2[1] <= speed
        else H.NONE_ELIGIBLE
        if ell[0] > 0 or v2[0] > speed
        else H.UNRESOLVED
    )
    return {
        "containment": contained,
        **exclusion,
        "hold": hold,
        "approach_residual_m": approach,
        "ellipse_residual_dimensionless": ell,
        "separation_squared_m2": r2,
        "speed_squared_m2_s2": v2,
    }


def separation_witness(box, prop, historical_excess_tolerance_m=0):
    eps = Q(historical_excess_tolerance_m)
    if eps < 0:
        raise ValueError("Nonnegative geometric tolerance required")
    lower = -max(
        Q(prop.upper_y) + eps,
        Q(prop.center[1]) + Q(prop.halfwidth[1]) * (1 + eps / min(map(Q, prop.halfwidth))),
    )
    if lower <= 0:
        return {"witness": False, "reason": "no_positive_separation_implication"}
    r2 = bounds(box, prop)["separation_squared_m2"]
    upper = Interval(*rational_bounds(r2[1])).sqrt().hi
    return {
        "witness": r2[1] < lower * lower,
        "required_separation_lower_m": str(lower),
        "enclosed_separation_upper_m": upper,
        "scope": "conditional_on_state_enclosure",
    }


def numerical_agreement_witness(states, prop):
    """Two or more numerical representations, never a truth-error certificate."""
    if len(states) < 2:
        return {"status": "unresolved", "reason": "fewer_than_two_representations"}
    try:
        boxes = [Box.point(s) for s in states]
        hull = Box(
            tuple(
                Interval(
                    min(b.coordinates[j].lo for b in boxes), max(b.coordinates[j].hi for b in boxes)
                )
                for j in range(4)
            )
        )
        result = bounds(hull, prop)
    except (ValueError, ArithmeticError, TypeError, OverflowError):
        return {"status": "unresolved", "reason": "invalid_numerical_state"}
    violated = any(
        result[k] == V.VIOLATED for k in ("containment", "collision_free", "keep_out_free")
    )
    return {
        "status": "numerically_corroborated_violation" if violated else "unresolved",
        "component_spread": list(hull.widths),
        "spread_is_error_bound": False,
        "containment_certified": False,
        "scope": "numerical_representations_only",
    }
