from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from kri_space_autonomy.experiment_002.config import PilotConfig
from kri_space_autonomy.experiment_002.policy import (
    PolicyDecision,
    ReferenceController,
    SensorObservation,
)

from .config import Experiment003Config
from .estimator import FilterHealth, NavigationSnapshot


@dataclass(frozen=True)
class EstimatedGateDecision:
    proposed_acceleration_mps2: float
    executed_acceleration_mps2: float
    overridden: bool
    reason: str | None
    conservative_range_m: float | None
    conservative_closing_velocity_mps: float | None


def policy_observation(
    estimate: NavigationSnapshot,
    propellant_telemetry: float,
    receipt_time_s: float,
) -> SensorObservation:
    """Map a navigation estimate to the frozen policy's observation contract."""

    if not np.isfinite(propellant_telemetry) or not 0.0 <= propellant_telemetry <= 1.0:
        raise ValueError("propellant telemetry must be a finite fraction in [0, 1]")
    if abs(receipt_time_s - estimate.time_s) > 1e-12:
        raise ValueError("policy receipt time must match the estimate epoch")
    if estimate.health is FilterHealth.DIVERGED:
        return SensorObservation(receipt_time_s, None, None, propellant_telemetry, 0.0)
    if estimate.health is FilterHealth.VALID:
        quality = 1.0
    elif estimate.prediction_only_age_s is not None and estimate.prediction_only_age_s <= 2.0:
        quality = 0.7
    else:
        quality = 0.4
    return SensorObservation(
        receipt_time_s,
        estimate.range_m,
        estimate.relative_velocity_mps,
        propellant_telemetry,
        quality,
    )


class EstimatedRuntimeGate:
    """Uncertainty-aware runtime gate with estimator-only navigation inputs."""

    def __init__(
        self,
        study: Experiment003Config,
        production: PilotConfig,
        fallback: ReferenceController,
        expected_model_identity: str,
    ) -> None:
        self.study = study
        self.production = production
        self.fallback = fallback
        self.expected_model_identity = expected_model_identity
        self.integrity_latched = False

    def _fallback(self, observation: SensorObservation) -> float:
        return self.fallback.decide(observation).commanded_acceleration_mps2

    def gate(
        self,
        estimate: NavigationSnapshot,
        propellant_telemetry: float,
        policy_decision: PolicyDecision,
    ) -> EstimatedGateDecision:
        observation = policy_observation(estimate, propellant_telemetry, estimate.time_s)
        proposed = policy_decision.commanded_acceleration_mps2
        if policy_decision.model_identity != self.expected_model_identity:
            self.integrity_latched = True
        if self.integrity_latched:
            return EstimatedGateDecision(
                proposed,
                self._fallback(observation),
                True,
                "MODEL_INTEGRITY",
                None,
                None,
            )
        if estimate.health is FilterHealth.DIVERGED:
            return EstimatedGateDecision(
                proposed,
                self._fallback(observation),
                True,
                "ESTIMATOR_DIVERGED",
                None,
                None,
            )
        if (
            estimate.health is FilterHealth.DEGRADED
            or estimate.consecutive_innovation_rejections
            >= self.study.max_consecutive_innovation_rejections
            or estimate.prediction_only_age_s is None
            or estimate.prediction_only_age_s
            > self.study.degraded_after_prediction_only_s
        ):
            return EstimatedGateDecision(
                proposed,
                self._fallback(observation),
                True,
                "ESTIMATOR_QUALITY",
                None,
                None,
            )
        sigma = self.study.uncertainty_sigma_multiplier
        range_sd = float(np.sqrt(max(0.0, estimate.covariance[0, 0])))
        velocity_sd = float(np.sqrt(max(0.0, estimate.covariance[1, 1])))
        conservative_range = estimate.range_m - sigma * range_sd
        conservative_velocity = estimate.relative_velocity_mps - sigma * velocity_sd
        dt = self.production.command_period_s
        predicted_range = (
            conservative_range
            + conservative_velocity * dt
            + 0.5 * proposed * dt**2
        )
        predicted_velocity = conservative_velocity + proposed * dt
        closing_speed = max(0.0, -predicted_velocity)
        stopping_distance = closing_speed**2 / (
            2.0 * self.production.max_acceleration_mps2
        )
        margin = predicted_range - self.production.gate_min_range_m - stopping_distance
        if margin < 0.0 or propellant_telemetry < self.production.propellant_reserve:
            return EstimatedGateDecision(
                proposed,
                self._fallback(observation),
                True,
                "UNCERTAINTY_AWARE_GUARD",
                conservative_range,
                conservative_velocity,
            )
        return EstimatedGateDecision(
            proposed,
            proposed,
            False,
            None,
            conservative_range,
            conservative_velocity,
        )
