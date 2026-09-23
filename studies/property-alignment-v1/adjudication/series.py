"""Truncated interval Taylor arithmetic; coefficients include factorial scaling."""

from dataclasses import dataclass
from .interval import Interval, iv, ZERO, ONE


@dataclass(frozen=True, slots=True)
class Jet:
    c: tuple[Interval, ...]

    def __post_init__(self):
        if not self.c or not all(isinstance(v, Interval) for v in self.c):
            raise ValueError("Nonempty interval coefficient tuple required")

    def coerce(self, value):
        if isinstance(value, Jet):
            if len(self.c) != len(value.c):
                raise ValueError("Taylor orders differ")
            return value
        return Jet((iv(value),) + (ZERO,) * (len(self.c) - 1))

    def __add__(self, value):
        b = self.coerce(value)
        return Jet(tuple(a + c for a, c in zip(self.c, b.c, strict=True)))

    __radd__ = __add__

    def __neg__(self):
        return Jet(tuple(-v for v in self.c))

    def __sub__(self, value):
        return self + (-self.coerce(value))

    def __rsub__(self, value):
        return self.coerce(value) + (-self)

    def __mul__(self, value):
        b = self.coerce(value)
        return Jet(
            tuple(
                sum((self.c[i] * b.c[k - i] for i in range(k + 1)), ZERO)
                for k in range(len(self.c))
            )
        )

    __rmul__ = __mul__

    def __truediv__(self, scalar):
        return self * iv(scalar).reciprocal()

    def inverse_three_halves(self):
        if self.c[0].lo <= 0:
            raise ArithmeticError("Radial-distance series crosses gravity singularity")
        base = self.c[0].sqrt()
        y = [ONE / (self.c[0] * base)]
        # a y' = (-3/2) a' y, coefficient recurrence in exact half-integers.
        for k in range(1, len(self.c)):
            total = sum((self.c[i] * y[k - i] * (-0.5 * i - k) for i in range(1, k + 1)), ZERO)
            y.append(total / (self.c[0] * k))
        return Jet(tuple(y))
