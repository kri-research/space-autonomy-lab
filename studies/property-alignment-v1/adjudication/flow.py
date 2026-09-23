"""Independent validated planar HCW and circular-chief nonlinear Taylor flow.

Only held, constant local acceleration is supported on each segment. Intervals
may bound a constant but unknown input, not an arbitrary time-varying input.
A checked a-priori Picard box bounds the Taylor remainder. No online imports.
"""

from dataclasses import dataclass
from fractions import Fraction as Q
from .interval import Interval, Box, iv, ONE
from .series import Jet


@dataclass(frozen=True)
class Model:
    kind: str
    mu: float = 398600441800000.0
    radius: float = 6778137.0
    mean_motion: float = 0.0011313666536110223

    def __post_init__(self):
        if self.kind not in ("hcw", "nonlinear"):
            raise ValueError("Unsupported validated model")
        if any(iv(x).lo <= 0 for x in (self.mu, self.radius, self.mean_motion)):
            raise ValueError("Positive finite model constants required")

    @property
    def n(self):
        if self.kind == "hcw":
            return iv(self.mean_motion)
        return (iv(self.mu) / (iv(self.radius) ** 3)).sqrt()

    def rhs(self, state, command):
        x, y, vx, vy = state
        n = self.n
        if self.kind == "hcw":
            return (vx, vy, x * (3 * n * n) + vy * (2 * n) + command[0], vx * (-2 * n) + command[1])
        r = iv(self.radius)
        s = (x / r) * 2 + (x * x + y * y) / (r * r) + 1
        inv = s.inverse_three_halves()
        ax = ((x / r + 1) * inv - 1) * (-iv(self.mu) / (r * r))
        ay = y * inv * (-iv(self.mu) / (r * r * r))
        return (
            vx,
            vy,
            ax + vy * (2 * n) + x * (n * n) + command[0],
            ay + vx * (-2 * n) + y * (n * n) + command[1],
        )

    def field(self, box, command):
        out = self.rhs(tuple(Jet((v,)) for v in box.coordinates), command)
        return tuple(j.c[0] for j in out)

    def lipschitz_bound(self, box):
        n = self.n
        if self.kind == "hcw":
            return max(1.0, (3 * n * n + 2 * n).hi)
        x, y, _, _ = box.coordinates
        r = iv(self.radius)
        rx, ry = ONE + x / r, y / r
        s = rx.square() + ry.square()
        if s.lo <= 0:
            raise ArithmeticError("Gravity singularity in existence box")
        g = (iv(self.mu) / (r * r * r)) / (s * s.sqrt())
        xx = -g + 3 * g * rx.square() / s + n * n
        xy = 3 * g * rx * ry / s
        yy = -g + 3 * g * ry.square() / s + n * n
        row_x = iv(xx.absmax) + xy.absmax + 2 * n
        row_y = iv(yy.absmax) + xy.absmax + 2 * n
        return max(1.0, row_x.hi, row_y.hi)


def coefficients(model, initial, command, order):
    c = [[v] for v in initial.coordinates]
    for k in range(order):
        derivatives = model.rhs(tuple(Jet(tuple(v)) for v in c), command)
        for j in range(4):
            c[j].append(derivatives[j].c[k] / (k + 1))
    return tuple(tuple(v) for v in c)


def existence_box(model, initial, command, h):
    time = Interval(0.0, h.hi)
    y = Box(tuple(v.inflate() for v in initial.coordinates))
    for _ in range(16):
        image = Box(
            tuple(
                x + time * f
                for x, f in zip(initial.coordinates, model.field(y, command), strict=True)
            )
        )
        if y.contains(image):
            contraction = (h * model.lipschitz_bound(y)).hi
            if contraction >= 1:
                raise ArithmeticError("Picard contraction bound not below one")
            return y, contraction
        y = Box(
            tuple(
                a.hull(b).inflate() for a, b in zip(y.coordinates, image.coordinates, strict=True)
            )
        )
    raise ArithmeticError("A-priori flow enclosure did not close")


@dataclass(frozen=True)
class TaylorArc:
    start: Q
    end: Q
    polynomial: tuple[tuple[Interval, ...], ...]
    remainder: tuple[Interval, ...]
    apriori: Box
    contraction: float
    model_kind: str
    evidence_kind: str = "validated_interval_taylor"

    def range(self, start, end):
        a, b = Q(start), Q(end)
        if not self.start <= a <= b <= self.end:
            raise ValueError("Requested time outside validated arc")
        if a == b == self.start:
            return Box(tuple(c[0] for c in self.polynomial))
        tau = Interval(iv(a - self.start).lo, iv(b - self.start).hi)
        out = []
        for c, rem in zip(self.polynomial, self.remainder, strict=True):
            value = c[-1]
            for coefficient in reversed(c[:-1]):
                value = value * tau + coefficient
            out.append(value + rem * (tau ** len(c)))
        return Box(tuple(out))

    def point(self, time):
        return self.range(time, time)


def make_arc(model, initial, command, start, end, order=8):
    a, b = Q(start), Q(end)
    if a < 0 or b <= a or b - a > Q(1, 4):
        raise ValueError("Positive segment of at most 0.25 s required")
    if type(order) is not int or not 2 <= order <= 12:
        raise ValueError("Taylor order must be between 2 and 12")
    if not isinstance(initial, Box) or len(command) != 2:
        raise ValueError("Planar interval state and held input required")
    u = tuple(iv(v) for v in command)
    h = iv(b - a)
    enclosure, contraction = existence_box(model, initial, u, h)
    nominal = coefficients(model, initial, u, order - 1)
    remainder = tuple(c[-1] for c in coefficients(model, enclosure, u, order))
    return TaylorArc(a, b, nominal, remainder, enclosure, contraction, model.kind)


def split_times(start, end, maximum_step, event_times=()):
    a, b, h = Q(start), Q(end), Q(maximum_step)
    if a < 0 or b <= a or not 0 < h <= Q(1, 4):
        raise ValueError("Invalid time domain or maximum validated step")
    events = [Q(t) for t in event_times]
    if any(t < a or t > b for t in events):
        raise ValueError("Event time outside propagation domain")
    knots = sorted({a, b, *events})
    result = [a]
    for boundary in knots[1:]:
        while boundary - result[-1] > h:
            result.append(result[-1] + h)
        result.append(boundary)
    return result


def propagate_schedule(model, initial, segments, *, maximum_step=0.25, event_times=(), order=8):
    """Segments are (start,end,held_realized_acceleration); no missing-input fallback."""
    segments = tuple(segments)
    event_times = tuple(event_times)
    if not segments:
        raise ValueError("Empty execution schedule")
    previous = Q(segments[0][0])
    if previous != 0:
        raise ValueError("Episode must begin at zero")
    for a, b, u in segments:
        if Q(a) != previous or Q(b) <= Q(a) or len(u) != 2:
            raise ValueError("Gap, overlap or malformed executed input")
        for value in u:
            iv(value)
        previous = Q(b)
    if any(Q(t) < 0 or Q(t) > previous for t in event_times):
        raise ValueError("Unexpected event outside execution")
    state = initial if isinstance(initial, Box) else Box.point(initial)
    arcs = []
    for a, b, u in segments:
        events = [t for t in event_times if Q(a) <= Q(t) <= Q(b)]
        knots = split_times(a, b, maximum_step, events)
        for ta, tb in zip(knots[:-1], knots[1:], strict=True):
            arc = make_arc(model, state, u, ta, tb, order)
            arcs.append(arc)
            state = arc.point(tb)
    return arcs
