"""Retargeted common-command criterion and explicitly scoped comparators."""

from fractions import Fraction as Q
import time
import numpy as np
from scipy.optimize import linprog, minimize
from .arithmetic import Interval
from .lag import maps, necessary, prefix_constraints, check_prefix, scalar_state
from .schema import NORMALS, rational, support, validate, mean_case

METHODS = (
    "lag_aware_common_command",
    "robust_predictive_prefix",
    "third_order_barrier",
    "mean_only_prefix",
    "instantaneous_actuator_ablation",
)


def propose(rows, rhs, authority):
    matrix = np.asarray([[c.mid() for c in row] for row in rows])
    b = np.asarray([c.mid() for c in rhs])
    limit = float(rational(authority)) * (1 - 1e-10)
    result = minimize(
        lambda u: float(u @ u),
        np.zeros(2),
        jac=lambda u: 2 * u,
        constraints=[
            {"type": "ineq", "fun": lambda u: b - matrix @ u - 1e-8, "jac": lambda u: -matrix},
            {"type": "ineq", "fun": lambda u: limit * limit - u @ u, "jac": lambda u: -2 * u},
        ],
        method="SLSQP",
        bounds=[(-limit, limit)] * 2,
        options={"ftol": 1e-10, "maxiter": 100},
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        return None, {
            "success": False,
            "status": int(result.status),
            "message": str(result.message),
        }
    u = tuple(Q(str(float(x))) for x in result.x)
    if sum(x * x for x in u) > rational(authority) ** 2:
        return None, {"success": False, "status": "exact_action_bound"}
    return u, {"success": True, "iterations": int(result.nit)}


def check_dual(rows, rhs, weights, authority):
    weights = tuple(map(rational, weights))
    if (
        len(weights) != len(rows)
        or len(rhs) != len(rows)
        or not any(weights)
        or any(w < 0 for w in weights)
    ):
        return {"proved": False, "reason": "bad_weights"}
    bmax = sum(w * Q(b.hi) for w, b in zip(weights, rhs, strict=True))
    residual = []
    for j in range(2):
        lo = sum(w * Q(row[j].lo) for w, row in zip(weights, rows, strict=True))
        hi = sum(w * Q(row[j].hi) for w, row in zip(weights, rows, strict=True))
        residual.append(max(abs(lo), abs(hi)))
    margin = -bmax - rational(authority) * sum(residual)
    return {
        "proved": margin > 0,
        "margin_lower": str(margin),
        "coordinate_residual_upper": list(map(str, residual)),
    }


def obstruction(case):
    rows, rhs, labels = necessary(case)
    m = np.asarray([[x.mid() for x in row] for row in rows])
    b = np.asarray([x.mid() for x in rhs])
    lp = linprog(
        b,
        A_eq=np.vstack((m.T, np.ones(len(b)))),
        b_eq=[0.0, 0.0, 1.0],
        bounds=(0, None),
        method="highs",
        options={"time_limit": 0.2},
    )
    if not lp.success or lp.x is None or not np.all(np.isfinite(lp.x)):
        return {"proved": False, "reason": "no_dual", "solver_status": int(lp.status)}
    weights = tuple(max(Q(0), Q(str(float(x)))) for x in lp.x)
    checked = check_dual(rows, rhs, weights, case["authority"])
    return {
        **checked,
        "weights": list(map(str, weights)),
        "obligations": labels,
        "model": "lag_cart",
    }


def initial_barrier(case):
    d = rational(case["delay"])
    lam = Q(2)
    worst = []
    for box in case["boxes"]:
        for n in NORMALS:
            q, v, a, w = scalar_state(case, box, n, d)
            h = 1 - q
            h1 = lam * h - v
            h2 = lam * lam * h - 2 * lam * v - a - w
            worst.extend((h.lo, h1.lo, h2.lo))
    return min(worst) >= 0, str(min(worst))


def barrier_constraints(case):
    tau = rational(case["tau"])
    d = rational(case["delay"])
    T = rational(case["duration"])
    eta = rational(case["eta"])
    lam = Q(2)
    times = [d + T * j / 32 for j in range(33)]
    rows = []
    rhs = []
    for box in case["boxes"]:
        for n in NORMALS:
            A = max(
                abs(support(box, n, 2, False)),
                abs(support(box, n, 2, True)),
                eta * rational(case["authority"]),
            )
            W = rational(case["disturbance"]) * sum(abs(c) for c in n)
            vmax = max(abs(support(box, n, 1, False)), abs(support(box, n, 1, True))) + (A + W) * (
                d + T
            )
            derivative = (
                abs(1 / tau - 3 * lam) * (A + eta * rational(case["authority"])) / tau
                + 3 * lam * lam * (A + W)
                + lam**3 * vmax
            )
            reserve = derivative * (T / 32) / 2
            origins = [
                Interval(
                    Interval.of(support(box, n, k, False)).lo,
                    Interval.of(support(box, n, k, True)).hi,
                )
                for k in range(3)
            ]
            for t in times:
                f, _, vf, _, ag = maps(t, tau)
                _, g, _, vg, au = maps(t - d, tau)
                weights = (
                    -(lam**3),
                    -3 * lam * lam - lam**3 * t,
                    (1 / tau - 3 * lam) * (1 - ag) - 3 * lam * lam * vf - lam**3 * f,
                )
                const = Interval.of(lam**3) + sum(
                    (Interval.of(c) * x for c, x in zip(weights, origins, strict=True)),
                    Interval.of(0),
                )
                wc = -3 * lam - 3 * lam * lam * t - lam**3 * t * t / 2
                const = const + Interval(Interval.of(-W).lo, Interval.of(W).hi) * wc
                gain = eta * ((1 / tau - 3 * lam) * au - 3 * lam * lam * vg - lam**3 * g - 1 / tau)
                rows.append(tuple(-gain * x for x in n))
                rhs.append(const - reserve)
    return rows, rhs


def verify_inequalities(rows, rhs, action):
    return all(
        (sum((m * u for m, u in zip(row, action, strict=True)), Interval.of(0)) - b).hi <= 0
        for row, b in zip(rows, rhs, strict=True)
    )


def decide(case, method="lag_aware_common_command", budget_s=1.0):
    validate(case)
    if method not in METHODS or not 0 < budget_s <= 60:
        raise ValueError("Unknown method/budget")
    maps.cache_clear()
    start = time.perf_counter()
    details = {}
    action = None
    status = "unresolved"
    model_case = mean_case(case) if method == "mean_only_prefix" else case
    instant = method == "instantaneous_actuator_ablation"
    try:
        if method == "lag_aware_common_command":
            neg = obstruction(case)
            details["obstruction"] = neg
            if neg["proved"]:
                status = "obstruction"
            else:
                rows, rhs = prefix_constraints(case, 16)
                action, solver = propose(rows, rhs, case["authority"])
                details["solver"] = solver
        elif method == "third_order_barrier":
            eligible, margin = initial_barrier(case)
            details["initial_derivative_domain"] = {"passed": eligible, "lower": margin}
            if eligible:
                rows, rhs = barrier_constraints(case)
                action, solver = propose(rows, rhs, case["authority"])
                details["solver"] = solver
                if action is not None and not verify_inequalities(rows, rhs, action):
                    action = None
                    details["rejected"] = "continuous_barrier_residual"
            else:
                details["rejected"] = "initial_derivative_domain"
        else:
            rows, rhs = prefix_constraints(model_case, 64, instant)
            action, solver = propose(rows, rhs, case["authority"])
            details["solver"] = solver
        if action is not None:
            proof = check_prefix(model_case, action, 64, instant)
            details["prefix"] = proof
            if proof["passed"]:
                status = "prefix"
            else:
                action = None
                details["rejected"] = "continuous_prefix_not_certified"
    except Exception as exc:
        details["exception"] = {"type": type(exc).__name__, "message": str(exc)}
        action = None
        status = "unresolved"
    elapsed = time.perf_counter() - start
    raw = status
    if elapsed > budget_s:
        status = "budget_miss"
        action = None
    return {
        "status": status,
        "mathematical_status_before_deadline": raw,
        "action": None if action is None else list(map(str, action)),
        "wall_s": elapsed,
        "on_time": elapsed <= budget_s,
        "budget_s": budget_s,
        "method": method,
        "details": details,
        "model_omits_lag": instant,
        "uses_only_mean": method == "mean_only_prefix",
        "recovery_claim": False,
    }
