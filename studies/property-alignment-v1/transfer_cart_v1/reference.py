"""Independent standard-library Taylor/Bernstein referee for the lagged cart.

No online maps, optimizer, orbital code, or online interval class is imported.
Only the declared input schema/geometry is shared. This is computational
independence of formulation, not an independent research team or laboratory.
"""

from dataclasses import dataclass
from decimal import Decimal as D, Context, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction as Q
from functools import lru_cache
from math import comb, factorial
from .schema import NORMALS, rational, support, validate

DN = Context(prec=80, rounding=ROUND_FLOOR)
UP = Context(prec=80, rounding=ROUND_CEILING)
ORDER = 10


@dataclass(frozen=True)
class R:
    lower: D
    upper: D

    def __post_init__(self):
        if not self.lower.is_finite() or not self.upper.is_finite() or self.lower > self.upper:
            raise ValueError("Bad reference enclosure")

    @classmethod
    def value(cls, x):
        if isinstance(x, cls):
            return x
        x = rational(x)
        return cls(
            DN.divide(D(x.numerator), D(x.denominator)), UP.divide(D(x.numerator), D(x.denominator))
        )

    def __add__(self, b):
        b = R.value(b)
        return R(DN.add(self.lower, b.lower), UP.add(self.upper, b.upper))

    __radd__ = __add__

    def __neg__(self):
        return R(self.upper.copy_negate(), self.lower.copy_negate())

    def __sub__(self, b):
        return self + -R.value(b)

    def __rsub__(self, b):
        return R.value(b) + -self

    def __mul__(self, b):
        b = R.value(b)
        pairs = [(a, c) for a in (self.lower, self.upper) for c in (b.lower, b.upper)]
        return R(min(DN.multiply(a, c) for a, c in pairs), max(UP.multiply(a, c) for a, c in pairs))

    __rmul__ = __mul__

    def __truediv__(self, b):
        b = R.value(b)
        if b.lower <= 0 <= b.upper:
            raise ValueError("Zero divisor")
        return self * R(DN.divide(D(1), b.upper), UP.divide(D(1), b.lower))

    def absolute(self):
        return max(self.lower.copy_abs(), self.upper.copy_abs())

    def padded(self, error):
        error = R.value(error).upper
        return R(DN.subtract(self.lower, error), UP.add(self.upper, error))

    def pair(self):
        return [str(self.lower), str(self.upper)]


def polynomial(state, c, w, tau, h):
    q, v, a = map(R.value, state)
    c, w = R.value(c), R.value(w)
    tau, h = map(rational, (tau, h))
    if not 0 < h <= tau / 2:
        raise ValueError("Taylor step outside tested bound")
    ac = [a, (c - a) / tau]
    for k in range(2, ORDER + 1):
        ac.append(-ac[-1] / (tau * k))
    vc = [v, a + w] + [ac[k - 1] / k for k in range(2, ORDER + 1)]
    qc = [q, v, (a + w) / 2] + [ac[k - 2] / (k * (k - 1)) for k in range(3, ORDER + 1)]
    # Alternating exponential tail: h/tau<=1/2. This bounds every point
    # on the whole step, with initial interval uncertainty retained.
    e = R.value((a - c).absolute()) * ((h / tau) ** (ORDER + 1)) / factorial(ORDER + 1)
    return (qc, vc, ac), (e * tau * tau, e * tau, e)


def value(coeff, t):
    out = R.value(0)
    for c in reversed(coeff):
        out = out * t + c
    return out


def bernstein(coeff, h):
    n = len(coeff) - 1
    scaled = [c * (h**k) for k, c in enumerate(coeff)]
    return [
        sum((scaled[k] * Q(comb(j, k), comb(n, k)) for k in range(j + 1)), R.value(0))
        for j in range(n + 1)
    ]


def halves(values):
    layer = list(values)
    left = [layer[0]]
    right = [layer[-1]]
    while len(layer) > 1:
        layer = [(a + b) / 2 for a, b in zip(layer[:-1], layer[1:], strict=True)]
        left.append(layer[0])
        right.append(layer[-1])
    return left, list(reversed(right))


def enclose_curve(coeff, error, h, offset=Q(0), max_cells=4096):
    stack = [(Q(0), h, bernstein(coeff, h))]
    count = 0
    largest = None
    unknown = False
    while stack:
        a, b, bs = stack.pop()
        count += 1
        if count > max_cells:
            return {"status": "unresolved", "reason": "reference_cell_budget", "cells": count}
        high = max(v.upper for v in bs)
        high = UP.add(high, R.value(error).upper)
        largest = high if largest is None else max(largest, high)
        if high <= 1:
            continue
        for t, v in ((a, bs[0]), (b, bs[-1])):
            point = v.padded(error)
            if point.lower > 1:
                return {
                    "status": "violation",
                    "cells": count,
                    "witness_time_s": str(offset + t),
                    "projection": point.pair(),
                    "reason": "attainable_support_trajectory",
                }
        if b - a <= Q(1, 1000000):
            unknown = True
            continue
        left, right = halves(bs)
        mid = (a + b) / 2
        stack.extend(((mid, b, right), (a, mid, left)))
    return {
        "status": "unresolved" if unknown else "contained",
        "cells": count,
        "examined_projection_upper": str(largest),
    }


def advance(state, c, w, tau, h):
    polys, errs = polynomial(state, c, w, tau, h)
    return tuple(value(poly, h).padded(err) for poly, err in zip(polys, errs, strict=True))


