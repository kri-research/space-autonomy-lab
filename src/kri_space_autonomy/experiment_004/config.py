from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

EXPECTED_BASE_COMMIT = "bef9bb4d34efd23767e3f247de11ff58ffba3876"
EXPECTED_BRANCH = "experiment-004-hcw-foundation"
STATE_ORDER = (
    "x_radial_m",
    "y_alongtrack_m",
    "vx_radial_mps",
    "vy_alongtrack_mps",
)
ACTION_ORDER = ("ax_radial_mps2", "ay_alongtrack_mps2")
MEASUREMENT_ORDER = STATE_ORDER
STATE_UNITS = ("m", "m", "m/s", "m/s")
ACTION_UNITS = ("m/s^2", "m/s^2")
MEASUREMENT_COVARIANCE_UNITS = (
    ("m^2", "m^2", "m^2/s", "m^2/s"),
    ("m^2", "m^2", "m^2/s", "m^2/s"),
    ("m^2/s", "m^2/s", "m^2/s^2", "m^2/s^2"),
    ("m^2/s", "m^2/s", "m^2/s^2", "m^2/s^2"),
)


@dataclass(frozen=True)
class Experiment004Config:
    schema_version: str
    parent_commit: str
    coordinate_frame: str
    x_axis_convention: str
    y_axis_convention: str
    state_order: tuple[str, ...]
    action_order: tuple[str, ...]
    measurement_order: tuple[str, ...]
    state_units: tuple[str, ...]
    action_units: tuple[str, ...]
    central_body: str
    gravitational_parameter_m3_s2: float
    reference_radius_m: float
    reference_altitude_above_equatorial_radius_m: float
    mean_motion_rad_s: float
    command_period_s: float
    event_interval_max_s: float
    numerical_fixture_horizon_s: float
    max_acceleration_mps2: float
    process_acceleration_sigma_mps2: tuple[float, float]
    process_acceleration_draw_period_s: float
    initial_mean: tuple[float, ...]
    initial_covariance_diagonal: tuple[float, ...]
    measurement_sigma: tuple[float, ...]
    measurement_quantization: tuple[float, ...]
    maximum_packet_lag_s: float
    degraded_after_prediction_only_s: float
    nis_reject_threshold: float
    max_consecutive_innovation_rejections: int
    covariance_negative_eigenvalue_tolerance: float
    covariance_trace_limit: float
    innovation_condition_limit: float
    state_absolute_limits: tuple[float, ...]
    uncertainty_sigma_multiplier: float
    hard_body_radius_m: float
    keep_out_radius_m: float
    hold_center_m: tuple[float, float]
    hold_position_halfwidth_m: tuple[float, float]
    hold_max_speed_mps: float
    hold_required_dwell_s: float
    approach_y_bounds_m: tuple[float, float]
    approach_radial_halfwidth_m: tuple[float, float]
    lqr_state_cost_diagonal: tuple[float, ...]
    lqr_control_cost_diagonal: tuple[float, ...]
    master_seed: int
    calibration_partition_code: int
    controller_fit_partition_code: int
    pilot_partition_code: int
    future_confirmatory_partition_code: int
    test_fixture_partition_code: int

    @property
    def derived_mean_motion_rad_s(self) -> float:
        return math.sqrt(self.gravitational_parameter_m3_s2 / self.reference_radius_m**3)

    @property
    def orbital_period_s(self) -> float:
        return 2.0 * math.pi / self.mean_motion_rad_s

    @property
    def initial_mean_array(self) -> np.ndarray:
        return np.asarray(self.initial_mean, dtype=np.float64)

    @property
    def initial_covariance(self) -> np.ndarray:
        return np.diag(np.asarray(self.initial_covariance_diagonal, dtype=np.float64))

    @property
    def nominal_measurement_covariance(self) -> np.ndarray:
        sigma = np.asarray(self.measurement_sigma, dtype=np.float64)
        quantum = np.asarray(self.measurement_quantization, dtype=np.float64)
        return np.diag(sigma**2 + quantum**2 / 12.0)

    def validate(self) -> None:
        if self.schema_version != "experiment-004-planar-hcw-foundation-1.0":
            raise ValueError("unexpected Experiment 004 schema")
        if self.parent_commit != EXPECTED_BASE_COMMIT:
            raise ValueError("Experiment 004 parent commit changed")
        if self.coordinate_frame != "target-centered LVLH rotating with a circular chief orbit":
            raise ValueError("coordinate-frame definition changed")
        if self.x_axis_convention != "+x radial outward from Earth":
            raise ValueError("radial-axis convention changed")
        if self.y_axis_convention != "+y along-track in the chief velocity direction":
            raise ValueError("along-track-axis convention changed")
        if self.state_order != STATE_ORDER or self.action_order != ACTION_ORDER:
            raise ValueError("state or action order changed")
        if self.measurement_order != MEASUREMENT_ORDER:
            raise ValueError("measurement order changed")
        if self.state_units != STATE_UNITS or self.action_units != ACTION_UNITS:
            raise ValueError("state or action units changed")
        if self.central_body != "Earth":
            raise ValueError("central body changed")
        if self.gravitational_parameter_m3_s2 != 3.986004418e14:
            raise ValueError("Earth gravitational parameter changed")
        if self.reference_radius_m != 6_778_137.0:
            raise ValueError("reference-orbit radius changed")
        if self.reference_altitude_above_equatorial_radius_m != 400_000.0:
            raise ValueError("reference-altitude statement changed")
        if abs(self.mean_motion_rad_s - self.derived_mean_motion_rad_s) > 5e-16:
            raise ValueError("mean motion is inconsistent with the orbital reference")
        positive = (
            self.command_period_s,
            self.event_interval_max_s,
            self.numerical_fixture_horizon_s,
            self.max_acceleration_mps2,
            self.process_acceleration_draw_period_s,
            self.maximum_packet_lag_s,
            self.degraded_after_prediction_only_s,
            self.nis_reject_threshold,
            self.covariance_trace_limit,
            self.innovation_condition_limit,
            self.uncertainty_sigma_multiplier,
            self.hard_body_radius_m,
            self.keep_out_radius_m,
            self.hold_max_speed_mps,
            self.hold_required_dwell_s,
        )
        if not all(np.isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("positive configuration values must be finite")
        if self.command_period_s != 1.0 or self.event_interval_max_s != 1.0:
            raise ValueError("the foundation uses one-second control and event intervals")
        if self.process_acceleration_draw_period_s != 0.25:
            raise ValueError("process acceleration draw period changed")
        ratio = self.command_period_s / self.process_acceleration_draw_period_s
        if abs(ratio - round(ratio)) > 1e-12:
            raise ValueError("command period must contain an integer number of process draws")
        if self.max_acceleration_mps2 != 0.02:
            raise ValueError("reference acceleration bound changed")
        if len(self.process_acceleration_sigma_mps2) != 2 or any(
            not np.isfinite(value) or value < 0.0
            for value in self.process_acceleration_sigma_mps2
        ):
            raise ValueError("process acceleration sigma must be a non-negative two-vector")
        four_vectors = (
            self.initial_mean,
            self.initial_covariance_diagonal,
            self.measurement_sigma,
            self.measurement_quantization,
            self.state_absolute_limits,
            self.lqr_state_cost_diagonal,
        )
        if any(len(value) != 4 for value in four_vectors):
            raise ValueError("state-space configuration vectors must have length four")
        if len(self.lqr_control_cost_diagonal) != 2:
            raise ValueError("control cost must have length two")
        if self.lqr_state_cost_diagonal != (1.0, 1.0, 100.0, 100.0):
            raise ValueError("reference-controller state cost changed")
        if self.lqr_control_cost_diagonal != (100_000.0, 100_000.0):
            raise ValueError("reference-controller control cost changed")
        if any(value <= 0.0 for value in self.initial_covariance_diagonal):
            raise ValueError("initial covariance diagonal must be positive")
        if any(value < 0.0 for value in self.measurement_sigma):
            raise ValueError("measurement sigmas must be non-negative")
        if any(value <= 0.0 for value in self.measurement_quantization):
            raise ValueError("measurement quantization must be positive")
        if self.maximum_packet_lag_s != self.command_period_s:
            raise ValueError("only a one-command-period fixed lag is supported")
        if self.degraded_after_prediction_only_s != 2.0:
            raise ValueError("prediction-only health threshold changed")
        if self.max_consecutive_innovation_rejections != 3:
            raise ValueError("innovation-rejection handling changed")
        if self.covariance_negative_eigenvalue_tolerance != 1e-12:
            raise ValueError("covariance tolerance changed")
        if self.hard_body_radius_m >= self.keep_out_radius_m:
            raise ValueError("hard-body radius must be inside the keep-out radius")
        if self.hard_body_radius_m != 2.0 or self.keep_out_radius_m != 10.0:
            raise ValueError("foundation collision or keep-out geometry changed")
        if self.hold_center_m != (0.0, -30.0):
            raise ValueError("hold point changed")
        if self.hold_position_halfwidth_m != (2.0, 3.0):
            raise ValueError("hold-region halfwidth changed")
        if self.approach_y_bounds_m != (-100.0, -30.0):
            raise ValueError("approach along-track bounds changed")
        if self.approach_radial_halfwidth_m != (10.0, 3.0):
            raise ValueError("approach corridor halfwidth changed")
        if self.hold_center_m[1] + self.hold_position_halfwidth_m[1] >= -self.keep_out_radius_m:
            raise ValueError("hold region must remain exterior to the keep-out disk")
        if (
            self.master_seed,
            self.calibration_partition_code,
            self.controller_fit_partition_code,
            self.pilot_partition_code,
            self.future_confirmatory_partition_code,
            self.test_fixture_partition_code,
        ) != (4004, 41, 42, 43, 44, 941):
            raise ValueError("Experiment 004 seed-domain contract changed")
        codes = {
            self.calibration_partition_code,
            self.controller_fit_partition_code,
            self.pilot_partition_code,
            self.future_confirmatory_partition_code,
            self.test_fixture_partition_code,
        }
        if len(codes) != 5:
            raise ValueError("Experiment 004 partition codes must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        }


def load_config(path: str | Path = "experiments/004/config.json") -> Experiment004Config:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tuple_fields = {
        "state_order",
        "action_order",
        "measurement_order",
        "state_units",
        "action_units",
        "process_acceleration_sigma_mps2",
        "initial_mean",
        "initial_covariance_diagonal",
        "measurement_sigma",
        "measurement_quantization",
        "state_absolute_limits",
        "hold_center_m",
        "hold_position_halfwidth_m",
        "approach_y_bounds_m",
        "approach_radial_halfwidth_m",
        "lqr_state_cost_diagonal",
        "lqr_control_cost_diagonal",
    }
    normalized = {
        key: tuple(value) if key in tuple_fields else value for key, value in data.items()
    }
    config = Experiment004Config(**normalized)
    config.validate()
    return config
