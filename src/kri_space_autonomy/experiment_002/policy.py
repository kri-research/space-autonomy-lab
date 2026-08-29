from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import PilotConfig
from .seeds import partition_rng, sha256_bytes

FEATURE_SCHEMA = (
    "bias",
    "range_error_over_50_clipped",
    "velocity_over_0p4_clipped",
    "range_velocity_interaction",
    "propellant_centered",
    "sensor_quality_centered",
    "range_missing",
    "velocity_missing",
    "both_missing",
)
FEATURE_VERSION = "exp002-observation-features-v1"
POLICY_ARCHITECTURE = "float64 bounded smooth linear tanh; 9 parameters"
TRAINING_OBJECTIVE = (
    "nominal observation-only fixed-horizon rollout loss: 50*collision + "
    "20*(1-final60_goal_dwell) + mean(abs(range-6.5)/100 clipped at 2) + "
    "0.2*mean(abs(velocity)) + 2*propellant_used"
)
OPTIMIZER = {
    "name": "deterministic cross-entropy method",
    "population": 24,
    "elite": 6,
    "generations": 8,
    "initial_sigma": 0.35,
    "sigma_floor": 0.02,
    "primary_optimizer_seed": 200212,
    "early_stop_patience": 3,
}
MODEL_SELECTION_RULE = (
    "retain each generation mean; stop by train-stop loss patience=3; among retained "
    "candidates select on validation lexicographically by fewer collisions, more sustained "
    "successes, lower objective, then lower L2 norm; never refit on validation"
)


@dataclass(frozen=True)
class SensorObservation:
    time_s: float
    range_m: float | None
    relative_velocity_mps: float | None
    propellant: float
    sensor_quality: float


@dataclass(frozen=True)
class PolicyDecision:
    commanded_acceleration_mps2: float
    confidence: float
    raw_output: float
    model_identity: str


class FrozenPolicy:
    def __init__(self, weights: np.ndarray, config: PilotConfig):
        array = np.asarray(weights, dtype=np.float64)
        if array.shape != (len(FEATURE_SCHEMA),):
            raise ValueError(f"policy weights must have shape {(len(FEATURE_SCHEMA),)}")
        self.weights = np.array(array, copy=True)
        self.config = config

    @staticmethod
    def features(observation: SensorObservation) -> np.ndarray:
        range_missing = observation.range_m is None
        velocity_missing = observation.relative_velocity_mps is None
        range_m = 6.5 if range_missing else float(observation.range_m)
        velocity = 0.0 if velocity_missing else float(observation.relative_velocity_mps)
        range_scaled = float(np.clip((range_m - 6.5) / 50.0, -1.0, 2.5))
        velocity_scaled = float(np.clip(velocity / 0.4, -2.0, 2.0))
        return np.array(
            [
                1.0,
                range_scaled,
                velocity_scaled,
                range_scaled * velocity_scaled,
                float(np.clip(observation.propellant - 0.5, -0.5, 0.5)),
                float(np.clip(observation.sensor_quality - 1.0, -1.0, 0.0)),
                float(range_missing),
                float(velocity_missing),
                float(range_missing and velocity_missing),
            ],
            dtype=np.float64,
        )

    @property
    def model_identity(self) -> str:
        payload = self.weights.astype("<f8", copy=False).tobytes() + FEATURE_VERSION.encode()
        return sha256_bytes(payload)

    @property
    def upset_scales(self) -> np.ndarray:
        return np.maximum(np.abs(self.weights), 0.25)

    def decide(self, observation: SensorObservation) -> PolicyDecision:
        raw = float(self.features(observation) @ self.weights)
        command = float(self.config.max_acceleration_mps2 * np.tanh(raw))
        if observation.range_m is None or observation.relative_velocity_mps is None:
            confidence = 0.0
        else:
            in_range = 0.0 <= observation.range_m <= 130.0
            in_velocity = abs(observation.relative_velocity_mps) <= 0.8
            confidence = float(observation.sensor_quality if in_range and in_velocity else 0.4)
        return PolicyDecision(command, confidence, raw, self.model_identity)

    def corrupted_copy(self, index: int, normalized_magnitude: float) -> FrozenPolicy:
        weights = self.weights.copy()
        weights[index] += normalized_magnitude * self.upset_scales[index]
        return FrozenPolicy(weights, self.config)

    @classmethod
    def load(
        cls, artifact_path: str | Path, manifest_path: str | Path, config: PilotConfig
    ) -> FrozenPolicy:
        artifact = Path(artifact_path)
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        actual_hash = sha256_bytes(artifact.read_bytes())
        if actual_hash != manifest["artifact_sha256"]:
            raise ValueError("policy artifact hash does not match manifest")
        with np.load(artifact, allow_pickle=False) as payload:
            weights = np.asarray(payload["weights"], dtype=np.float64)
        policy = cls(weights, config)
        if policy.model_identity != manifest["model_identity"]:
            raise ValueError("policy model identity does not match manifest")
        if tuple(manifest["feature_schema"]) != FEATURE_SCHEMA:
            raise ValueError("policy feature schema does not match implementation")
        return policy


