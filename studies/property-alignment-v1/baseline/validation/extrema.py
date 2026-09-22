"""Additive sampled-extrema preservation with explicit refinement diagnostics.

This search does not certify a global extremum or continuous-time containment.
Callers may use require_resolved=True to fail on an unresolved refinement.
"""

from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable
import numpy as np
from scipy.optimize import minimize_scalar


@dataclass(frozen=True)
class ExtremeResult:
    value: float
    time_s: float
    sampled_extreme: float
    refinement_attempts: int
    unresolved: tuple[str, ...]
    globally_certified: bool = False


def bounded_extreme(
    function: Callable[[float], float],
    duration_s: float,
    *,
    maximize: bool,
    nodes: int = 65,
    optimizer=None,
    require_resolved: bool = False,
) -> ExtremeResult:
    if not np.isfinite(duration_s) or duration_s <= 0 or type(nodes) is not int or nodes < 3:
        raise ValueError("Positive finite duration and at least three nodes required")
    opt = minimize_scalar if optimizer is None else optimizer
    times = np.linspace(0.0, duration_s, nodes)
    values = np.array([float(function(float(t))) for t in times])
    if not np.all(np.isfinite(values)):
        raise ArithmeticError("Nonfinite sampled objective")
    sign = -1.0 if maximize else 1.0
    transformed = sign * values
    # Retain every observed node; refinements can never worsen this evidence.
    candidates = list(zip(values.tolist(), times.tolist()))
    unresolved, attempts = [], 0
    for i in range(1, nodes - 1):
        if not (transformed[i] <= transformed[i - 1] and transformed[i] <= transformed[i + 1]):
            continue
        attempts += 1
        lo, hi = float(times[i - 1]), float(times[i + 1])
        try:
            result = opt(
                lambda t: sign * function(float(t)),
                bounds=(lo, hi),
                method="bounded",
                options={"xatol": 1e-13, "maxiter": 200},
            )
        except (ArithmeticError, ValueError, RuntimeError) as exc:
            unresolved.append(f"bracket {i}: exception {type(exc).__name__}")
            continue
        if not result.success:
            unresolved.append(f"bracket {i}: optimizer unsuccessful")
            continue
        if not np.isfinite(result.x) or not np.isfinite(result.fun) or not lo <= result.x <= hi:
            unresolved.append(f"bracket {i}: invalid refinement result")
            continue
        value = float(function(float(result.x)))
        if not np.isfinite(value):
            unresolved.append(f"bracket {i}: nonfinite refined objective")
            continue
        best_bracket = min(transformed[i - 1 : i + 2])
        tolerance = 16 * np.finfo(float).eps * max(1.0, abs(best_bracket), abs(value))
        if sign * value > best_bracket + tolerance:
            unresolved.append(f"bracket {i}: refinement inferior to sampled bracket")
        candidates.append((value, float(result.x)))
    if require_resolved and unresolved:
        raise ArithmeticError("; ".join(unresolved))
    value, time_s = (max if maximize else min)(candidates, key=lambda p: p[0])
    sampled = float((np.max if maximize else np.min)(values))
    return ExtremeResult(value, time_s, sampled, attempts, tuple(unresolved))
