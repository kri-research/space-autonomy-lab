from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SpacecraftState:
    """Minimal relative-motion state for a one-dimensional proximity operation."""

    step: int
    range_m: float
    relative_velocity_mps: float
    propellant: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Observation:
    """Observation presented to a controller or independent runtime monitor."""

    step: int
    range_m: float | None
    relative_velocity_mps: float | None
    propellant: float
    sensor_quality: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Action:
    """Commanded relative acceleration. Positive acceleration increases separation."""

    acceleration_mps2: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDecision:
    action: Action
    confidence: float
    raw_output: float
    model_hash: str


@dataclass(frozen=True)
class GateDecision:
    proposed: Action
    executed: Action
    overridden: bool
    reason: str | None
    active_constraints: tuple[str, ...]
