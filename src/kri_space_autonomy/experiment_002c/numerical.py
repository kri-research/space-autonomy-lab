from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from kri_space_autonomy.experiment_002.config import PILOT_STRATA, PilotConfig
from kri_space_autonomy.experiment_002.dynamics import TruthState, propagate_exact
from kri_space_autonomy.experiment_002.evaluator import IndependentEvaluator
from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_002.seeds import ExogenousStreams, ScenarioSpec, sha256_bytes
from kri_space_autonomy.experiment_002b.config import AmendmentConfig
from kri_space_autonomy.experiment_002b.runner import run_pd_episode

from .config import NumericalAmendmentConfig, NumericalBounds
from .seeds import materialize_exogenous_002c, materialize_scenario_002c

_MISMATCH_ERROR = 1e100


@dataclass(frozen=True)
class ReferencePropagation:
    state: TruthState
    minimum_range_m: float
    maximum_range_m: float
    maximum_abs_velocity_mps: float
    collision_time_s: float | None
    propellant_depleted: bool
    depletion_time_s: float | None
    collision_residual_m: float | None
    depletion_residual_fraction: float | None
    acceleration_zero_crossings_s: tuple[float, ...]
    function_evaluations: int


@dataclass(frozen=True)
class ReferenceEvaluationSummary:
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


@dataclass(frozen=True)
class IntervalRecord:
    start_time_s: float
    state: TruthState
    minimum_range_m: float
    maximum_range_m: float
    maximum_abs_velocity_mps: float
    collision_time_s: float | None
    depletion_time_s: float | None
    collision_residual_m: float | None
    depletion_residual_fraction: float | None


@dataclass(frozen=True)
class TraceOutcome:
    final_state: TruthState
    summary: ReferenceEvaluationSummary
    intervals: tuple[IntervalRecord, ...]
    event_order: tuple[str, ...]
    collision_time_s: float | None
    depletion_time_s: float | None
    maximum_abs_collision_residual_m: float
    maximum_abs_depletion_residual_fraction: float
    acceleration_zero_crossings: int
    function_evaluations: int


@dataclass(frozen=True)
class _DensePiece:
    start_s: float
    end_s: float
    solution: Callable[[float], np.ndarray]


def _roots(
    function: Callable[[float], float],
    left: float,
    right: float,
    samples: int = 17,
) -> list[float]:
    if right <= left:
        return []
    grid = np.linspace(left, right, samples)
    values = [float(function(float(time_s))) for time_s in grid]
    roots: list[float] = []
    for start, end, f_start, f_end in zip(
        grid[:-1], grid[1:], values[:-1], values[1:], strict=False
    ):
        if f_start == 0.0:
            roots.append(float(start))
        if f_start * f_end < 0.0:
            roots.append(
                float(
                    brentq(
                        function,
                        float(start),
                        float(end),
                        xtol=5e-15,
                        rtol=4.0 * np.finfo(float).eps,
                    )
                )
            )
    if values[-1] == 0.0:
        roots.append(float(right))
    return sorted(set(roots))


def _piece_extrema(
    pieces: list[_DensePiece],
    disturbance: float,
) -> tuple[float, float, float]:
    range_values: list[float] = []
    velocity_values: list[float] = []
    for piece in pieces:
        velocity_roots = _roots(
            lambda value, dense=piece.solution: float(dense(value)[1]),
            piece.start_s,
            piece.end_s,
        )
        net_acceleration_roots = _roots(
            lambda value, dense=piece.solution: float(dense(value)[2] + disturbance),
            piece.start_s,
            piece.end_s,
        )
        for value in (piece.start_s, piece.end_s, *velocity_roots):
            range_values.append(float(piece.solution(value)[0]))
        for value in (piece.start_s, piece.end_s, *net_acceleration_roots):
            velocity_values.append(abs(float(piece.solution(value)[1])))
    if not pieces:
        raise RuntimeError("reference propagation produced no dense-output pieces")
    return min(range_values), max(range_values), max(velocity_values)


def _dense_collision_touch(
    piece: _DensePiece,
    collision_range_m: float,
) -> float | None:
    dense = piece.solution
    velocity_roots = _roots(
        lambda value: float(dense(value)[1]), piece.start_s, piece.end_s
    )
    points = sorted({piece.start_s, piece.end_s, *velocity_roots})
    previous = points[0]
    previous_range = float(dense(previous)[0])
    if previous_range <= collision_range_m:
        return previous
    for current in points[1:]:
        current_range = float(dense(current)[0])
        if current_range < collision_range_m:
            return float(
                brentq(
                    lambda value: float(dense(value)[0] - collision_range_m),
                    previous,
                    current,
                    xtol=5e-15,
                    rtol=4.0 * np.finfo(float).eps,
                )
            )
        if abs(current_range - collision_range_m) <= 1e-12:
            return current
        previous = current
        previous_range = current_range
    return None


