from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize_scalar

from .config import Experiment004Config
from .dynamics import propagate_exact

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class SegmentGeometry:
    duration_s: float
    minimum_separation_m: float
    minimum_separation_time_s: float
    collision: bool
    keep_out_entry: bool
    maximum_corridor_excess_m: float
    maximum_corridor_excess_time_s: float
    corridor_departure: bool


@dataclass(frozen=True)
class HoldSegmentGeometry:
    maximum_position_ellipse_excess: float
    maximum_speed_excess_mps: float
    entirely_inside: bool


class HCWSegment:
    """One exact constant-command HCW arc, never an endpoint chord."""

    def __init__(
        self,
        start_state: FloatArray,
        acceleration_mps2: FloatArray,
        mean_motion_rad_s: float,
        duration_s: float,
        *,
        maximum_duration_s: float,
    ) -> None:
        state = np.asarray(start_state, dtype=np.float64)
        command = np.asarray(acceleration_mps2, dtype=np.float64)
        values = (mean_motion_rad_s, duration_s, maximum_duration_s)
        if state.shape != (4,) or not np.all(np.isfinite(state)):
            raise ValueError("segment start state must be a finite four-vector")
        if command.shape != (2,) or not np.all(np.isfinite(command)):
            raise ValueError("segment command must be a finite two-vector")
        if not all(np.isfinite(value) and value > 0.0 for value in values):
            raise ValueError("segment timing and mean motion must be finite and positive")
        if duration_s > maximum_duration_s + 1e-12:
            raise ValueError("segment must be split at each frozen event interval")
        self.start_state = np.array(state, copy=True)
        self.acceleration_mps2 = np.array(command, copy=True)
        self.mean_motion_rad_s = float(mean_motion_rad_s)
        self.duration_s = float(duration_s)

    def state_at(self, elapsed_s: float) -> FloatArray:
        if not np.isfinite(elapsed_s) or not -1e-12 <= elapsed_s <= self.duration_s + 1e-12:
            raise ValueError("elapsed time lies outside the segment")
        clipped = min(self.duration_s, max(0.0, float(elapsed_s)))
        return propagate_exact(
            self.start_state,
            self.acceleration_mps2,
            self.mean_motion_rad_s,
            clipped,
        )


def _bounded_extreme(
    function: Callable[[float], float],
    duration_s: float,
    *,
    maximize: bool,
    nodes: int = 65,
) -> tuple[float, float]:
    """Find a deterministic segment extreme using bracketed local refinements.

    The foundation restricts calls to at most one second. Sixty-five brackets are
    therefore extremely fine relative to the 92.6-minute reference orbit. A dense
    independent comparison is part of fail-closed validation.
    """

    times = np.linspace(0.0, duration_s, nodes, dtype=np.float64)
    values = np.array([function(float(time_s)) for time_s in times], dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ArithmeticError("geometry objective produced non-finite values")
    sign = -1.0 if maximize else 1.0
    candidates = [(float(values[0]), 0.0), (float(values[-1]), duration_s)]
    transformed = sign * values
    for index in range(1, nodes - 1):
        local_minimum = (
            transformed[index] <= transformed[index - 1]
            and transformed[index] <= transformed[index + 1]
        )
        if local_minimum:
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


def corridor_halfwidth_m(y_alongtrack_m: float, config: Experiment004Config) -> float:
    lower_y, upper_y = config.approach_y_bounds_m
    outer_width, inner_width = config.approach_radial_halfwidth_m
    if not lower_y <= y_alongtrack_m <= upper_y:
        raise ValueError("along-track position is outside the frozen approach corridor")
    fraction = (y_alongtrack_m - lower_y) / (upper_y - lower_y)
    return float(outer_width + fraction * (inner_width - outer_width))


def evaluate_segment(
    segment: HCWSegment,
    config: Experiment004Config,
    *,
    boundary_tolerance_m: float = 1e-9,
) -> SegmentGeometry:
    if not np.isfinite(boundary_tolerance_m) or boundary_tolerance_m < 0.0:
        raise ValueError("boundary tolerance must be finite and non-negative")

    def separation_squared(time_s: float) -> float:
        position = segment.state_at(time_s)[:2]
        return float(position @ position)

    minimum_squared, minimum_time = _bounded_extreme(
        separation_squared,
        segment.duration_s,
        maximize=False,
    )
    minimum_separation = float(np.sqrt(max(0.0, minimum_squared)))

    lower_y, upper_y = config.approach_y_bounds_m

    def corridor_excess(time_s: float) -> float:
        state = segment.state_at(time_s)
        x_radial, y_alongtrack = float(state[0]), float(state[1])
        if not lower_y <= y_alongtrack <= upper_y:
            return -max(config.approach_radial_halfwidth_m)
        return abs(x_radial) - corridor_halfwidth_m(y_alongtrack, config)

    maximum_excess, maximum_excess_time = _bounded_extreme(
        corridor_excess,
        segment.duration_s,
        maximize=True,
    )
    return SegmentGeometry(
        duration_s=segment.duration_s,
        minimum_separation_m=minimum_separation,
        minimum_separation_time_s=minimum_time,
        collision=minimum_separation <= config.hard_body_radius_m + boundary_tolerance_m,
        keep_out_entry=minimum_separation <= config.keep_out_radius_m + boundary_tolerance_m,
        maximum_corridor_excess_m=maximum_excess,
        maximum_corridor_excess_time_s=maximum_excess_time,
        corridor_departure=maximum_excess > boundary_tolerance_m,
    )


def in_hold_region(state: FloatArray, config: Experiment004Config) -> bool:
    vector = np.asarray(state, dtype=np.float64)
    if vector.shape != (4,) or not np.all(np.isfinite(vector)):
        raise ValueError("hold classification requires a finite four-vector")
    center = np.asarray(config.hold_center_m, dtype=np.float64)
    halfwidth = np.asarray(config.hold_position_halfwidth_m, dtype=np.float64)
    normalized_position = (vector[:2] - center) / halfwidth
    return bool(
        normalized_position @ normalized_position <= 1.0
        and np.linalg.norm(vector[2:]) <= config.hold_max_speed_mps
    )


def evaluate_hold_segment(
    segment: HCWSegment,
    config: Experiment004Config,
    *,
    boundary_tolerance: float = 1e-12,
) -> HoldSegmentGeometry:
    center = np.asarray(config.hold_center_m, dtype=np.float64)
    halfwidth = np.asarray(config.hold_position_halfwidth_m, dtype=np.float64)

    def position_excess(time_s: float) -> float:
        normalized = (segment.state_at(time_s)[:2] - center) / halfwidth
        return float(normalized @ normalized - 1.0)

    def speed_excess(time_s: float) -> float:
        return float(
            np.linalg.norm(segment.state_at(time_s)[2:]) - config.hold_max_speed_mps
        )

    maximum_position, _ = _bounded_extreme(
        position_excess,
        segment.duration_s,
        maximize=True,
    )
    maximum_speed, _ = _bounded_extreme(
        speed_excess,
        segment.duration_s,
        maximize=True,
    )
    return HoldSegmentGeometry(
        maximum_position_ellipse_excess=maximum_position,
        maximum_speed_excess_mps=maximum_speed,
        entirely_inside=bool(
            maximum_position <= boundary_tolerance
            and maximum_speed <= boundary_tolerance
        ),
    )
