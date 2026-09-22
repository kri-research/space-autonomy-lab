from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def _vector(name: str, value: FloatArray, size: int) -> FloatArray:
    vector = np.asarray(value, dtype=np.float64)
    if vector.shape != (size,) or not np.all(np.isfinite(vector)):
        raise ValueError(f"{name} must be a finite {size}-vector")
    return vector


def _positive(name: str, value: float, *, allow_zero: bool = False) -> float:
    if not np.isfinite(value) or value < 0.0 or (value == 0.0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return float(value)


def circular_chief_state(
    gravitational_parameter_m3_s2: float,
    radius_m: float,
    elapsed_s: float = 0.0,
    *,
    phase_rad: float = 0.0,
) -> FloatArray:
    """Return an analytic equatorial prograde circular-orbit inertial state."""

    mu = _positive("gravitational_parameter_m3_s2", gravitational_parameter_m3_s2)
    radius = _positive("radius_m", radius_m)
    if not np.isfinite(elapsed_s) or not np.isfinite(phase_rad):
        raise ValueError("elapsed time and phase must be finite")
    mean_motion = math.sqrt(mu / radius**3)
    angle = float(phase_rad + mean_motion * elapsed_s)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    speed = math.sqrt(mu / radius)
    return np.array(
        [
            radius * cosine,
            radius * sine,
            0.0,
            -speed * sine,
            speed * cosine,
            0.0,
        ],
        dtype=np.float64,
    )


def lvlh_basis(chief_state: FloatArray) -> FloatArray:
    """Map LVLH components to inertial components using [radial, along-track, normal]."""

    chief = _vector("chief_state", chief_state, 6)
    position = chief[:3]
    velocity = chief[3:]
    radius = float(np.linalg.norm(position))
    angular_momentum = np.cross(position, velocity)
    momentum_norm = float(np.linalg.norm(angular_momentum))
    if radius <= 0.0 or momentum_norm <= 0.0:
        raise ValueError("chief state cannot define a non-degenerate LVLH frame")
    radial = position / radius
    normal = angular_momentum / momentum_norm
    alongtrack = np.cross(normal, radial)
    basis = np.column_stack((radial, alongtrack, normal))
    if not np.allclose(basis.T @ basis, np.eye(3), rtol=0.0, atol=5e-15):
        raise ArithmeticError("LVLH basis lost orthonormality")
    if np.linalg.det(basis) <= 0.0:
        raise ArithmeticError("LVLH basis is not right-handed")
    return basis


def lvlh_angular_velocity_local(chief_state: FloatArray) -> FloatArray:
    """Return the instantaneous LVLH angular velocity resolved in LVLH axes."""

    chief = _vector("chief_state", chief_state, 6)
    radius_squared = float(chief[:3] @ chief[:3])
    angular_momentum_norm = float(np.linalg.norm(np.cross(chief[:3], chief[3:])))
    if radius_squared <= 0.0 or angular_momentum_norm <= 0.0:
        raise ValueError("chief state cannot define LVLH angular velocity")
    return np.array([0.0, 0.0, angular_momentum_norm / radius_squared], dtype=np.float64)


def relative_to_inertial(chief_state: FloatArray, relative_state: FloatArray) -> FloatArray:
    """Convert LVLH relative position/rotating velocity to deputy inertial state.

    The relative state is ``[x, y, z, vx, vy, vz]``. The velocity conversion includes
    ``omega x rho`` and therefore does not treat rotating-frame velocity as inertial.
    """

    chief = _vector("chief_state", chief_state, 6)
    relative = _vector("relative_state", relative_state, 6)
    basis = lvlh_basis(chief)
    omega_local = lvlh_angular_velocity_local(chief)
    deputy_position = chief[:3] + basis @ relative[:3]
    deputy_velocity = chief[3:] + basis @ (
        relative[3:] + np.cross(omega_local, relative[:3])
    )
    return np.concatenate((deputy_position, deputy_velocity)).astype(np.float64)


def inertial_to_relative(chief_state: FloatArray, deputy_state: FloatArray) -> FloatArray:
    """Convert chief/deputy inertial states to LVLH position and rotating velocity."""

    chief = _vector("chief_state", chief_state, 6)
    deputy = _vector("deputy_state", deputy_state, 6)
    basis = lvlh_basis(chief)
    relative_position = basis.T @ (deputy[:3] - chief[:3])
    relative_velocity = basis.T @ (deputy[3:] - chief[3:]) - np.cross(
        lvlh_angular_velocity_local(chief), relative_position
    )
    return np.concatenate((relative_position, relative_velocity)).astype(np.float64)


def pair_state(chief_state: FloatArray, deputy_state: FloatArray) -> FloatArray:
    chief = _vector("chief_state", chief_state, 6)
    deputy = _vector("deputy_state", deputy_state, 6)
    return np.concatenate((chief, deputy)).astype(np.float64)


def split_pair_state(state: FloatArray) -> tuple[FloatArray, FloatArray]:
    pair = _vector("pair_state", state, 12)
    chief = np.concatenate((pair[:3], pair[3:6]))
    deputy = np.concatenate((pair[6:9], pair[9:12]))
    return chief, deputy


def pair_from_relative(chief_state: FloatArray, relative_state: FloatArray) -> FloatArray:
    chief = _vector("chief_state", chief_state, 6)
    deputy = relative_to_inertial(chief, relative_state)
    return pair_state(chief, deputy)


def pair_to_relative(state: FloatArray) -> FloatArray:
    chief, deputy = split_pair_state(state)
    return inertial_to_relative(chief, deputy)


def command_to_inertial(chief_state: FloatArray, command_lvlh_mps2: FloatArray) -> FloatArray:
    """Map a commanded LVLH acceleration into inertial axes at this chief state."""

    command = _vector("command_lvlh_mps2", command_lvlh_mps2, 3)
    return lvlh_basis(chief_state) @ command


def central_gravity(position_m: FloatArray, gravitational_parameter_m3_s2: float) -> FloatArray:
    position = _vector("position_m", position_m, 3)
    mu = _positive("gravitational_parameter_m3_s2", gravitational_parameter_m3_s2)
    radius = float(np.linalg.norm(position))
    if radius <= 0.0:
        raise ValueError("central-gravity position cannot be zero")
    return -mu * position / radius**3


def two_body_pair_derivative(
    state: FloatArray,
    command_lvlh_mps2: FloatArray,
    gravitational_parameter_m3_s2: float,
) -> FloatArray:
    """Derivative for chief and deputy nonlinear central-gravity inertial truth.

    The LVLH command is zero-order held in local components over a control interval.
    Its inertial direction is recomputed from the instantaneous chief state at every
    integration stage; a local radial command therefore rotates in inertial space.
    """

    pair = _vector("pair_state", state, 12)
    command = _vector("command_lvlh_mps2", command_lvlh_mps2, 3)
    chief, deputy = split_pair_state(pair)
    derivative = np.empty(12, dtype=np.float64)
    derivative[:3] = chief[3:]
    derivative[3:6] = central_gravity(chief[:3], gravitational_parameter_m3_s2)
    derivative[6:9] = deputy[3:]
    derivative[9:12] = central_gravity(
        deputy[:3], gravitational_parameter_m3_s2
    ) + command_to_inertial(chief, command)
    if not np.all(np.isfinite(derivative)):
        raise ArithmeticError("two-body truth derivative became non-finite")
    return derivative


def rk4_step(
    state: FloatArray,
    command_lvlh_mps2: FloatArray,
    gravitational_parameter_m3_s2: float,
    step_s: float,
) -> FloatArray:
    pair = _vector("pair_state", state, 12)
    command = _vector("command_lvlh_mps2", command_lvlh_mps2, 3)
    step = _positive("step_s", step_s)
    derivative = two_body_pair_derivative
    first = derivative(pair, command, gravitational_parameter_m3_s2)
    second = derivative(pair + 0.5 * step * first, command, gravitational_parameter_m3_s2)
    third = derivative(pair + 0.5 * step * second, command, gravitational_parameter_m3_s2)
    fourth = derivative(pair + step * third, command, gravitational_parameter_m3_s2)
    result = pair + (step / 6.0) * (first + 2.0 * second + 2.0 * third + fourth)
    if not np.all(np.isfinite(result)):
        raise ArithmeticError("fixed-step RK4 produced a non-finite truth state")
    return result


def propagate_fixed(
    state: FloatArray,
    command_lvlh_mps2: FloatArray,
    gravitational_parameter_m3_s2: float,
    duration_s: float,
    maximum_step_s: float,
) -> FloatArray:
    """Deterministic bounded-step RK4 propagation split exactly at the endpoint."""

    current = np.array(_vector("pair_state", state, 12), copy=True)
    command = _vector("command_lvlh_mps2", command_lvlh_mps2, 3)
    duration = _positive("duration_s", duration_s, allow_zero=True)
    maximum_step = _positive("maximum_step_s", maximum_step_s)
    if duration == 0.0:
        return current
    ratio = duration / maximum_step
    full_steps = int(math.floor(ratio))
    remainder = duration - full_steps * maximum_step
    tolerance = 1e-14 * maximum_step
    if remainder < tolerance:
        remainder = 0.0
    elif maximum_step - remainder < tolerance:
        full_steps += 1
        remainder = 0.0
    for _ in range(full_steps):
        current = rk4_step(
            current, command, gravitational_parameter_m3_s2, maximum_step
        )
    if remainder > 0.0:
        current = rk4_step(current, command, gravitational_parameter_m3_s2, remainder)
    return current


def specific_energy(state: FloatArray, gravitational_parameter_m3_s2: float) -> float:
    body = _vector("body_state", state, 6)
    mu = _positive("gravitational_parameter_m3_s2", gravitational_parameter_m3_s2)
    radius = float(np.linalg.norm(body[:3]))
    if radius <= 0.0:
        raise ValueError("specific energy is undefined at zero radius")
    return float(0.5 * (body[3:] @ body[3:]) - mu / radius)


def angular_momentum(state: FloatArray) -> FloatArray:
    body = _vector("body_state", state, 6)
    return np.cross(body[:3], body[3:]).astype(np.float64)
