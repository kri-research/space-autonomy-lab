from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import expm

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class ObservabilityDiagnostics:
    rank: int
    smallest_singular_value: float
    condition_number: float
    scaled_matrix: FloatArray


def _finite_positive(name: str, value: float, *, allow_zero: bool = False) -> float:
    if not np.isfinite(value) or value < 0.0 or (value == 0.0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return float(value)


def continuous_matrices(mean_motion_rad_s: float) -> tuple[FloatArray, FloatArray]:
    """Return planar HCW matrices for +x radial-outward and +y along-track.

    The state is ``[x, y, vx, vy]`` in m and m/s. The input is ``[ax, ay]``
    in m/s^2, expressed in the same rotating LVLH frame.
    """

    n = _finite_positive("mean_motion_rad_s", mean_motion_rad_s)
    transition_rate = np.array(
        [
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [3.0 * n**2, 0.0, 0.0, 2.0 * n],
            [0.0, 0.0, -2.0 * n, 0.0],
        ],
        dtype=np.float64,
    )
    input_rate = np.array(
        [[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
        dtype=np.float64,
    )
    return transition_rate, input_rate


@lru_cache(maxsize=64)
def _cached_discrete(mean_motion_rad_s: float, dt_s: float) -> tuple[FloatArray, FloatArray]:
    transition_rate, input_rate = continuous_matrices(mean_motion_rad_s)
    augmented = np.zeros((6, 6), dtype=np.float64)
    augmented[:4, :4] = transition_rate
    augmented[:4, 4:] = input_rate
    discrete = expm(augmented * dt_s)
    return discrete[:4, :4], discrete[:4, 4:]


def discrete_matrices(
    mean_motion_rad_s: float,
    dt_s: float,
) -> tuple[FloatArray, FloatArray]:
    """Exact zero-order-hold HCW transition from one augmented exponential."""

    n = _finite_positive("mean_motion_rad_s", mean_motion_rad_s)
    dt = _finite_positive("dt_s", dt_s, allow_zero=True)
    transition, command = _cached_discrete(n, dt)
    return np.array(transition, copy=True), np.array(command, copy=True)


def closed_form_matrices(
    mean_motion_rad_s: float,
    dt_s: float,
) -> tuple[FloatArray, FloatArray]:
    """Independent analytical HCW state and zero-order-hold input matrices."""

    n = _finite_positive("mean_motion_rad_s", mean_motion_rad_s)
    dt = _finite_positive("dt_s", dt_s, allow_zero=True)
    theta = n * dt
    sine = float(np.sin(theta))
    cosine = float(np.cos(theta))
    one_minus_cosine = 2.0 * float(np.sin(0.5 * theta)) ** 2
    if abs(theta) < 0.01:
        theta_minus_sine = theta**3 * (
            1.0 / 6.0
            - theta**2 / 120.0
            + theta**4 / 5040.0
            - theta**6 / 362880.0
        )
    else:
        theta_minus_sine = theta - sine
    sine_minus_theta = -theta_minus_sine
    transition = np.array(
        [
            [4.0 - 3.0 * cosine, 0.0, sine / n, 2.0 * one_minus_cosine / n],
            [
                6.0 * sine_minus_theta,
                1.0,
                -2.0 * one_minus_cosine / n,
                (4.0 * sine - 3.0 * theta) / n,
            ],
            [3.0 * n * sine, 0.0, cosine, 2.0 * sine],
            [
                -6.0 * n * one_minus_cosine,
                0.0,
                -2.0 * sine,
                4.0 * cosine - 3.0,
            ],
        ],
        dtype=np.float64,
    )
    command = np.array(
        [
            [one_minus_cosine / n**2, 2.0 * theta_minus_sine / n**2],
            [
                2.0 * sine_minus_theta / n**2,
                (4.0 * one_minus_cosine - 1.5 * theta**2) / n**2,
            ],
            [sine / n, 2.0 * one_minus_cosine / n],
            [-2.0 * one_minus_cosine / n, 4.0 * sine / n - 3.0 * dt],
        ],
        dtype=np.float64,
    )
    return transition, command


def propagate_exact(
    state: FloatArray,
    acceleration_mps2: FloatArray,
    mean_motion_rad_s: float,
    dt_s: float,
) -> FloatArray:
    vector = np.asarray(state, dtype=np.float64)
    command = np.asarray(acceleration_mps2, dtype=np.float64)
    if vector.shape != (4,) or not np.all(np.isfinite(vector)):
        raise ValueError("state must be a finite four-vector")
    if command.shape != (2,) or not np.all(np.isfinite(command)):
        raise ValueError("acceleration must be a finite two-vector")
    transition, command_map = discrete_matrices(mean_motion_rad_s, dt_s)
    result = transition @ vector + command_map @ command
    if not np.all(np.isfinite(result)):
        raise ArithmeticError("HCW propagation produced non-finite state")
    return result


def piecewise_acceleration_covariance(
    mean_motion_rad_s: float,
    command_period_s: float,
    draw_period_s: float,
    acceleration_sigma_mps2: tuple[float, float],
) -> FloatArray:
    """Exact covariance for independent piecewise-constant LVLH acceleration draws.

    A new two-axis zero-mean acceleration is drawn every ``draw_period_s`` and
    held over that subinterval. The supplied sigma therefore has units m/s^2;
    it is not a continuous white-noise spectral density.
    """

    total = _finite_positive("command_period_s", command_period_s)
    draw = _finite_positive("draw_period_s", draw_period_s)
    sigma = np.asarray(acceleration_sigma_mps2, dtype=np.float64)
    if sigma.shape != (2,) or np.any(sigma < 0.0) or not np.all(np.isfinite(sigma)):
        raise ValueError("acceleration sigma must be a finite non-negative two-vector")
    ratio = total / draw
    steps = round(ratio)
    if abs(ratio - steps) > 1e-12:
        raise ValueError("command period must be an integer multiple of draw period")
    draw_covariance = np.diag(sigma**2)
    transition_draw, command_draw = discrete_matrices(mean_motion_rad_s, draw)
    covariance = np.zeros((4, 4), dtype=np.float64)
    influence = np.array(command_draw, copy=True)
    for _ in range(steps):
        covariance += influence @ draw_covariance @ influence.T
        influence = transition_draw @ influence
    covariance = 0.5 * (covariance + covariance.T)
    return covariance


def measurement_matrix(*, position_only: bool = False) -> FloatArray:
    if position_only:
        return np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
            dtype=np.float64,
        )
    return np.eye(4, dtype=np.float64)


def observability_diagnostics(
    mean_motion_rad_s: float,
    dt_s: float,
    *,
    position_only: bool,
    state_scales: tuple[float, float, float, float] = (100.0, 100.0, 0.2, 0.2),
) -> ObservabilityDiagnostics:
    transition, _ = discrete_matrices(mean_motion_rad_s, dt_s)
    observation = measurement_matrix(position_only=position_only)
    matrix = np.vstack(
        [observation @ np.linalg.matrix_power(transition, power) for power in range(4)]
    )
    scales = np.asarray(state_scales, dtype=np.float64)
    if scales.shape != (4,) or np.any(scales <= 0.0) or not np.all(np.isfinite(scales)):
        raise ValueError("state scales must be a finite positive four-vector")
    scaled = matrix @ np.diag(scales)
    singular_values = np.linalg.svd(scaled, compute_uv=False)
    rank = int(np.linalg.matrix_rank(scaled, tol=1e-12))
    smallest = float(singular_values[-1])
    condition = float(singular_values[0] / smallest) if smallest > 0.0 else np.inf
    return ObservabilityDiagnostics(rank, smallest, condition, scaled)
