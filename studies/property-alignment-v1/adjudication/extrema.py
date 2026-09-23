"""Sample-preserving helper v1.1; derived from the supplied baseline utility.

Retains its grid and scalar bracket/refinement strategy. Additional validation
contains malformed optimizer results and exceptions during refined reevaluation.
This method never certifies a global continuous-time extreme.
"""

from dataclasses import dataclass
import math
import numpy as np
from scipy.optimize import minimize_scalar

VERSION = "sample-preserving/1.1"


@dataclass(frozen=True)
class Result:
    value: float
    time_s: float
    sampled_extreme: float
    unresolved: tuple[str, ...]
    refinement_attempts: int
    globally_certified: bool = False


def bounded_extreme(
    function, duration_s, *, maximize, nodes=65, optimizer=None, require_resolved=False
):
    if type(maximize) is not bool or type(require_resolved) is not bool:
        raise ValueError("Explicit Boolean search options required")
    if type(duration_s) not in (int, float) or not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("Positive finite duration required")
    if type(nodes) is not int or nodes < 3:
        raise ValueError("At least three nodes required")
    times = np.linspace(0.0, duration_s, nodes)
    values = [float(function(float(t))) for t in times]
    if not all(math.isfinite(v) for v in values):
        raise ArithmeticError("Nonfinite sampled objective")
    candidates = list(zip(values, map(float, times), strict=True))
    sign = -1 if maximize else 1
    transformed = [sign * v for v in values]
    unresolved = []
    attempts = 0
    opt = minimize_scalar if optimizer is None else optimizer
    for i in range(1, nodes - 1):
        if not transformed[i] <= min(transformed[i - 1], transformed[i + 1]):
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
            if not isinstance(result.success, (bool, np.bool_)) or not result.success:
                raise ValueError("unsuccessful optimizer")
            x, value = float(result.x), float(result.fun)
            if not math.isfinite(x) or not math.isfinite(value) or not lo <= x <= hi:
                raise ValueError("nonfinite or out-of-bracket result")
            actual = float(function(x))
            if not math.isfinite(actual):
                raise ValueError("nonfinite reevaluated objective")
            tolerance = 16 * np.finfo(float).eps * max(1.0, abs(actual), abs(values[i]))
            if sign * actual > min(transformed[i - 1 : i + 2]) + tolerance:
                unresolved.append(f"bracket {i}: inferior refinement")
            candidates.append((actual, x))
        except Exception as exc:
            # The optional strict mode surfaces any refinement failure. Grid evidence
            # survives even a plugin programming error; no success certificate follows.
            unresolved.append(f"bracket {i}: {type(exc).__name__}: {exc}")
    if require_resolved and unresolved:
        raise ArithmeticError("; ".join(unresolved))
    selector = max if maximize else min
    value, time = selector(candidates, key=lambda p: p[0])
    return Result(value, time, selector(values), tuple(unresolved), attempts)
