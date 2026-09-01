from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

EXPECTED_BASE_COMMIT = "ce50129946a40c36dc89ece88130ba6e90707605"
EXPECTED_BRANCH = "experiment-005-nonlinear-truth-foundation"
SCHEMA_VERSION = "experiment-005-nonlinear-truth-foundation-1.0"
INERTIAL_STATE_ORDER = (
    "chief_rx_m",
    "chief_ry_m",
    "chief_rz_m",
    "chief_vx_mps",
    "chief_vy_mps",
    "chief_vz_mps",
    "deputy_rx_m",
    "deputy_ry_m",
    "deputy_rz_m",
    "deputy_vx_mps",
    "deputy_vy_mps",
    "deputy_vz_mps",
)
RELATIVE_STATE_ORDER = (
    "x_radial_m",
    "y_alongtrack_m",
    "z_crosstrack_m",
    "vx_radial_mps",
    "vy_alongtrack_mps",
    "vz_crosstrack_mps",
)
COMMAND_ORDER = (
    "ax_radial_mps2",
    "ay_alongtrack_mps2",
    "az_crosstrack_mps2",
)


@dataclass(frozen=True)
class Experiment005Config:
    schema_version: str
    parent_commit: str
    truth_model: str
    controller_estimator_model: str
    central_body: str
    gravitational_parameter_m3_s2: float
    reference_radius_m: float
    reference_altitude_above_equatorial_radius_m: float
    inertial_state_order: tuple[str, ...]
    relative_state_order: tuple[str, ...]
    command_order: tuple[str, ...]
    command_period_s: float
    production_integrator: str
    production_max_step_s: float
    reference_integrator: str
    reference_rtol: float
    reference_position_atol_m: float
    reference_velocity_atol_mps: float
    production_position_tolerance_m: float
    production_velocity_tolerance_mps: float
    frame_roundtrip_position_tolerance_m: float
    frame_roundtrip_velocity_tolerance_mps: float
    command_mapping_tolerance_mps2: float
    circular_radius_tolerance_m: float
    circular_speed_tolerance_mps: float
    invariant_relative_drift_tolerance: float
    validation_horizon_s: float
    event_interval_max_s: float
    max_acceleration_mps2: float
    initial_relative_state_planar: tuple[float, ...]
    radial_envelope_m: tuple[float, float]
    alongtrack_envelope_m: tuple[float, float]
    velocity_envelope_abs_mps: float
    hard_body_radius_m: float
    keep_out_radius_m: float
    hold_center_m: tuple[float, float]
    hold_position_halfwidth_m: tuple[float, float]
    hold_max_speed_mps: float
    hold_required_dwell_s: float
    approach_y_bounds_m: tuple[float, float]
    approach_radial_halfwidth_m: tuple[float, float]
    experiment_004_config_sha256: str
    master_seed: int
    mechanics_calibration_partition_code: int
    future_pilot_partition_code: int
    future_confirmatory_partition_code: int
    test_fixture_partition_code: int

    @property
    def mean_motion_rad_s(self) -> float:
        return math.sqrt(self.gravitational_parameter_m3_s2 / self.reference_radius_m**3)

    @property
    def orbital_period_s(self) -> float:
        return 2.0 * math.pi / self.mean_motion_rad_s

    @property
    def initial_relative_state(self) -> np.ndarray:
        planar = np.asarray(self.initial_relative_state_planar, dtype=np.float64)
        return np.array(
            [planar[0], planar[1], 0.0, planar[2], planar[3], 0.0],
            dtype=np.float64,
        )

    def validate(self, *, root: str | Path = ".") -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unexpected Experiment 005 schema")
        if self.parent_commit != EXPECTED_BASE_COMMIT:
            raise ValueError("Experiment 005 parent commit changed")
        if self.truth_model != "nonlinear central-gravity two-body inertial Cartesian":
            raise ValueError("truth-model declaration changed")
        if self.controller_estimator_model != "Experiment 004 planar HCW":
            raise ValueError("controller/estimator model declaration changed")
        if self.central_body != "Earth":
            raise ValueError("central body changed")
        if self.gravitational_parameter_m3_s2 != 3.986004418e14:
            raise ValueError("Earth gravitational parameter changed")
        if self.reference_radius_m != 6_778_137.0:
            raise ValueError("reference-orbit radius changed")
        if self.reference_altitude_above_equatorial_radius_m != 400_000.0:
            raise ValueError("reference altitude changed")
        if self.inertial_state_order != INERTIAL_STATE_ORDER:
            raise ValueError("inertial truth-state order changed")
        if self.relative_state_order != RELATIVE_STATE_ORDER:
            raise ValueError("relative state order changed")
        if self.command_order != COMMAND_ORDER:
            raise ValueError("command order changed")
        if self.command_period_s != 1.0 or self.event_interval_max_s != 1.0:
            raise ValueError("foundation control/event interval changed")
        if self.production_integrator != "fixed-step-rk4":
            raise ValueError("production integrator must remain fixed-step RK4")
        if self.production_max_step_s != 0.1:
            raise ValueError("production RK4 step bound changed")
        if self.reference_integrator != "DOP853":
            raise ValueError("independent numerical reference changed")
        positive = (
            self.reference_rtol,
            self.reference_position_atol_m,
            self.reference_velocity_atol_mps,
            self.production_position_tolerance_m,
            self.production_velocity_tolerance_mps,
            self.frame_roundtrip_position_tolerance_m,
            self.frame_roundtrip_velocity_tolerance_mps,
            self.command_mapping_tolerance_mps2,
            self.circular_radius_tolerance_m,
            self.circular_speed_tolerance_mps,
            self.invariant_relative_drift_tolerance,
            self.validation_horizon_s,
            self.max_acceleration_mps2,
            self.velocity_envelope_abs_mps,
            self.hard_body_radius_m,
            self.keep_out_radius_m,
            self.hold_max_speed_mps,
            self.hold_required_dwell_s,
        )
        if not all(np.isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("positive configuration values must be finite")
        if self.max_acceleration_mps2 != 0.02:
            raise ValueError("Experiment 004 acceleration bound changed")
        if (
            self.frame_roundtrip_position_tolerance_m,
            self.frame_roundtrip_velocity_tolerance_mps,
            self.command_mapping_tolerance_mps2,
            self.circular_radius_tolerance_m,
            self.circular_speed_tolerance_mps,
            self.invariant_relative_drift_tolerance,
        ) != (5e-9, 5e-12, 1e-15, 1e-4, 1e-7, 1e-11):
            raise ValueError("prospective mechanics acceptance tolerances changed")
        if len(self.initial_relative_state_planar) != 4:
            raise ValueError("initial planar state must have four entries")
        if self.initial_relative_state_planar != (0.0, -100.0, 0.0, 0.12):
            raise ValueError("initial planar geometry changed")
        if self.radial_envelope_m != (-10.0, 10.0):
            raise ValueError("radial envelope must come from the E004 corridor")
        if self.alongtrack_envelope_m != (-100.0, -27.0):
            raise ValueError("along-track envelope must cover approach and hold geometry")
        derived_velocity = max(
            abs(self.initial_relative_state_planar[3]), self.hold_max_speed_mps
        ) + self.max_acceleration_mps2 * self.command_period_s
        if abs(self.velocity_envelope_abs_mps - derived_velocity) > 1e-15:
            raise ValueError("velocity envelope is not derived from E004 bounds")
        if self.hard_body_radius_m != 2.0 or self.keep_out_radius_m != 10.0:
            raise ValueError("physical event geometry changed")
        if self.hard_body_radius_m >= self.keep_out_radius_m:
            raise ValueError("hard-body radius must remain inside keep-out radius")
        if self.hold_center_m != (0.0, -30.0):
            raise ValueError("hold center changed")
        if self.hold_position_halfwidth_m != (2.0, 3.0):
            raise ValueError("hold ellipse changed")
        if self.approach_y_bounds_m != (-100.0, -30.0):
            raise ValueError("approach y bounds changed")
        if self.approach_radial_halfwidth_m != (10.0, 3.0):
            raise ValueError("approach corridor widths changed")
        hold_outer_y = self.hold_center_m[1] + self.hold_position_halfwidth_m[1]
        if hold_outer_y != self.alongtrack_envelope_m[1]:
            raise ValueError("along-track envelope does not include the hold boundary")
        if (
            self.master_seed,
            self.mechanics_calibration_partition_code,
            self.future_pilot_partition_code,
            self.future_confirmatory_partition_code,
            self.test_fixture_partition_code,
        ) != (5005, 51, 52, 53, 951):
            raise ValueError("Experiment 005 seed-domain contract changed")
        codes = {
            self.mechanics_calibration_partition_code,
            self.future_pilot_partition_code,
            self.future_confirmatory_partition_code,
            self.test_fixture_partition_code,
        }
        if len(codes) != 4:
            raise ValueError("Experiment 005 partition codes must be unique")
        e004_path = Path(root) / "experiments/004/config.json"
        if not e004_path.is_file():
            raise ValueError("Experiment 004 foundation config is unavailable")
        observed_hash = hashlib.sha256(e004_path.read_bytes()).hexdigest()
        if observed_hash != self.experiment_004_config_sha256:
            raise ValueError("Experiment 004 config identity changed")
        e004 = json.loads(e004_path.read_text(encoding="utf-8"))
        required_equal = {
            "gravitational_parameter_m3_s2": self.gravitational_parameter_m3_s2,
            "reference_radius_m": self.reference_radius_m,
            "reference_altitude_above_equatorial_radius_m": (
                self.reference_altitude_above_equatorial_radius_m
            ),
            "command_period_s": self.command_period_s,
            "event_interval_max_s": self.event_interval_max_s,
            "max_acceleration_mps2": self.max_acceleration_mps2,
            "hard_body_radius_m": self.hard_body_radius_m,
            "keep_out_radius_m": self.keep_out_radius_m,
        }
        mismatches = [key for key, value in required_equal.items() if e004.get(key) != value]
        if mismatches:
            raise ValueError(f"Experiment 004 transfer constants changed: {mismatches}")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        }


def load_config(
    path: str | Path = "experiments/005/config.json",
    *,
    root: str | Path = ".",
) -> Experiment005Config:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tuple_fields = {
        "inertial_state_order",
        "relative_state_order",
        "command_order",
        "initial_relative_state_planar",
        "radial_envelope_m",
        "alongtrack_envelope_m",
        "hold_center_m",
        "hold_position_halfwidth_m",
        "approach_y_bounds_m",
        "approach_radial_halfwidth_m",
    }
    normalized = {
        key: tuple(value) if key in tuple_fields else value for key, value in data.items()
    }
    config = Experiment005Config(**normalized)
    config.validate(root=root)
    return config
