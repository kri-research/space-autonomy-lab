from __future__ import annotations

import hashlib

import numpy as np

from .environment import EnvironmentConfig
from .types import Action, Observation, PolicyDecision


def _clip_acceleration(value: float, cfg: EnvironmentConfig) -> float:
    return float(np.clip(value, -cfg.max_acceleration_mps2, cfg.max_acceleration_mps2))


class DeterministicSafetyController:
    """Simple trusted controller used as a deterministic fallback."""

    model_hash = "deterministic-safety-controller-v1"

    def __init__(self, config: EnvironmentConfig | None = None):
        self.config = config or EnvironmentConfig()

    def target_velocity(self, range_m: float) -> float:
        if range_m > 60.0:
            return -0.35
        if range_m > 25.0:
            return -0.22
        if range_m > 12.0:
            return -0.12
        if range_m > 8.0:
            return -0.05
        return 0.0

    def decide(self, observation: Observation) -> PolicyDecision:
        if observation.range_m is None or observation.relative_velocity_mps is None:
            return PolicyDecision(Action(0.05), 1.0, 0.05, self.model_hash)
        target = self.target_velocity(observation.range_m)
        error = target - observation.relative_velocity_mps
        acceleration = _clip_acceleration(0.35 * error, self.config)
        if observation.range_m < 5.0:
            acceleration = self.config.max_acceleration_mps2
        return PolicyDecision(Action(acceleration), 1.0, acceleration, self.model_hash)


class LearnedPolicyController:
    """Tiny learned policy used to exercise assurance mechanisms without a heavy ML stack.

    The policy is trained deterministically by least-squares imitation of the safety controller
    over a bounded training distribution. It is intentionally lightweight and replaceable by
    external policies in later versions.
    """

    def __init__(self, config: EnvironmentConfig | None = None):
        self.config = config or EnvironmentConfig()
        self.weights = self._fit_reference_policy()

    @staticmethod
    def _features(range_m: float, velocity_mps: float, propellant: float) -> np.ndarray:
        # Piecewise basis learned from demonstrations. The bins deliberately mirror distinct
        # operating regimes while the coefficients are fitted from expert data.
        bins = np.array(
            [
                range_m > 60.0,
                25.0 < range_m <= 60.0,
                12.0 < range_m <= 25.0,
                8.0 < range_m <= 12.0,
                range_m <= 8.0,
            ],
            dtype=np.float64,
        )
        v = float(np.clip(velocity_mps, -1.0, 1.0))
        return np.concatenate([bins, bins * v, np.array([propellant], dtype=np.float64)])

    def _fit_reference_policy(self) -> np.ndarray:
        expert = DeterministicSafetyController(self.config)
        rows: list[np.ndarray] = []
        targets: list[float] = []
        for range_m in np.linspace(4.0, 120.0, 60):
            for velocity in np.linspace(-0.6, 0.35, 32):
                obs = Observation(0, float(range_m), float(velocity), 1.0, 1.0)
                rows.append(self._features(float(range_m), float(velocity), 1.0))
                targets.append(expert.decide(obs).action.acceleration_mps2)
        x = np.vstack(rows)
        y = np.asarray(targets, dtype=np.float64)
        weights, *_ = np.linalg.lstsq(x, y, rcond=None)
        return weights

    @property
    def model_hash(self) -> str:
        return hashlib.sha256(self.weights.tobytes()).hexdigest()

    def corrupt_weight(self, index: int = 0, delta: float = 2.5) -> None:
        self.weights[index % len(self.weights)] += delta

    def decide(self, observation: Observation) -> PolicyDecision:
        if observation.range_m is None or observation.relative_velocity_mps is None:
            return PolicyDecision(Action(0.0), 0.0, 0.0, self.model_hash)

        features = self._features(
            observation.range_m,
            observation.relative_velocity_mps,
            observation.propellant,
        )
        raw = float(features @ self.weights)
        acceleration = _clip_acceleration(raw, self.config)

        # Confidence falls outside the training region and with degraded sensor quality.
        range_penalty = max(0.0, 4.0 - observation.range_m) / 4.0
        velocity_penalty = max(0.0, abs(observation.relative_velocity_mps) - 0.6) / 0.6
        confidence = float(
            np.clip(
                observation.sensor_quality * (1.0 - range_penalty - velocity_penalty),
                0.0,
                1.0,
            )
        )
        return PolicyDecision(Action(acceleration), confidence, raw, self.model_hash)
