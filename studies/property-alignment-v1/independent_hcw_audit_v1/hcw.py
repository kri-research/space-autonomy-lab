"""Closed-form planar HCW response, separate from the online ODE-Taylor core."""

from fractions import Fraction as Q
from functools import lru_cache
from math import factorial
from .arithmetic import Interval, ZERO, ONE, mv, mm, rational

N = Q(5217507778172933, 4611686018427387904)
SERIES_TERMS = 10
MAX_TIME = Q(3)
MAX_ARGUMENT = Q(1, 32)


def response(z, offset):
    """sum (-1)^k z^(2k)/(2k+offset)!, with a uniform alternating remainder.

    On [0,1/32] successive magnitudes decrease. With k=0,...,9 the
    remainder is positive and at most z_hi^20/(20+offset)!. Horner interval
    evaluation plus directed dyadic rounding encloses the whole argument range.
    """
    z = Interval.value(z)
    if offset not in (1, 2, 3) or z.lo < 0 or z.upper > MAX_ARGUMENT:
        raise ValueError("Unsupported response-series domain")
    zz = z.square()
    result = Interval.value(Q(-1, factorial(18 + offset)))
    for k in range(8, -1, -1):
        result = result * zz + Q((-1) ** k, factorial(2 * k + offset))
    tail = z.upper**20 / Q(factorial(20 + offset))
    return result + Interval.bounds(0, tail)


@lru_cache(maxsize=8192)
def maps(start, end, n=N):
    """All four state rows and two constant-input columns for t in [start,end].

    n can be a nonnegative interval for explicit post hoc model-bound fixtures.
    A fixed mean motion is assumed along each admitted trajectory.
    """
    a, b = rational(start), rational(end)
    n = Interval.value(n)
    if not 0 <= a <= b <= MAX_TIME or n.lo < 0 or (n * Interval.value(b)).upper > MAX_ARGUMENT:
        raise ValueError("HCW time or mean-motion domain")
    t = Interval.bounds(a, b)
    t2 = t.square()
    t3 = t2 * t
    s, c, d = (response(n * t, j) for j in (1, 2, 3))
    n2 = n.square()
    n3 = n2 * n
    omc = n2 * t2 * c
    qms = n3 * t3 * d
    phi = (
        (1 + 3 * omc, ZERO, t * s, 2 * n * t2 * c),
        (-6 * qms, ONE, -2 * n * t2 * c, t - 4 * n2 * t3 * d),
        (3 * n2 * t * s, ZERO, 1 - omc, 2 * n * t * s),
        (-6 * n3 * t2 * c, ZERO, -2 * n * t * s, 1 - 4 * omc),
    )
    gamma = (
        (t2 * c, 2 * n * t3 * d),
        (-2 * n * t3 * d, t2 * (4 * c - Q(3, 2))),
        (t * s, 2 * n * t2 * c),
        (-2 * n * t2 * c, t - 4 * n2 * t3 * d),
    )
    return phi, gamma


def advance(state, forcing, duration, n=N):
    a, b = maps(duration, duration, n)
    return tuple(x + y for x, y in zip(mv(a, state), mv(b, forcing), strict=True))


def validate_segments(segments, end=None):
    cursor = Q(0)
    if not segments:
        raise ValueError("Empty input schedule")
    out = []
    for a, b, u in segments:
        a, b = rational(a), rational(b)
        if a != cursor or not a < b <= MAX_TIME or len(u) != 2:
            raise ValueError("Gap/overlap or unsupported duration")
        u = tuple(Interval.value(v) for v in u)
        out.append((a, b, u))
        cursor = b
    if end is not None and cursor != rational(end):
        raise ValueError("Wrong end time")
    return tuple(out)


@lru_cache(maxsize=8192)
def past_response(a, b, begin, end, n=N):
    phi, _ = maps(a - end, b - end, n)
    _, gamma = maps(end - begin, end - begin, n)
    return mm(phi, gamma)


def state_range(initial, segments, a, b, n=N):
    """Superposition from the ORIGINAL box and each independent forcing segment.

    No propagated-box corner is treated as an attainable origin. Coefficient
    intervals are summed outward. The query must lie within one input segment.
    """
    a, b = rational(a), rational(b)
    if len(initial) != 4 or not 0 <= a <= b <= segments[-1][1]:
        raise ValueError("Invalid query")
    for begin, end, u in segments:
        if begin < a < end < b:
            raise ValueError("Query crosses an input event")
        if a <= begin < b and begin > a:
            raise ValueError("Query crosses an input event")
    phi, _ = maps(a, b, n)
    result = list(mv(phi, initial))
    for begin, end, u in segments:
        if begin >= b:
            break
        if end <= a:
            gamma = past_response(a, b, begin, end, n)
        elif begin <= a and b <= end:
            _, gamma = maps(a - begin, b - begin, n)
        else:
            raise ValueError("Query crosses an input event")
        term = mv(gamma, u)
        result = [x + y for x, y in zip(result, term, strict=True)]
    return tuple(result)


def exact_schedule_range(state, segments, time, n=N):
    """Point-state/point-input validated trajectory enclosure, not a point sample proof."""
    segments = validate_segments(segments)
    return state_range(tuple(Interval.value(v) for v in state), segments, time, time, n)
