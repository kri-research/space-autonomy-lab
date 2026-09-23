"""Exact declared observation-equivalence classes and queued-command interface."""

from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import product
import hashlib
import json
from .scalar import rational
from adjudication.interval import Box, Interval, rational_bounds


@dataclass(frozen=True)
class Hypothesis:
    lower: tuple
    upper: tuple

    def __post_init__(self):
        for name in ("lower", "upper"):
            object.__setattr__(self, name, tuple(map(rational, getattr(self, name))))
        if (
            len(self.lower) != 4
            or len(self.upper) != 4
            or any(a > b for a, b in zip(self.lower, self.upper, strict=True))
        ):
            raise ValueError("Four ordered SI state intervals required")

    @classmethod
    def point(cls, state):
        return cls(tuple(state), tuple(state))

    def enclosure(self):
        return Box(
            tuple(
                Interval(rational_bounds(a)[0], rational_bounds(b)[1])
                for a, b in zip(self.lower, self.upper, strict=True)
            )
        )

    def vertices(self):
        return tuple(
            sorted(
                set(
                    product(
                        *[
                            tuple(sorted({a, b}))
                            for a, b in zip(self.lower, self.upper, strict=True)
                        ]
                    )
                )
            )
        )

    def contains(self, state):
        return len(state) == 4 and all(
            a <= rational(x) <= b for a, x, b in zip(self.lower, state, self.upper, strict=True)
        )


@dataclass(frozen=True)
class InformationSet:
    hypotheses: tuple[Hypothesis, ...]
    age: int = 0
    delay: int = 0
    queue: tuple = ()
    authority: Q = Q(1, 50)
    effectiveness: tuple = (Q(1), Q(1))
    disturbance: Q = Q(0)
    kind: str = "declared_exact_information_set"
    units: tuple = ("m", "m", "m/s", "m/s")

    def __post_init__(self):
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(self, "queue", tuple(tuple(map(rational, u)) for u in self.queue))
        object.__setattr__(self, "authority", rational(self.authority))
        object.__setattr__(self, "effectiveness", tuple(map(rational, self.effectiveness)))
        object.__setattr__(self, "disturbance", rational(self.disturbance))
        if (
            not self.hypotheses
            or len(self.hypotheses) > 16
            or any(not isinstance(h, Hypothesis) for h in self.hypotheses)
        ):
            raise ValueError("One to sixteen exact hypothesis boxes required")
        if (
            type(self.age) is not int
            or type(self.delay) is not int
            or self.age not in (0, 1)
            or self.delay not in (0, 1)
        ):
            raise ValueError("Separate zero/one-second age and intervention delay required")
        if len(self.queue) != self.age + self.delay:
            raise ValueError(
                "Known one-second command history must cover measurement to application"
            )
        if self.authority < 0 or self.authority > Q(1, 50) or self.disturbance < 0:
            raise ValueError("Invalid authority or disturbance")
        if (
            len(self.effectiveness) != 2
            or not 0 <= self.effectiveness[0] <= self.effectiveness[1] <= 1
        ):
            raise ValueError("Invalid actuator-effectiveness bounds")
        if any(len(u) != 2 or sum(v * v for v in u) > self.authority**2 for u in self.queue):
            raise ValueError("Invalid queued command")
        if self.kind not in (
            "declared_exact_information_set",
            "covariance_only",
            "outer_enclosure_only",
        ):
            raise ValueError("Unsupported evidence interpretation")
        if self.units != ("m", "m", "m/s", "m/s"):
            raise ValueError("Unsupported units or coordinate order")

    @property
    def application_time(self):
        return self.age + self.delay

    def payload(self):
        return {
            "schema": "sal-common-information/1",
            "hypotheses": [
                {"lower": list(map(str, h.lower)), "upper": list(map(str, h.upper))}
                for h in self.hypotheses
            ],
            "age": self.age,
            "delay": self.delay,
            "queue": [[str(x) for x in u] for u in self.queue],
            "authority": str(self.authority),
            "effectiveness": list(map(str, self.effectiveness)),
            "disturbance": str(self.disturbance),
            "kind": self.kind,
            "units": list(self.units),
            "command_period_s": 1,
            "observation_pattern": "no new distinguishing observation before this held command ends",
        }

    def identity(self):
        return hashlib.sha256(
            json.dumps(self.payload(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def hull(self):
        return Hypothesis(
            tuple(min(h.lower[j] for h in self.hypotheses) for j in range(4)),
            tuple(max(h.upper[j] for h in self.hypotheses) for j in range(4)),
        )