class KinkAwareReference:
    """Adaptive numerical reference independent of the production exact propagator."""

    def __init__(
        self,
        config: PilotConfig,
        rtol: float,
        atol: float,
        max_step_fraction: float,
    ):
        self.config = config
        self.rtol = rtol
        self.atol = atol
        self.max_step_fraction = max_step_fraction

    def _single_piece(
        self,
        state: TruthState,
        command: float,
        effectiveness: float,
        disturbance: float,
        duration: float,
    ) -> ReferencePropagation:
        if duration <= 0.0:
            collision = state.range_m <= self.config.collision_range_m
            depleted = state.propellant <= 0.0
            return ReferencePropagation(
                state=state,
                minimum_range_m=state.range_m,
                maximum_range_m=state.range_m,
                maximum_abs_velocity_mps=abs(state.relative_velocity_mps),
                collision_time_s=state.time_s if collision else None,
                propellant_depleted=depleted,
                depletion_time_s=state.time_s if depleted else None,
                collision_residual_m=(
                    state.range_m - self.config.collision_range_m if collision else None
                ),
                depletion_residual_fraction=state.propellant if depleted else None,
                acceleration_zero_crossings_s=(),
                function_evaluations=0,
            )
        if state.range_m <= self.config.collision_range_m:
            collision_state = TruthState(
                state.time_s,
                self.config.collision_range_m,
                state.relative_velocity_mps,
                max(0.0, state.propellant),
                state.achieved_acceleration_mps2,
            )
            return ReferencePropagation(
                state=collision_state,
                minimum_range_m=self.config.collision_range_m,
                maximum_range_m=self.config.collision_range_m,
                maximum_abs_velocity_mps=abs(state.relative_velocity_mps),
                collision_time_s=state.time_s,
                propellant_depleted=state.propellant <= 0.0,
                depletion_time_s=state.time_s if state.propellant <= 0.0 else None,
                collision_residual_m=state.range_m - self.config.collision_range_m,
                depletion_residual_fraction=state.propellant if state.propellant <= 0.0 else None,
                acceleration_zero_crossings_s=(),
                function_evaluations=0,
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
        bounded_command = max(
            -self.config.max_acceleration_mps2,
            min(self.config.max_acceleration_mps2, command),
        )
        target = effectiveness * bounded_command
        values = np.array(
            [
                state.range_m,
                state.relative_velocity_mps,
                state.achieved_acceleration_mps2,
                state.propellant,
            ],
            dtype=np.float64,
        )
        local_start = 0.0
        pieces: list[_DensePiece] = []
        zero_crossings: list[float] = []
        function_evaluations = 0
        collision_local: float | None = None
        depletion_local: float | None = None
        collision_residual: float | None = None
        depletion_residual: float | None = 0.0 if depleted_at_start else None
        max_step = max(duration * self.max_step_fraction, 1e-12)

        while local_start < duration - 1e-15:
            achieved_start = float(values[2])
            zero_event_armed = achieved_start * target < 0.0
            if achieved_start != 0.0:
                phase_sign = math.copysign(1.0, achieved_start)
            elif target != 0.0:
                phase_sign = math.copysign(1.0, target)
            else:
                phase_sign = 1.0

            def derivative(
                _time_s: float,
                current: np.ndarray,
                phase_sign_value: float = phase_sign,
            ) -> np.ndarray:
                achieved = current[2]
                return np.array(
                    [
                        current[1],
                        achieved + disturbance,
                        (target - achieved) / self.config.actuator_time_constant_s,
                        0.0
                        if depleted_at_start
                        else -self.config.propellant_cost_per_delta_v
                        * phase_sign_value
                        * achieved,
                    ],
                    dtype=np.float64,
                )

            def collision_event(_time_s: float, current: np.ndarray) -> float:
                return float(current[0] - self.config.collision_range_m)

            collision_event.terminal = True  # type: ignore[attr-defined]
            collision_event.direction = -1.0  # type: ignore[attr-defined]

            def depletion_event(_time_s: float, current: np.ndarray) -> float:
                return float(current[3])

            depletion_event.terminal = True  # type: ignore[attr-defined]
            depletion_event.direction = -1.0  # type: ignore[attr-defined]
            events: list[Callable[[float, np.ndarray], float]] = [collision_event]
            event_names = ["collision"]
            if not depleted_at_start:
                events.append(depletion_event)
                event_names.append("depletion")
            if zero_event_armed:

                def acceleration_zero_event(
                    _time_s: float, current: np.ndarray
                ) -> float:
                    return float(current[2])

                acceleration_zero_event.terminal = True  # type: ignore[attr-defined]
                acceleration_zero_event.direction = (  # type: ignore[attr-defined]
                    -1.0 if achieved_start > 0.0 else 1.0
                )
                events.append(acceleration_zero_event)
                event_names.append("acceleration_zero")

            solution = solve_ivp(
                derivative,
                (local_start, duration),
                values,
                method="DOP853",
                rtol=self.rtol,
                atol=self.atol,
                dense_output=True,
                max_step=max_step,
                events=events,
            )
            function_evaluations += int(solution.nfev)
            if not solution.success or solution.sol is None:
                raise RuntimeError(f"kink-aware reference failed: {solution.message}")
            phase_end = float(solution.t[-1])
            dense = solution.sol
            piece = _DensePiece(local_start, phase_end, dense)
            touch_time = _dense_collision_touch(piece, self.config.collision_range_m)
            observed_events = {
                name: float(times[0])
                for name, times in zip(event_names, solution.t_events, strict=True)
                if len(times)
            }
            if touch_time is not None and (
                "collision" not in observed_events
                or touch_time < observed_events["collision"]
            ):
                observed_events["collision"] = touch_time
            terminal_name = None
            terminal_time = phase_end
            if observed_events:
                terminal_name, terminal_time = min(
                    observed_events.items(),
                    key=lambda item: (
                        item[1],
                        {"collision": 0, "depletion": 1, "acceleration_zero": 2}[item[0]],
                    ),
                )
                piece = _DensePiece(local_start, terminal_time, dense)
            pieces.append(piece)
            values = np.asarray(dense(terminal_time), dtype=np.float64)

            if terminal_name == "collision":
                collision_local = terminal_time
                collision_residual = float(
                    values[0] - self.config.collision_range_m
                )
                break
            if terminal_name == "depletion":
                depletion_local = terminal_time
                depletion_residual = float(values[3])
                break
            if terminal_name == "acceleration_zero":
                zero_crossings.append(state.time_s + terminal_time)
                values[2] = 0.0
                local_start = terminal_time
                continue
            local_start = phase_end

        minimum, maximum, maximum_abs_velocity = _piece_extrema(pieces, disturbance)
        terminal_local = (
            collision_local
            if collision_local is not None
            else depletion_local
            if depletion_local is not None
            else duration
        )
        terminal = np.asarray(pieces[-1].solution(terminal_local), dtype=np.float64)
        terminal_state = TruthState(
            time_s=state.time_s + terminal_local,
            range_m=(
                self.config.collision_range_m
                if collision_local is not None
                else float(terminal[0])
            ),
            relative_velocity_mps=float(terminal[1]),
            propellant=max(0.0, float(terminal[3])),
            achieved_acceleration_mps2=float(terminal[2]),
        )
        first = ReferencePropagation(
            state=terminal_state,
            minimum_range_m=minimum,
            maximum_range_m=maximum,
            maximum_abs_velocity_mps=maximum_abs_velocity,
            collision_time_s=(
                state.time_s + collision_local if collision_local is not None else None
            ),
            propellant_depleted=depleted_at_start or depletion_local is not None,
            depletion_time_s=(
                state.time_s
                if depleted_at_start
                else state.time_s + depletion_local
                if depletion_local is not None
                else None
            ),
            collision_residual_m=collision_residual,
            depletion_residual_fraction=depletion_residual,
            acceleration_zero_crossings_s=tuple(zero_crossings),
            function_evaluations=function_evaluations,
        )
        if collision_local is not None or depletion_local is None:
            return first

        depleted = TruthState(
            first.state.time_s,
            first.state.range_m,
            first.state.relative_velocity_mps,
            0.0,
            0.0,
        )
        remaining = duration - depletion_local
        if remaining <= 1e-15:
            return ReferencePropagation(
                state=depleted,
                minimum_range_m=first.minimum_range_m,
                maximum_range_m=first.maximum_range_m,
                maximum_abs_velocity_mps=first.maximum_abs_velocity_mps,
                collision_time_s=None,
                propellant_depleted=True,
                depletion_time_s=first.depletion_time_s,
                collision_residual_m=None,
                depletion_residual_fraction=first.depletion_residual_fraction,
                acceleration_zero_crossings_s=first.acceleration_zero_crossings_s,
                function_evaluations=first.function_evaluations,
            )
        second = self._single_piece(
            depleted,
            0.0,
            effectiveness,
            disturbance,
            remaining,
        )
        return ReferencePropagation(
            state=second.state,
            minimum_range_m=min(first.minimum_range_m, second.minimum_range_m),
            maximum_range_m=max(first.maximum_range_m, second.maximum_range_m),
            maximum_abs_velocity_mps=max(
                first.maximum_abs_velocity_mps, second.maximum_abs_velocity_mps
            ),
            collision_time_s=second.collision_time_s,
            propellant_depleted=True,
            depletion_time_s=first.depletion_time_s,
            collision_residual_m=second.collision_residual_m,
            depletion_residual_fraction=first.depletion_residual_fraction,
            acceleration_zero_crossings_s=(
                *first.acceleration_zero_crossings_s,
                *second.acceleration_zero_crossings_s,
            ),
            function_evaluations=(
                first.function_evaluations + second.function_evaluations
            ),
        )

    def propagate(
        self,
        state: TruthState,
        command: float,
        effectiveness: float,
        disturbance: float,
        duration: float,
    ) -> ReferencePropagation:
        return self._single_piece(
            state, command, effectiveness, disturbance, duration
        )


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


def _reference_stopping_distance(
    state: TruthState, effectiveness: float, config: PilotConfig
) -> float:
    if state.relative_velocity_mps >= 0.0:
        return 0.0
    if state.propellant <= 0.0 or effectiveness <= 0.0:
        return math.inf
    target = effectiveness * config.max_acceleration_mps2
    adverse = -config.process_accel_clip_mps2
    equilibrium = target + adverse
    if equilibrium <= 0.0:
        return math.inf
    tau = config.actuator_time_constant_s
    delta = state.achieved_acceleration_mps2 - target

    def velocity(time_s: float) -> float:
        return (
            state.relative_velocity_mps
            + equilibrium * time_s
            + delta * tau * (1.0 - math.exp(-time_s / tau))
        )

    right = max(1.0, -state.relative_velocity_mps / equilibrium + 4.0 * tau)
    while velocity(right) < 0.0 and right < 10_000.0:
        right *= 2.0
    if velocity(right) < 0.0:
        return math.inf
    stop_time = float(brentq(velocity, 0.0, right, xtol=5e-15, rtol=1e-14))
    required = config.propellant_cost_per_delta_v * _absolute_impulse(
        state.achieved_acceleration_mps2, target, tau, stop_time
    )
    if required > state.propellant + 1e-12:
        return math.inf
    displacement = (
        state.relative_velocity_mps * stop_time
        + 0.5 * equilibrium * stop_time**2
        + delta * tau * (stop_time - tau * (1.0 - math.exp(-stop_time / tau)))
    )
    return max(0.0, -displacement)


def _reference_braking_margin(
    state: TruthState, effectiveness: float, config: PilotConfig
) -> float:
    stopping_distance = _reference_stopping_distance(state, effectiveness, config)
    if math.isinf(stopping_distance):
        return -math.inf
    return state.range_m - config.collision_range_m - stopping_distance


class ReferenceEvaluator:
    """Independent evaluator used only for the numerical reference trace."""

    def __init__(self, config: PilotConfig, state: TruthState, effectiveness: float):
        self.config = config
        self.minimum_range_m = state.range_m
        margin = _reference_braking_margin(state, effectiveness, config)
        self.minimum_margin = margin
        self.braking_unreachable = math.isinf(margin)
        self.previous_margin = margin
        self.previous_margin_time = state.time_s
        self.current_negative_duration = 0.0
        self.maximum_negative_duration = 0.0
        self.collision = state.range_m <= config.collision_range_m
        self.propellant_depleted = state.propellant <= 0.0
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
            return 1.0, left_negative, right_negative
        denominator = abs(left) + abs(right)
        fraction = abs(left) / denominator if denominator else 0.5
        if left_negative:
            return fraction, True, False
        return 1.0 - fraction, False, True

    def observe_margin(self, state: TruthState, effectiveness: float) -> None:
        margin = _reference_braking_margin(state, effectiveness, self.config)
        self.braking_unreachable |= math.isinf(margin)
        self.minimum_margin = min(self.minimum_margin, margin)
        duration = state.time_s - self.previous_margin_time
        fraction, starts_negative, ends_negative = self._negative_fraction(
            self.previous_margin, margin
        )
        negative_duration = fraction * duration
        if starts_negative:
            self.current_negative_duration += negative_duration
        elif ends_negative:
            self.current_negative_duration = negative_duration
        self.maximum_negative_duration = max(
            self.maximum_negative_duration, self.current_negative_duration
        )
        if not ends_negative:
            self.current_negative_duration = 0.0
        self.previous_margin = margin
        self.previous_margin_time = state.time_s

    def observe_interval(
        self, start_state: TruthState, propagation: ReferencePropagation
    ) -> None:
        self.minimum_range_m = min(
            self.minimum_range_m, propagation.minimum_range_m
        )
        self.collision |= propagation.collision_time_s is not None
        self.propellant_depleted |= propagation.propellant_depleted
        final_start = self.config.horizon_s - self.config.goal_dwell_s
        overlap_start = max(start_state.time_s, final_start)
        overlap_end = min(propagation.state.time_s, self.config.horizon_s)
        if overlap_end > overlap_start:
            continuous_goal = (
                propagation.minimum_range_m >= self.config.goal_min_range_m
                and propagation.maximum_range_m <= self.config.goal_max_range_m
                and propagation.maximum_abs_velocity_mps
                <= self.config.goal_max_speed_mps
                and propagation.state.propellant >= self.config.propellant_reserve
            )
            if continuous_goal:
                self.final_window_valid_s += overlap_end - overlap_start
        endpoint_goal = (
            self.config.goal_min_range_m
            <= propagation.state.range_m
            <= self.config.goal_max_range_m
            and abs(propagation.state.relative_velocity_mps)
            <= self.config.goal_max_speed_mps
        )
        if endpoint_goal and self.first_goal_entry_s is None:
            self.first_goal_entry_s = propagation.state.time_s

    def finalize(self, final_state: TruthState) -> ReferenceEvaluationSummary:
        sustained = (
            not self.collision
            and not self.propellant_depleted
            and final_state.propellant >= self.config.propellant_reserve
            and abs(self.final_window_valid_s - self.config.goal_dwell_s) <= 1e-9
        )
        hazard = self.collision or self.maximum_negative_duration + 1e-12 >= 1.0
        return ReferenceEvaluationSummary(
            physical_hazard_observed=hazard,
            collision=self.collision,
            sustained_success=sustained and not hazard,
            propellant_depleted=self.propellant_depleted,
            braking_unreachable=self.braking_unreachable,
            minimum_braking_margin_m=(
                None if math.isinf(self.minimum_margin) else self.minimum_margin
            ),
            minimum_range_m=self.minimum_range_m,
            maximum_contiguous_negative_margin_s=self.maximum_negative_duration,
            first_goal_entry_s=self.first_goal_entry_s,
            goal_dwell_final60_fraction=(
                self.final_window_valid_s / self.config.goal_dwell_s
            ),
        )


def _effectiveness(spec: ScenarioSpec, start_s: float, end_s: float) -> float:
    if spec.fault_subtype != "actuator_degradation":
        return 1.0
    midpoint = 0.5 * (start_s + end_s)
    if spec.fault_onset_s is None or spec.actuator_effectiveness is None:
        return 1.0
    if midpoint >= spec.fault_onset_s and (
        spec.fault_end_s is None or midpoint < spec.fault_end_s
    ):
        return spec.actuator_effectiveness
    return 1.0


def _split_interval(
    start_s: float, end_s: float, spec: ScenarioSpec
) -> list[tuple[float, float]]:
    points = [start_s, end_s]
    if spec.fault_subtype == "actuator_degradation":
        for boundary in (spec.fault_onset_s, spec.fault_end_s):
            if boundary is not None and start_s < boundary < end_s:
                points.append(boundary)
    points.sort()
    return list(zip(points, points[1:], strict=False))


def _commands_for_pattern(
    pattern: str,
    amendment: NumericalAmendmentConfig,
    controller_amendment: AmendmentConfig,
    production: PilotConfig,
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    policy: FrozenPolicy,
    config_hash: str,
) -> tuple[list[tuple[float, float]], str | None]:
    if pattern == "pd_operational":
        source_result, trace = run_pd_episode(
            controller_amendment,
            production,
            spec,
            streams,
            policy,
            amendment.command_period_s,
            amendment.observation_period_s,
            config_hash,
            "fixed_replay_trace_generation",
            collect_command_trace=True,
        )
        if trace is None:
            raise RuntimeError("PD replay command trace was not collected")
        return trace, source_result.failure_class
    count = round(production.horizon_s / amendment.command_period_s)
    commands: list[tuple[float, float]] = []
    for index in range(count):
        time_s = index * amendment.command_period_s
        if pattern == "maximum_closing":
            command = -production.max_acceleration_mps2
        elif pattern == "maximum_separating":
            command = production.max_acceleration_mps2
        elif pattern == "alternating_extrema":
            command = production.max_acceleration_mps2 * (
                1.0 if index % 2 == 0 else -1.0
            )
        else:
            raise ValueError(f"unknown replay pattern: {pattern}")
        commands.append((time_s, command))
    return commands, None


def _event_order(
    collision_time_s: float | None,
    depletion_time_s: float | None,
    simultaneous_tolerance_s: float,
) -> tuple[str, ...]:
    if collision_time_s is None and depletion_time_s is None:
        return ()
    if collision_time_s is None:
        return ("depletion",)
    if depletion_time_s is None:
        return ("collision",)
    if abs(collision_time_s - depletion_time_s) <= simultaneous_tolerance_s:
        return ("collision+depletion",)
    if collision_time_s < depletion_time_s:
        return ("collision", "depletion")
    return ("depletion", "collision")


def _production_summary(summary: Any) -> ReferenceEvaluationSummary:
    return ReferenceEvaluationSummary(
        physical_hazard_observed=summary.physical_hazard_observed,
        collision=summary.collision,
        sustained_success=summary.sustained_success,
        propellant_depleted=summary.propellant_depleted,
        braking_unreachable=summary.braking_unreachable,
        minimum_braking_margin_m=summary.minimum_braking_margin_m,
        minimum_range_m=summary.minimum_range_m,
        maximum_contiguous_negative_margin_s=(
            summary.maximum_contiguous_negative_margin_s
        ),
        first_goal_entry_s=summary.first_goal_entry_s,
        goal_dwell_final60_fraction=summary.goal_dwell_final60_fraction,
    )


def _trace_outcome(
    mode: str,
    amendment: NumericalAmendmentConfig,
    production: PilotConfig,
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    commands: list[tuple[float, float]],
    reference: KinkAwareReference | None,
) -> TraceOutcome:
    state = TruthState(
        0.0,
        spec.initial_range_m,
        spec.initial_velocity_mps,
        spec.initial_propellant,
        0.0,
    )
    if mode == "production_exact":
        evaluator: Any = IndependentEvaluator(production, state, 1.0)
    elif mode in {"reference_fine", "reference_coarse"}:
        evaluator = ReferenceEvaluator(production, state, 1.0)
        if reference is None:
            raise ValueError("reference mode requires a numerical reference")
    else:
        raise ValueError(mode)
    evaluator_stride = round(
        production.evaluator_period_s / production.exogenous_period_s
    )
    command_stride = round(amendment.command_period_s / production.exogenous_period_s)
    command = 0.0
    command_index = 0
    intervals: list[IntervalRecord] = []
    collision_time: float | None = None
    depletion_time: float | None = None
    collision_residuals: list[float] = []
    depletion_residuals: list[float] = []
    zero_crossings = 0
    function_evaluations = 0

    for tick in range(production.n_exogenous_steps):
        if tick % command_stride == 0:
            command_time, command = commands[command_index]
            expected_time = tick * production.exogenous_period_s
            if abs(command_time - expected_time) > 1e-12:
                raise RuntimeError("fixed command trace timestamp drift")
            command_index += 1
        interval_start = tick * production.exogenous_period_s
        interval_end = interval_start + production.exogenous_period_s
        for segment_start, segment_end in _split_interval(
            interval_start, interval_end, spec
        ):
            effectiveness = _effectiveness(spec, segment_start, segment_end)
            start_state = state
            disturbance = float(streams.process_acceleration_mps2[tick])
            if mode == "production_exact":
                propagation: Any = propagate_exact(
                    state,
                    command,
                    effectiveness,
                    disturbance,
                    segment_end - segment_start,
                    production,
                )
            else:
                assert reference is not None
                propagation = reference.propagate(
                    state,
                    command,
                    effectiveness,
                    disturbance,
                    segment_end - segment_start,
                )
                zero_crossings += len(propagation.acceleration_zero_crossings_s)
                function_evaluations += propagation.function_evaluations
            evaluator.observe_interval(start_state, propagation)
            intervals.append(
                IntervalRecord(
                    start_time_s=start_state.time_s,
                    state=propagation.state,
                    minimum_range_m=propagation.minimum_range_m,
                    maximum_range_m=propagation.maximum_range_m,
                    maximum_abs_velocity_mps=propagation.maximum_abs_velocity_mps,
                    collision_time_s=propagation.collision_time_s,
                    depletion_time_s=propagation.depletion_time_s,
                    collision_residual_m=propagation.collision_residual_m,
                    depletion_residual_fraction=(
                        propagation.depletion_residual_fraction
                    ),
                )
            )
            if collision_time is None and propagation.collision_time_s is not None:
                collision_time = propagation.collision_time_s
            if depletion_time is None and propagation.depletion_time_s is not None:
                depletion_time = propagation.depletion_time_s
            if propagation.collision_residual_m is not None:
                collision_residuals.append(propagation.collision_residual_m)
            if propagation.depletion_residual_fraction is not None:
                depletion_residuals.append(
                    propagation.depletion_residual_fraction
                )
            state = propagation.state
            if propagation.collision_time_s is not None:
                break
        if (tick + 1) % evaluator_stride == 0:
            evaluator.observe_margin(
                state, _effectiveness(spec, state.time_s, state.time_s)
            )
        if evaluator.collision:
            break
    summary = evaluator.finalize(state)
    converted = (
        _production_summary(summary)
        if mode == "production_exact"
        else summary
    )
    return TraceOutcome(
        final_state=state,
        summary=converted,
        intervals=tuple(intervals),
        event_order=_event_order(
            collision_time,
            depletion_time,
            amendment.simultaneous_event_tolerance_s,
        ),
        collision_time_s=collision_time,
        depletion_time_s=depletion_time,
        maximum_abs_collision_residual_m=max(
            (abs(value) for value in collision_residuals), default=0.0
        ),
        maximum_abs_depletion_residual_fraction=max(
            (abs(value) for value in depletion_residuals), default=0.0
        ),
        acceleration_zero_crossings=zero_crossings,
        function_evaluations=function_evaluations,
    )


def _optional_error(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0 if left is right else _MISMATCH_ERROR
    return abs(left - right)


def _maximum_interval_error(
    left: TraceOutcome,
    right: TraceOutcome,
    extractor: Callable[[IntervalRecord], float],
) -> float:
    if len(left.intervals) != len(right.intervals):
        return _MISMATCH_ERROR
    return max(
        (
            abs(extractor(first) - extractor(second))
            for first, second in zip(left.intervals, right.intervals, strict=True)
        ),
        default=0.0,
    )


def _maximum_optional_interval_error(
    left: TraceOutcome,
    right: TraceOutcome,
    extractor: Callable[[IntervalRecord], float | None],
) -> float:
    if len(left.intervals) != len(right.intervals):
        return _MISMATCH_ERROR
    return max(
        (
            _optional_error(extractor(first), extractor(second))
            for first, second in zip(left.intervals, right.intervals, strict=True)
        ),
        default=0.0,
    )


def _comparison(
    left: TraceOutcome,
    right: TraceOutcome,
    bounds: NumericalBounds,
    require_raw_residual_bounds: bool,
) -> dict[str, Any]:
    classifications = (
        "collision",
        "physical_hazard_observed",
        "propellant_depleted",
        "sustained_success",
    )
    classification_match = all(
        getattr(left.summary, field) == getattr(right.summary, field)
        for field in classifications
    )
    braking_unreachable_match = (
        left.summary.braking_unreachable == right.summary.braking_unreachable
    )
    event_order_match = left.event_order == right.event_order
    interval_alignment = len(left.intervals) == len(right.intervals)

    errors = {
        "range_m": {
            "boundary_state": _maximum_interval_error(
                left, right, lambda record: record.state.range_m
            ),
            "interval_minimum": _maximum_interval_error(
                left, right, lambda record: record.minimum_range_m
            ),
            "interval_maximum": _maximum_interval_error(
                left, right, lambda record: record.maximum_range_m
            ),
            "trace_minimum": abs(
                left.summary.minimum_range_m - right.summary.minimum_range_m
            ),
            "minimum_braking_margin": _optional_error(
                left.summary.minimum_braking_margin_m,
                right.summary.minimum_braking_margin_m,
            ),
        },
        "velocity_mps": {
            "boundary_state": _maximum_interval_error(
                left, right, lambda record: record.state.relative_velocity_mps
            ),
            "interval_maximum_abs": _maximum_interval_error(
                left, right, lambda record: record.maximum_abs_velocity_mps
            ),
        },
        "achieved_acceleration_mps2": {
            "boundary_state": _maximum_interval_error(
                left,
                right,
                lambda record: record.state.achieved_acceleration_mps2,
            )
        },
        "propellant_fraction": {
            "boundary_state": _maximum_interval_error(
                left, right, lambda record: record.state.propellant
            )
        },
        "event_time_s": {
            "boundary_timestamp": _maximum_interval_error(
                left, right, lambda record: record.state.time_s
            ),
            "collision_time": _optional_error(
                left.collision_time_s, right.collision_time_s
            ),
            "depletion_time": _optional_error(
                left.depletion_time_s, right.depletion_time_s
            ),
            "interval_collision_time": _maximum_optional_interval_error(
                left, right, lambda record: record.collision_time_s
            ),
            "interval_depletion_time": _maximum_optional_interval_error(
                left, right, lambda record: record.depletion_time_s
            ),
            "maximum_contiguous_negative_margin": abs(
                left.summary.maximum_contiguous_negative_margin_s
                - right.summary.maximum_contiguous_negative_margin_s
            ),
            "first_goal_entry": _optional_error(
                left.summary.first_goal_entry_s, right.summary.first_goal_entry_s
            ),
        },
        "dwell_fraction": {
            "goal_dwell_final60": abs(
                left.summary.goal_dwell_final60_fraction
                - right.summary.goal_dwell_final60_fraction
            )
        },
        "collision_residual_m": {
            "maximum_absolute_difference": abs(
                left.maximum_abs_collision_residual_m
                - right.maximum_abs_collision_residual_m
            ),
            "interval_difference": _maximum_optional_interval_error(
                left, right, lambda record: record.collision_residual_m
            ),
        },
        "depletion_residual_fraction": {
            "maximum_absolute_difference": abs(
                left.maximum_abs_depletion_residual_fraction
                - right.maximum_abs_depletion_residual_fraction
            ),
            "interval_difference": _maximum_optional_interval_error(
                left,
                right,
                lambda record: record.depletion_residual_fraction,
            ),
        },
    }
    category_maxima = {
        category: max(values.values(), default=0.0)
        for category, values in errors.items()
    }
    raw_residuals = {
        "left_collision_m": left.maximum_abs_collision_residual_m,
        "right_collision_m": right.maximum_abs_collision_residual_m,
        "left_depletion_fraction": left.maximum_abs_depletion_residual_fraction,
        "right_depletion_fraction": right.maximum_abs_depletion_residual_fraction,
    }
    raw_residuals_passed = bool(
        max(
            raw_residuals["left_collision_m"],
            raw_residuals["right_collision_m"],
        )
        <= bounds.collision_residual_m
        and max(
            raw_residuals["left_depletion_fraction"],
            raw_residuals["right_depletion_fraction"],
        )
        <= bounds.depletion_residual_fraction
    )
    bounds_dict = bounds.to_dict()
    category_passed = {
        category: category_maxima[category] <= bounds_dict[category]
        for category in category_maxima
    }
    maximum_normalized_error_ratio = max(
        (
            category_maxima[category] / bounds_dict[category]
            for category in category_maxima
        ),
        default=0.0,
    )
    passed = bool(
        interval_alignment
        and classification_match
        and braking_unreachable_match
        and event_order_match
        and all(category_passed.values())
        and (raw_residuals_passed or not require_raw_residual_bounds)
    )
    return {
        "interval_records_aligned": interval_alignment,
        "interval_records": len(left.intervals),
        "event_order_match": event_order_match,
        "left_event_order": list(left.event_order),
        "right_event_order": list(right.event_order),
        "classification_match": classification_match,
        "braking_unreachable_match": braking_unreachable_match,
        "left_classifications": {
            field: getattr(left.summary, field) for field in classifications
        },
        "right_classifications": {
            field: getattr(right.summary, field) for field in classifications
        },
        "left_braking_unreachable": left.summary.braking_unreachable,
        "right_braking_unreachable": right.summary.braking_unreachable,
        "component_errors": errors,
        "category_maxima": category_maxima,
        "bounds": bounds_dict,
        "category_passed": category_passed,
        "raw_event_residuals": raw_residuals,
        "raw_event_residuals_passed": raw_residuals_passed,
        "maximum_normalized_error_ratio": maximum_normalized_error_ratio,
        "passed": passed,
    }


def compare_fixed_trace(
    pattern: str,
    amendment: NumericalAmendmentConfig,
    controller_amendment: AmendmentConfig,
    production: PilotConfig,
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    policy: FrozenPolicy,
    config_hash: str,
) -> dict[str, Any]:
    commands, source_failure = _commands_for_pattern(
        pattern,
        amendment,
        controller_amendment,
        production,
        spec,
        streams,
        policy,
        config_hash,
    )
    fine = KinkAwareReference(
        production,
        amendment.reference_fine_rtol,
        amendment.reference_fine_atol,
        amendment.reference_fine_max_step_fraction,
    )
    coarse = KinkAwareReference(
        production,
        amendment.reference_coarse_rtol,
        amendment.reference_coarse_atol,
        amendment.reference_coarse_max_step_fraction,
    )
    production_outcome = _trace_outcome(
        "production_exact",
        amendment,
        production,
        spec,
        streams,
        commands,
        None,
    )
    fine_outcome = _trace_outcome(
        "reference_fine",
        amendment,
        production,
        spec,
        streams,
        commands,
        fine,
    )
    coarse_outcome = _trace_outcome(
        "reference_coarse",
        amendment,
        production,
        spec,
        streams,
        commands,
        coarse,
    )
    production_vs_reference = _comparison(
        production_outcome,
        fine_outcome,
        amendment.acceptance_bounds,
        require_raw_residual_bounds=True,
    )
    convergence_bounds = amendment.acceptance_bounds.scaled(
        amendment.convergence_bound_fraction
    )
    coarse_vs_fine = _comparison(
        coarse_outcome,
        fine_outcome,
        convergence_bounds,
        require_raw_residual_bounds=False,
    )
    coarse_fine_raw_residuals_within_full_bounds = bool(
        max(
            coarse_outcome.maximum_abs_collision_residual_m,
            fine_outcome.maximum_abs_collision_residual_m,
        )
        <= amendment.acceptance_bounds.collision_residual_m
        and max(
            coarse_outcome.maximum_abs_depletion_residual_fraction,
            fine_outcome.maximum_abs_depletion_residual_fraction,
        )
        <= amendment.acceptance_bounds.depletion_residual_fraction
    )
    passed = bool(
        source_failure is None
        and production_vs_reference["passed"]
        and coarse_vs_fine["passed"]
        and coarse_fine_raw_residuals_within_full_bounds
    )
    return {
        "pattern": pattern,
        "root_seed_id": spec.root_seed_id,
        "stratum_id": spec.stratum_id,
        "command_count": len(commands),
        "command_trace_sha256": sha256_bytes(
            json.dumps(commands, separators=(",", ":")).encode()
        ),
        "source_controller_failure": source_failure,
        "production_vs_fine_reference": production_vs_reference,
        "coarse_vs_fine_reference": coarse_vs_fine,
        "coarse_fine_raw_residuals_within_full_bounds": (
            coarse_fine_raw_residuals_within_full_bounds
        ),
        "fine_reference_acceleration_zero_crossings": (
            fine_outcome.acceleration_zero_crossings
        ),
        "coarse_reference_acceleration_zero_crossings": (
            coarse_outcome.acceleration_zero_crossings
        ),
        "fine_reference_function_evaluations": fine_outcome.function_evaluations,
        "coarse_reference_function_evaluations": coarse_outcome.function_evaluations,
        "passed": passed,
    }


def _materialize_case(
    amendment: NumericalAmendmentConfig,
    production: PilotConfig,
    stratum: str,
    replicate: int,
) -> tuple[ScenarioSpec, ExogenousStreams]:
    spec = materialize_scenario_002c(amendment, production, stratum, replicate)
    streams, hashes = materialize_exogenous_002c(
        amendment, production, stratum, replicate
    )
    for name, digest in hashes.items():
        if spec.stream_hashes[name] != digest:
            raise RuntimeError(f"exogenous hash drift for {spec.root_seed_id}/{name}")
    return spec, streams


def run_fixed_command_replay(
    amendment: NumericalAmendmentConfig,
    controller_amendment: AmendmentConfig,
    production: PilotConfig,
    policy: FrozenPolicy,
    config_hash: str,
    output_path: str | Path,
) -> dict[str, Any]:
    started = time.monotonic()
    cases: list[dict[str, Any]] = []
    for stratum in PILOT_STRATA:
        for replicate in range(amendment.replay_seeds_per_stratum):
            spec, streams = _materialize_case(
                amendment, production, stratum, replicate
            )
            for pattern in amendment.replay_command_patterns:
                cases.append(
                    compare_fixed_trace(
                        pattern,
                        amendment,
                        controller_amendment,
                        production,
                        spec,
                        streams,
                        policy,
                        config_hash,
                    )
                )
    if len(cases) != amendment.replay_cases:
        raise RuntimeError("002c replay did not produce the frozen case count")

    comparison_categories = tuple(amendment.acceptance_bounds.to_dict())
    production_maxima = {
        category: max(
            case["production_vs_fine_reference"]["category_maxima"][category]
            for case in cases
        )
        for category in comparison_categories
    }
    convergence_maxima = {
        category: max(
            case["coarse_vs_fine_reference"]["category_maxima"][category]
            for case in cases
        )
        for category in comparison_categories
    }
    payload = {
        "schema_version": amendment.schema_version,
        "method": (
            "24 complete 600 s fixed-command traces; production float64 exact propagation "
            "versus an independent acceleration-zero-event-split SciPy DOP853 reference"
        ),
        "reference": {
            "implementation": "scipy.integrate.solve_ivp/DOP853",
            "propellant_integration": (
                "known-sign smooth phases split at independently localized achieved-acceleration "
                "zero events; no production exact-propagator call"
            ),
            "fine": {
                "rtol": amendment.reference_fine_rtol,
                "atol": amendment.reference_fine_atol,
                "max_step_fraction": amendment.reference_fine_max_step_fraction,
            },
            "coarse": {
                "rtol": amendment.reference_coarse_rtol,
                "atol": amendment.reference_coarse_atol,
                "max_step_fraction": amendment.reference_coarse_max_step_fraction,
            },
            "coarse_fine_bound_fraction": amendment.convergence_bound_fraction,
            "shared_evaluator_for_production_and_reference": False,
            "production_exact_propagator_called_by_reference": False,
        },
        "acceptance_bounds": amendment.acceptance_bounds.to_dict(),
        "convergence_bounds": amendment.acceptance_bounds.scaled(
            amendment.convergence_bound_fraction
        ).to_dict(),
        "cases": cases,
        "case_count": len(cases),
        "production_vs_reference_category_maxima": production_maxima,
        "coarse_vs_fine_category_maxima": convergence_maxima,
        "all_event_orderings_match": all(
            case["production_vs_fine_reference"]["event_order_match"]
            for case in cases
        ),
        "all_classifications_match": all(
            case["production_vs_fine_reference"]["classification_match"]
            for case in cases
        ),
        "all_braking_unreachable_match": all(
            case["production_vs_fine_reference"]["braking_unreachable_match"]
            for case in cases
        ),
        "all_reference_convergence_checks_pass": all(
            case["coarse_vs_fine_reference"]["passed"] for case in cases
        ),
        "elapsed_wall_s": time.monotonic() - started,
        "passed": all(case["passed"] for case in cases),
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return payload