class ReferenceController:
    """Observation-only deterministic reference and fallback controller."""

    model_identity = "experiment-002-reference-controller-v1"

    def __init__(self, config: PilotConfig):
        self.config = config

    def decide(self, observation: SensorObservation) -> PolicyDecision:
        if observation.range_m is None or observation.relative_velocity_mps is None:
            command = self.config.max_acceleration_mps2
        else:
            error_m = max(0.0, observation.range_m - 6.5)
            target_velocity = -min(0.35, 0.04 * error_m)
            command = float(
                np.clip(
                    1.0 * (target_velocity - observation.relative_velocity_mps),
                    -self.config.max_acceleration_mps2,
                    self.config.max_acceleration_mps2,
                )
            )
            if observation.range_m < 5.0:
                command = self.config.max_acceleration_mps2
        return PolicyDecision(command, 1.0, command, self.model_identity)


@dataclass(frozen=True)
class TrainingData:
    initial_range_m: np.ndarray
    initial_velocity_mps: np.ndarray
    initial_propellant: np.ndarray
    process: np.ndarray
    range_noise: np.ndarray
    velocity_noise: np.ndarray


def _truncated_velocity(rng: np.random.Generator) -> float:
    while True:
        value = float(rng.normal(-0.15, 0.05))
        if -0.30 <= value <= 0.0:
            return value


def _training_data(config: PilotConfig, partition: str, size: int) -> TrainingData:
    n_steps = config.n_command_steps
    initial_range = np.empty(size, dtype=np.float64)
    initial_velocity = np.empty(size, dtype=np.float64)
    initial_propellant = np.empty(size, dtype=np.float64)
    process = np.empty((size, n_steps), dtype=np.float64)
    range_noise = np.empty((size, n_steps), dtype=np.float64)
    velocity_noise = np.empty((size, n_steps), dtype=np.float64)
    for index in range(size):
        init_rng = partition_rng(config, partition, index, "initial_state")
        initial_range[index] = init_rng.uniform(80.0, 120.0)
        initial_velocity[index] = _truncated_velocity(init_rng)
        initial_propellant[index] = init_rng.uniform(0.85, 1.0)
        process_rng = partition_rng(config, partition, index, "process_disturbance")
        process[index] = np.clip(
            process_rng.normal(0.0, config.process_accel_sigma_mps2, n_steps),
            -config.process_accel_clip_mps2,
            config.process_accel_clip_mps2,
        )
        sensor_rng = partition_rng(config, partition, index, "primary_sensor")
        range_noise[index] = sensor_rng.normal(0.0, config.range_noise_sigma_m, n_steps)
        velocity_noise[index] = sensor_rng.normal(0.0, config.velocity_noise_sigma_mps, n_steps)
    return TrainingData(
        initial_range,
        initial_velocity,
        initial_propellant,
        process,
        range_noise,
        velocity_noise,
    )


