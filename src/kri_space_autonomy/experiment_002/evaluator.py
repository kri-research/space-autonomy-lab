from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .config import PilotConfig
from .dynamics import PropagationResult, TruthState


@dataclass(frozen=True)
class RecoveryCorridor:
    min_range_m: float
    max_range_m: float
    max_abs_velocity_mps: float
    min_propellant: float
    calibration_partition: str
    calibration_method: str
    calibration_sha256: str

    def contains(self, state: TruthState) -> bool:
        return (
            self.min_range_m <= state.range_m <= self.max_range_m
            and abs(state.relative_velocity_mps) <= self.max_abs_velocity_mps
            and state.propellant >= self.min_propellant
        )


@dataclass(frozen=True)
class EvaluationSummary:
    physical_hazard_observed: bool
    collision: bool
    sustained_success: bool
    propellant_depleted: bool
    braking_unreachable: bool
    minimum_braking_margin_m: float | None
    minimum_range_m: float
    maximum_contiguous_negative_margin_s: float
    first_goal_entry_s: float | None
    goal_dwell_final60_fraction: float


def _signed_impulse(a0: float, target: float, tau: float, time_s: float) -> float:
    return target * time_s + (a0 - target) * tau * (1.0 - math.exp(-time_s / tau))


def _absolute_impulse(a0: float, target: float, tau: float, time_s: float) -> float:
    signed = _signed_impulse(a0, target, tau, time_s)
    if a0 == 0.0 or target == 0.0 or a0 * target >= 0.0:
        return abs(signed)
    ratio = -target / (a0 - target)
    if not 0.0 < ratio < 1.0:
        return abs(signed)
    crossing = -tau * math.log(ratio)
    if not 0.0 < crossing < time_s:
        return abs(signed)
    before = _signed_impulse(a0, target, tau, crossing)
    return abs(before) + abs(signed - before)


def reachable_stopping_distance_m(
    state: TruthState, effectiveness: float, config: PilotConfig
) -> float:
    """Truth-based stopping reach under maximum separation command.

    The evaluator holds current latent effectiveness fixed, assumes the frozen
    adverse process acceleration ``-process_accel_clip``, accounts for the
    current lag state and available propellant, and returns infinity if zero
    closing speed cannot be reached before depletion. It is independent of the
    runtime gate's nominal one-step predicate.
    """

    if state.relative_velocity_mps >= 0.0:
        return 0.0
    if state.propellant <= 0.0 or effectiveness <= 0.0:
        return math.inf
    target = effectiveness * config.max_acceleration_mps2
    adverse = -config.process_accel_clip_mps2
    net_equilibrium = target + adverse
    if net_equilibrium <= 0.0:
        return math.inf
    tau = config.actuator_time_constant_s
    delta = state.achieved_acceleration_mps2 - target

    def velocity(time_s: float) -> float:
        return (
            state.relative_velocity_mps
            + net_equilibrium * time_s
            + delta * tau * (1.0 - math.exp(-time_s / tau))
        )

    right = max(1.0, -state.relative_velocity_mps / net_equilibrium + 4.0 * tau)
    while velocity(right) < 0.0 and right < 10_000.0:
        right *= 2.0
    if velocity(right) < 0.0:
        return math.inf
    left = 0.0
    for _ in range(64):
        midpoint = 0.5 * (left + right)
        if velocity(midpoint) < 0.0:
            left = midpoint
        else:
            right = midpoint
    stop_time = 0.5 * (left + right)
    required_propellant = config.propellant_cost_per_delta_v * _absolute_impulse(
        state.achieved_acceleration_mps2, target, tau, stop_time
    )
    if required_propellant > state.propellant + 1e-12:
        return math.inf
    displacement = (
        state.relative_velocity_mps * stop_time
        + 0.5 * net_equilibrium * stop_time**2
        + delta * tau * (stop_time - tau * (1.0 - math.exp(-stop_time / tau)))
    )
    return max(0.0, -displacement)


