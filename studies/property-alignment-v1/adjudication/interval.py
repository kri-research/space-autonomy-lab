"""Finite outward binary64 intervals; no solver, gate, NumPy or BLAS dependency.

The four basic floating operations require IEEE-754 binary64 rounding. Each is
widened by one representable number. Square-root bounds are checked with exact
rational squares, not an assumed libm error bound. Overflow is an error.
"""

from dataclasses import dataclass
from fractions import Fraction as Q
import math
import sys


def down(x):
    if not math.isfinite(x):
        raise ArithmeticError("Nonfinite interval operation")
    y = math.nextafter(x, -math.inf)
    if not math.isfinite(y):
        raise ArithmeticError("Interval endpoint overflow")
    return y


def up(x):
    if not math.isfinite(x):
        raise ArithmeticError("Nonfinite interval operation")
    y = math.nextafter(x, math.inf)
    if not math.isfinite(y):
        raise ArithmeticError("Interval endpoint overflow")
    return y


def rational_bounds(q):
    q = Q(q)
    x = float(q)
    if not math.isfinite(x):
        raise ArithmeticError("Rational conversion overflow")
    return (down(x) if Q(x) > q else x, up(x) if Q(x) < q else x)


@dataclass(frozen=True, slots=True)
class Interval:
    lo: float
    hi: float

    def __post_init__(self):
        if sys.float_info.radix != 2 or sys.float_info.mant_dig != 53:
            raise RuntimeError("IEEE binary64 required")
        for x in (self.lo, self.hi):
            if type(x) not in (int, float) or not math.isfinite(x):
                raise ValueError("Finite interval endpoints required")
            if isinstance(x, int) and Q(float(x)) != x:
                raise ValueError("Integer endpoint is not exactly representable")
        if self.lo > self.hi:
            raise ValueError("Reversed interval")

    @classmethod
    def point(cls, x):
        if type(x) not in (int, float, Q):
            raise ValueError("Explicit finite real parameter required")
        return cls(*rational_bounds(x))

    def __add__(self, other):
        b = iv(other)
        if self == ZERO:
            return b
        if b == ZERO:
            return self
        return Interval(down(self.lo + b.lo), up(self.hi + b.hi))

    __radd__ = __add__

    def __neg__(self):
        return Interval(-self.hi, -self.lo)

    def __sub__(self, other):
        b = iv(other)
        if self.lo == self.hi == b.lo == b.hi:
            return ZERO
        return self + (-b)

    def __rsub__(self, other):
        return iv(other) + (-self)

    def __mul__(self, other):
        b = iv(other)
        if self == ZERO or b == ZERO:
            return ZERO
        if self == ONE:
            return b
        if b == ONE:
            return self
        values = [a * c for a in (self.lo, self.hi) for c in (b.lo, b.hi)]
        if not all(math.isfinite(v) for v in values):
            raise ArithmeticError("Interval multiplication overflow")
        return Interval(down(min(values)), up(max(values)))

    __rmul__ = __mul__

    def reciprocal(self):
        if self.lo <= 0 <= self.hi:
            raise ArithmeticError("Division interval includes zero")
        return Interval(down(1.0 / self.hi), up(1.0 / self.lo))

    def __truediv__(self, other):
        return self * iv(other).reciprocal()

    def __rtruediv__(self, other):
        return iv(other) * self.reciprocal()

    def square(self):
        if self == ZERO:
            return ZERO
        lo = 0.0 if self.lo <= 0 <= self.hi else min(abs(self.lo), abs(self.hi))
        hi = max(abs(self.lo), abs(self.hi))
        return Interval(0.0 if lo == 0 else max(0.0, down(lo * lo)), up(hi * hi))

    def __pow__(self, n):
        if type(n) is not int or n < 0:
            raise ValueError("Nonnegative integer power required")
        if n == 0:
            return ONE
        if n == 1:
            return self
        half = self ** (n // 2)
        return half.square() * (self if n % 2 else ONE)

    def sqrt(self):
        if self.lo < 0:
            raise ArithmeticError("Square root domain violated")
        ends = []
        for value, lower in ((self.lo, True), (self.hi, False)):
            x = math.sqrt(value)
            for _ in range(8):
                square = Q(x) * Q(x)
                if (square <= Q(value)) if lower else (square >= Q(value)):
                    break
                x = down(x) if lower else up(x)
            else:
                raise ArithmeticError("Could not verify square-root bound")
            ends.append(x)
        return Interval(*ends)

    def contains(self, other):
        b = iv(other)
        return self.lo <= b.lo and b.hi <= self.hi

    def hull(self, other):
        b = iv(other)
        return Interval(min(self.lo, b.lo), max(self.hi, b.hi))

    def inflate(self):
        # A-priori existence search only; this is not a classification tolerance.
        pad = up(up((self.hi - self.lo) * 0.125) + up(max(1.0, abs(self.lo), abs(self.hi)) * 1e-12))
        return self + Interval(-pad, pad)

    @property
    def absmax(self):
        return max(abs(self.lo), abs(self.hi))


def iv(x):
    return x if isinstance(x, Interval) else Interval.point(x)


ZERO = Interval(0.0, 0.0)
ONE = Interval(1.0, 1.0)


@dataclass(frozen=True, slots=True)
class Box:
    coordinates: tuple[Interval, Interval, Interval, Interval]

    def __post_init__(self):
        if len(self.coordinates) != 4 or not all(isinstance(x, Interval) for x in self.coordinates):
            raise ValueError("Exactly four planar state intervals required")

    @classmethod
    def point(cls, state):
        if len(state) != 4:
            raise ValueError("Nonplanar or malformed state")
        return cls(tuple(iv(x) for x in state))

    @classmethod
    def center_error(cls, state, errors):
        if len(state) != 4 or len(errors) != 4:
            raise ValueError("Four state components and component errors required")
        ee = [iv(e) for e in errors]
        if any(e.lo < 0 for e in ee):
            raise ValueError("Negative numerical uncertainty")
        return cls(tuple(iv(x) + Interval(-e.hi, e.hi) for x, e in zip(state, ee, strict=True)))

    def contains(self, state):
        b = state if isinstance(state, Box) else Box.point(state)
        return all(a.contains(c) for a, c in zip(self.coordinates, b.coordinates, strict=True))

    @property
    def widths(self):
        return tuple(up(x.hi - x.lo) if x.hi != x.lo else 0.0 for x in self.coordinates)
