"""Analytical clarification after the developmental matrix; no trial replacement.
The longest safe blind prefix and the longest blind interval compatible with
later recovery are different objects even for a scalar double integrator.
"""

from fractions import Fraction as Q
from ..scalar import quadratic_range, ScalarBox, action_is_safe, held_duration_bracket


def viable(q, v, halfwidth=1, authority=Q(2, 5)):
    q, v, L, U = map(Q, (q, v, halfwidth, authority))
    if L <= 0 or U <= 0:
        raise ValueError("Positive physical scales required")
    return q + max(v, 0) ** 2 / (2 * U) <= L and -q + max(-v, 0) ** 2 / (2 * U) <= L


def symmetric_deadline(position, speed, halfwidth=1, authority=Q(2, 5)):
    a, v, L, U = map(Q, (position, speed, halfwidth, authority))
    if not 0 <= a <= L or v <= 0 or U <= 0:
        raise ValueError("Symmetric outward moving pair required")
    margin = L - a - v * v / (2 * U)
    return None if margin < 0 else margin / v


def witness(duration):
    t = Q(duration)
    if t < 0:
        raise ValueError("Nonnegative blind time")
    paths = []
    for sign in (-1, 1):
        q, v = sign * Q(9, 10), sign * Q(1, 5)
        segments = []
        for length, u in [(t, Q(0)), (Q(1), -sign * Q(2, 5)), (Q(1), sign * Q(1, 5)), (Q(1), Q(0))]:
            lo, hi = quadratic_range(q, v, u, length)
            segments.append(
                {"duration": str(length), "command": str(u), "minimum": str(lo), "maximum": str(hi)}
            )
            q = q + v * length + u * length * length / 2
            v = v + u * length
        paths.append(
            {
                "sign": sign,
                "segments": segments,
                "contained": all(Q(s["minimum"]) >= -1 and Q(s["maximum"]) <= 1 for s in segments),
                "final_q": str(q),
                "final_v": str(v),
                "zero_command_remains_safe": v == 0 and abs(q) <= 1,
            }
        )
    return {
        "blind_time_s": str(t),
        "paths": paths,
        "all_recover": all(p["contained"] and p["zero_command_remains_safe"] for p in paths),
    }


def result():
    pair = [ScalarBox(".9", ".9", ".2", ".2"), ScalarBox("-.9", "-.9", "-.2", "-.2")]
    durations = (Q(0), Q(1, 8), Q(1, 4), Q(2501, 10000), Q(1, 2))
    rows = []
    for t in durations:
        paths = witness(t)
        true_recovery = t <= Q(1, 4)
        if paths["all_recover"] != true_recovery:
            raise AssertionError("Analytical witness mismatch")
        rows.append(
            {
                **paths,
                "exact_recovery_feasible": true_recovery,
                "safe_blind_prefix": True if t == 0 else action_is_safe(pair, 0, t),
            }
        )
    deadline = symmetric_deadline(".9", ".2")
    assert deadline == Q(1, 4)
    return {
        "schema": "sal-scalar-recovery-clarification/1",
        "recovery_deadline_s": str(deadline),
        "prefix_deadline_bracket": held_duration_bracket(pair, 1),
        "rows": rows,
        "scope": "Exact deterministic scalar symmetric pair; full state revealed at the end of blindness; no noise or orbital-theorem claim",
        "proof_outline": "Viability set is convex and reflection-symmetric. The common held-action feasibility set is convex and symmetric, so feasibility implies zero is feasible. Under zero, the outward state must satisfy a+v*T+v^2/(2U)<=L. Maximal braking proves sufficiency.",
        "explicit_sampled_recovery": "The exhibited specific pair uses one-second held recovery commands after the blind interval, then exact zero-velocity holding.",
        "broad_novelty_claim": False,
        "original_development_rows_changed": False,
    }
