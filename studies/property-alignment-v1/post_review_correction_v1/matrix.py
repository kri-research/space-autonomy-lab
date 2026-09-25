"""Additional exact-rational checks of the existing three-state construction.

Adapted from author-provided corrected checking code. Exact fractions decide the
verdicts; floats appear only in display fields. The augmented-matrix formulation
is separate from the original trigonometric and ODE-based implementations.
The complete original-source identities and adaptation boundary are recorded in
SOURCE.json. No original command, model constant or perturbation bound is changed.
"""

from fractions import Fraction as F
from math import comb, factorial


def require(condition):
    if not condition:
        raise ValueError("Exact-rational matrix certificate check failed")


N = F(5217507778172933, 4611686018427387904)
U = F(1, 50)
ORDER = 22
STATE = (
    (F(0), F("-99.99905"), F(0), F("-0.001")),
    (F("7.99905"), F(-80), F(".001"), F(0)),
    (F("-7.99905"), F(-80), F("-.001"), F(0)),
)
PAIRS = (
    ((0, 1), (F("-.004"), F(".004"))),
    ((0, 2), (F(".004"), F(".004"))),
    ((1, 2), (F(0), F("-.006"))),
)
FACES = (
    ((F(0), F(-1)), F(100)),
    ((F(0), F(1)), F(-30)),
    ((F(1), F(1, 10)), F(0)),
    ((F(-1), F(1, 10)), F(0)),
)


def zeros():
    return [[F(0) for _ in range(6)] for _ in range(6)]


def multiply(a, b):
    return [
        [sum((a[i][k] * b[k][j] for k in range(6) if a[i][k] and b[k][j]), F(0)) for j in range(6)]
        for i in range(6)
    ]


def matrix_series():
    h = zeros()
    h[0][2] = h[1][3] = h[2][4] = h[3][5] = F(1)
    h[2][0], h[2][3], h[3][2] = 3 * N * N, 2 * N, -2 * N
    norm = max(sum(abs(x) for x in row) for row in h)
    coeff = [[[F(int(i == j)) for j in range(6)] for i in range(6)]]
    for k in range(1, ORDER + 1):
        nxt = multiply(h, coeff[-1])
        coeff.append([[x / F(k) for x in row] for row in nxt])
    require(all(isinstance(x, F) for matrix in coeff for row in matrix for x in row))
    # Every remaining term ratio is at most norm/(ORDER+2), for 0 <= t <= 1.
    require(norm < ORDER + 2)
    tail = norm ** (ORDER + 1) / factorial(ORDER + 1) / (1 - norm / F(ORDER + 2))
    return coeff, tail, norm


def combine_rows(matrix, normal):
    return [normal[0] * matrix[0][j] + normal[1] * matrix[1][j] for j in range(6)]


def evaluate():
    coefficients, tail, norm = matrix_series()
    endpoint = [[sum(c[i][j] for c in coefficients) for j in range(6)] for i in range(6)]
    bernstein = []
    for j in range(ORDER + 1):
        weights = [F(comb(j, k), comb(ORDER, k)) for k in range(j + 1)]
        bernstein.append(
            [
                [
                    sum(weights[k] * coefficients[k][i][column] for k in range(j + 1))
                    for column in range(6)
                ]
                for i in range(6)
            ]
        )
    require(all(isinstance(x, F) for matrix in bernstein for row in matrix for x in row))
    require(all(isinstance(x, F) for row in endpoint for x in row))
    results = []
    for label, p, v in [
        ("nominal", F(0), F(0)),
        ("reported_simultaneous_shift", F(3, 102400), F(3, 102400)),
    ]:
        initial_slacks = [
            bound - sum(a * x for a, x in zip(normal, s)) - p * sum(abs(a) for a in normal)
            for s in STATE
            for normal, bound in FACES
        ]
        require(min(initial_slacks) >= 0)
        pair_proofs = []
        for pair, command in PAIRS:
            require(sum(x * x for x in command) <= U * U)
            all_slacks = []
            for index in pair:
                augmented = (*STATE[index], *command)
                maximum_initial_norm = max(
                    abs(x) + ((p if j < 2 else v) if j < 4 else 0) for j, x in enumerate(augmented)
                )
                for face, (normal, bound) in enumerate(FACES):
                    error = sum(abs(a) for a in normal) * tail * maximum_initial_norm
                    for b in bernstein:
                        row = combine_rows(b, normal)
                        upper = (
                            sum(a * x for a, x in zip(row, augmented))
                            + p * sum(abs(a) for a in row[:2])
                            + v * sum(abs(a) for a in row[2:4])
                            + error
                        )
                        all_slacks.append((bound - upper, index, face))
            least, index, face = min(all_slacks)
            require(isinstance(least, F) and least > 0)
            pair_proofs.append(
                {
                    "pair": list(pair),
                    "command": [str(x) for x in command],
                    "minimum_continuous_slack_lower_m": str(least),
                    "display_slack_lower_m": float(least),
                    "limiting_state": index,
                    "limiting_face": face,
                    "bernstein_halfspace_checks": len(all_slacks),
                }
            )
        weights = (F(1, 11), F(5, 11), F(5, 11))
        selected = (FACES[0], FACES[2], FACES[3])
        rhs_upper = F(0)
        residual_intervals = [[F(0), F(0)] for _ in range(2)]
        for s, (normal, bound), weight in zip(STATE, selected, weights):
            row = combine_rows(endpoint, normal)
            component_error = tail * sum(abs(a) for a in normal)
            rhs = (
                bound
                - sum(a * x for a, x in zip(row[:4], s))
                + component_error * sum(abs(x) for x in s)
                + p * sum(abs(x) + component_error for x in row[:2])
                + v * sum(abs(x) + component_error for x in row[2:4])
            )
            rhs_upper += weight * rhs
            for j in range(2):
                residual_intervals[j][0] += weight * (row[4 + j] - component_error)
                residual_intervals[j][1] += weight * (row[4 + j] + component_error)
        residual = [max(abs(a), abs(b)) for a, b in residual_intervals]
        delta = -rhs_upper - U * sum(residual)
        require(isinstance(delta, F) and delta > 0)
        results.append(
            {
                "case": label,
                "position_radius_m": str(p),
                "velocity_radius_mps": str(v),
                "minimum_initial_slack_m": str(min(initial_slacks)),
                "pairwise_continuous_checks": pair_proofs,
                "obstruction_weights": [str(w) for w in weights],
                "uniform_obstruction_margin_lower_m": str(delta),
                "display_uniform_obstruction_margin_lower_m": float(delta),
                "all_independently_shifted_triples_verified": True,
            }
        )
    return {
        "schema": "sal-matrix-bernstein-check/1",
        "model_mean_motion_exact": str(N),
        "degree": ORDER,
        "matrix_infinity_norm": str(norm),
        "uniform_operator_tail_bound": str(tail),
        "results": results,
        "passed": True,
    }
