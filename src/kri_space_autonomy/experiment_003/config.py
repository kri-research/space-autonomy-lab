from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.config import PilotConfig
from kri_space_autonomy.experiment_002.config import load_config as load_production

ARMS = ("R", "D", "PS", "PD")
ESTIMATOR_STRATA = (
    "E0_nominal",
    "E1_primary_range_bias",
    "E2_primary_dropout",
    "E3_primary_stale",
    "E4_primary_covariance_underreporting",
    "E5_monitor_range_bias",
    "E6_shared_range_bias",
)
STREAM_NAMES = (
    "initial_state",
    "process_disturbance",
    "primary_measurement",
    "monitor_measurement",
    "fault_parameters",
    "arm_run_order",
)
EXPECTED_BASE_COMMIT = "3656dc10982ac343f9ea6b106f4ce67bf51e84d8"
EXPECTED_BRANCH = "experiment-003-navigation-estimation"


@dataclass(frozen=True)
class Experiment003Config:
    schema_version: str
    parent_commit: str
    master_seed: int
    pilot_partition_code: int
    confirmatory_partition_code: int
    test_fixture_partition_code: int
    pilot_roots_per_stratum: int
    pilot_replay_roots_per_stratum: int
    future_candidate_roots_per_stratum: tuple[int, ...]
    arms: tuple[str, ...]
    strata: tuple[str, ...]
    state_order: tuple[str, ...]
    measurement_order: tuple[str, ...]
    initial_mean: tuple[float, ...]
    initial_covariance_diagonal: tuple[float, ...]
    actuator_model_process_sigma_mps2: float
    maximum_packet_lag_s: float
    degraded_after_prediction_only_s: float
    nis_reject_threshold: float
    max_consecutive_innovation_rejections: int
    covariance_negative_eigenvalue_tolerance: float
    covariance_trace_limit: float
    innovation_condition_limit: float
    state_absolute_limits: tuple[float, ...]
    uncertainty_sigma_multiplier: float
    covariance_underreporting_factor: float
    bias_min_m: float
    bias_max_m: float
    shared_bias_max_m: float
    fault_onset_min_s: float
    fault_onset_max_s: float
    bias_duration_min_s: float
    bias_duration_max_s: float
    dropout_duration_min_s: float
    dropout_duration_max_s: float
    h1_two_sided_alpha: float
    h1_minimum_absolute_reduction: float
    h1_minimum_relative_reduction: float
    h2_one_sided_alpha: float
    h2_noninferiority_margin: float
    bootstrap_replicates: int
    bootstrap_seed: int
    secondary_randomization_replicates: int
    secondary_randomization_seed: int
    power_simulation_replicates: int
    power_simulation_seed: int
    confirmatory_power_target: float
    confirmatory_incomplete_block_limit: float
    pilot_requires_complete_blocks: bool
    recovery_deadline_s: float
    recovery_dwell_s: float
    recovery_max_abs_range_error_m: float
    recovery_max_abs_velocity_error_mps: float
    offline_nees_recovery_threshold: float
    infrastructure_retry_allowlist: tuple[str, ...]

    @property
    def pilot_blocks(self) -> int:
        return len(self.strata) * self.pilot_roots_per_stratum

    @property
    def pilot_episodes(self) -> int:
        return self.pilot_blocks * len(self.arms)

    @property
    def initial_mean_array(self) -> np.ndarray:
        return np.asarray(self.initial_mean, dtype=np.float64)

    @property
    def initial_covariance(self) -> np.ndarray:
        return np.diag(np.asarray(self.initial_covariance_diagonal, dtype=np.float64))

    def validate(self, production: PilotConfig) -> None:
        if self.schema_version != "experiment-003-navigation-estimation-1.0":
            raise ValueError("unexpected Experiment 003 schema")
        if self.parent_commit != EXPECTED_BASE_COMMIT:
            raise ValueError("Experiment 003 parent commit changed")
        if self.master_seed != 3003:
            raise ValueError("Experiment 003 master seed must remain 3003")
        if (
            self.pilot_partition_code,
            self.confirmatory_partition_code,
            self.test_fixture_partition_code,
        ) != (31, 32, 931):
            raise ValueError("Experiment 003 partition codes changed")
        if self.pilot_roots_per_stratum != 64:
            raise ValueError("the design-validation pilot requires 64 roots per stratum")
        if self.pilot_replay_roots_per_stratum != 8:
            raise ValueError("the pilot replay reservation requires eight roots per stratum")
        if self.future_candidate_roots_per_stratum != (250, 500, 750, 1000, 1500):
            raise ValueError("future confirmatory candidate-size grid changed")
        if self.arms != ARMS or self.strata != ESTIMATOR_STRATA:
            raise ValueError("Experiment 003 arms or strata changed")
        if self.pilot_blocks != 448 or self.pilot_episodes != 1792:
            raise ValueError("canonical pilot size is 448 blocks / 1,792 episodes")
        if self.state_order != ("range_m", "relative_velocity_mps", "achieved_acceleration_mps2"):
            raise ValueError("estimator state order changed")
        if self.measurement_order != ("range_m", "relative_velocity_mps"):
            raise ValueError("measurement order changed")
        if len(self.initial_mean) != 3 or len(self.initial_covariance_diagonal) != 3:
            raise ValueError("estimator initialization must contain three states")
        if any(value <= 0.0 for value in self.initial_covariance_diagonal):
            raise ValueError("initial covariance diagonal must be positive")
        if self.actuator_model_process_sigma_mps2 != 0.001:
            raise ValueError("achieved-acceleration process uncertainty changed")
        if production.horizon_s != 600.0 or production.command_period_s != 1.0:
            raise ValueError("Experiment 003 retains the 600 s / 1 s production schedule")
        if production.exogenous_period_s != 0.25 or production.actuator_time_constant_s != 0.5:
            raise ValueError("Experiment 003 retains corrected plant timing and actuator lag")
        if self.maximum_packet_lag_s != 1.0:
            raise ValueError("only the frozen one-second fixed-lag update is supported")
        if self.degraded_after_prediction_only_s != 2.0:
            raise ValueError("prediction-only health threshold changed")
        if not 0.0 < self.nis_reject_threshold < 100.0:
            raise ValueError("NIS rejection threshold is invalid")
        if self.max_consecutive_innovation_rejections != 3:
            raise ValueError("innovation-rejection handling changed")
        if self.covariance_negative_eigenvalue_tolerance != 1e-12:
            raise ValueError("covariance eigenvalue tolerance changed")
        if self.covariance_trace_limit != 1e6 or self.innovation_condition_limit != 1e12:
            raise ValueError("numerical divergence limits changed")
        if self.state_absolute_limits != (10_000.0, 100.0, 1.0):
            raise ValueError("physical estimator state bounds changed")
        if self.uncertainty_sigma_multiplier != 3.0:
            raise ValueError("runtime uncertainty multiplier changed")
        if self.covariance_underreporting_factor != 0.25:
            raise ValueError("covariance inconsistency severity changed")
        if (self.bias_min_m, self.bias_max_m, self.shared_bias_max_m) != (5.0, 30.0, 20.0):
            raise ValueError("range-bias bounds must retain the historical channel bounds")
        if (self.fault_onset_min_s, self.fault_onset_max_s) != (120.0, 300.0):
            raise ValueError("fault-onset bounds changed")
        if (self.bias_duration_min_s, self.bias_duration_max_s) != (30.0, 120.0):
            raise ValueError("bias-duration bounds changed")
        if (self.dropout_duration_min_s, self.dropout_duration_max_s) != (5.0, 30.0):
            raise ValueError("dropout/stale-duration bounds changed")
        if (
            self.h1_two_sided_alpha,
            self.h1_minimum_absolute_reduction,
            self.h1_minimum_relative_reduction,
        ) != (0.05, 0.02, 0.25):
            raise ValueError("H1 thresholds changed")
        if (self.h2_one_sided_alpha, self.h2_noninferiority_margin) != (0.025, -0.03):
            raise ValueError("H2 thresholds changed")
        if (self.bootstrap_replicates, self.bootstrap_seed) != (50_000, 300318):
            raise ValueError("paired bootstrap procedure changed")
        if (
            self.secondary_randomization_replicates,
            self.secondary_randomization_seed,
        ) != (200_000, 300319):
            raise ValueError("secondary randomization procedure changed")
        if (self.power_simulation_replicates, self.power_simulation_seed) != (20_000, 300317):
            raise ValueError("future power-simulation procedure changed")
        if self.confirmatory_power_target != 0.95:
            raise ValueError("confirmatory marginal-power target changed")
        if self.confirmatory_incomplete_block_limit != 0.01:
            raise ValueError("confirmatory incomplete-block limit changed")
        if self.pilot_requires_complete_blocks is not True:
            raise ValueError("pilot must require every scheduled four-arm block")
        if (self.recovery_deadline_s, self.recovery_dwell_s) != (180.0, 30.0):
            raise ValueError("recovery timing changed")
        if (
            self.recovery_max_abs_range_error_m,
            self.recovery_max_abs_velocity_error_mps,
        ) != (1.0, 0.04):
            raise ValueError("offline estimator recovery corridor changed")
        if abs(self.offline_nees_recovery_threshold - 16.26623619623813) > 1e-12:
            raise ValueError("offline NEES recovery threshold changed")
        if self.infrastructure_retry_allowlist:
            raise ValueError("the outcome-era infrastructure retry allowlist must be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        }


def load_config(
    path: str | Path,
    production_path: str | Path = "experiments/002/config.json",
) -> tuple[Experiment003Config, PilotConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    tuple_fields = {
        "future_candidate_roots_per_stratum",
        "arms",
        "strata",
        "state_order",
        "measurement_order",
        "initial_mean",
        "initial_covariance_diagonal",
        "state_absolute_limits",
        "infrastructure_retry_allowlist",
    }
    normalized = {
        key: tuple(value) if key in tuple_fields else value for key, value in data.items()
    }
    config = Experiment003Config(**normalized)
    production = load_production(production_path)
    config.validate(production)
    return config, production
