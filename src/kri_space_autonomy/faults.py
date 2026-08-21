from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .controllers import LearnedPolicyController
from .types import Action, Observation


class Fault(Protocol):
    name: str

    def apply_observation(self, observation: Observation) -> Observation: ...

    def apply_action(self, step: int, action: Action) -> Action: ...

    def apply_model(self, step: int, controller: LearnedPolicyController) -> str | None: ...


@dataclass
class NoFault:
    name: str = "none"

    def apply_observation(self, observation: Observation) -> Observation:
        return observation

    def apply_action(self, step: int, action: Action) -> Action:
        return action

    def apply_model(self, step: int, controller: LearnedPolicyController) -> str | None:
        return None


@dataclass
class SensorBiasFault(NoFault):
    start_step: int = 80
    end_step: int = 180
    range_bias_m: float = 25.0
    name: str = "sensor_bias"

    def apply_observation(self, observation: Observation) -> Observation:
        if self.start_step <= observation.step <= self.end_step and observation.range_m is not None:
            return Observation(
                step=observation.step,
                range_m=observation.range_m + self.range_bias_m,
                relative_velocity_mps=observation.relative_velocity_mps,
                propellant=observation.propellant,
                sensor_quality=0.85,
            )
        return observation


@dataclass
class SensorDropoutFault(NoFault):
    start_step: int = 90
    end_step: int = 105
    name: str = "sensor_dropout"

    def apply_observation(self, observation: Observation) -> Observation:
        if self.start_step <= observation.step <= self.end_step:
            return Observation(
                step=observation.step,
                range_m=None,
                relative_velocity_mps=None,
                propellant=observation.propellant,
                sensor_quality=0.0,
            )
        return observation


@dataclass
class SingleEventUpsetFault(NoFault):
    step: int = 90
    weight_index: int = 1
    delta: float = -7.0
    name: str = "model_seu"
    _applied: bool = False

    def apply_model(self, step: int, controller: LearnedPolicyController) -> str | None:
        if step == self.step and not self._applied:
            before = controller.model_hash
            controller.corrupt_weight(self.weight_index, self.delta)
            self._applied = True
            return f"MODEL_HASH_CHANGED:{before[:12]}->{controller.model_hash[:12]}"
        return None


@dataclass
class ActuatorDegradationFault(NoFault):
    start_step: int = 80
    end_step: int = 150
    effectiveness: float = 0.35
    name: str = "actuator_degradation"

    def apply_action(self, step: int, action: Action) -> Action:
        if self.start_step <= step <= self.end_step:
            return Action(action.acceleration_mps2 * self.effectiveness)
        return action


def fault_from_config(data: dict) -> Fault:
    kind = data.get("type", "none")
    params = {key: value for key, value in data.items() if key != "type"}
    classes = {
        "none": NoFault,
        "sensor_bias": SensorBiasFault,
        "sensor_dropout": SensorDropoutFault,
        "model_seu": SingleEventUpsetFault,
        "actuator_degradation": ActuatorDegradationFault,
    }
    if kind not in classes:
        raise ValueError(f"Unknown fault type: {kind}")
    return classes[kind](**params)
