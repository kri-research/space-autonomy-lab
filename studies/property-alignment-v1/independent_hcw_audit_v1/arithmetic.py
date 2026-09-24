"""192-bit fixed-fraction dyadic interval arithmetic using only Python integers.

Each endpoint is an integer multiple of 2**-192. All operations round outward.
There is no floating-point decision or external interval library in this module.
"""

from dataclasses import dataclass
from fractions import Fraction as Q
import re

BITS = 192
SCALE = 1 << BITS


def rational(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Q)):
        raise ValueError("Exact rational string/integer required")
    if isinstance(value, str) and (
        len(value) > 4096
        or re.fullmatch(r"[+-]?(?:[0-9]+(?:/[0-9]+|\.[0-9]*)?|\.[0-9]+)", value) is None
    ):
        # Reject exponential expansion before Fraction construction. Decimal
        # fixtures remain exact; production records require canonical a/b below.
        raise ValueError("Bounded exact rational or decimal literal required")
    try:
        return Q(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid rational") from exc


def floor_q(value):
    q = rational(value)
    return q.numerator * SCALE // q.denominator


def ceil_q(value):
    q = rational(value)
    return -((-q.numerator * SCALE) // q.denominator)


@dataclass(frozen=True, slots=True)
class Interval:
    lo: int
    hi: int

    def __post_init__(self):
        if type(self.lo) is not int or type(self.hi) is not int or self.lo > self.hi:
            raise ValueError("Ordered integer dyadic endpoints required")

    @classmethod
    def value(cls, x):
        return x if isinstance(x, cls) else cls(floor_q(x), ceil_q(x))

    @classmethod
    def bounds(cls, lo, hi):
        if rational(lo) > rational(hi):
            raise ValueError("Reversed interval")
        return cls(floor_q(lo), ceil_q(hi))

    @property
    def lower(self):
        return Q(self.lo, SCALE)

    @property
    def upper(self):
        return Q(self.hi, SCALE)

    def __add__(self, other):
        b = Interval.value(other)
        return Interval(self.lo + b.lo, self.hi + b.hi)

    __radd__ = __add__

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def __sub__(self, other):
        return self + -Interval.value(other)

    def __rsub__(self, other):
        return Interval.value(other) + -self

    def __mul__(self, other):
        b = Interval.value(other)
        v = (self.lo * b.lo, self.lo * b.hi, self.hi * b.lo, self.hi * b.hi)
        return Interval(min(v) // SCALE, -((-max(v)) // SCALE))

    __rmul__ = __mul__

    def __truediv__(self, other):
        b = Interval.value(other)
        if b.lo <= 0 <= b.hi:
            raise ZeroDivisionError("Interval denominator contains zero")
        ratios = [Q(x * SCALE, y) for x in (self.lo, self.hi) for y in (b.lo, b.hi)]
        a, z = min(ratios), max(ratios)
        return Interval(a.numerator // a.denominator, -((-z.numerator) // z.denominator))

    def square(self):
        lower = 0 if self.lo <= 0 <= self.hi else min(self.lo * self.lo, self.hi * self.hi)
        upper = max(self.lo * self.lo, self.hi * self.hi)
        return Interval(lower // SCALE, -((-upper) // SCALE))

    def __pow__(self, n):
        if type(n) is not int or n < 0:
            raise ValueError("Nonnegative integer power")
        out = Interval.value(1)
        for _ in range(n):
            out = out * self
        return out

    def contains(self, x):
        b = Interval.value(x)
        return self.lo <= b.lo and self.hi >= b.hi

    def overlaps(self, other):
        b = Interval.value(other)
        return max(self.lo, b.lo) <= min(self.hi, b.hi)

    def payload(self):
        return [str(self.lower), str(self.upper)]


ZERO = Interval.value(0)
ONE = Interval.value(1)


def dot(a, b):
    if len(a) != len(b):
        raise ValueError("Dot-product dimensions")
    return sum((Interval.value(x) * y for x, y in zip(a, b, strict=True)), ZERO)


def mv(a, x):
    return tuple(dot(row, x) for row in a)


def mm(a, b):
    if not a or not b or any(len(row) != len(b) for row in a):
        raise ValueError("Matrix dimensions")
    return tuple(tuple(dot(row, col) for col in zip(*b, strict=True)) for row in a)
