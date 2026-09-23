"""Constructive continuous prefix checks paired with necessary impossibility.
Positive checks cover the complete information SET, not just witness vertices.
A feasible endpoint relaxation never becomes a safety certificate.
"""

from fractions import Fraction as Q
from itertools import product
import time
import numpy as np
import cvxpy as cp
from adjudication.interval import Interval, iv
from adjudication.flow import Model, propagate_schedule
from adjudication.engine import adjudicate
from specification.contract import load_property
from .affine import obstruction, necessary_system


def action_ok(info, action):
    try:
        return len(action) == 2 and sum(Q(x) ** 2 for x in action) <= info.authority**2
    except (ValueError, TypeError, OverflowError):
        return False


def realized(info, action):
    eta = Interval(iv(info.effectiveness[0]).lo, iv(info.effectiveness[1]).hi)
    w = Interval(iv(-info.disturbance).lo, iv(info.disturbance).hi)
    return tuple(eta * iv(Q(x)) + w for x in action)


def execution_schedule(info, action):
    if not action_ok(info, action):
        raise ValueError("Held command exceeds exact Euclidean authority")
    schedule = []
    for k, u in enumerate((*info.queue, tuple(action))):
        if not action_ok(info, u):
            raise ValueError("Bad queued command")
        for j in range(4):
            start = Q(k) + Q(j, 4)
            schedule.append((start, start + Q(1, 4), realized(info, u)))
    return schedule


def terminal_member(box):
    from protective.common import P, TARGET, ALPHA

    # Exact rational evaluation of each vertex suffices for this convex quadratic.
    extremes = product(*[(Q(c.lo), Q(c.hi)) for c in box.coordinates])
    p = [[Q(float(v)) for v in row] for row in P]
    target = list(map(lambda v: Q(float(v)), TARGET))
    maximum = Q(0)
    for vertex in extremes:
        delta = [x - y for x, y in zip(vertex, target, strict=True)]
        value = sum(delta[i] * p[i][j] * delta[j] for i in range(4) for j in range(4))
        maximum = max(maximum, value)
    return maximum <= Q(ALPHA) ** 2


def certify_action(info, action, model="hcw", max_cells=32768):
    if info.kind == "covariance_only":
        return {"status": "unresolved", "reason": "no_deterministic_information_set"}
    if not action_ok(info, action):
        return {"status": "unresolved", "reason": "invalid_or_overlimit_action"}
    try:
        schedule = execution_schedule(info, action)
        final = Q(info.application_time + 1)
        records = []
        terminal = []
        for hypothesis in info.hypotheses:
            arcs = propagate_schedule(Model(model), hypothesis.enclosure(), schedule)
            judged = adjudicate(
                arcs,
                load_property(),
                end=final,
                max_cells=max_cells,
                minimum_width=Q(1, 4096),
                required_events=[a for a, b, u in schedule],
            )
            records.append(
                {
                    "status": judged["status"],
                    "components": judged["components"],
                    "range_evaluations": judged.get("range_evaluations"),
                    "ambiguous_intervals": judged.get("ambiguous_intervals"),
                    "reason": judged.get("reason"),
                    "enclosure_final": [[c.lo, c.hi] for c in arcs[-1].point(final).coordinates],
                }
            )
            terminal.append(terminal_member(arcs[-1].point(final)))
        passed = all(r["status"] == "validated_containment" for r in records)
        return {
            "status": "certified_common_prefix" if passed else "unresolved",
            "information_sha256": info.identity(),
            "model": model,
            "action": list(map(lambda v: str(Q(v)), action)),
            "end_after_measurement_s": str(final),
            "hypotheses": records,
            "all_terminal_members": bool(passed and all(terminal)),
            "recovery_status": "terminal_membership_needs_resumed_baseline_assumptions"
            if passed and all(terminal)
            else "unassessed",
            "scope": "continuous_common_held_input; not an infinite-horizon or floating-feedback theorem",
        }
    except Exception as exc:
        return {"status": "unresolved", "reason": type(exc).__name__ + ":" + str(exc)}


def seek_command(info, proposal, solver_time_limit=0.2):
    """Relaxed SOCP proposes only; the positive checker must validate its result."""
    try:
        rows, rhs, _ = necessary_system(info)
        matrix = np.array([[float((Q(v.lo) + Q(v.hi)) / 2) for v in row] for row in rows])
        b = np.array([float((Q(v.lo) + Q(v.hi)) / 2) for v in rhs])
        u = cp.Variable(2)
        problem = cp.Problem(
            cp.Minimize(cp.sum_squares(u - np.asarray(proposal, float))),
            [matrix @ u <= b - 1.0e-8, cp.norm(u, 2) <= float(info.authority) * (1 - 1.0e-8)],
        )
        problem.solve(
            solver=cp.CLARABEL,
            max_iter=100,
            time_limit=solver_time_limit,
            tol_feas=1.0e-10,
            tol_gap_abs=1.0e-10,
            tol_gap_rel=1.0e-10,
        )
        if problem.status != "optimal" or u.value is None or not np.all(np.isfinite(u.value)):
            return None, {"status": str(problem.status)}
        return tuple(map(float, u.value)), {
            "status": "proposed_by_relaxation",
            "not_certified": True,
        }
    except Exception as exc:
        return None, {"status": "unresolved", "reason": type(exc).__name__}


def decide(info, proposal=(0, 0), model="hcw", budget_s=1.0, force_solver_failure=False):
    if not np.isfinite(budget_s) or budget_s <= 0:
        raise ValueError("Positive finite decision budget required")
    start = time.perf_counter()
    negative = (
        obstruction(info, force_failure=force_solver_failure)
        if model == "hcw"
        else {"status": "unresolved", "reason": "negative_certificate_supported_for_HCW_only"}
    )
    if negative["status"] == "proved_no_common_held_command":
        elapsed = time.perf_counter() - start
        return {
            "status": negative["status"] if elapsed <= budget_s else "unresolved_budget",
            "negative": negative,
            "action": None,
            "wall_s": elapsed,
            "deadline_exceeded": elapsed > budget_s,
        }
    umax = float(info.authority) * (1 - 1.0e-10)
    proposed, search = (
        (None, {"status": "forced_failure"})
        if force_solver_failure
        else seek_command(info, proposal)
    )
    candidates = [tuple(proposal)]
    if proposed is not None:
        candidates.append(proposed)
    candidates.extend([(0.0, 0.0), (-umax, 0.0), (umax, 0.0), (0.0, -umax), (0.0, umax)])
    attempts = []
    for action in dict.fromkeys(candidates):
        if time.perf_counter() - start > budget_s:
            break
        checked = certify_action(info, action, model)
        attempts.append(checked)
        if checked["status"] == "certified_common_prefix":
            elapsed = time.perf_counter() - start
            return {
                "status": checked["status"] if elapsed <= budget_s else "unresolved_budget",
                "action": checked["action"] if elapsed <= budget_s else None,
                "positive": checked,
                "negative": negative,
                "search": search,
                "wall_s": elapsed,
                "deadline_exceeded": elapsed > budget_s,
                "attempts": len(attempts),
            }
    elapsed = time.perf_counter() - start
    return {
        "status": "unresolved_budget" if elapsed > budget_s else "unresolved",
        "action": None,
        "negative": negative,
        "search": search,
        "attempts": attempts,
        "wall_s": elapsed,
        "deadline_exceeded": elapsed > budget_s,
    }
