from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PILOT_STRATA = (
    "P0_nominal",
    "P1_primary_navigation",
    "P2_monitor_only",
    "P3_shared_cause_navigation",
    "P4_model_upset",
    "P5_actuator_degradation",
)
MIXED_STRATA = PILOT_STRATA[1:4]
ARMS = ("R", "D", "PS", "PD")
STREAM_NAMES = (
    "initial_state",
    "process_disturbance",
    "primary_sensor",
    "monitor_sensor",
    "fault_parameters",
    "arm_run_order",
)
PARTITION_CODES = {
    "train_fit": 11,
    "train_stop": 12,
    "validation": 13,
    "metric_calibration": 14,
    "pilot": 15,
    "future_confirmatory_reserved": 16,
    "bootstrap": 17,
    "replay_subset": 18,
    "command_rate_subset": 19,
}
STREAM_CODES = {name: index + 101 for index, name in enumerate(STREAM_NAMES)}
STRATUM_CODES = {name: index + 1 for index, name in enumerate(PILOT_STRATA)}


@dataclass(frozen=True)
class PilotConfig:
    schema_version: str
    master_seed: int
    seeds_per_stratum: int
    horizon_s: float
    command_period_s: float
    exogenous_period_s: float
    evaluator_period_s: float
    collision_range_m: float
    goal_min_range_m: float
    goal_max_range_m: float
    goal_max_speed_mps: float
    goal_dwell_s: float
    max_acceleration_mps2: float
    actuator_time_constant_s: float
    propellant_cost_per_delta_v: float
    propellant_reserve: float
    process_accel_sigma_mps2: float
    process_accel_clip_mps2: float
    range_noise_sigma_m: float
    velocity_noise_sigma_mps: float
    range_quantization_m: float
    velocity_quantization_mps: float
    sensor_latency_one_second_probability: float
    gate_min_range_m: float
    gate_confidence_threshold: float
    recovery_deadline_s: float
    recovery_dwell_s: float
    bootstrap_replicates: int
    bootstrap_seed: int
    replay_blocks_per_stratum: int
    command_rate_blocks_per_stratum: int
    float_absolute_tolerance: float
    float_relative_tolerance: float

    @property
    def n_exogenous_steps(self) -> int:
        return round(self.horizon_s / self.exogenous_period_s)

    @property
    def n_command_steps(self) -> int:
        return round(self.horizon_s / self.command_period_s)

    @property
    def planned_blocks(self) -> int:
        return len(PILOT_STRATA) * self.seeds_per_stratum

    @property
    def planned_episodes(self) -> int:
        return self.planned_blocks * len(ARMS)

    def validate(self) -> None:
        if self.seeds_per_stratum != 400:
            raise ValueError("Experiment 002 pilot requires exactly 400 seeds per stratum")
        if self.planned_blocks != 2400 or self.planned_episodes != 9600:
            raise ValueError("canonical pilot size is 2,400 blocks / 9,600 episodes")
        if self.horizon_s != 600.0 or self.command_period_s != 1.0:
            raise ValueError("pilot horizon/command period must remain frozen at 600 s / 1 s")
        ratio = self.command_period_s / self.exogenous_period_s
        if abs(ratio - round(ratio)) > 1e-12:
            raise ValueError("command period must be an integer multiple of exogenous period")
        eval_ratio = self.evaluator_period_s / self.exogenous_period_s
        if abs(eval_ratio - round(eval_ratio)) > 1e-12:
            raise ValueError("evaluator period must be an integer multiple of exogenous period")
        if not 0.0 < self.propellant_reserve < 1.0:
            raise ValueError("propellant reserve must be in (0, 1)")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def load_config(path: str | Path) -> PilotConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cfg = PilotConfig(**data)
    cfg.validate()
    return cfg
