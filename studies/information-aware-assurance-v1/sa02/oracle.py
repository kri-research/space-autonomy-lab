"""Separately written exact polytope reference for small linear observation histories.

No production interval arithmetic, polar contractor or observer is imported.
For y_i = x0 + t_i*v + b + known_i + error_i, enumerate exact feasible vertices.
The initial box makes the polytope compact. This does not verify nonlinear HCW.
"""

from fractions import Fraction
from itertools import combinations


def solve(rows, rhs):
    n = len(rhs)
    a = [list(map(Fraction, row)) + [Fraction(b)] for row, b in zip(rows, rhs, strict=True)]
    for j in range(n):
        pivot = next((i for i in range(j, n) if a[i][j]), None)
        if pivot is None:
            return None
        a[j], a[pivot] = a[pivot], a[j]
        v = a[j][j]
        a[j] = [x / v for x in a[j]]
        for i in range(n):
            if i == j:
                continue
            v = a[i][j]
            a[i] = [x - v * y for x, y in zip(a[i], a[j], strict=True)]
    return tuple(row[-1] for row in a)


def vertices(bounds, constraints):
    n = len(bounds)
    if not 1 <= n <= 3 or len(constraints) > 16:
        raise ValueError("Small exact oracle only")
    rows = []
    rhs = []
    for j, (low, high) in enumerate(bounds):
        row = [Fraction(0)] * n
        row[j] = Fraction(1)
        rows.extend([tuple(row), tuple(-x for x in row)])
        rhs.extend([Fraction(high), -Fraction(low)])
    for row, low, high in constraints:
        row = tuple(map(Fraction, row))
        if len(row) != n:
            raise ValueError("Oracle dimension")
        rows.extend([row, tuple(-x for x in row)])
        rhs.extend([Fraction(high), -Fraction(low)])
    found = set()
    for chosen in combinations(range(len(rows)), n):
        x = solve([rows[i] for i in chosen], [rhs[i] for i in chosen])
        if x is not None and all(
            sum(a * b for a, b in zip(row, x, strict=True)) <= r
            for row, r in zip(rows, rhs, strict=True)
        ):
            found.add(x)
    return tuple(sorted(found))


def hull(points):
    if not points:
        return None
    return tuple(
        (min(p[j] for p in points), max(p[j] for p in points)) for j in range(len(points[0]))
    )


def scalar_history(bounds, packets, now):
    constraints = []
    for t, value, error, known in packets:
        y = Fraction(value) - Fraction(known)
        e = Fraction(error)
        constraints.append(((1, Fraction(t), 1), y - e, y + e))
    points = vertices(bounds, constraints)
    projected = tuple((x + Fraction(now) * v, v, b) for x, v, b in points)
    return {"vertices": points, "initial_hull": hull(points), "decision_hull": hull(projected)}


def hcw_point_bounds(initial, action, duration, effectiveness=1, disturbance=(0, 0)):
    """Independent rational augmented-matrix series with a rigorous tail.

    Covers one constant-input HCW point trajectory, 0 <= duration <= 3 s.
    The matrix is written here from the equations, without production imports.
    This is a propagation oracle, not an observation-compatible witness builder.
    """
    from math import factorial

    q = Fraction
    n = q(11, 10000)
    t = q(duration)
    if not 0 <= t <= 3 or len(initial) != 4 or len(action) != 2:
        raise ValueError("Small HCW reference domain")
    u = tuple(q(effectiveness) * q(a) + q(w) for a, w in zip(action, disturbance, strict=True))
    matrix = (
        (0, 0, 1, 0, 0),
        (0, 0, 0, 1, 0),
        (3 * n * n, 0, 0, 2 * n, u[0]),
        (0, 0, -2 * n, 0, u[1]),
        (0, 0, 0, 0, 0),
    )
    degree = 28
    original = tuple(map(q, initial)) + (q(1),)
    term = original
    total = original
    for k in range(1, degree + 1):
        term = tuple(
            sum(q(a) * x for a, x in zip(row, term, strict=True)) * t / k for row in matrix
        )
        total = tuple(a + b for a, b in zip(total, term, strict=True))
    norm_time = max(sum(abs(q(a)) for a in row) for row in matrix) * t
    ratio = norm_time / (degree + 2)
    if ratio >= 1:
        raise ValueError("Reference series tail not bounded")
    tail = max(map(abs, original)) * norm_time ** (degree + 1) / factorial(degree + 1) / (1 - ratio)
    return tuple((x - tail, x + tail) for x in total[:4])