def integrate(state, c, w, tau, duration):
    duration = rational(duration)
    tau = rational(tau)
    state = tuple(map(R.value, state))
    t = Q(0)
    while t < duration:
        h = min(tau / 2, duration - t)
        state = advance(state, c, w, tau, h)
        t += h
    return state


@lru_cache(maxsize=1024)
def coefficient(t, tau, kind):
    if kind == "initial_acceleration":
        return integrate((0, 0, 1), 0, 0, tau, t)[0]
    if kind == "command":
        return integrate((0, 0, 0), 1, 0, tau, t)[0]
    raise ValueError("Unknown reference coefficient")


def action_check(case, action, *, actual_tau=None):
    validate(case)
    u = tuple(map(rational, action))
    if len(u) != 2 or sum(x * x for x in u) > rational(case["authority"]) ** 2:
        return {"status": "invalid_input", "reason": "command_bound"}
    tau = rational(case["tau"] if actual_tau is None else actual_tau)
    if not 0 < tau <= 3:
        raise ValueError("Unsupported actual lag")
    delay = rational(case["delay"])
    duration = rational(case["duration"])
    rows = []
    for index, box in enumerate(case["boxes"]):
        for face, n in enumerate(NORMALS):
            initial = tuple(support(box, n, k) for k in range(3))
            origin = [
                str(rational(box["upper" if c >= 0 else "lower"][2 * k + j]))
                for k in range(3)
                for j, c in enumerate(n)
            ]
            w = rational(case["disturbance"]) * sum(abs(c) for c in n)
            command = rational(case["eta"]) * sum(c * x for c, x in zip(n, u, strict=True))
            state = tuple(map(R.value, initial))
            offset = Q(0)
            verdict = "contained"
            count = 0
            witness = None
            if state[0].lower > 1:
                verdict = "violation"
                witness = {"time_s": "0", "projection": state[0].pair()}
            phases = [(delay, Q(0)), (duration, command)]
            for length, c in phases:
                t = Q(0)
                while t < length and verdict == "contained":
                    h = min(tau / 2, length - t)
                    polys, errs = polynomial(state, c, w, tau, h)
                    result = enclose_curve(
                        polys[0], errs[0], h, offset + t, max_cells=max(1, 4096 - count)
                    )
                    count += result["cells"]
                    if result["status"] != "contained":
                        verdict = result["status"]
                        witness = result
                    state = tuple(
                        value(poly, h).padded(e) for poly, e in zip(polys, errs, strict=True)
                    )
                    t += h
                offset += length
            rows.append(
                {
                    "hypothesis": index,
                    "face": face,
                    "status": verdict,
                    "cells": count,
                    "compatible_origin": origin,
                    "disturbance_vector": [
                        str(rational(case["disturbance"]) * (1 if c >= 0 else -1)) for c in n
                    ],
                    "witness": witness,
                    "last_projected_state": [x.pair() for x in state],
                }
            )
    statuses = {r["status"] for r in rows}
    status = (
        "violation"
        if "violation" in statuses
        else "contained"
        if statuses == {"contained"}
        else "unresolved"
    )
    return {
        "status": status,
        "rows": rows,
        "model": "lag_cart",
        "tau": str(tau),
        "actual_model_matches_declared": tau == rational(case["tau"]),
        "state_box_support_argument": "cooperative scalar lag dynamics, positive position/velocity/acceleration kernels; fixed disturbance corners attain each halfspace maximum",
        "independent_engine": "80-digit outward Taylor/Bernstein; no online map imports",
        "recovery_assessed": False,
    }


def necessary_rows(case):
    d, tau, T = map(rational, (case["delay"], case["tau"], case["duration"]))
    times = sorted(set((Q(0), d / 2, d, d + T / 2, d + T)))
    rows = []
    rhs = []
    for box in case["boxes"]:
        for n in NORMALS:
            q, v, a = [support(box, n, k) for k in range(3)]
            w = rational(case["disturbance"]) * sum(abs(c) for c in n)
            for t in times:
                f = coefficient(t, tau, "initial_acceleration")
                g = coefficient(max(Q(0), t - d), tau, "command") * case["eta"]
                rows.append(tuple(g * c for c in n))
                rhs.append(1 - (R.value(q) + v * t + f * a + Q(1, 2) * w * t * t))
    for j in range(2):
        for sign in (-1, 1):
            rows.append(tuple(R.value(sign if j == k else 0) for k in range(2)))
            rhs.append(R.value(case["authority"]))
    return rows, rhs


def dual_check(case, weights):
    rows, b = necessary_rows(case)
    weights = tuple(map(rational, weights))
    if len(weights) != len(rows) or any(w < 0 for w in weights) or not any(weights):
        return {"proved": False, "reason": "invalid_weights"}
    bmax = sum(w * Q(v.upper) for w, v in zip(weights, b, strict=True))
    residual = []
    for j in range(2):
        low = sum(w * Q(row[j].lower) for w, row in zip(weights, rows, strict=True))
        high = sum(w * Q(row[j].upper) for w, row in zip(weights, rows, strict=True))
        residual.append(max(abs(low), abs(high)))
    margin = -bmax - rational(case["authority"]) * sum(residual)
    return {
        "proved": margin > 0,
        "margin_lower": str(margin),
        "arithmetic": "exact rational residual on independent Taylor map bounds",
        "no_policy_or_optimizer_called": True,
    }
