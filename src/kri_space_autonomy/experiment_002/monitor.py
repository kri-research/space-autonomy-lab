from __future__ import annotations

from dataclasses import dataclass

from .config import PilotConfig
from .policy import PolicyDecision, ReferenceController, SensorObservation


@dataclass(frozen=True)
class GateDecision:
    proposed_acceleration_mps2: float
    executed_acceleration_mps2: float
    overridden: bool
    reason: str | None


class RuntimeGate:
    """Observation-only runtime gate.

    This intentionally simplified one-step estimated guard is not imported by the
    truth evaluator. It has no parameter or type through which hidden actuator
    effectiveness, process disturbance, or fault labels can enter.
    """

    def __init__(
        self,
        config: PilotConfig,
        fallback: ReferenceController,
        expected_model_identity: str,
    ):
        self.config = config
        self.fallback = fallback
        self.expected_model_identity = expected_model_identity
        self.integrity_latched = False

    def _fallback(self, observation: SensorObservation) -> float:
        return self.fallback.decide(observation).commanded_acceleration_mps2

    def gate(self, observation: SensorObservation, policy_decision: PolicyDecision) -> GateDecision:
        if policy_decision.model_identity != self.expected_model_identity:
            self.integrity_latched = True
        if self.integrity_latched:
            return GateDecision(
                policy_decision.commanded_acceleration_mps2,
                self._fallback(observation),
                True,
                "MODEL_INTEGRITY",
            )
        if (
            observation.range_m is None
            or observation.relative_velocity_mps is None
            or policy_decision.confidence < self.config.gate_confidence_threshold
        ):
            return GateDecision(
                policy_decision.commanded_acceleration_mps2,
                self._fallback(observation),
                True,
                "OBSERVATION_QUALITY",
            )
        dt = self.config.command_period_s
        proposed = policy_decision.commanded_acceleration_mps2
        estimated_velocity = observation.relative_velocity_mps + proposed * dt
        estimated_range = (
            observation.range_m + observation.relative_velocity_mps * dt + 0.5 * proposed * dt**2
        )
        closing_speed = max(0.0, -estimated_velocity)
        nominal_stopping_distance = closing_speed**2 / (2.0 * self.config.max_acceleration_mps2)
        estimated_margin = (
            estimated_range - self.config.gate_min_range_m - nominal_stopping_distance
        )
        if estimated_margin < 0.0 or observation.propellant < self.config.propellant_reserve:
            return GateDecision(
                proposed,
                self._fallback(observation),
                True,
                "ESTIMATED_ONE_STEP_GUARD",
            )
        return GateDecision(proposed, proposed, False, None)
