from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize_scalar

from .config import Experiment005Config
from .dynamics import pair_to_relative, propagate_fixed

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class TruthSegmentGeometry:
    duration_s: float
    minimum_separation_m: float
    minimum_separation_time_s: float
    collision: bool
    keep_out_entry: bool
    maximum_admissible_position_excess_m: float
    maximum_admissible_position_excess_time_s: float
    corridor_departure: bool
    maximum_abs_crosstrack_m: float


@dataclass(frozen=True)
class TruthHoldGeometry:
    maximum_position_ellipse_excess: float
    maximum_speed_excess_mps: float
    entirely_inside: bool


@dataclass(frozen=True)
class TruthPhysicalSummary:
    collision: bool
    unauthorized_keep_out_entry: bool
    corridor_departure: bool
    minimum_separation_m: float
    maximum_admissible_position_excess_m: float
    maximum_abs_crosstrack_m: float


class NonlinearTruthSegment:
    """One nonlinear chief/deputy inertial arc under a held LVLH command."""

    def __init__(
        self,
        start_pair_state: FloatArray,
        command_lvlh_mps2: FloatArray,
        config: Experiment005Config,
        duration_s: float,
    ) -> None:
        state = np.asarray(start_pair_state, dtype=np.float64)
        command = np.asarray(command_lvlh_mps2, dtype=np.float64)
        if state.shape != (12,) or not np.all(np.isfinite(state)):
            raise ValueError("truth segment start must be a finite 12-vector")
        if command.shape != (3,) or not np.all(np.isfinite(command)):
            raise ValueError("truth segment command must be a finite three-vector")
        if not np.isfinite(duration_s) or duration_s <= 0.0:
            raise ValueError("truth segment duration must be finite and positive")
        if duration_s > config.event_interval_max_s + 1e-12:
            raise ValueError("truth segment must be split at the frozen event interval")
        if np.linalg.norm(command) > config.max_acceleration_mps2 + 1e-12:
            raise ValueError("truth segment command exceeds the transferred command bound")
        self.start_pair_state = np.array(state, copy=True)
        self.command_lvlh_mps2 = np.array(command, copy=True)
        self.config = config
        self.duration_s = float(duration_s)

    def state_at(self, elapsed_s: float) -> FloatArray:
        if not np.isfinite(elapsed_s) or not -1e-12 <= elapsed_s <= self.duration_s + 1e-12:
            raise ValueError("elapsed time lies outside the truth segment")
        elapsed = min(self.duration_s, max(0.0, float(elapsed_s)))
        return propagate_fixed(
            self.start_pair_state,
            self.command_lvlh_mps2,
            self.config.gravitational_parameter_m3_s2,
            elapsed,
            self.config.production_max_step_s,
        )

    def relative_state_at(self, elapsed_s: float) -> FloatArray:
        return pair_to_relative(self.state_at(elapsed_s))


class IndependentTruthEvaluator:
    """Offline physical evaluator using only nonlinear inertial truth arcs.

    It has no controller, estimator, fault-label, or monitor dependency. The admissible
    position set is the union of the closed E004 approach corridor and closed hold ellipse.
    This prospective union fixes the historical corridor oracle's out-of-range false-safe
    behavior without changing historical files or results.
    """

    def __init__(self, config: Experiment005Config) -> None:
        self.config = config
        self.collision = False
        self.keep_out_entry = False
        self.corridor_departure = False
        self.minimum_separation_m = np.inf
        self.maximum_admissible_position_excess_m = -np.inf
        self.maximum_abs_crosstrack_m = 0.0

    def observe(self, segment: NonlinearTruthSegment) -> TruthSegmentGeometry:
        result = evaluate_truth_segment(segment, self.config)
        self.collision = self.collision or result.collision
        self.keep_out_entry = self.keep_out_entry or result.keep_out_entry
        self.corridor_departure = self.corridor_departure or result.corridor_departure
        self.minimum_separation_m = min(
            self.minimum_separation_m, result.minimum_separation_m
        )
        self.maximum_admissible_position_excess_m = max(
            self.maximum_admissible_position_excess_m,
            result.maximum_admissible_position_excess_m,
        )
        self.maximum_abs_crosstrack_m = max(
            self.maximum_abs_crosstrack_m, result.maximum_abs_crosstrack_m
        )
        return result

    def finalize(self) -> TruthPhysicalSummary:
        return TruthPhysicalSummary(
            collision=self.collision,
            unauthorized_keep_out_entry=self.keep_out_entry,
            corridor_departure=self.corridor_departure,
            minimum_separation_m=float(self.minimum_separation_m),
            maximum_admissible_position_excess_m=float(
                self.maximum_admissible_position_excess_m
            ),
            maximum_abs_crosstrack_m=float(self.maximum_abs_crosstrack_m),
        )


