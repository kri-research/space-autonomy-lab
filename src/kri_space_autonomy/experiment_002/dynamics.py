from __future__ import annotations

import math
from dataclasses import dataclass

from .config import PilotConfig


@dataclass(frozen=True)
class TruthState:
    """Hidden physical state; never accepted by policy or runtime-gate interfaces."""

    time_s: float
    range_m: float
    relative_velocity_mps: float
    propellant: float
    achieved_acceleration_mps2: float


@dataclass(frozen=True)
class PropagationResult:
    state: TruthState
    minimum_range_m: float
    maximum_range_m: float
    maximum_abs_velocity_mps: float
    collision_time_s: float | None
    propellant_depleted: bool
    depletion_time_s: float | None = None
    collision_residual_m: float | None = None
    depletion_residual_fraction: float | None = None


def actuator_effectiveness(
    time_s: float, onset_s: float | None, end_s: float | None, degraded: float | None
) -> float:
    if onset_s is None or degraded is None:
        return 1.0
    if time_s >= onset_s and (end_s is None or time_s < end_s):
        return degraded
    return 1.0


def _signed_impulse(a0: float, target: float, tau: float, t: float) -> float:
    return target * t + (a0 - target) * tau * (1.0 - math.exp(-t / tau))


def _abs_impulse(a0: float, target: float, tau: float, t: float) -> float:
    if t <= 0.0:
        return 0.0
    total = _signed_impulse(a0, target, tau, t)
    if a0 == 0.0 or target == 0.0 or a0 * target >= 0.0:
        return abs(total)
    ratio = -target / (a0 - target)
    if not 0.0 < ratio < 1.0:
        return abs(total)
    crossing = -tau * math.log(ratio)
    if not 0.0 < crossing < t:
        return abs(total)
    before = _signed_impulse(a0, target, tau, crossing)
    after = total - before
    return abs(before) + abs(after)


def state_at(
    state: TruthState,
    commanded_acceleration_mps2: float,
    effectiveness: float,
    process_acceleration_mps2: float,
    dt_s: float,
    config: PilotConfig,
) -> TruthState:
    target = effectiveness * commanded_acceleration_mps2 if state.propellant > 0.0 else 0.0
    tau = config.actuator_time_constant_s
    decay = math.exp(-dt_s / tau)
    delta = state.achieved_acceleration_mps2 - target
    achieved = target + delta * decay
    impulse = target * dt_s + delta * tau * (1.0 - decay)
    velocity = state.relative_velocity_mps + impulse + process_acceleration_mps2 * dt_s
    displacement = (
        state.relative_velocity_mps * dt_s
        + 0.5 * (target + process_acceleration_mps2) * dt_s**2
        + delta * tau * (dt_s - tau * (1.0 - decay))
    )
    used = config.propellant_cost_per_delta_v * _abs_impulse(
        state.achieved_acceleration_mps2, target, tau, dt_s
    )
    return TruthState(
        time_s=state.time_s + dt_s,
        range_m=state.range_m + displacement,
        relative_velocity_mps=velocity,
        propellant=max(0.0, state.propellant - used),
        achieved_acceleration_mps2=achieved,
    )


def _bisect(function, left: float, right: float, tolerance: float = 1e-12) -> float:
    f_left = function(left)
    f_right = function(right)
    if f_left == 0.0:
        return left
    if f_right == 0.0:
        return right
    if f_left * f_right > 0.0:
        raise ValueError("root is not bracketed")
    for _ in range(80):
        midpoint = 0.5 * (left + right)
        f_mid = function(midpoint)
        if abs(f_mid) <= tolerance or right - left <= tolerance:
            return midpoint
        if f_left * f_mid <= 0.0:
            right = midpoint
        else:
            left = midpoint
            f_left = f_mid
    return 0.5 * (left + right)


def _kinematic_functions(
    state: TruthState,
    command: float,
    effectiveness: float,
    disturbance: float,
    config: PilotConfig,
):
    target = effectiveness * command if state.propellant > 0.0 else 0.0
    tau = config.actuator_time_constant_s
    delta = state.achieved_acceleration_mps2 - target

    def velocity(t: float) -> float:
        return (
            state.relative_velocity_mps
            + (target + disturbance) * t
            + delta * tau * (1.0 - math.exp(-t / tau))
        )

    def range_at(t: float) -> float:
        return (
            state.range_m
            + state.relative_velocity_mps * t
            + 0.5 * (target + disturbance) * t**2
            + delta * tau * (t - tau * (1.0 - math.exp(-t / tau)))
        )

    return velocity, range_at


