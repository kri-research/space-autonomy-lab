"""Tube predictive safety filter with stored-plan and invariant-terminal backup.
Reconstructs the linear deterministic special case of published predictive filters.
Mode enumeration is an explicit conservative search restriction, not a convexified union.
"""

from dataclasses import dataclass
import time
import warnings
import numpy as np
import cvxpy as cp
from .solver import solver_diagnostics
from .common import (
    A,
    B,
    K,
    ROOT_P,
    TARGET,
    H,
    BAND,
    ELLIPSE,
    U_MAX,
    ALPHA,
    CHORD_MARGIN,
    CHECK_MARGIN,
    pnorm,
    radius_for_box,
    pending_safe,
)


@dataclass
class Decision:
    command: np.ndarray | None
    status: str
    protected: bool
    details: dict


class PredictiveFilter:
    def __init__(self, tube, horizon=180, solver_time_limit=0.2, decision_limit=1.0, switches=None):
        self.tube = tube
        self.horizon = int(horizon)
        if self.horizon < 2 or self.horizon > 200:
            raise ValueError("Bounded prediction horizon required")
        self.solver_time_limit = solver_time_limit
        self.decision_limit = decision_limit
        self.switches = tuple(
            sorted(set(switches or [0, int(0.5 * horizon), int(0.75 * horizon), horizon - 1]))
        )
        if any(type(j) is not int or not 0 <= j < horizon for j in self.switches):
            raise ValueError("Mode schedule")
        self.programs = []
        self.plan = None
        started = time.perf_counter()
        for switch in self.switches:
            self.programs.append(self._program(switch))
        self.setup_wall_s = time.perf_counter() - started

    def _program(self, switch):
        n = self.horizon
        tube = self.tube
        z = cp.Variable((4, n + 1))
        u = cp.Variable((2, n))
        x0 = cp.Parameter(4)
        radii = cp.Parameter(n + 1, nonneg=True)
        proposal = cp.Parameter(2)
        reserve = tube.support_U * radii[:-1] + tube.input_error
        constraints = [
            z[:, 0] == x0 - TARGET,
            z[:, 1:] == A @ z[:, :-1] + B @ u,
            cp.norm(u, axis=0) <= U_MAX - reserve - 1.0e-7,
            cp.norm(z[2:, :], axis=0) <= 2.0 - tube.support_V * radii - CHECK_MARGIN,
            cp.norm(ROOT_P @ z[:, -1]) <= ALPHA - radii[-1] - CHECK_MARGIN,
        ]
        if switch > 0:
            margins = np.linalg.norm(H, axis=1) * (CHORD_MARGIN + CHECK_MARGIN)
            rhs = (BAND - H @ TARGET[:2] - margins)[:, None] - cp.multiply(
                tube.support_A[:, None], radii[None, : switch + 1]
            )
            constraints.append(H @ z[:2, : switch + 1] <= rhs)
        constraints.append(
            cp.norm(ELLIPSE @ z[:2, switch:], axis=0)
            <= 1.0 - 0.5 * (CHORD_MARGIN + CHECK_MARGIN) - tube.support_E * radii[switch:]
        )
        objective = cp.Minimize(
            cp.sum_squares((u[:, 0] - proposal) / U_MAX) + 1.0e-8 * cp.sum_squares(u / U_MAX)
        )
        problem = cp.Problem(objective, constraints)
        x0.value = TARGET
        proposal.value = np.zeros(2)
        radii.value = np.full(n + 1, 0.001)
        problem.get_problem_data(cp.CLARABEL)
        return dict(switch=switch, z=z, u=u, x0=x0, radii=radii, proposal=proposal, problem=problem)

    def residuals(self, x0, u, z_solver, radii, switch):
        z = np.empty((4, self.horizon + 1))
        z[:, 0] = x0 - TARGET
        for i in range(self.horizon):
            z[:, i + 1] = A @ z[:, i] + B @ u[:, i]
        dynamic = float(np.max(np.abs(z - z_solver)))
        tube = self.tube
        values = [
            float(
                np.max(
                    np.linalg.norm(u, axis=0)
                    + tube.support_U * radii[:-1]
                    + tube.input_error
                    - U_MAX
                    + 5.0e-8
                )
            ),
            float(
                np.max(
                    np.linalg.norm(z[2:, :], axis=0)
                    + tube.support_V * radii
                    - 2.0
                    + CHECK_MARGIN / 2
                )
            ),
            pnorm(z[:, -1]) + radii[-1] - ALPHA + CHECK_MARGIN / 2,
        ]
        if switch > 0:
            margins = np.linalg.norm(H, axis=1) * (CHORD_MARGIN + CHECK_MARGIN / 2)
            q = z[:2, : switch + 1] + TARGET[:2, None]
            values.append(
                float(
                    np.max(
                        H @ q
                        - BAND[:, None]
                        + margins[:, None]
                        + tube.support_A[:, None] * radii[None, : switch + 1]
                    )
                )
            )
        values.append(
            float(
                np.max(
                    np.linalg.norm(ELLIPSE @ z[:2, switch:], axis=0)
                    + 0.5 * (CHORD_MARGIN + CHECK_MARGIN / 2)
                    + tube.support_E * radii[switch:]
                    - 1.0
                )
            )
        )
        return z, {
            "dynamic_max_abs": dynamic,
            "max_tightened_constraint_residual": max(values),
            "terminal_residual": values[2],
            "passed": dynamic <= 1.0e-5 and max(values) <= 0.0,
        }

    def backup(self, info):
        if self.plan is None:
            return Decision(None, "no_previous_feasible_plan", False, {})
        p = self.plan
        index = info.application_at - p["start"]
        if index < 0:
            return Decision(None, "nonmonotone_application_time", False, {})
        if index >= self.horizon:
            u = K @ (info.estimate - TARGET)
            origin = "terminal_feedback"
            consistent = (
                pnorm(info.estimate - TARGET) <= ALPHA + radius_for_box(info.error) + 1.0e-8
            )
        else:
            u = p["u"][:, index] + K @ (info.estimate - TARGET - p["z"][:, index])
            origin = "stored_tube_feedback"
            consistent = (
                pnorm(info.estimate - TARGET - p["z"][:, index])
                <= p["radii"][index] + radius_for_box(info.error) + 1.0e-8
            )
        if not consistent or not np.all(np.isfinite(u)) or np.linalg.norm(u) > U_MAX:
            return Decision(None, "backup_assumption_or_bound_failure", False, {"backup": origin})
        return Decision(
            u,
            origin,
            True,
            {
                "backup_plan_start": p["start"],
                "backup_index": index,
                "guarantee": "conditional_stored_plan_under_unchanged_admitted_bounds",
            },
        )

    def decide(self, info, proposal, force_solver_failure=False):
        started = time.perf_counter()
        cpu = time.process_time()
        proposal = np.asarray(proposal, dtype=float)
        if proposal.shape != (2,) or not np.all(np.isfinite(proposal)):
            raise ValueError("Finite proposal required")
        if not self.tube.check_information(info) or not pending_safe(info, self.tube):
            return Decision(None, "uncertified_information_or_terminal_bound", False, {})
        radii = self.tube.radii(radius_for_box(info.error), self.horizon)
        attempts = []
        candidates = []
        for p in self.programs:
            if force_solver_failure or time.perf_counter() - started > self.decision_limit:
                break
            p["x0"].value = info.estimate
            p["radii"].value = radii
            p["proposal"].value = proposal
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    p["problem"].solve(
                        solver=cp.CLARABEL,
                        warm_start=True,
                        verbose=False,
                        max_iter=100,
                        time_limit=self.solver_time_limit,
                        tol_gap_abs=1.0e-9,
                        tol_gap_rel=1.0e-9,
                        tol_feas=1.0e-9,
                    )
                status = p["problem"].status
                attempt = {
                    "switch": p["switch"],
                    "status": status,
                    "solver_s": p["problem"].solver_stats.solve_time,
                    "iterations": p["problem"].solver_stats.num_iters,
                }
                attempt.update(solver_diagnostics(p["problem"]))
                if status == "optimal" and p["u"].value is not None:
                    u = np.array(p["u"].value)
                    z = np.array(p["z"].value)
                    if np.all(np.isfinite(u)) and np.all(np.isfinite(z)):
                        exact_z, check = self.residuals(info.estimate, u, z, radii, p["switch"])
                        attempt.update(check)
                        if check["passed"] and attempt["optimality_residual_check"]:
                            candidates.append((float(p["problem"].value), u, exact_z, p["switch"]))
                attempts.append(attempt)
            except Exception as exc:
                attempts.append(
                    {
                        "switch": p["switch"],
                        "status": "solver_exception",
                        "error": type(exc).__name__,
                    }
                )
        elapsed = time.perf_counter() - started
        if candidates and elapsed <= self.decision_limit:
            objective, u, z, switch = min(candidates, key=lambda r: r[0])
            self.plan = {
                "start": info.application_at,
                "u": u,
                "z": z,
                "radii": radii.copy(),
                "switch": switch,
            }
            result = Decision(
                u[:, 0].copy(),
                "feasible_predictive_plan",
                True,
                {
                    "objective": objective,
                    "switch": switch,
                    "terminal_radius": radii[-1],
                    "searched_all_declared_subproblems": len(attempts) == len(self.programs),
                    "global_nonconvex_optimum_claimed": False,
                },
            )
        else:
            result = self.backup(info)
            if (
                not candidates
                and result.command is None
                and all(a.get("status") == "infeasible" for a in attempts)
                and attempts
            ):
                result.status = "infeasible_declared_schedule_search"
        result.details.update(
            attempts=attempts,
            wall_s=time.perf_counter() - started,
            cpu_s=time.process_time() - cpu,
            deadline_exceeded=elapsed > self.decision_limit,
            setup_wall_s=self.setup_wall_s,
            numerical_implementation_not_machine_proved=True,
        )
        return result
