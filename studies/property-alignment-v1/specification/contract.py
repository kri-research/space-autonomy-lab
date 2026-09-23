"""Executable point and evidence-contract semantics, not a trajectory certifier."""

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from numbers import Real
import json
import math


def finite(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


class Verdict(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNRESOLVED = "unresolved"


class HoldCoverage(StrEnum):
    ALL_ELIGIBLE = "all_eligible"
    NONE_ELIGIBLE = "none_eligible"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class State:
    x: float
    y: float
    vx: float
    vy: float

    def __post_init__(self):
        for key in ("x", "y", "vx", "vy"):
            finite(getattr(self, key), key)


@dataclass(frozen=True)
class Property:
    lower_y: float
    upper_y: float
    outer_width: float
    inner_width: float
    center: tuple[float, float]
    halfwidth: tuple[float, float]
    collision_radius: float
    keep_out_radius: float
    hold_speed: float
    hold_dwell: float
    horizon: float
    command_limit: float

    def __post_init__(self):
        values = [
            self.lower_y,
            self.upper_y,
            self.outer_width,
            self.inner_width,
            *self.center,
            *self.halfwidth,
            self.collision_radius,
            self.keep_out_radius,
            self.hold_speed,
            self.hold_dwell,
            self.horizon,
            self.command_limit,
        ]
        for value in values:
            finite(value, "property parameter")
        if len(self.center) != 2 or len(self.halfwidth) != 2:
            raise ValueError("Planar geometry required")
        if self.lower_y >= self.upper_y or any(v <= 0 for v in values[2:4] + values[6:]):
            raise ValueError("Invalid geometry or positive scale")
        if not self.collision_radius < self.keep_out_radius or self.hold_dwell > self.horizon:
            raise ValueError("Nested exclusion radii and feasible dwell required")
        if max(self.upper_y, self.center[1] + self.halfwidth[1]) >= -self.keep_out_radius:
            raise ValueError("This contract requires a trailing set disjoint from keep-out")

    def classify(self, state: State, phase: str = "approach") -> dict:
        if not isinstance(state, State) or phase not in ("approach", "holding", "abort"):
            raise ValueError("Explicit planar state and supported phase required")
        width = self.outer_width + (state.y - self.lower_y) * (
            self.inner_width - self.outer_width
        ) / (self.upper_y - self.lower_y)
        approach = self.lower_y <= state.y <= self.upper_y and abs(state.x) <= width
        ellipse = (
            math.hypot(
                (state.x - self.center[0]) / self.halfwidth[0],
                (state.y - self.center[1]) / self.halfwidth[1],
            )
            <= 1
        )
        separation = math.hypot(state.x, state.y)
        return {
            "inside_approach": approach,
            "inside_hold_position": ellipse,
            "inside_union": approach or ellipse,
            "collision": separation <= self.collision_radius,
            "keep_out_entry": separation <= self.keep_out_radius,
            "hold_eligible": ellipse and math.hypot(state.vx, state.vy) <= self.hold_speed,
            "phase": phase,
            "recovery_status": "unassessed",
            "scope": "point_only",
        }

    def validate_command(self, command) -> tuple[float, float]:
        if len(command) != 2:
            raise ValueError("Two local acceleration components required")
        u = tuple(finite(v, "command") for v in command)
        if math.hypot(*u) > self.command_limit:
            raise ValueError("Command exceeds norm bound")
        return u


def load_property(path: Path | None = None) -> Property:
    path = path or Path(__file__).with_name("property_contract.json")
    doc = json.loads(path.read_text())
    if doc["schema"] != "sal-property-contract/1.0":
        raise ValueError("Unsupported contract")
    expected_units = {
        "position_units": "m",
        "velocity_units": "m/s",
        "acceleration_units": "m/s^2",
        "time_units": "s",
    }
    if any(doc["frame"].get(k) != v for k, v in expected_units.items()):
        raise ValueError("Unsupported units")
    if doc["frame"]["axes"] != ["radial_outward", "prograde_along_track"]:
        raise ValueError("Unsupported axis convention")
    if doc.get("phase_position_sets") != dict.fromkeys(("approach", "holding", "abort"), "union"):
        raise ValueError("Unsupported phase-dependent position semantics")
    if (
        doc.get("abort_relaxes_union") is not False
        or doc.get("abort_counts_as_nominal_completion") is not False
    ):
        raise ValueError("Abort may not waive containment or count as nominal completion")
    g = doc["geometry"]
    if doc["frame"]["state_order"] != ["x_m", "y_m", "vx_mps", "vy_mps"]:
        raise ValueError("Unsupported coordinate order")
    return Property(
        *g["approach_y_bounds_m"],
        *g["approach_radial_halfwidths_m"],
        tuple(g["hold_center_m"]),
        tuple(g["hold_halfwidths_m"]),
        g["collision_radius_m"],
        g["keep_out_radius_m"],
        g["hold_max_speed_mps"],
        g["hold_required_dwell_s"],
        doc["time"]["episode_horizon_s"],
        doc["control"]["command_norm_limit_mps2"],
    )


@dataclass(frozen=True)
class Information:
    measured_at: float
    received_at: float
    estimate: State
    error_bounds: tuple[float, float, float, float] | None
    bound_kind: str

    def __post_init__(self):
        if not isinstance(self.estimate, State):
            raise ValueError("Invalid estimate")
        tm, tr = finite(self.measured_at, "measurement time"), finite(self.received_at, "receipt")
        if tm < 0 or tr < tm:
            raise ValueError("Invalid packet chronology")
        if self.bound_kind not in ("ideal", "deterministic_interval", "covariance_only"):
            raise ValueError("Unknown uncertainty semantics")
        if self.bound_kind == "covariance_only":
            if self.error_bounds is not None:
                raise ValueError("Covariance is not an interval bound")
        else:
            if self.error_bounds is None or len(self.error_bounds) != 4:
                raise ValueError("Four error bounds required")
            if any(finite(v, "error bound") < 0 for v in self.error_bounds):
                raise ValueError("Negative error bound")
            if self.bound_kind == "ideal" and any(self.error_bounds):
                raise ValueError("Ideal information requires zero error bounds")

    def timing(self, decision: float, applied: float, max_age: float, max_delay: float) -> dict:
        for x in (decision, applied, max_age, max_delay):
            finite(x, "timing")
        if min(max_age, max_delay) < 0 or decision < self.received_at or applied < decision:
            raise ValueError("Invalid decision/application chronology")
        age, delay = decision - self.measured_at, applied - decision
        return {
            "information_age_s": age,
            "intervention_delay_s": delay,
            "within_declared_timing": age <= max_age and delay <= max_delay,
            "has_deterministic_measurement_bound": self.bound_kind != "covariance_only",
            "current_state_enclosure_produced": False,
        }


@dataclass(frozen=True)
class IntervalEvidence:
    """Input interface for Task 03; verdicts must cover the entire closed interval."""

    start: float
    end: float
    containment: Verdict
    collision_free: Verdict
    keep_out_free: Verdict
    hold: HoldCoverage
    evidence_kind: str = "continuous_interval"

    def __post_init__(self):
        if finite(self.start, "start") < 0 or finite(self.end, "end") <= self.start:
            raise ValueError("Positive interval duration required")
        for v in (self.containment, self.collision_free, self.keep_out_free):
            if not isinstance(v, Verdict):
                raise ValueError("Explicit three-valued verdict required")
        if not isinstance(self.hold, HoldCoverage):
            raise ValueError("Explicit all/none/unresolved hold coverage required")
        if self.evidence_kind not in ("continuous_interval", "samples_only"):
            raise ValueError("Unknown evidence kind")
        if self.collision_free == Verdict.VIOLATED and self.keep_out_free == Verdict.SATISFIED:
            raise ValueError("Collision contradicts keep-out freedom")
        if self.containment == Verdict.SATISFIED and self.keep_out_free == Verdict.VIOLATED:
            raise ValueError("Union containment contradicts keep-out entry")
        if self.hold == HoldCoverage.ALL_ELIGIBLE and self.containment == Verdict.VIOLATED:
            raise ValueError("Entire-interval holding contradicts union violation")


def conjunction(values) -> Verdict:
    values = tuple(values)
    if any(not isinstance(v, Verdict) for v in values):
        raise ValueError("Unknown three-valued status")
    if Verdict.VIOLATED in values:
        return Verdict.VIOLATED
    if Verdict.UNRESOLVED in values:
        return Verdict.UNRESOLVED
    return Verdict.SATISFIED


def summarize_intervals(prop: Property, intervals: list[IntervalEvidence], aborted=False) -> dict:
    """Conditional temporal reduction only; this function cannot certify its inputs."""
    if type(aborted) is not bool or not intervals:
        raise ValueError("Complete evidence required")
    previous = 0.0
    certain_run = possible_run = longest_certain = longest_possible = Fraction(0)
    for e in intervals:
        if e.evidence_kind != "continuous_interval":
            raise ValueError("Sample-only evidence cannot certify continuous containment or dwell")
        if e.start != previous or e.end > prop.horizon:
            raise ValueError("Evidence must cover [0,T] exactly without gaps or overlaps")
        duration = Fraction(e.end) - Fraction(e.start)
        certain_run = certain_run + duration if e.hold == HoldCoverage.ALL_ELIGIBLE else Fraction(0)
        possible_run = (
            possible_run + duration if e.hold != HoldCoverage.NONE_ELIGIBLE else Fraction(0)
        )
        longest_certain = max(longest_certain, certain_run)
        longest_possible = max(longest_possible, possible_run)
        previous = e.end
    if previous != prop.horizon:
        raise ValueError("Incomplete temporal coverage")
    hold = (
        Verdict.SATISFIED
        if longest_certain >= prop.hold_dwell
        else Verdict.VIOLATED
        if longest_possible < prop.hold_dwell
        else Verdict.UNRESOLVED
    )
    result = {
        k: conjunction([getattr(e, k) for e in intervals])
        for k in ("containment", "collision_free", "keep_out_free")
    }
    result.update(
        hold_acquired=hold,
        guaranteed_dwell_s=float(longest_certain),
        possible_dwell_upper_s=float(longest_possible),
        aborted=aborted,
        nominal_goal=Verdict.VIOLATED if aborted else conjunction([hold, *result.values()]),
        conditional_on_supplied_interval_evidence=True,
    )
    return result


@dataclass(frozen=True)
class ExecutionBounds:
    """Declared deterministic execution bounds; values require experimental justification."""

    effectiveness_min: float
    effectiveness_max: float
    disturbance_norm: float
    maximum_information_age: float
    maximum_intervention_delay: float

    def __post_init__(self):
        for value in (
            self.effectiveness_min,
            self.effectiveness_max,
            self.disturbance_norm,
            self.maximum_information_age,
            self.maximum_intervention_delay,
        ):
            finite(value, "execution bound")
        if not 0 <= self.effectiveness_min <= self.effectiveness_max <= 1:
            raise ValueError("Effectiveness interval must lie in [0,1]")
        if (
            min(
                self.disturbance_norm, self.maximum_information_age, self.maximum_intervention_delay
            )
            < 0
        ):
            raise ValueError("Nonnegative disturbance and timing bounds required")

    def realize(self, prop: Property, held_command, effectiveness, disturbance):
        command = prop.validate_command(held_command)
        eta = finite(effectiveness, "effectiveness")
        if not self.effectiveness_min <= eta <= self.effectiveness_max:
            raise ValueError("Effectiveness assumption violated")
        if len(disturbance) != 2:
            raise ValueError("Two disturbance components required")
        w = tuple(finite(x, "disturbance") for x in disturbance)
        if math.hypot(*w) > self.disturbance_norm:
            raise ValueError("Disturbance assumption violated")
        return tuple(eta * u + d for u, d in zip(command, w, strict=True))


@dataclass(frozen=True)
class HeldCommand:
    start: float
    end: float
    acceleration: tuple[float, float]

    def __post_init__(self):
        if finite(self.start, "start") < 0 or finite(self.end, "end") <= self.start:
            raise ValueError("Positive held-command interval required")


def validate_pending_commands(
    prop: Property, commands: list[HeldCommand], start: float, end: float
) -> None:
    """Require explicit command history through application time; never impute zero thrust."""
    if finite(start, "start") < 0 or finite(end, "end") < start:
        raise ValueError("Invalid propagation interval")
    cursor = start
    for segment in commands:
        if not isinstance(segment, HeldCommand) or segment.start != cursor or segment.end > end:
            raise ValueError("Pending command history has a gap, overlap or wrong extent")
        prop.validate_command(segment.acceleration)
        cursor = segment.end
    if cursor != end:
        raise ValueError("Pending command history is incomplete")
