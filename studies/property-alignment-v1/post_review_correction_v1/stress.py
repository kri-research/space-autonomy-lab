"""Named fixed-command stress checks; not an all-command impossibility test."""

from .matrix import matrix_series, F, STATE, FACES, PAIRS, require


def point(state, command):
    co, tail, _norm = matrix_series()
    aug = (*state, *command)
    error = tail * max(abs(x) for x in aug)
    center = [sum(sum(c[i][j] * aug[j] for j in range(6)) for c in co) for i in range(4)]
    return [(x - error, x + error) for x in center]


def min_square(lo, hi):
    return F(0) if lo <= 0 <= hi else min(lo * lo, hi * hi)


def evaluate():
    trials = []
    for kind, index, shift, command in [
        ("outward_position", 1, (F(".0009"), F(0), F(0), F(0)), PAIRS[2][1]),
        ("outward_velocity", 1, (F(0), F(0), F(".001"), F(0)), PAIRS[2][1]),
        ("one_second_zero_queue", 0, (F(0),) * 4, (F(0), F(0))),
    ]:
        state = tuple(x + d for x, d in zip(STATE[index], shift))
        require(all(sum(a * x for a, x in zip(n, state[:2])) <= b for n, b in FACES))
        z = point(state, command)
        excess = [
            sum(a * (z[i][0] if a >= 0 else z[i][1]) for i, a in enumerate(n)) - b for n, b in FACES
        ]
        ellipse_lower = 9 * min_square(*z[0]) + 4 * min_square(z[1][0] + 30, z[1][1] + 30) - 36
        require(max(excess) > 0 and ellipse_lower > 0)
        trials.append(
            {
                "kind": kind,
                "origin": [str(x) for x in state],
                "command_on_first_second": [str(x) for x in command],
                "time_s": "1",
                "enclosure": [[str(a), str(b)] for a, b in z],
                "corridor_violation_lower_m": float(max(excess)),
                "ellipse_polynomial_excess_lower": float(ellipse_lower),
                "outside_both_components": True,
            }
        )
    result = {
        "passed": True,
        "cases": trials,
        "imported_study_code": False,
        "scope": "fixed-command stress witnesses only; no all-command impossibility inferred",
    }
    return result