def _feature_matrix(
    range_m: np.ndarray,
    velocity_mps: np.ndarray,
    propellant: np.ndarray,
) -> np.ndarray:
    range_scaled = np.clip((range_m - 6.5) / 50.0, -1.0, 2.5)
    velocity_scaled = np.clip(velocity_mps / 0.4, -2.0, 2.0)
    return np.column_stack(
        [
            np.ones_like(range_m),
            range_scaled,
            velocity_scaled,
            range_scaled * velocity_scaled,
            np.clip(propellant - 0.5, -0.5, 0.5),
            np.zeros_like(range_m),
            np.zeros_like(range_m),
            np.zeros_like(range_m),
            np.zeros_like(range_m),
        ]
    )


def evaluate_training_objective(
    weights: np.ndarray, data: TrainingData, config: PilotConfig
) -> dict[str, float | int]:
    range_m = data.initial_range_m.copy()
    velocity = data.initial_velocity_mps.copy()
    propellant = data.initial_propellant.copy()
    acceleration = np.zeros_like(range_m)
    collided = np.zeros(range_m.shape, dtype=bool)
    dwell = np.zeros(range_m.shape, dtype=np.float64)
    range_loss = np.zeros(range_m.shape, dtype=np.float64)
    speed_loss = np.zeros(range_m.shape, dtype=np.float64)
    dt = config.command_period_s
    tau = config.actuator_time_constant_s
    decay = float(np.exp(-dt / tau))
    for step in range(config.n_command_steps):
        observed_range = range_m + data.range_noise[:, step]
        observed_velocity = velocity + data.velocity_noise[:, step]
        features = _feature_matrix(observed_range, observed_velocity, propellant)
        command = config.max_acceleration_mps2 * np.tanh(features @ weights)
        command = np.where(propellant > 0.0, command, 0.0)
        previous_acceleration = acceleration
        acceleration = command + (previous_acceleration - command) * decay
        impulse = command * dt + (previous_acceleration - command) * tau * (1.0 - decay)
        displacement = (
            velocity * dt
            + 0.5 * (command + data.process[:, step]) * dt**2
            + (previous_acceleration - command) * tau * (dt - tau * (1.0 - decay))
        )
        range_m = range_m + displacement
        velocity = velocity + impulse + data.process[:, step] * dt
        propellant = np.maximum(
            0.0,
            propellant - config.propellant_cost_per_delta_v * np.abs(impulse),
        )
        collided |= range_m <= config.collision_range_m
        range_loss += np.minimum(np.abs(range_m - 6.5) / 100.0, 2.0)
        speed_loss += np.minimum(np.abs(velocity), 2.0)
        if step >= config.n_command_steps - round(config.goal_dwell_s / dt):
            dwell += (
                (range_m >= config.goal_min_range_m)
                & (range_m <= config.goal_max_range_m)
                & (np.abs(velocity) <= config.goal_max_speed_mps)
                & ~collided
            )
    dwell_fraction = dwell / round(config.goal_dwell_s / dt)
    propellant_used = data.initial_propellant - propellant
    per_episode = (
        50.0 * collided
        + 20.0 * (1.0 - dwell_fraction)
        + range_loss / config.n_command_steps
        + 0.2 * speed_loss / config.n_command_steps
        + 2.0 * propellant_used
    )
    return {
        "objective": float(np.mean(per_episode)),
        "collisions": int(np.sum(collided)),
        "sustained_successes": int(np.sum(dwell_fraction == 1.0)),
        "mean_goal_dwell_fraction": float(np.mean(dwell_fraction)),
        "mean_propellant_used": float(np.mean(propellant_used)),
    }


