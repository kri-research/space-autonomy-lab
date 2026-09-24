"""Online analytic actuator-lag maps and curvature-certified finite prefixes."""

from fractions import Fraction as Q
from functools import lru_cache
from .arithmetic import Interval
from .schema import NORMALS, rational, support, validate


@lru_cache(maxsize=4096)
def maps(t, tau, instant=False):
    t, tau = map(rational, (t, tau))
    if t < 0 or tau <= 0:
        raise ValueError("Invalid propagation time")
    if t == 0:
        return (Interval.of(0),) * 5
    tt, ta = Interval.of(t), Interval.of(tau)
    if instant:
        return Interval.of(0), tt * tt / 2, Interval.of(0), tt, Interval.of(1)
    e = (-tt / ta).exp()
    f = ta * tt - ta * ta * (1 - e)
    g = tt * tt / 2 - f
    return f, g, ta * (1 - e), tt - ta * (1 - e), 1 - e


def scalar_state(case, box, n, t, action=(0, 0), instant=False):
    tau = rational(case["tau"])
    d = rational(case["delay"])
    t = rational(t)
    f, g, vf, vg, ag = maps(t, tau, instant)
    s = max(Q(0), t - d)
    _, gs, _, vs, as_ = maps(s, tau, instant)
    uc = (
        sum((Interval.of(v) * c for v, c in zip(action, n, strict=True)), Interval.of(0))
        * case["eta"]
    )
    w = Interval.of(case["disturbance"]) * sum(abs(c) for c in n)
    q0, v0, a0 = [Interval.of(support(box, n, k)) for k in range(3)]
    q = q0 + v0 * t + f * a0 + gs * uc + w * Interval.of(t) * t / 2
    v = v0 + vf * a0 + vs * uc + w * t
    a = (1 - ag) * a0 + as_ * uc if not instant else (uc if t > d else Interval.of(0))
    return q, v, a, w


def necessary(case, times=(Q(1, 2), Q(1)), instant=False):
    validate(case)
    d = rational(case["delay"])
    end = rational(case["duration"])
    knots = sorted(set([Q(0), d / 2, d, *[d + x * end for x in times]]))
    rows = []
    rhs = []
    labels = []
    for i, b in enumerate(case["boxes"]):
        for face, n in enumerate(NORMALS):
            for t in knots:
                base = scalar_state(case, b, n, t, instant=instant)[0]
                _, g, _, _, _ = maps(max(Q(0), t - d), rational(case["tau"]), instant)
                rows.append(tuple(g * case["eta"] * c for c in n))
                rhs.append(1 - base)
                labels.append({"hypothesis": i, "face": face, "time": str(t)})
    for j in range(2):
        for sign in (-1, 1):
            rows.append(tuple(Interval.of(sign if k == j else 0) for k in range(2)))
            rhs.append(Interval.of(case["authority"]))
            labels.append({"actuator_coordinate": j, "sign": sign})
    return rows, rhs, labels


def time_grid(case, subdivisions):
    d = rational(case["delay"])
    t = rational(case["duration"])
    knots = [Q(0)]
    if d:
        knots.extend(d * j / subdivisions for j in range(1, subdivisions + 1))
    knots.extend(d + t * j / subdivisions for j in range(1, subdivisions + 1))
    return knots


def curvature(case, box, n, instant=False):
    a = max(abs(support(box, n, 2, False)), abs(support(box, n, 2, True)))
    return max(
        Q(0) if instant else a, rational(case["eta"]) * rational(case["authority"])
    ) + rational(case["disturbance"]) * sum(abs(c) for c in n)


def prefix_constraints(case, subdivisions, instant=False):
    knots = time_grid(case, subdivisions)
    rows = []
    rhs = []
    d = rational(case["delay"])
    for b in case["boxes"]:
        for n in NORMALS:
            bound = curvature(case, b, n, instant)
            for j, t in enumerate(knots):
                width = max(
                    t - knots[j - 1] if j else 0, knots[j + 1] - t if j + 1 < len(knots) else 0
                )
                margin = bound * width * width / 8
                base = scalar_state(case, b, n, t, instant=instant)[0]
                _, g, _, _, _ = maps(max(Q(0), t - d), rational(case["tau"]), instant)
                rows.append(tuple(g * case["eta"] * c for c in n))
                rhs.append(1 - base - margin)
    return rows, rhs


def check_prefix(case, action, subdivisions=64, instant=False):
    u = tuple(map(rational, action))
    if len(u) != 2 or sum(x * x for x in u) > rational(case["authority"]) ** 2:
        return {"passed": False, "reason": "command_bound"}
    rows, rhs = prefix_constraints(case, subdivisions, instant)
    upper = max(
        (sum((m * x for m, x in zip(row, u, strict=True)), Interval.of(0)) - b).hi
        for row, b in zip(rows, rhs, strict=True)
    )
    return {
        "passed": upper <= 0,
        "largest_tightened_residual": str(upper),
        "subdivisions": subdivisions,
        "model": "instantaneous_ablation" if instant else "lag_cart",
        "proof": "continuous chord bound with directed endpoint enclosures",
        "recovery_assessed": False,
    }
