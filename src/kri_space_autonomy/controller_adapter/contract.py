from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from typing import Protocol

CONTRACT_VERSION = "1.0"
ACCELERATION_UNIT = "m/s^2"
POSITIVE_ACCELERATION = "increases separation"
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _finite_real(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


class ObservationStatus(StrEnum):
    NOMINAL = "nominal"
    DEGRADED = "degraded"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class ControllerMetadata:
    """Stable, user-declared identity for one deterministic controller implementation."""

    controller_id: str
    controller_version: str
    contract_version: str = CONTRACT_VERSION
    deterministic: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.controller_id, str) or not _IDENTIFIER.fullmatch(
            self.controller_id
        ):
            raise ValueError(
                "controller_id must match [a-z0-9][a-z0-9._-]{0,63}"
            )
        if (
            not isinstance(self.controller_version, str)
            or not self.controller_version.strip()
            or len(self.controller_version) > 64
        ):
            raise ValueError("controller_version must be a non-empty string of at most 64 chars")
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError(f"contract_version must be {CONTRACT_VERSION!r}")
        if self.deterministic is not True:
            raise ValueError("external benchmark controllers must declare deterministic=True")


@dataclass(frozen=True, slots=True)
class ControllerContext:
    """Episode constants delivered once through ``reset`` before any observation."""

    command_period_s: float
    minimum_acceleration_mps2: float
    maximum_acceleration_mps2: float
    acceleration_unit: str = ACCELERATION_UNIT
    positive_acceleration: str = POSITIVE_ACCELERATION

    def __post_init__(self) -> None:
        period = _finite_real("command_period_s", self.command_period_s)
        minimum = _finite_real(
            "minimum_acceleration_mps2", self.minimum_acceleration_mps2
        )
        maximum = _finite_real(
            "maximum_acceleration_mps2", self.maximum_acceleration_mps2
        )
        if period <= 0.0:
            raise ValueError("command_period_s must be positive")
        if minimum >= maximum:
            raise ValueError("minimum acceleration must be below maximum acceleration")
        if self.acceleration_unit != ACCELERATION_UNIT:
            raise ValueError(f"acceleration_unit must be {ACCELERATION_UNIT!r}")
        if self.positive_acceleration != POSITIVE_ACCELERATION:
            raise ValueError(
                f"positive_acceleration must be {POSITIVE_ACCELERATION!r}"
            )


@dataclass(frozen=True, slots=True)
class ControllerObservation:
    """Controller-observable navigation and resource telemetry; no simulator truth state."""

    step: int
    time_s: float
    range_m: float | None
    relative_velocity_mps: float | None
    propellant_fraction: float
    sensor_quality: float

    def __post_init__(self) -> None:
        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step < 0:
            raise ValueError("step must be a non-negative integer")
        time_s = _finite_real("time_s", self.time_s)
        if time_s < 0.0:
            raise ValueError("time_s must be non-negative")
        if self.range_m is not None:
            _finite_real("range_m", self.range_m)
        if self.relative_velocity_mps is not None:
            _finite_real("relative_velocity_mps", self.relative_velocity_mps)
        propellant = _finite_real("propellant_fraction", self.propellant_fraction)
        quality = _finite_real("sensor_quality", self.sensor_quality)
        if not 0.0 <= propellant <= 1.0:
            raise ValueError("propellant_fraction must be in [0, 1]")
        if not 0.0 <= quality <= 1.0:
            raise ValueError("sensor_quality must be in [0, 1]")

    @property
    def status(self) -> ObservationStatus:
        if self.range_m is None or self.relative_velocity_mps is None:
            return ObservationStatus.MISSING
        if self.sensor_quality < 1.0:
            return ObservationStatus.DEGRADED
        return ObservationStatus.NOMINAL

    @property
    def missing_fields(self) -> tuple[str, ...]:
        fields: list[str] = []
        if self.range_m is None:
            fields.append("range_m")
        if self.relative_velocity_mps is None:
            fields.append("relative_velocity_mps")
        return tuple(fields)


@dataclass(frozen=True, slots=True)
class ControllerCommand:
    """Requested relative acceleration; positive increases separation."""

    acceleration_mps2: float
    acceleration_unit: str = ACCELERATION_UNIT


class Controller(Protocol):
    """Small lifecycle implemented by an external deterministic controller."""

    metadata: ControllerMetadata

    def reset(self, context: ControllerContext) -> None: ...

    def command(self, observation: ControllerObservation) -> ControllerCommand: ...
