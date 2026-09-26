"""Conventional Picard/Euler inclusion in dimensionless SI-scaled coordinates.

All bound arithmetic is rational. Quantisation rounds outwards, never to nearest.
This is a coarse finite-horizon bound, not a sensor estimator or recovery theorem.
"""

from fractions import Fraction as Q

from .types import StateBox, millis, rational

N = Q(11, 10000)
A = (
    (Q(0), Q(0), Q(1), Q(0)),
    (Q(0), Q(0), Q(0), Q(1)),
    (3 * N * N, Q(0), Q(0), 2 * N),
    (Q(0), Q(0), -2 * N, Q(0)),
)
LIPSCHITZ = max(sum(abs(x) for x in row) for row in A)
GRID = 10**12


def down(value):
    return Q((value * GRID).__floor__(), GRID)


def up(value):
    return Q((value * GRID).__ceil__(), GRID)


def derivative(box, action, effectiveness, disturbance):
    eta_lo, eta_hi = map(rational, effectiveness)
    w = rational(disturbance)
    if not 0 <= eta_lo <= eta_hi <= 1 or w < 0:
        raise ValueError("Invalid dynamics uncertainty")
    u = tuple(map(rational, action))
    if len(u) != 2:
        raise ValueError("Two acceleration components required")
    lo, hi = [], []
    for i, row in enumerate(A):
        low = sum(
            min(a * lower, a * h) for a, lower, h in zip(row, box.lower, box.upper, strict=True)
        )
        high = sum(
            max(a * lower, a * h) for a, lower, h in zip(row, box.lower, box.upper, strict=True)
        )
        if i >= 2:
            low += min(eta_lo * u[i - 2], eta_hi * u[i - 2]) - w
            high += max(eta_lo * u[i - 2], eta_hi * u[i - 2]) + w
        lo.append(low)
        hi.append(high)
    return tuple(lo), tuple(hi)


def step(box, action, duration_ms, effectiveness=(Q(4, 5), Q(1)), disturbance=Q(1, 100000)):
    """Return endpoint enclosure and continuous tube; see CONTRACT.md derivation."""
    millis(duration_ms)
    if not 0 < duration_ms <= 50:
        raise ValueError("Validated step is restricted to (0, 50] ms")
    h = Q(duration_ms, 1000)
    f0, f1 = derivative(box, action, effectiveness, disturbance)
    magnitude = max(abs(x) for x in (*f0, *f1))
    radius = h * magnitude / (1 - h * LIPSCHITZ)
    broad = StateBox(tuple(x - radius for x in box.lower), tuple(x + radius for x in box.upper))
    fl, fu = derivative(broad, action, effectiveness, disturbance)
    tube = StateBox(
        tuple(down(x + min(Q(0), h * f)) for x, f in zip(box.lower, fl, strict=True)),
        tuple(up(x + max(Q(0), h * f)) for x, f in zip(box.upper, fu, strict=True)),
    )
    endpoint = StateBox(
        tuple(down(x + h * f) for x, f in zip(box.lower, fl, strict=True)),
        tuple(up(x + h * f) for x, f in zip(box.upper, fu, strict=True)),
    )
    return endpoint, tube


def propagate(box, action, duration_ms, effectiveness=(Q(4, 5), Q(1)), disturbance=Q(1, 100000)):
    millis(duration_ms)
    if duration_ms > 60000:
        raise ValueError("Bounded reference propagation only")
    tubes = []
    remaining = duration_ms
    while remaining:
        h = min(50, remaining)
        box, tube = step(box, action, h, effectiveness, disturbance)
        tubes.append(tube)
        remaining -= h
    return box, tuple(tubes)


def inside(box):
    """Closed research box, distinct from mission success or invariant recovery."""
    return -8 <= box.lower[0] <= box.upper[0] <= 8 and -60 <= box.lower[1] <= box.upper[1] <= -30


def separated(box, radius=Q(10)):
    nearest = [
        Q(0) if lower <= 0 <= h else min(abs(lower), abs(h))
        for lower, h in zip(box.lower[:2], box.upper[:2], strict=True)
    ]
    return sum(x * x for x in nearest) > radius**2


def terminal(box):
    """Sufficient dwell eligibility only, not an invariant terminal set."""
    return (
        box.lower[0] >= Q(-35, 100)
        and box.upper[0] <= Q(35, 100)
        and box.lower[1] >= Q(-4035, 100)
        and box.upper[1] <= Q(-3965, 100)
        and sum(
            max(abs(lower), abs(h)) ** 2
            for lower, h in zip(box.lower[2:], box.upper[2:], strict=True)
        )
        <= Q(1, 20) ** 2
    )
