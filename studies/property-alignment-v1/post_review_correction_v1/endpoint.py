"""Illustrate the ambiguous inclusive sum, not a defect in the actual kernel."""

from fractions import Fraction as F
from .matrix import matrix_series, require


def evaluate():
    co, tail, norm = matrix_series()
    t = F(1, 4)
    matrix = [
        [sum((c[i][j] * t**k for k, c in enumerate(co)), F(0)) for j in range(6)] for i in range(6)
    ]
    command = (F(1, 100), F(0))
    forcing = sum((matrix[0][4 + j] * command[j] for j in range(2)), F(0))
    error = tail * max(abs(x) for x in command)
    require(forcing - error > 0)
    require(forcing + error < 2 * (forcing - error))
    result = {
        "assessed_formula": "completed sum b_j <= t plus the current segment contribution",
        "initial_state": ["0", "-80", "0", "0"],
        "command": [str(x) for x in command],
        "single_segment": ["0", str(t)],
        "evaluation_time": str(t),
        "correct_radial_forcing_contribution": [str(forcing - error), str(forcing + error)],
        "double_counted_radial_forcing_contribution": [
            str(2 * (forcing - error)),
            str(2 * (forcing + error)),
        ],
        "correct_display_m": float(forcing),
        "double_counted_display_m": float(2 * forcing),
        "intervals_disjoint": True,
        "claim": "The current segment must be excluded from the completed sum, including at its endpoint.",
        "implementation_contradiction_claimed": False,
        "supplement_S46_already_uses_correct_j_less_than_k": True,
    }
    return result
