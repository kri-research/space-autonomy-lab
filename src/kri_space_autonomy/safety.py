from __future__ import annotations

from dataclasses import dataclass

from .controllers import DeterministicSafetyController
from .environment import EnvironmentConfig, ProximityEnvironment
from .types import Action, GateDecision, Observation, PolicyDecision, SpacecraftState


@dataclass(frozen=True)
class SafetyEnvelope:
    min_range_m: float = 2.0
    propellant_reserve: float = 0.10

    @staticmethod
    def minimum_allowed_velocity(range_m: float) -> float:
        """Most-negative permitted closing speed at a given range."""
        if range_m > 60.0:
            return -0.65
        if range_m > 25.0:
            return -0.40
        if range_m > 12.0:
            return -0.22
        if range_m > 8.0:
            return -0.12
        if range_m > 5.0:
            return -0.07
        return -0.02

    def constraints(self, state: SpacecraftState) -> tuple[str, ...]:
        return (
            f"range_m>{self.min_range_m}",
            f"relative_velocity_mps>={self.minimum_allowed_velocity(state.range_m):.3f}",
            f"propellant>={self.propellant_reserve:.2f}",
        )

    def contains(self, state: SpacecraftState) -> bool:
        return (
            state.range_m > self.min_range_m
            and state.relative_velocity_mps >= self.minimum_allowed_velocity(state.range_m)
            and state.propellant >= self.propellant_reserve
        )


class RuntimeAssuranceMonitor:
    """Independent runtime monitor and decision gate inspired by KRI-STD-001 §§4.1 and 5.1."""

    def __init__(
        self,
        environment: ProximityEnvironment,
        fallback: DeterministicSafetyController,
        envelope: SafetyEnvelope | None = None,
        confidence_threshold: float = 0.60,
        expected_model_hash: str | None = None,
    ):
        self.environment = environment
        self.fallback = fallback
        self.envelope = envelope or SafetyEnvelope(
            propellant_reserve=environment.config.propellant_reserve
        )
        self.confidence_threshold = confidence_threshold
        self.expected_model_hash = expected_model_hash

    def _fallback_action(
        self, current_state: SpacecraftState, observation: Observation
    ) -> Action:
        preferred = self.fallback.decide(observation).action
        candidates = (
            preferred,
            Action(self.environment.config.max_acceleration_mps2),
            Action(self.environment.config.max_acceleration_mps2 / 2.0),
            Action(0.0),
        )
        for candidate in candidates:
            if self.envelope.contains(self.environment.step(current_state, candidate)):
                return candidate
        # If no one-step action can recover the state, command maximum separation.
        return Action(self.environment.config.max_acceleration_mps2)

    def gate(
        self,
        current_state: SpacecraftState,
        monitor_observation: Observation,
        policy_decision: PolicyDecision,
    ) -> GateDecision:
        constraints = self.envelope.constraints(current_state)

        if (
            self.expected_model_hash is not None
            and policy_decision.model_hash != self.expected_model_hash
        ):
            return GateDecision(
                proposed=policy_decision.action,
                executed=self._fallback_action(current_state, monitor_observation),
                overridden=True,
                reason="MODEL_INTEGRITY",
                active_constraints=constraints,
            )

        if policy_decision.confidence < self.confidence_threshold:
            return GateDecision(
                proposed=policy_decision.action,
                executed=self._fallback_action(current_state, monitor_observation),
                overridden=True,
                reason="LOW_CONFIDENCE",
                active_constraints=constraints,
            )

        proposed_next = self.environment.step(current_state, policy_decision.action)
        if not self.envelope.contains(proposed_next):
            return GateDecision(
                proposed=policy_decision.action,
                executed=self._fallback_action(current_state, monitor_observation),
                overridden=True,
                reason="SAFE_FLIGHT_ENVELOPE",
                active_constraints=constraints,
            )

        return GateDecision(
            proposed=policy_decision.action,
            executed=policy_decision.action,
            overridden=False,
            reason=None,
            active_constraints=constraints,
        )
