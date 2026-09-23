"""Exact-rational polynomial fixtures with Bernstein convex-hull range bounds."""

from dataclasses import dataclass
from fractions import Fraction as Q
from math import comb
from .interval import Interval, Box, rational_bounds


def bernstein_range(coefficients, lower, upper):
    c = tuple(Q(v) for v in coefficients)
    a, b = Q(lower), Q(upper)
    if not c or a > b:
        raise ValueError("Polynomial coefficients and ordered interval required")
    n = len(c) - 1
    # Substitute t = a+(b-a)s, then convert power coefficients to Bernstein.
    power = [
        sum((c[j] * comb(j, k) * a ** (j - k) * (b - a) ** k for j in range(k, n + 1)), Q(0))
        for k in range(n + 1)
    ]
    bernstein = [
        sum((power[k] * Q(comb(j, k), comb(n, k)) for k in range(j + 1)), Q(0))
        for j in range(n + 1)
    ]
    return min(bernstein), max(bernstein)


@dataclass(frozen=True)
class PolynomialArc:
    start: Q
    end: Q
    c: tuple[tuple[Q, ...], ...]
    evidence_kind: str = "exact_polynomial_enclosure"

    def __post_init__(self):
        if Q(self.start) < 0 or Q(self.end) <= Q(self.start) or len(self.c) != 4:
            raise ValueError("Finite positive planar polynomial arc required")
        for c in self.c:
            if not c:
                raise ValueError("Empty coordinate polynomial")
            for v in c:
                Q(v)

    def range(self, start, end):
        a, b = Q(start), Q(end)
        if not Q(self.start) <= a <= b <= Q(self.end):
            raise ValueError("Requested time outside polynomial arc")
        result = []
        for c in self.c:
            lo, hi = bernstein_range(c, a - Q(self.start), b - Q(self.start))
            result.append(Interval(rational_bounds(lo)[0], rational_bounds(hi)[1]))
        return Box(tuple(result))

    def point(self, time):
        return self.range(time, time)
