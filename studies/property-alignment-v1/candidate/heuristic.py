"""Interpretable stopping-score ablation, deliberately NOT an assurance rule."""

from fractions import Fraction as Q
import math
from .affine import checked_outer_halfspaces


def individual_wall_scores(info):
    normals, limits = checked_outer_halfspaces()
    rows = []
    for i, h in enumerate(info.hypotheses):
        for normal, limit in zip(normals, limits, strict=True):
            position = max(
                sum(Q(n) * x for n, x in zip(normal, v[:2], strict=True)) for v in h.vertices()
            )
            velocity = max(
                sum(Q(n) * x for n, x in zip(normal, v[2:], strict=True)) for v in h.vertices()
            )
            clearance = float(limit - position)
            norm = math.hypot(*map(float, normal))
            brake = float(info.authority * info.effectiveness[0]) * norm - float(
                info.disturbance
            ) * sum(abs(float(n)) for n in normal)
            closing = max(0.0, float(velocity))
            distance = (
                None
                if brake <= 0 and closing > 0
                else (closing**2 / (2 * brake) if closing else 0.0)
            )
            score = None if distance is None else clearance - distance
            rows.append(
                {
                    "hypothesis": i,
                    "normal": list(map(str, normal)),
                    "clearance_m": clearance / norm,
                    "score_m": None if score is None else score / norm,
                }
            )
    return {
        "wall_scores": rows,
        "all_nonnegative": all(r["score_m"] is not None and r["score_m"] >= 0 for r in rows),
        "certified_safe": False,
        "known_omissions": [
            "orbital coupling",
            "joint common-command quantifier",
            "nonconvex region shape",
            "command queue",
        ],
        "scope": "per-hypothesis scalar stopping heuristic, not the exact scalar common-input comparator",
    }