def _bounded_extreme(
    function: Callable[[float], float],
    duration_s: float,
    *,
    maximize: bool,
    nodes: int = 65,
) -> tuple[float, float]:
    times = np.linspace(0.0, duration_s, nodes, dtype=np.float64)
    values = np.array([function(float(time_s)) for time_s in times], dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ArithmeticError("truth-geometry objective became non-finite")
    sign = -1.0 if maximize else 1.0
    transformed = sign * values
    candidates = [(float(values[0]), 0.0), (float(values[-1]), duration_s)]
    for index in range(1, nodes - 1):
        if (
            transformed[index] <= transformed[index - 1]
            and transformed[index] <= transformed[index + 1]
        ):
            result = minimize_scalar(
                lambda time_s: sign * function(float(time_s)),
                bounds=(float(times[index - 1]), float(times[index + 1])),
                method="bounded",
                options={"xatol": 1e-13, "maxiter": 200},
            )
            if result.success and np.isfinite(result.fun):
                time_s = float(result.x)
                candidates.append((float(function(time_s)), time_s))
    selector = max if maximize else min
    return selector(candidates, key=lambda item: item[0])


def corridor_halfwidth_m(y_alongtrack_m: float, config: Experiment005Config) -> float:
    lower_y, upper_y = config.approach_y_bounds_m
    outer_width, inner_width = config.approach_radial_halfwidth_m
    if not lower_y <= y_alongtrack_m <= upper_y:
        raise ValueError("along-track position lies outside the closed approach corridor")
    fraction = (y_alongtrack_m - lower_y) / (upper_y - lower_y)
    return float(outer_width + fraction * (inner_width - outer_width))


def approach_corridor_excess_m(
    x_radial_m: float,
    y_alongtrack_m: float,
    config: Experiment005Config,
) -> float:
    """Signed excess for the closed approach set; positive means outside."""

    lower_y, upper_y = config.approach_y_bounds_m
    clipped_y = min(upper_y, max(lower_y, y_alongtrack_m))
    radial_excess = abs(x_radial_m) - corridor_halfwidth_m(clipped_y, config)
    return float(max(lower_y - y_alongtrack_m, y_alongtrack_m - upper_y, radial_excess))


def hold_position_excess_m(
    x_radial_m: float,
    y_alongtrack_m: float,
    config: Experiment005Config,
) -> float:
    center = np.asarray(config.hold_center_m, dtype=np.float64)
    halfwidth = np.asarray(config.hold_position_halfwidth_m, dtype=np.float64)
    normalized = (np.array([x_radial_m, y_alongtrack_m]) - center) / halfwidth
    return float((np.linalg.norm(normalized) - 1.0) * np.min(halfwidth))


def admissible_position_excess_m(relative_state: FloatArray, config: Experiment005Config) -> float:
    relative = np.asarray(relative_state, dtype=np.float64)
    if relative.shape != (6,) or not np.all(np.isfinite(relative)):
        raise ValueError("admissible-position check requires a finite six-vector")
    approach = approach_corridor_excess_m(float(relative[0]), float(relative[1]), config)
    hold = hold_position_excess_m(float(relative[0]), float(relative[1]), config)
    return min(approach, hold)


def evaluate_truth_segment(
    segment: NonlinearTruthSegment,
    config: Experiment005Config,
    *,
    boundary_tolerance_m: float = 1e-9,
) -> TruthSegmentGeometry:
    if not np.isfinite(boundary_tolerance_m) or boundary_tolerance_m < 0.0:
        raise ValueError("boundary tolerance must be finite and non-negative")

    def separation_squared(time_s: float) -> float:
        position = segment.relative_state_at(time_s)[:3]
        return float(position @ position)

    minimum_squared, minimum_time = _bounded_extreme(
        separation_squared, segment.duration_s, maximize=False
    )
    minimum_separation = float(np.sqrt(max(0.0, minimum_squared)))

    def position_excess(time_s: float) -> float:
        return admissible_position_excess_m(segment.relative_state_at(time_s), config)

    maximum_excess, maximum_excess_time = _bounded_extreme(
        position_excess, segment.duration_s, maximize=True
    )

    def abs_crosstrack(time_s: float) -> float:
        return abs(float(segment.relative_state_at(time_s)[2]))

    maximum_crosstrack, _ = _bounded_extreme(
        abs_crosstrack, segment.duration_s, maximize=True
    )
    return TruthSegmentGeometry(
        duration_s=segment.duration_s,
        minimum_separation_m=minimum_separation,
        minimum_separation_time_s=minimum_time,
        collision=minimum_separation <= config.hard_body_radius_m + boundary_tolerance_m,
        keep_out_entry=minimum_separation <= config.keep_out_radius_m + boundary_tolerance_m,
        maximum_admissible_position_excess_m=maximum_excess,
        maximum_admissible_position_excess_time_s=maximum_excess_time,
        corridor_departure=maximum_excess > boundary_tolerance_m,
        maximum_abs_crosstrack_m=maximum_crosstrack,
    )


def evaluate_truth_hold_segment(
    segment: NonlinearTruthSegment,
    config: Experiment005Config,
    *,
    boundary_tolerance: float = 1e-12,
) -> TruthHoldGeometry:
    center = np.asarray(config.hold_center_m, dtype=np.float64)
    halfwidth = np.asarray(config.hold_position_halfwidth_m, dtype=np.float64)

    def position_excess(time_s: float) -> float:
        relative = segment.relative_state_at(time_s)
        normalized = (relative[:2] - center) / halfwidth
        return float(normalized @ normalized - 1.0)

    def speed_excess(time_s: float) -> float:
        relative = segment.relative_state_at(time_s)
        return float(np.linalg.norm(relative[3:]) - config.hold_max_speed_mps)

    maximum_position, _ = _bounded_extreme(
        position_excess, segment.duration_s, maximize=True
    )
    maximum_speed, _ = _bounded_extreme(speed_excess, segment.duration_s, maximize=True)
    return TruthHoldGeometry(
        maximum_position_ellipse_excess=maximum_position,
        maximum_speed_excess_mps=maximum_speed,
        entirely_inside=bool(
            maximum_position <= boundary_tolerance and maximum_speed <= boundary_tolerance
        ),
    )