def train_and_freeze_policy(
    config: PilotConfig,
    artifact_path: str | Path,
    manifest_path: str | Path,
    source_identity: dict[str, Any],
) -> dict[str, Any]:
    train_fit = _training_data(config, "train_fit", 2000)
    train_stop = _training_data(config, "train_stop", 500)
    validation = _training_data(config, "validation", 500)
    optimizer_rng = np.random.Generator(
        np.random.PCG64DXSM(np.random.SeedSequence([OPTIMIZER["primary_optimizer_seed"]]))
    )
    mean = np.array([0.0, -1.0, -2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    sigma = np.full(mean.shape, OPTIMIZER["initial_sigma"], dtype=np.float64)
    retained: list[tuple[np.ndarray, dict[str, float | int], int]] = []
    best_stop = float("inf")
    stale = 0
    history: list[dict[str, Any]] = []
    for generation in range(OPTIMIZER["generations"]):
        candidates = optimizer_rng.normal(mean, sigma, size=(OPTIMIZER["population"], len(mean)))
        candidates[0] = mean
        scores = [
            evaluate_training_objective(candidate, train_fit, config) for candidate in candidates
        ]
        ranking = np.argsort([float(score["objective"]) for score in scores])
        elite = candidates[ranking[: OPTIMIZER["elite"]]]
        mean = elite.mean(axis=0)
        sigma = np.maximum(elite.std(axis=0), OPTIMIZER["sigma_floor"])
        stop_score = evaluate_training_objective(mean, train_stop, config)
        retained.append((mean.copy(), stop_score, generation))
        history.append(
            {
                "generation": generation,
                "train_fit_best": scores[int(ranking[0])],
                "train_stop_mean": stop_score,
                "sigma_max": float(np.max(sigma)),
            }
        )
        if float(stop_score["objective"]) < best_stop - 1e-9:
            best_stop = float(stop_score["objective"])
            stale = 0
        else:
            stale += 1
        if stale >= OPTIMIZER["early_stop_patience"]:
            break

    validation_rows = []
    for weights, stop_score, generation in retained:
        score = evaluate_training_objective(weights, validation, config)
        validation_rows.append((weights, stop_score, generation, score))
    validation_rows.sort(
        key=lambda row: (
            int(row[3]["collisions"]),
            -int(row[3]["sustained_successes"]),
            float(row[3]["objective"]),
            float(np.linalg.norm(row[0])),
        )
    )
    selected_weights, selected_stop, generation, selected_validation = validation_rows[0]
    policy = FrozenPolicy(selected_weights, config)

    artifact = Path(artifact_path)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    np.savez(artifact, weights=selected_weights.astype("<f8"))
    artifact_hash = sha256_bytes(artifact.read_bytes())
    manifest = {
        "schema_version": config.schema_version,
        "artifact_sha256": artifact_hash,
        "model_identity": policy.model_identity,
        "architecture": POLICY_ARCHITECTURE,
        "feature_version": FEATURE_VERSION,
        "feature_schema": list(FEATURE_SCHEMA),
        "missing_value_rule": "impute range=6.5 m and velocity=0; set explicit flags",
        "action_transform": "0.05*tanh(features@weights) m/s^2",
        "dtype": "float64 little-endian",
        "shape": list(selected_weights.shape),
        "byte_order": "little",
        "training_objective": TRAINING_OBJECTIVE,
        "optimizer": OPTIMIZER,
        "model_selection_rule": MODEL_SELECTION_RULE,
        "selected_generation": generation,
        "train_stop_metrics": selected_stop,
        "validation_metrics": selected_validation,
        "training_history": history,
        "upset_scale_rule": "max(abs(weight), 0.25); eligible indices 0..5",
        "source_identity": source_identity,
        "prohibited_training_inputs": [
            "fallback actions",
            "runtime gate labels",
            "monitor-channel observations",
            "pilot outcomes",
            "future confirmatory outcomes",
        ],
    }
    manifest_file = Path(manifest_path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest["manifest_sha256"] = sha256_bytes(manifest_file.read_bytes())
    return manifest


def policy_manifest_identity(path: str | Path) -> dict[str, str]:
    payload = Path(path).read_bytes()
    data = json.loads(payload)
    return {
        "artifact_sha256": data["artifact_sha256"],
        "model_identity": data["model_identity"],
        "manifest_sha256": hashlib.sha256(payload).hexdigest(),
    }
