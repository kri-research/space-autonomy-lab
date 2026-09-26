"""Typed internal contracts with explicit units, versions and evidence semantics."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from fractions import Fraction as Q

FRAME = "chief-centred-radial-alongtrack/1"
STATE_UNITS = ("m", "m", "m/s", "m/s")
AUTHORITY = Q(1, 50)


def rational(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Q)):
        raise ValueError("Finite real or rational required")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Nonfinite value")
    return Q(str(value))


def millis(value):
    if type(value) is not int or value < 0:
        raise ValueError("Nonnegative integer milliseconds required")
    return value


def primitive(value):
    if is_dataclass(value):
        return primitive(asdict(value))
    if isinstance(value, Q):
        return str(value)
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    return value


def encode(value):
    return json.dumps(primitive(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


class Status(StrEnum):
    BOUNDED_PREFIX = "bounded_prefix"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class StateBox:
    lower: tuple[Q, Q, Q, Q]
    upper: tuple[Q, Q, Q, Q]
    frame: str = FRAME
    units: tuple[str, ...] = STATE_UNITS

    def __post_init__(self):
        for name in ("lower", "upper"):
            object.__setattr__(self, name, tuple(rational(x) for x in getattr(self, name)))
        if len(self.lower) != 4 or len(self.upper) != 4:
            raise ValueError("Four state components required")
        if any(a > b for a, b in zip(self.lower, self.upper, strict=True)):
            raise ValueError("Reversed state interval")
        if self.frame != FRAME or self.units != STATE_UNITS:
            raise ValueError("Frame or units mismatch")

    @classmethod
    def around(cls, centre, radii):
        if len(centre) != 4 or len(radii) != 4:
            raise ValueError("Four components required")
        c = tuple(rational(x) for x in centre)
        r = tuple(rational(x) for x in radii)
        if any(x < 0 for x in r):
            raise ValueError("Negative radius")
        return cls(
            tuple(x - y for x, y in zip(c, r, strict=True)),
            tuple(x + y for x, y in zip(c, r, strict=True)),
        )

    def contains(self, state):
        return len(state) == 4 and all(
            a <= rational(x) <= b for a, x, b in zip(self.lower, state, self.upper, strict=True)
        )


@dataclass(frozen=True)
class ObservationPacket:
    packet_id: str
    sequence: int
    channel: str
    value: float
    acquired_ms: int
    available_ms: int
    timestamp_uncertainty_ms: int = 2
    unit: str = "m"
    frame: str = FRAME
    schema: str = "iaa-observation/1"

    def __post_init__(self):
        for name in ("sequence", "acquired_ms", "available_ms", "timestamp_uncertainty_ms"):
            millis(getattr(self, name))
        if self.schema != "iaa-observation/1" or self.frame != FRAME:
            raise ValueError("Unsupported observation schema/frame")
        if self.channel not in ("range", "bearing"):
            raise ValueError("Unsupported channel")
        if self.unit != ("m" if self.channel == "range" else "rad"):
            raise ValueError("Wrong observation unit")
        if not isinstance(self.packet_id, str) or not self.packet_id or len(self.packet_id) > 100:
            raise ValueError("Invalid packet identifier")
        rational(self.value)
        if self.channel == "range" and self.value < 0:
            raise ValueError("Negative range")
        if self.channel == "bearing" and not -math.pi <= self.value <= math.pi:
            raise ValueError("Bearing must be wrapped to [-pi, pi]")
        if self.acquired_ms - self.timestamp_uncertainty_ms > self.available_ms:
            raise ValueError("Acquisition is definitely after availability")


@dataclass(frozen=True)
class Uncertainty:
    box: StateBox | None
    at_ms: int
    kind: str = "propagated_initial_enclosure"
    measurement_update_status: str = "unsupported_in_SA01"
    schema: str = "iaa-uncertainty/1"

    def __post_init__(self):
        millis(self.at_ms)
        if self.schema != "iaa-uncertainty/1":
            raise ValueError("Unsupported uncertainty schema")
        if self.kind not in ("propagated_initial_enclosure", "unsupported"):
            raise ValueError("Unsupported uncertainty interpretation")
        if self.box is not None and not isinstance(self.box, StateBox):
            raise ValueError("Invalid state enclosure")
        if self.kind == "unsupported" and self.box is not None:
            raise ValueError("Unsupported information must not carry a credited box")


@dataclass(frozen=True)
class Command:
    acceleration: tuple[Q, Q]
    apply_ms: int
    end_ms: int
    request_id: str
    schema: str = "iaa-command/1"
    unit: str = "m/s^2"
    frame: str = FRAME

    def __post_init__(self):
        object.__setattr__(self, "acceleration", tuple(rational(x) for x in self.acceleration))
        millis(self.apply_ms)
        millis(self.end_ms)
        if self.end_ms <= self.apply_ms or not self.request_id:
            raise ValueError("Invalid command interval or identity")
        if len(self.acceleration) != 2 or sum(x * x for x in self.acceleration) > AUTHORITY**2:
            raise ValueError("Acceleration exceeds Euclidean authority")
        if self.schema != "iaa-command/1" or self.unit != "m/s^2" or self.frame != FRAME:
            raise ValueError("Unsupported command schema, unit or frame")


@dataclass(frozen=True)
class CheckResult:
    status: Status
    request_id: str
    command_sha256: str
    information_sha256: str
    valid_until_ms: int
    reason: str
    schema: str = "iaa-check/1"
    scope: str = "HCW_finite_prefix_and_three_second_coast_only"
    recovery_claim: bool = False

    def __post_init__(self):
        millis(self.valid_until_ms)
        if self.schema != "iaa-check/1" or not isinstance(self.status, Status):
            raise ValueError("Unsupported check result")
        if self.recovery_claim is not False:
            raise ValueError("Recovery is not established by SA01")


@dataclass(frozen=True)
class ExecutionRecord:
    at_ms: int
    event: str
    details: dict
    schema: str = "iaa-execution/1"

    def __post_init__(self):
        millis(self.at_ms)
        if self.schema != "iaa-execution/1":
            raise ValueError("Unsupported execution schema")
        encode(self.details)
