from __future__ import annotations

import math
from dataclasses import replace
from numbers import Real

from kri_space_autonomy.types import Action, Observation

from .errors import FaultApplicationError, FaultSpecError
from .manifest import (
    ActuatorEffectivenessFault,
    FaultCase,
    NavigationDropoutFault,
    ObservedRangeBiasFault,
)


class DeterministicFaultPipeline:
    """Apply one case's faults in manifest-array order at inclusive step windows."""

    def __init__(self, case: FaultCase):
        if type(case) is not FaultCase:
            raise FaultSpecError("fault pipeline case must be a FaultCase")
        self._case = case

    @property
    def case(self) -> FaultCase:
        return self._case

    @property
    def fault_ids(self) -> tuple[str, ...]:
        return tuple(fault.fault_id for fault in self._case.faults)

    def active_fault_ids(self, step: int) -> tuple[str, ...]:
        self._validate_step(step)
        return tuple(
            fault.fault_id
            for fault in self._case.faults
            if fault.activation.active(step)
        )

    def apply_observation(self, observation: Observation) -> Observation:
        """Transform observed telemetry only; no state object crosses this boundary."""

        if type(observation) is not Observation:
            raise FaultApplicationError("observation input must be an Observation")
        self._validate_observation(observation)
        current = observation
        for fault in self._case.faults:
            if not fault.activation.active(observation.step):
                continue
            if isinstance(fault, ObservedRangeBiasFault):
                if current.range_m is None:
                    continue
                range_m = current.range_m + fault.bias_m
                if not math.isfinite(range_m):
                    raise FaultApplicationError("observed range bias produced a non-finite value")
                current = replace(
                    current,
                    range_m=range_m,
                    sensor_quality=min(current.sensor_quality, fault.sensor_quality),
                )
            elif isinstance(fault, NavigationDropoutFault):
                current = replace(
                    current,
                    range_m=None,
                    relative_velocity_mps=None,
                    sensor_quality=0.0,
                )
        return current

    def apply_action(self, step: int, action: Action) -> Action:
        """Transform requested actuation after the controller returns its public command."""

        self._validate_step(step)
        if type(action) is not Action:
            raise FaultApplicationError("action input must be an Action")
        acceleration = action.acceleration_mps2
        if (
            isinstance(acceleration, bool)
            or not isinstance(acceleration, Real)
            or not math.isfinite(acceleration)
        ):
            raise FaultApplicationError("action acceleration_mps2 must be a finite real scalar")
        executed = float(acceleration)
        for fault in self._case.faults:
            if isinstance(fault, ActuatorEffectivenessFault) and fault.activation.active(step):
                executed *= fault.effectiveness
                if not math.isfinite(executed):
                    raise FaultApplicationError(
                        "actuator effectiveness produced a non-finite value"
                    )
        return Action(executed)

    @staticmethod
    def _validate_observation(observation: Observation) -> None:
        DeterministicFaultPipeline._validate_step(observation.step)
        for name, value in (
            ("range_m", observation.range_m),
            ("relative_velocity_mps", observation.relative_velocity_mps),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
            ):
                raise FaultApplicationError(
                    f"observation {name} must be None or a finite real scalar"
                )
        for name, value in (
            ("propellant", observation.propellant),
            ("sensor_quality", observation.sensor_quality),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
                or not 0.0 <= value <= 1.0
            ):
                raise FaultApplicationError(f"observation {name} must be in [0, 1]")

    @staticmethod
    def _validate_step(step: object) -> None:
        if type(step) is not int or step < 0:
            raise FaultApplicationError("fault application step must be a non-negative integer")
