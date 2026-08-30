from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class ObservabilityDiagnostics:
    rank: int
    smallest_singular_value: float
    condition_number: float
    scaled_matrix: FloatArray


def transition_matrices(
    dt_s: float,
    actuator_time_constant_s: float,
) -> tuple[FloatArray, FloatArray]:
    """Exact discrete transition for ``[range, velocity, achieved acceleration]``.

    Command is held constant over the interval. Process acceleration has zero mean
    in the estimator and is represented separately in the covariance.
    """

    if not np.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    if not np.isfinite(actuator_time_constant_s) or actuator_time_constant_s <= 0.0:
        raise ValueError("actuator_time_constant_s must be finite and positive")
    tau = float(actuator_time_constant_s)
    decay = float(np.exp(-dt_s / tau))
    acceleration_to_velocity = tau * (1.0 - decay)
    acceleration_to_range = tau * (dt_s - acceleration_to_velocity)
    transition = np.array(
        [
            [1.0, dt_s, acceleration_to_range],
            [0.0, 1.0, acceleration_to_velocity],
            [0.0, 0.0, decay],
        ],
        dtype=np.float64,
    )
    command = np.array(
        [
            0.5 * dt_s**2 - acceleration_to_range,
            dt_s - acceleration_to_velocity,
            1.0 - decay,
        ],
        dtype=np.float64,
    )
    return transition, command


def constant_disturbance_vector(dt_s: float) -> FloatArray:
    if not np.isfinite(dt_s) or dt_s <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    return np.array([0.5 * dt_s**2, dt_s, 0.0], dtype=np.float64)


def propagate_mean(
    state: FloatArray,
    command_mps2: float,
    dt_s: float,
    actuator_time_constant_s: float,
    disturbance_mps2: float = 0.0,
) -> FloatArray:
    vector = np.asarray(state, dtype=np.float64)
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError("state must be a finite three-vector")
    if not np.isfinite(command_mps2) or not np.isfinite(disturbance_mps2):
        raise ValueError("command and disturbance must be finite")
    transition, command = transition_matrices(dt_s, actuator_time_constant_s)
    return (
        transition @ vector
        + command * float(command_mps2)
        + constant_disturbance_vector(dt_s) * float(disturbance_mps2)
    )


def piecewise_disturbance_covariance(
    command_period_s: float,
    exogenous_period_s: float,
    disturbance_sigma_mps2: float,
    actuator_model_sigma_mps2: float = 0.0,
) -> FloatArray:
    """Exact covariance for independent piecewise-constant acceleration draws.

    This matches the Experiment 002 generator: one independent acceleration draw
    per exogenous interval, held constant within that interval.
    """

    values = (
        command_period_s,
        exogenous_period_s,
        disturbance_sigma_mps2,
        actuator_model_sigma_mps2,
    )
    if not all(np.isfinite(value) for value in values):
        raise ValueError("process-covariance inputs must be finite")
    if command_period_s <= 0.0 or exogenous_period_s <= 0.0:
        raise ValueError("periods must be positive")
    ratio = command_period_s / exogenous_period_s
    steps = round(ratio)
    if abs(ratio - steps) > 1e-12:
        raise ValueError("command period must be an integer multiple of exogenous period")
    if disturbance_sigma_mps2 < 0.0 or actuator_model_sigma_mps2 < 0.0:
        raise ValueError("process uncertainty values must be non-negative")
    covariance = np.zeros((3, 3), dtype=np.float64)
    h = float(exogenous_period_s)
    for index in range(steps):
        remaining_after_start = command_period_s - index * h
        influence = np.array(
            [h * (remaining_after_start - 0.5 * h), h, 0.0],
            dtype=np.float64,
        )
        covariance += disturbance_sigma_mps2**2 * np.outer(influence, influence)
    covariance[2, 2] += actuator_model_sigma_mps2**2
    return covariance


def measurement_matrix() -> FloatArray:
    return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64)


def nominal_measurement_covariance(
    range_sigma_m: float,
    velocity_sigma_mps: float,
    range_quantization_m: float,
    velocity_quantization_mps: float,
) -> FloatArray:
    values = (
        range_sigma_m,
        velocity_sigma_mps,
        range_quantization_m,
        velocity_quantization_mps,
    )
    if not all(np.isfinite(value) and value >= 0.0 for value in values):
        raise ValueError("measurement uncertainty values must be finite and non-negative")
    return np.diag(
        np.array(
            [
                range_sigma_m**2 + range_quantization_m**2 / 12.0,
                velocity_sigma_mps**2 + velocity_quantization_mps**2 / 12.0,
            ],
            dtype=np.float64,
        )
    )


def observability_diagnostics(
    dt_s: float,
    actuator_time_constant_s: float,
    state_scales: tuple[float, float, float] = (100.0, 0.3, 0.05),
) -> ObservabilityDiagnostics:
    transition, _ = transition_matrices(dt_s, actuator_time_constant_s)
    observation = measurement_matrix()
    matrix = np.vstack(
        (observation, observation @ transition, observation @ transition @ transition)
    )
    scales = np.asarray(state_scales, dtype=np.float64)
    if scales.shape != (3,) or np.any(scales <= 0.0) or not np.all(np.isfinite(scales)):
        raise ValueError("state scales must be a finite positive three-vector")
    scaled = matrix @ np.diag(scales)
    singular_values = np.linalg.svd(scaled, compute_uv=False)
    rank = int(np.linalg.matrix_rank(scaled, tol=1e-12))
    smallest = float(singular_values[-1])
    condition = float(singular_values[0] / singular_values[-1]) if smallest > 0.0 else np.inf
    return ObservabilityDiagnostics(rank, smallest, condition, scaled)
