"""Robust relative-degree-two barrier constraints under one-second held control.
Each smooth component is certified separately and switching requires the new
component's h and psi1 conditions. This deliberately conservative union cover
never differentiates min(h_A,h_H) or treats a position barrier as degree one.
"""

from fractions import Fraction as Q
import time
import numpy as np
import cvxpy as cp
from adjudication.interval import Interval as I, Box, iv
from .common import N, U_MAX, uncertain_ranges, pending_safe
from .predictive import Decision
from .solver import solver_diagnostics


def forms(box, mode, rates, disturbance):
    x, y, vx, vy = box.coordinates
    k1, k2 = rates
    drift = (3 * iv(N) * iv(N) * x + 2 * iv(N) * vy, -2 * iv(N) * vx)
    w = I(-disturbance, disturbance)
    results = []
    if mode == "approach":
        for ax, ay, b in ((0, -1, 100), (0, 1, -30), (1, Q(1, 10), 0), (-1, Q(1, 10), 0)):
            h = iv(b) - ax * x - ay * y
            hd = -ax * vx - ay * vy
            const = -ax * (drift[0] + w) - ay * (drift[1] + w) + (k1 + k2) * hd + k1 * k2 * h
            results.append((h, hd + k1 * h, const, (iv(-ax), iv(-ay))))
    elif mode == "hold":
        qy = y + 30
        h = 1 - (x / 2).square() - (qy / 3).square()
        hd = -2 * (x * vx / 4 + qy * vy / 9)
        grad = (-x / 2, -2 * qy / 9)
        const = (
            -2 * (vx.square() / 4 + vy.square() / 9)
            + grad[0] * (drift[0] + w)
            + grad[1] * (drift[1] + w)
            + (k1 + k2) * hd
            + k1 * k2 * h
        )
        results.append((h, hd + k1 * h, const, grad))
    else:
        raise ValueError("Unknown smooth component")
    return results


