from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Experiment004Config
from .geometry import (
    HCWSegment,
    SegmentGeometry,
    evaluate_hold_segment,
    evaluate_segment,
)


@dataclass(frozen=True)
class PhysicalGeometrySummary:
    collision: bool
    unauthorized_keep_out_entry: bool
    corridor_departure: bool
    minimum_separation_m: float
    maximum_corridor_excess_m: float


@dataclass(frozen=True)
class MissionSummary:
    hold_acquired: bool
    maximum_contiguous_hold_dwell_s: float
    hold_lost_after_acquisition: bool
    safe_incomplete: bool


@dataclass(frozen=True)
class TechnicalStatus:
    primary_estimator_fault: bool = False
    monitor_estimator_fault: bool = False
    monitor_logic_fault: bool = False
    shared_cause_fault: bool = False
    controller_fault: bool = False
    invalid_action: bool = False
    numerical_failure: bool = False

    @property
    def any_fault(self) -> bool:
        return any(
            (
                self.primary_estimator_fault,
                self.monitor_estimator_fault,
                self.monitor_logic_fault,
                self.shared_cause_fault,
                self.controller_fault,
                self.invalid_action,
                self.numerical_failure,
            )
        )


@dataclass(frozen=True)
class EvaluationSummary:
    physical: PhysicalGeometrySummary
    mission: MissionSummary
    technical: TechnicalStatus


class IndependentPlanarEvaluator:
    """Offline geometry and mission evaluator with no controller or filter imports."""

    def __init__(self, config: Experiment004Config) -> None:
        self.config = config
        self.collision = False
        self.keep_out_entry = False
        self.corridor_departure = False
        self.minimum_separation_m = np.inf
        self.maximum_corridor_excess_m = -np.inf
        self.current_hold_dwell_s = 0.0
        self.maximum_hold_dwell_s = 0.0
        self.hold_acquired = False
        self.hold_lost_after_acquisition = False

    def observe(self, segment: HCWSegment) -> SegmentGeometry:
        geometry = evaluate_segment(segment, self.config)
        hold = evaluate_hold_segment(segment, self.config)
        self.collision = self.collision or geometry.collision
        self.keep_out_entry = self.keep_out_entry or geometry.keep_out_entry
        self.corridor_departure = self.corridor_departure or geometry.corridor_departure
        self.minimum_separation_m = min(
            self.minimum_separation_m,
            geometry.minimum_separation_m,
        )
        self.maximum_corridor_excess_m = max(
            self.maximum_corridor_excess_m,
            geometry.maximum_corridor_excess_m,
        )
        if hold.entirely_inside:
            self.current_hold_dwell_s += segment.duration_s
            self.maximum_hold_dwell_s = max(
                self.maximum_hold_dwell_s,
                self.current_hold_dwell_s,
            )
            if self.current_hold_dwell_s >= self.config.hold_required_dwell_s - 1e-12:
                self.hold_acquired = True
        else:
            if self.hold_acquired:
                self.hold_lost_after_acquisition = True
            self.current_hold_dwell_s = 0.0
        return geometry

    def finalize(self, technical: TechnicalStatus | None = None) -> EvaluationSummary:
        status = technical or TechnicalStatus()
        physical = PhysicalGeometrySummary(
            collision=self.collision,
            unauthorized_keep_out_entry=self.keep_out_entry,
            corridor_departure=self.corridor_departure,
            minimum_separation_m=float(self.minimum_separation_m),
            maximum_corridor_excess_m=float(self.maximum_corridor_excess_m),
        )
        mission = MissionSummary(
            hold_acquired=self.hold_acquired,
            maximum_contiguous_hold_dwell_s=self.maximum_hold_dwell_s,
            hold_lost_after_acquisition=self.hold_lost_after_acquisition,
            safe_incomplete=bool(
                not self.collision
                and not self.keep_out_entry
                and not self.hold_acquired
                and not status.any_fault
            ),
        )
        return EvaluationSummary(physical, mission, status)
