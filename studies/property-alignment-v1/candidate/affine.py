"""Validated necessary linear inequalities and independently checked dual witnesses.
A finite subset of truly compatible origins supplies NECESSARY constraints only.
No endpoint of a propagated outer enclosure is treated as an attainable origin.
"""

from fractions import Fraction as Q
from functools import lru_cache
from itertools import product
import numpy as np
from scipy.optimize import linprog
from adjudication.interval import iv, ZERO
from adjudication.flow import Model, propagate_schedule
from specification.contract import load_property


def dot(a, b):
    return sum((iv(x) * y for x, y in zip(a, b, strict=True)), ZERO)


@lru_cache(maxsize=16)
def maps(duration):
    t = Q(duration)
    if not 0 <= t <= 3:
        raise ValueError("Map duration outside checked domain")
    if t == 0:
        return tuple(tuple(iv(int(i == j)) for j in range(4)) for i in range(4)), tuple(
            (ZERO, ZERO) for _ in range(4)
        )
    cols = []
    for j in range(6):
        state = [int(j == k) for k in range(4)]
        control = [int(j == k + 4) for k in range(2)]
        arcs = propagate_schedule(Model("hcw"), state, [(0, t, control)])
        cols.append(arcs[-1].point(t).coordinates)
    return tuple(tuple(cols[j][i] for j in range(4)) for i in range(4)), tuple(
        tuple(cols[j][i] for j in (4, 5)) for i in range(4)
    )


def mv(matrix, vector):
    return tuple(dot(row, vector) for row in matrix)


def checked_outer_halfspaces():
    prop = load_property()
    assert (
        prop.lower_y,
        prop.upper_y,
        prop.outer_width,
        prop.inner_width,
        prop.center,
        prop.halfwidth,
    ) == (-100, -30, 10, 3, (0, -30), (2, 3))
    normals = ((0, -1), (0, 1), (1, 0), (-1, 0), (1, Q(1, 10)), (-1, Q(1, 10)))
    limits = (100, -27, 10, 10, 0, 0)
    vertices = ((-10, -100), (10, -100), (-3, -30), (3, -30))
    for normal, limit in zip(normals, limits, strict=True):
        a = max(sum(Q(c) * x for c, x in zip(normal, v, strict=True)) for v in vertices)
        rad = (2 * Q(normal[0])) ** 2 + (3 * Q(normal[1])) ** 2
        e = -30 * Q(normal[1]) + Q(iv(rad).sqrt().hi)
        if max(a, e) > limit:
            raise ArithmeticError("Necessary halfspace does not contain the complete union")
    return normals, tuple(map(Q, limits))


def necessary_system(info, times=(Q(1, 2), Q(1)), max_origins=64):
    """HCW only. Extreme constant disturbances/effectiveness are admissible witnesses.
    Using only some origins/times weakens rejection power, never certifies safety.
    """
    if info.kind != "declared_exact_information_set":
        raise ValueError("Impossibility needs attainable origins, not an outer-only enclosure")
    if type(max_origins) is not int or max_origins < 1:
        raise ValueError("Positive witness budget required")
    times = tuple(map(Q, times))
    if not times or any(not 0 < t <= 1 for t in times):
        raise ValueError("Necessary checks must lie in the held interval")
    origins = sorted(set(x for h in info.hypotheses for x in h.vertices()))
    origins = origins[:max_origins]
    normals, limits = checked_outer_halfspaces()
    ws = tuple(sorted(set(product((-info.disturbance, info.disturbance), repeat=2))))
    rows = []
    rhs = []
    labels = []
    for origin in origins:
        if not any(h.contains(origin) for h in info.hypotheses):
            raise ValueError("Invalid witness origin")
        for eta in sorted(set(info.effectiveness)):
            for w in ws:
                for t in times:
                    total = info.application_time + t
                    at, bt = maps(total)
                    constant = list(mv(at, origin))
                    dw = mv(bt, w)
                    constant = [x + y for x, y in zip(constant, dw, strict=True)]
                    for j, u in enumerate(info.queue):
                        after, _ = maps(total - j - 1)
                        _, one = maps(1)
                        term = mv(after, mv(one, [eta * v for v in u]))
                        constant = [x + y for x, y in zip(constant, term, strict=True)]
                    _, controlled = maps(t)
                    for normal, limit in zip(normals, limits, strict=True):
                        row = tuple(
                            dot(normal, [controlled[i][j] for i in range(2)]) * eta
                            for j in range(2)
                        )
                        rows.append(row)
                        rhs.append(iv(limit) - dot(normal, constant[:2]))
                        labels.append(
                            {
                                "origin": list(map(str, origin)),
                                "effectiveness": str(eta),
                                "disturbance": list(map(str, w)),
                                "time_after_application": str(t),
                                "normal": list(map(str, normal)),
                            }
                        )
    for j, sign in product(range(2), (-1, 1)):
        rows.append(tuple(iv(sign if k == j else 0) for k in range(2)))
        rhs.append(iv(info.authority))
        labels.append({"outer_actuator_box_coordinate": j, "sign": sign})
    return rows, rhs, labels


