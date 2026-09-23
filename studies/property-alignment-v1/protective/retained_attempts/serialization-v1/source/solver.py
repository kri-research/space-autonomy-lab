"""Pinned Clarabel diagnostics, separate from physical endpoint adjudication."""

import math


def solver_diagnostics(problem):
    try:
        solution = problem._solver_cache["CLARABEL"].get_solution()
        primal = float(solution.r_prim)
        dual = float(solution.r_dual)
        objective = float(solution.obj_val)
        dual_objective = float(solution.obj_val_dual)
        gap = abs(objective - dual_objective)
        finite = all(math.isfinite(x) for x in (primal, dual, objective, dual_objective, gap))
        passed = (
            finite
            and str(solution.status) == "Solved"
            and primal <= 1.0e-7
            and dual <= 1.0e-7
            and gap <= 1.0e-6 * (1 + abs(objective))
        )
        return {
            "backend_status": str(solution.status),
            "primal_residual": primal,
            "dual_residual": dual,
            "objective": objective,
            "dual_objective": dual_objective,
            "absolute_duality_gap": gap,
            "optimality_residual_check": bool(passed),
            "interface": "CVXPY1.9.2 pinned Clarabel backend cache",
        }
    except Exception as exc:
        return {"optimality_residual_check": False, "diagnostic_error": type(exc).__name__}
