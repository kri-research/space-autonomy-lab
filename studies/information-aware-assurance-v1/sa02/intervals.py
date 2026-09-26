"""Exact-rational interval contractors; outer bounds, never feasibility witnesses."""

from dataclasses import dataclass
from fractions import Fraction as Q
from functools import lru_cache
from math import factorial, isqrt

from iaa.types import rational

GRID = 10**12


@dataclass(frozen=True)
class Interval:
    lo: Q
    hi: Q

    def __post_init__(self):
        object.__setattr__(self, "lo", rational(self.lo))
        object.__setattr__(self, "hi", rational(self.hi))
        if self.lo > self.hi:
            raise ValueError("Empty interval")

    def __add__(self, other):
        other = interval(other)
        return Interval(self.lo + other.lo, self.hi + other.hi)

    __radd__ = __add__

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def __sub__(self, other):
        return self + -interval(other)

    def __mul__(self, other):
        other = interval(other)
        values = [a * b for a in (self.lo, self.hi) for b in (other.lo, other.hi)]
        return Interval(min(values), max(values))

    __rmul__ = __mul__

    def intersect(self, other):
        low, high = max(self.lo, other.lo), min(self.hi, other.hi)
        return None if low > high else Interval(low, high)

    def square(self):
        low = 0 if self.lo <= 0 <= self.hi else min(self.lo**2, self.hi**2)
        return Interval(low, max(self.lo**2, self.hi**2))

    @property
    def width(self):
        return self.hi - self.lo

    def contains(self, value):
        return self.lo <= rational(value) <= self.hi


def interval(value):
    return value if isinstance(value, Interval) else Interval(value, value)


def symmetric(radius):
    radius = rational(radius)
    if radius < 0:
        raise ValueError("Negative uncertainty")
    return Interval(-radius, radius)


def rounded(value):
    return Interval(Q((value.lo * GRID).__floor__(), GRID), Q((value.hi * GRID).__ceil__(), GRID))


def sqrt_bounds(value):
    if value.lo < 0:
        raise ValueError("Negative radicand")

    def lower(x):
        return Q(isqrt((x.numerator * GRID**2) // x.denominator), GRID)

    lo, hi = lower(value.lo), lower(value.hi)
    if hi * hi < value.hi:
        hi += Q(1, GRID)
    return Interval(lo, hi)


@lru_cache(maxsize=1024)
def sincos(value):
    """Taylor remainder plus 1-Lipschitz extension; valid across bearing wrap."""
    centre = (value.lo + value.hi) / 2
    radius = value.width / 2
    if abs(centre) > 8 or radius >= 2:
        return Interval(-1, 1), Interval(-1, 1)
    sine = sum((-1) ** k * centre ** (2 * k + 1) / factorial(2 * k + 1) for k in range(18))
    cosine = sum((-1) ** k * centre ** (2 * k) / factorial(2 * k) for k in range(19))
    se = abs(centre) ** 37 / factorial(37) + radius
    ce = abs(centre) ** 38 / factorial(38) + radius
    unit = Interval(-1, 1)
    return rounded(Interval(sine - se, sine + se)).intersect(unit), rounded(
        Interval(cosine - ce, cosine + ce)
    ).intersect(unit)


def contract_linear(box, coefficients, target, passes=2):
    """Box consistency for target containing sum(a_i*x_i); never an inner set."""
    if len(box) != len(coefficients):
        raise ValueError("Constraint dimension mismatch")
    out = list(box)
    coefficients = tuple(map(rational, coefficients))
    for _ in range(passes):
        total = sum((x * a for x, a in zip(out, coefficients, strict=True)), interval(0))
        if total.intersect(target) is None:
            return None
        for j, a in enumerate(coefficients):
            if not a:
                continue
            other = sum(
                (x * b for k, (x, b) in enumerate(zip(out, coefficients, strict=True)) if k != j),
                interval(0),
            )
            permitted = (target - other) * (1 / a)
            out[j] = out[j].intersect(permitted)
            if out[j] is None:
                return None
    return tuple(out)


def radial_contract(x, y, radius):
    """Necessary Cartesian bounds for a nonnegative distance interval."""
    if radius.lo < 0:
        raise ValueError("Negative radius")
    out = [x, y]
    for j in range(2):
        other = out[1 - j].square()
        sq = (
            Interval(max(Q(0), radius.lo**2 - other.hi), radius.hi**2 - other.lo)
            if radius.hi**2 >= other.lo
            else None
        )
        if sq is None:
            return None
        roots = sqrt_bounds(sq)
        permitted = Interval(-roots.hi, roots.hi)
        if out[j].lo >= 0:
            permitted = Interval(roots.lo, roots.hi)
        elif out[j].hi <= 0:
            permitted = Interval(-roots.hi, -roots.lo)
        out[j] = out[j].intersect(permitted)
        if out[j] is None:
            return None
    return tuple(out)