def braking_margin_m(state: TruthState, effectiveness: float, config: PilotConfig) -> float:
    stopping_distance = reachable_stopping_distance_m(state, effectiveness, config)
    if math.isinf(stopping_distance):
        return -math.inf
    return state.range_m - config.collision_range_m - stopping_distance


class IndependentEvaluator:
    """Offline truth evaluator with no runtime-gate dependency."""

    def __init__(self, config: PilotConfig, initial_state: TruthState, effectiveness: float):
        self.config = config
        self.minimum_range_m = initial_state.range_m
        initial_margin = braking_margin_m(initial_state, effectiveness, config)
        self.minimum_margin = initial_margin
        self.braking_unreachable = math.isinf(initial_margin)
        self.previous_margin = initial_margin
        self.previous_margin_time = initial_state.time_s
        self.current_negative_duration = 0.0
        self.max_negative_duration = 0.0
        self.collision = initial_state.range_m <= config.collision_range_m
        self.propellant_depleted = initial_state.propellant <= 0.0
        self.first_goal_entry_s: float | None = None
        self.final_window_valid_s = 0.0

    @staticmethod
    def _negative_fraction(left: float, right: float) -> tuple[float, bool, bool]:
        left_negative = left < 0.0
        right_negative = right < 0.0
        if left_negative and right_negative:
            return 1.0, True, True
        if not left_negative and not right_negative:
            return 0.0, False, False
        if math.isinf(left) or math.isinf(right):
            return (1.0, left_negative, right_negative)
        denominator = abs(left) + abs(right)
        fraction = abs(left) / denominator if denominator else 0.5
        if left_negative:
            return fraction, True, False
        return 1.0 - fraction, False, True

    def observe_margin(self, state: TruthState, effectiveness: float) -> None:
        margin = braking_margin_m(state, effectiveness, self.config)
        self.braking_unreachable |= math.isinf(margin)
        self.minimum_margin = min(self.minimum_margin, margin)
        dt = state.time_s - self.previous_margin_time
        fraction, starts_negative, ends_negative = self._negative_fraction(
            self.previous_margin, margin
        )
        negative_duration = fraction * dt
        if starts_negative:
            self.current_negative_duration += negative_duration
        elif ends_negative:
            self.current_negative_duration = negative_duration
        if not ends_negative:
            self.max_negative_duration = max(
                self.max_negative_duration, self.current_negative_duration
            )
            self.current_negative_duration = 0.0
        else:
            self.max_negative_duration = max(
                self.max_negative_duration, self.current_negative_duration
            )
        self.previous_margin = margin
        self.previous_margin_time = state.time_s

    def observe_interval(
        self,
        start_state: TruthState,
        propagation: PropagationResult,
    ) -> None:
        self.minimum_range_m = min(self.minimum_range_m, propagation.minimum_range_m)
        self.collision |= propagation.collision_time_s is not None
        self.propellant_depleted |= propagation.propellant_depleted
        final_start = self.config.horizon_s - self.config.goal_dwell_s
        overlap_start = max(start_state.time_s, final_start)
        overlap_end = min(propagation.state.time_s, self.config.horizon_s)
        if overlap_end > overlap_start:
            continuous_goal = (
                propagation.minimum_range_m >= self.config.goal_min_range_m
                and propagation.maximum_range_m <= self.config.goal_max_range_m
                and propagation.maximum_abs_velocity_mps <= self.config.goal_max_speed_mps
                and propagation.state.propellant >= self.config.propellant_reserve
            )
            if continuous_goal:
                self.final_window_valid_s += overlap_end - overlap_start
        endpoint_goal = (
            self.config.goal_min_range_m
            <= propagation.state.range_m
            <= self.config.goal_max_range_m
            and abs(propagation.state.relative_velocity_mps) <= self.config.goal_max_speed_mps
        )
        if endpoint_goal and self.first_goal_entry_s is None:
            self.first_goal_entry_s = propagation.state.time_s

    def finalize(self, final_state: TruthState) -> EvaluationSummary:
        sustained = (
            not self.collision
            and not self.propellant_depleted
            and final_state.propellant >= self.config.propellant_reserve
            and abs(self.final_window_valid_s - self.config.goal_dwell_s) <= 1e-9
        )
        margin_hazard = self.max_negative_duration + 1e-12 >= 1.0
        hazard = self.collision or margin_hazard
        minimum_margin = None if math.isinf(self.minimum_margin) else self.minimum_margin
        return EvaluationSummary(
            physical_hazard_observed=hazard,
            collision=self.collision,
            sustained_success=sustained and not hazard,
            propellant_depleted=self.propellant_depleted,
            braking_unreachable=self.braking_unreachable,
            minimum_braking_margin_m=minimum_margin,
            minimum_range_m=self.minimum_range_m,
            maximum_contiguous_negative_margin_s=self.max_negative_duration,
            first_goal_entry_s=self.first_goal_entry_s,
            goal_dwell_final60_fraction=self.final_window_valid_s / self.config.goal_dwell_s,
        )


