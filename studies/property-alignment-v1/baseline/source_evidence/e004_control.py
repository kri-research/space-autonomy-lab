from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import solve_discrete_are

from .config import Experiment004Config
from .dynamics import discrete_matrices
from .estimator import FilterHealth, NavigationSnapshot
from .geometry import HCWSegment, evaluate_segment

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class PlanarObservation:
    receipt_time_s: float
    estimated_state: FloatArray | None
    covariance: FloatArray | None
    health: FilterHealth
    prediction_only_age_s: float | None

    def __post_init__(self) -> None:
        if not np.isfinite(self.receipt_time_s) or self.receipt_time_s < 0.0:
            raise ValueError("observation receipt time must be finite and non-negative")
        if self.estimated_state is None:
            if self.covariance is not None:
                raise ValueError("covariance cannot be present without an estimated state")
            return
        state = np.asarray(self.estimated_state, dtype=np.float64)
        covariance = np.asarray(self.covariance, dtype=np.float64)
        if state.shape != (4,) or not np.all(np.isfinite(state)):
            raise ValueError("estimated state must be a finite four-vector")
        if covariance.shape != (4, 4) or not np.all(np.isfinite(covariance)):
            raise ValueError("estimated covariance must be a finite 4 by 4 matrix")
        object.__setattr__(self, "estimated_state", np.array(state, copy=True))
        object.__setattr__(self, "covariance", np.array(covariance, copy=True))


@dataclass(frozen=True)
class PlanarControllerDecision:
    acceleration_mps2: FloatArray
    controller_identity: str

    def __post_init__(self) -> None:
        command = np.asarray(self.acceleration_mps2, dtype=np.float64)
        if command.shape != (2,) or not np.all(np.isfinite(command)):
            raise ValueError("controller command must be a finite two-vector")
        if not self.controller_identity:
            raise ValueError("controller identity must be non-empty")
        object.__setattr__(self, "acceleration_mps2", np.array(command, copy=True))


@dataclass(frozen=True)
class GateDecision:
    proposed_acceleration_mps2: FloatArray
    executed_acceleration_mps2: FloatArray
    overridden: bool
    reason: str | None
    conservative_keep_out_radius_m: float | None


def observation_from_snapshot(snapshot: NavigationSnapshot) -> PlanarObservation:
    if snapshot.health is FilterHealth.DIVERGED:
        return PlanarObservation(
            snapshot.time_s,
            None,
            None,
            snapshot.health,
            snapshot.prediction_only_age_s,
        )
    return PlanarObservation(
        snapshot.time_s,
        snapshot.mean,
        snapshot.covariance,
        snapshot.health,
        snapshot.prediction_only_age_s,
    )


def _identity(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "experiment-004-reference:" + hashlib.sha256(canonical).hexdigest()


class DeterministicHoldController:
    """Deterministic planar LQR reference used only for foundation and pilot sanity."""

    def __init__(self, config: Experiment004Config) -> None:
        self.config = config
        transition, command = discrete_matrices(
            config.mean_motion_rad_s,
            config.command_period_s,
        )
        state_cost = np.diag(np.asarray(config.lqr_state_cost_diagonal, dtype=np.float64))
        control_cost = np.diag(
            np.asarray(config.lqr_control_cost_diagonal, dtype=np.float64)
        )
        riccati = solve_discrete_are(transition, command, state_cost, control_cost)
        self.gain = np.linalg.solve(
            command.T @ riccati @ command + control_cost,
            command.T @ riccati @ transition,
        )
        self.target_state = np.array(
            [config.hold_center_m[0], config.hold_center_m[1], 0.0, 0.0],
            dtype=np.float64,
        )
        self.controller_identity = _identity(
            {
                "schema": config.schema_version,
                "kind": "deterministic-discrete-lqr-hold-reference",
                "mean_motion_rad_s": config.mean_motion_rad_s,
                "command_period_s": config.command_period_s,
                "max_acceleration_mps2": config.max_acceleration_mps2,
                "state_cost": list(config.lqr_state_cost_diagonal),
                "control_cost": list(config.lqr_control_cost_diagonal),
                "target_state": self.target_state.tolist(),
            }
        )

    def decide(self, observation: PlanarObservation) -> PlanarControllerDecision:
        if observation.estimated_state is None:
            command = np.zeros(2, dtype=np.float64)
        else:
            command = -self.gain @ (observation.estimated_state - self.target_state)
            norm = float(np.linalg.norm(command))
            if norm > self.config.max_acceleration_mps2:
                command = command * (self.config.max_acceleration_mps2 / norm)
        return PlanarControllerDecision(command, self.controller_identity)


class EstimatedGeometryMonitor:
    """A bounded one-step estimated-geometry screen, not a reachability proof."""

    def __init__(
        self,
        config: Experiment004Config,
        fallback: DeterministicHoldController,
        expected_controller_identity: str,
    ) -> None:
        self.config = config
        self.fallback = fallback
        self.expected_controller_identity = expected_controller_identity
        self.integrity_latched = False

    def _fallback(self, snapshot: NavigationSnapshot) -> FloatArray:
        return self.fallback.decide(observation_from_snapshot(snapshot)).acceleration_mps2

    def gate(
        self,
        snapshot: NavigationSnapshot,
        decision: PlanarControllerDecision,
    ) -> GateDecision:
        proposed = np.asarray(decision.acceleration_mps2, dtype=np.float64)
        if decision.controller_identity != self.expected_controller_identity:
            self.integrity_latched = True
        if self.integrity_latched:
            return GateDecision(
                proposed,
                self._fallback(snapshot),
                True,
                "CONTROLLER_INTEGRITY",
                None,
            )
        if snapshot.health is FilterHealth.DIVERGED:
            return GateDecision(
                proposed,
                self._fallback(snapshot),
                True,
                "ESTIMATOR_DIVERGED",
                None,
            )
        if (
            snapshot.health is FilterHealth.DEGRADED
            or snapshot.prediction_only_age_s is None
            or snapshot.prediction_only_age_s
            > self.config.degraded_after_prediction_only_s
            or snapshot.consecutive_innovation_rejections
            >= self.config.max_consecutive_innovation_rejections
        ):
            return GateDecision(
                proposed,
                self._fallback(snapshot),
                True,
                "ESTIMATOR_QUALITY",
                None,
            )
        command_norm = float(np.linalg.norm(proposed))
        if command_norm > self.config.max_acceleration_mps2 + 1e-12:
            return GateDecision(
                proposed,
                self._fallback(snapshot),
                True,
                "COMMAND_BOUND",
                None,
            )
        position_covariance = snapshot.covariance[:2, :2]
        position_sigma = float(
            np.sqrt(max(0.0, float(np.linalg.eigvalsh(position_covariance)[-1])))
        )
        conservative_radius = (
            self.config.keep_out_radius_m
            + self.config.uncertainty_sigma_multiplier * position_sigma
        )
        segment = HCWSegment(
            snapshot.mean,
            proposed,
            self.config.mean_motion_rad_s,
            self.config.command_period_s,
            maximum_duration_s=self.config.event_interval_max_s,
        )
        geometry = evaluate_segment(segment, self.config)
        if (
            geometry.minimum_separation_m <= conservative_radius
            or geometry.corridor_departure
        ):
            return GateDecision(
                proposed,
                self._fallback(snapshot),
                True,
                "UNCERTAINTY_AWARE_GEOMETRY",
                conservative_radius,
            )
        return GateDecision(
            proposed,
            proposed,
            False,
            None,
            conservative_radius,
        )