def verify_dual(rows, rhs, weights, authority):
    """Exact rational residual budget; NOT trusting an optimizer infeasible flag."""
    weights = tuple(Q(x) for x in weights)
    authority = Q(authority)
    if (
        authority < 0
        or len(rows) != len(rhs)
        or len(rows) != len(weights)
        or not weights
        or any(w < 0 for w in weights)
        or not any(weights)
    ):
        return {"proved": False, "reason": "invalid_nonnegative_weights_or_dimensions"}
    if any(len(row) != 2 for row in rows):
        return {"proved": False, "reason": "invalid_action_dimension"}
    b_upper = sum(w * Q(b.hi) for w, b in zip(weights, rhs, strict=True))
    residual = []
    for j in range(2):
        lo = sum(w * Q(row[j].lo) for w, row in zip(weights, rows, strict=True))
        hi = sum(w * Q(row[j].hi) for w, row in zip(weights, rows, strict=True))
        residual.append(max(abs(lo), abs(hi)))
    margin = -b_upper - authority * sum(residual)
    return {
        "proved": margin > 0,
        "margin_lower": str(margin),
        "weighted_rhs_upper": str(b_upper),
        "coefficient_residual_upper": list(map(str, residual)),
        "arithmetic": "exact_rational_recheck_of_outward_ODE_coefficients",
    }


def obstruction(info, time_limit=0.2, force_failure=False):
    if force_failure:
        return {"status": "unresolved", "reason": "forced_solver_failure"}
    try:
        rows, rhs, labels = necessary_system(info)

        def middle(v):
            return float((Q(v.lo) + Q(v.hi)) / 2)

        matrix = np.array([[middle(v) for v in row] for row in rows])
        b = np.array([middle(v) for v in rhs])
        result = linprog(
            b,
            A_eq=np.vstack((matrix.T, np.ones(len(b)))),
            b_eq=[0.0, 0.0, 1.0],
            bounds=(0, None),
            method="highs",
            options={"time_limit": time_limit},
        )
        if not result.success or result.x is None or not np.all(np.isfinite(result.x)):
            return {
                "status": "unresolved",
                "reason": "no_checked_dual",
                "solver_status": int(result.status),
            }
        weights = [max(Q(0), Q(float(v))) for v in result.x]
        checked = verify_dual(rows, rhs, weights, info.authority)
        if not checked["proved"]:
            return {
                "status": "unresolved",
                "reason": "nonpositive_verified_margin",
                "checked": checked,
            }
        return {
            "status": "proved_no_common_held_command",
            "model": "hcw",
            "information_sha256": info.identity(),
            "weights": list(map(str, weights)),
            "checked": checked,
            "active_obligations": [
                dict(weight=str(w), **label) for w, label in zip(weights, labels, strict=True) if w
            ],
            "scope": "necessary_conditions_at_attainable_hypotheses; not each-state impossibility",
        }
    except Exception as exc:
        return {"status": "unresolved", "reason": type(exc).__name__ + ":" + str(exc)}


def recheck_certificate(info, certificate):
    if (
        certificate.get("information_sha256") != info.identity()
        or certificate.get("model") != "hcw"
    ):
        return {"proved": False, "reason": "wrong_information_or_model"}
    try:
        rows, rhs, _ = necessary_system(info)
        return verify_dual(rows, rhs, certificate["weights"], info.authority)
    except Exception as exc:
        return {"proved": False, "reason": type(exc).__name__}