class BarrierFilter:
    def __init__(self, tube, rates=(0.02, 0.04), solver_time_limit=0.2, decision_limit=1.0):
        if len(rates) != 2 or min(rates) <= 0:
            raise ValueError("Positive degree-two rates")
        self.tube = tube
        self.rates = tuple(rates)
        self.solver_time_limit = solver_time_limit
        self.decision_limit = decision_limit
        self.programs = {}
        started = time.perf_counter()
        for mode, m in [("approach", 4), ("hold", 1)]:
            u = cp.Variable(2)
            c = cp.Parameter(m)
            center = cp.Parameter((m, 2))
            radius = cp.Parameter((m, 2), nonneg=True)
            desired = cp.Parameter(2)
            constraints = [
                cp.norm(u) <= U_MAX - 1.0e-8,
                c + center @ u - radius @ cp.abs(u) >= 1.0e-7,
            ]
            problem = cp.Problem(cp.Minimize(cp.sum_squares((u - desired) / U_MAX)), constraints)
            c.value = np.ones(m)
            center.value = np.zeros((m, 2))
            radius.value = np.zeros((m, 2))
            desired.value = np.zeros(2)
            problem.get_problem_data(cp.CLARABEL)
            self.programs[mode] = (problem, u, c, center, radius, desired)
        self.setup_wall_s = time.perf_counter() - started

    def constraints(self, info, mode):
        initial = Box.center_error(info.estimate.tolist(), info.error.tolist())
        initial_forms = forms(initial, mode, self.rates, self.tube.disturbance_component)
        if any(h.lo < 0 or psi.lo < 0 for h, psi, c, a in initial_forms):
            return None, {
                "status": "outside_or_unresolved_barrier_domain",
                "initial_h_lower": [v[0].lo for v in initial_forms],
                "initial_psi1_lower": [v[1].lo for v in initial_forms],
            }
        # Comparison-system bounds also cover time-varying model discrepancy.
        boxes = uncertain_ranges(
            info.estimate, info.error, [0.0, 0.0], U_MAX + self.tube.disturbance_component
        )
        enclosure = initial
        for current in boxes:
            enclosure = Box(
                tuple(
                    a.hull(b)
                    for a, b in zip(enclosure.coordinates, current.coordinates, strict=True)
                )
            )
        data = forms(enclosure, mode, self.rates, self.tube.disturbance_component)
        constants = np.array([r[2].lo for r in data])
        centers = np.array([[(a.lo + a.hi) / 2 for a in r[3]] for r in data])
        widths = np.array(
            [
                [max(c - a.lo, a.hi - c) + 1.0e-14 for a, c in zip(r[3], cen, strict=True)]
                for r, cen in zip(data, centers, strict=True)
            ]
        )
        return (constants, centers, widths, data), {
            "status": "barrier_domain_valid",
            "initial_h_lower": [v[0].lo for v in initial_forms],
            "initial_psi1_lower": [v[1].lo for v in initial_forms],
            "cover_step_s": 1.0,
        }

    def decide(self, info, proposal, force_solver_failure=False):
        start = time.perf_counter()
        cpu = time.process_time()
        if not self.tube.check_information(info) or not pending_safe(info, self.tube):
            return Decision(None, "uncertified_information", False, {})
        attempts = []
        candidates = []
        for mode in ("approach", "hold"):
            try:
                data, detail = self.constraints(info, mode)
                detail["component"] = mode
                if data is None:
                    attempts.append(detail)
                    continue
                c, center, radius, interval_forms = data
                problem, u, pc, pa, pr, pd = self.programs[mode]
                pc.value = c
                pa.value = center
                pr.value = radius
                pd.value = proposal
                if force_solver_failure:
                    raise RuntimeError("Deliberately forced solver failure")
                problem.solve(
                    solver=cp.CLARABEL,
                    warm_start=True,
                    verbose=False,
                    max_iter=100,
                    time_limit=self.solver_time_limit,
                    tol_feas=1.0e-10,
                    tol_gap_abs=1.0e-10,
                    tol_gap_rel=1.0e-10,
                )
                detail.update(
                    solver_status=problem.status,
                    solver_s=problem.solver_stats.solve_time,
                    iterations=problem.solver_stats.num_iters,
                )
                detail.update(solver_diagnostics(problem))
                if problem.status == "optimal" and u.value is not None:
                    value = np.asarray(u.value).copy()
                    # Validate the candidate directly using interval arithmetic, not solver flags.
                    lower = [
                        (f[2] + f[3][0] * iv(float(value[0])) + f[3][1] * iv(float(value[1]))).lo
                        for f in interval_forms
                    ]
                    valid = (
                        detail["optimality_residual_check"]
                        and np.all(np.isfinite(value))
                        and np.linalg.norm(value) <= U_MAX
                        and min(lower) >= 0
                    )
                    detail.update(
                        psi2_lower=lower,
                        action_norm=float(np.linalg.norm(value)),
                        checked_feasible=bool(valid),
                    )
                    if valid:
                        candidates.append((float(problem.value), value, mode))
                attempts.append(detail)
            except Exception as exc:
                attempts.append(
                    {"component": mode, "status": "unresolved", "error": type(exc).__name__}
                )
        elapsed = time.perf_counter() - start
        if candidates and elapsed <= self.decision_limit:
            obj, u, mode = min(candidates, key=lambda row: row[0])
            result = Decision(
                u,
                "robust_sampled_barrier",
                True,
                {
                    "component": mode,
                    "objective": obj,
                    "guarantee": "one_step_comparison_principle; continued protection requires persistent feasibility",
                },
            )
        else:
            result = Decision(None, "no_feasible_barrier_certificate", False, {})
        result.details.update(
            attempts=attempts,
            wall_s=elapsed,
            cpu_s=time.process_time() - cpu,
            deadline_exceeded=elapsed > self.decision_limit,
            setup_wall_s=self.setup_wall_s,
        )
        return result