def _continuous_events(
    state: TruthState,
    command: float,
    effectiveness: float,
    disturbance: float,
    dt_s: float,
    config: PilotConfig,
) -> tuple[float, float, float, float | None]:
    velocity, range_at = _kinematic_functions(state, command, effectiveness, disturbance, config)
    grid = [dt_s * index / 32.0 for index in range(33)]
    velocity_roots: list[float] = []
    previous_t = grid[0]
    previous_v = velocity(previous_t)
    for current_t in grid[1:]:
        current_v = velocity(current_t)
        if previous_v * current_v < 0.0:
            velocity_roots.append(_bisect(velocity, previous_t, current_t))
        elif current_v == 0.0:
            velocity_roots.append(current_t)
        previous_t = current_t
        previous_v = current_v

    full_range_points = sorted({0.0, dt_s, *velocity_roots})
    full_ranges = [(time_s, range_at(time_s)) for time_s in full_range_points]
    collision_time: float | None = None
    if state.range_m <= config.collision_range_m:
        collision_time = 0.0
    else:
        for (left_t, left_r), (right_t, right_r) in zip(
            full_ranges, full_ranges[1:], strict=False
        ):
            if left_r > config.collision_range_m >= right_r:
                collision_time = _bisect(
                    lambda t: range_at(t) - config.collision_range_m,
                    left_t,
                    right_t,
                )
                break
            if right_r == config.collision_range_m:
                collision_time = right_t
                break

    terminal_t = collision_time if collision_time is not None else dt_s
    range_points = sorted(
        {
            0.0,
            terminal_t,
            *(root for root in velocity_roots if 0.0 < root < terminal_t),
        }
    )
    range_values = [range_at(time_s) for time_s in range_points]
    minimum_range = (
        config.collision_range_m if collision_time is not None else min(range_values)
    )
    maximum_range = max(range_values)

    target = effectiveness * command if state.propellant > 0.0 else 0.0
    delta = state.achieved_acceleration_mps2 - target
    acceleration_candidates = [0.0, terminal_t]
    denominator = target + disturbance
    if delta != 0.0 and denominator != 0.0:
        ratio = -denominator / delta
        if 0.0 < ratio < 1.0:
            root = -config.actuator_time_constant_s * math.log(ratio)
            if 0.0 < root < terminal_t:
                acceleration_candidates.append(root)
    maximum_abs_velocity = max(abs(velocity(time_s)) for time_s in acceleration_candidates)
    return minimum_range, maximum_range, maximum_abs_velocity, collision_time


def propagate_exact(
    state: TruthState,
    commanded_acceleration_mps2: float,
    effectiveness: float,
    process_acceleration_mps2: float,
    dt_s: float,
    config: PilotConfig,
) -> PropagationResult:
    command = max(
        -config.max_acceleration_mps2,
        min(config.max_acceleration_mps2, commanded_acceleration_mps2),
    )
    depleted_at_start = state.propellant <= 0.0
    if depleted_at_start:
        state = TruthState(
            state.time_s,
            state.range_m,
            state.relative_velocity_mps,
            0.0,
            0.0,
        )
        command = 0.0
    target = effectiveness * command
    required = config.propellant_cost_per_delta_v * _abs_impulse(
        state.achieved_acceleration_mps2,
        target,
        config.actuator_time_constant_s,
        dt_s,
    )
    if required <= state.propellant + 1e-15:
        minimum, maximum, maximum_abs_velocity, collision_local = _continuous_events(
            state, command, effectiveness, process_acceleration_mps2, dt_s, config
        )
        depletion_time = state.time_s if depleted_at_start else None
        depletion_residual = 0.0 if depleted_at_start else None
        if collision_local is not None:
            raw_collision_state = state_at(
                state,
                command,
                effectiveness,
                process_acceleration_mps2,
                collision_local,
                config,
            )
            collision_residual = raw_collision_state.range_m - config.collision_range_m
            collision_state = TruthState(
                raw_collision_state.time_s,
                config.collision_range_m,
                raw_collision_state.relative_velocity_mps,
                raw_collision_state.propellant,
                raw_collision_state.achieved_acceleration_mps2,
            )
            return PropagationResult(
                collision_state,
                minimum,
                maximum,
                maximum_abs_velocity,
                collision_state.time_s,
                collision_state.propellant <= 0.0 or depleted_at_start,
                depletion_time,
                collision_residual,
                depletion_residual,
            )
        end = state_at(state, command, effectiveness, process_acceleration_mps2, dt_s, config)
        return PropagationResult(
            end,
            minimum,
            maximum,
            maximum_abs_velocity,
            None,
            end.propellant <= 0.0 or depleted_at_start,
            depletion_time,
            None,
            depletion_residual,
        )

    tau = config.actuator_time_constant_s
    depletion_local = _bisect(
        lambda t: (
            config.propellant_cost_per_delta_v
            * _abs_impulse(state.achieved_acceleration_mps2, target, tau, t)
            - state.propellant
        ),
        0.0,
        dt_s,
    )
    depletion_time = state.time_s + depletion_local
    depletion_residual = state.propellant - (
        config.propellant_cost_per_delta_v
        * _abs_impulse(state.achieved_acceleration_mps2, target, tau, depletion_local)
    )
    first = propagate_exact(
        state,
        command,
        effectiveness,
        process_acceleration_mps2,
        depletion_local,
        config,
    )
    if first.collision_time_s is not None:
        simultaneous = abs(first.collision_time_s - depletion_time) <= 1e-12
        if not simultaneous:
            return first
        return PropagationResult(
            first.state,
            first.minimum_range_m,
            first.maximum_range_m,
            first.maximum_abs_velocity_mps,
            first.collision_time_s,
            True,
            depletion_time,
            first.collision_residual_m,
            depletion_residual,
        )
    depleted = TruthState(
        first.state.time_s,
        first.state.range_m,
        first.state.relative_velocity_mps,
        0.0,
        0.0,
    )
    remaining = dt_s - depletion_local
    if remaining <= 1e-15:
        return PropagationResult(
            depleted,
            first.minimum_range_m,
            first.maximum_range_m,
            first.maximum_abs_velocity_mps,
            None,
            True,
            depletion_time,
            None,
            depletion_residual,
        )
    second = propagate_exact(
        depleted,
        0.0,
        effectiveness,
        process_acceleration_mps2,
        remaining,
        config,
    )
    return PropagationResult(
        second.state,
        min(first.minimum_range_m, second.minimum_range_m),
        max(first.maximum_range_m, second.maximum_range_m),
        max(first.maximum_abs_velocity_mps, second.maximum_abs_velocity_mps),
        second.collision_time_s,
        True,
        depletion_time,
        second.collision_residual_m,
        depletion_residual,
    )