def classify_recovery(
    corridor_samples: list[tuple[float, bool]],
    fault_onset_s: float | None,
    fault_end_s: float | None,
    failed: bool,
    sustained_success: bool,
    persistent_model_upset: bool,
    fallback_latched: bool,
    arm: str,
    config: PilotConfig,
) -> dict[str, Any]:
    """Apply frozen precedence FAILED > UNAFFECTED > RECOVERED > GRACEFUL > NOT."""

    if fault_onset_s is None:
        return {
            "recovery_state": "NOT_APPLICABLE",
            "corridor_first_exit_s": None,
            "qualifying_reentry_start_s": None,
            "recovery_favorable_180": None,
            "restricted_time_unrecovered_s_180": None,
        }
    post_fault = [
        (time_s, inside) for time_s, inside in corridor_samples if time_s >= fault_onset_s
    ]
    first_exit = next((time_s for time_s, inside in post_fault if not inside), None)
    if failed:
        state = "FAILED"
        qualifying = None
    elif first_exit is None:
        state = "UNAFFECTED"
        qualifying = None
    else:
        qualifying = None
        required_restoration = (
            math.inf if persistent_model_upset else (fault_end_s or fault_onset_s)
        )
        dwell_start: float | None = None
        for time_s, inside in post_fault:
            if time_s < first_exit or time_s < required_restoration:
                continue
            if inside and dwell_start is None:
                dwell_start = time_s
            elif not inside:
                dwell_start = None
            if (
                inside
                and dwell_start is not None
                and time_s - dwell_start >= config.recovery_dwell_s
            ):
                qualifying = dwell_start
                break
        within_deadline = (
            qualifying is not None
            and qualifying - first_exit <= config.recovery_deadline_s
            and sustained_success
        )
        if within_deadline:
            state = "RECOVERED"
        elif (
            persistent_model_upset
            and arm in {"PS", "PD"}
            and fallback_latched
            and sustained_success
        ):
            state = "GRACEFUL_DEGRADED"
        else:
            state = "NOT_RECOVERED"
    favorable = state in {"UNAFFECTED", "RECOVERED"}
    if state == "UNAFFECTED":
        restricted = 0.0
    elif state == "RECOVERED" and first_exit is not None and qualifying is not None:
        restricted = min(config.recovery_deadline_s, qualifying - first_exit)
    else:
        restricted = config.recovery_deadline_s
    return {
        "recovery_state": state,
        "corridor_first_exit_s": first_exit,
        "qualifying_reentry_start_s": qualifying,
        "recovery_favorable_180": favorable,
        "restricted_time_unrecovered_s_180": restricted,
    }
