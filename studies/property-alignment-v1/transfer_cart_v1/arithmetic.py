"""Directed decimal enclosures used only by the online transfer formulation."""

from dataclasses import dataclass
from decimal import Decimal as D, Context, ROUND_FLOOR, ROUND_CEILING, ROUND_HALF_EVEN
from fractions import Fraction as Q

LOW = Context(prec=50, rounding=ROUND_FLOOR)
HIGH = Context(prec=50, rounding=ROUND_CEILING)
NEAR = Context(prec=50, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class Interval:
    lo: D
    hi: D

    def __post_init__(self):
        if not self.lo.is_finite() or not self.hi.is_finite() or self.lo > self.hi:
            raise ValueError("Invalid finite interval")

    @classmethod
    def of(cls, x):
        if isinstance(x, cls):
            return x
        if isinstance(x, bool):
            raise ValueError("Boolean quantity")
        q = Q(str(x))
        return cls(
            LOW.divide(D(q.numerator), D(q.denominator)),
            HIGH.divide(D(q.numerator), D(q.denominator)),
        )

    def __add__(self, x):
        x = Interval.of(x)
        return Interval(LOW.add(self.lo, x.lo), HIGH.add(self.hi, x.hi))

    __radd__ = __add__

    def __neg__(self):
        return Interval(self.hi.copy_negate(), self.lo.copy_negate())

    def __sub__(self, x):
        return self + -Interval.of(x)

    def __rsub__(self, x):
        return Interval.of(x) + -self

    def __mul__(self, x):
        x = Interval.of(x)
        return Interval(
            min(LOW.multiply(a, b) for a in (self.lo, self.hi) for b in (x.lo, x.hi)),
            max(HIGH.multiply(a, b) for a in (self.lo, self.hi) for b in (x.lo, x.hi)),
        )

    __rmul__ = __mul__

    def __truediv__(self, x):
        x = Interval.of(x)
        if x.lo <= 0 <= x.hi:
            raise ValueError("Division through zero")
        return self * Interval(LOW.divide(D(1), x.hi), HIGH.divide(D(1), x.lo))

    def exp(self):
        a = NEAR.exp(self.lo)
        b = NEAR.exp(self.hi)
        return Interval(NEAR.next_minus(a), NEAR.next_plus(b))

    def square(self):
        products = self * self
        return (
            Interval(max(D(0), products.lo), products.hi) if self.lo <= 0 <= self.hi else products
        )

    def mid(self):
        return float(NEAR.divide(NEAR.add(self.lo, self.hi), D(2)))

    def absmax(self):
        return max(self.lo.copy_abs(), self.hi.copy_abs())

    def strings(self):
        return [str(self.lo), str(self.hi)]
