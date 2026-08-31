from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import SCHEMA_VERSION

FOUNDATION_COMMIT = "5b2e5fe7346c60ac407b11b47b31693077ee25b1"
FOUNDATION_FREEZE_ID = "54a0f1a8dc985fba02973c09ac994fbc76a2ef1abbc7dfe5def82585c85aaa14"
FOUNDATION_READINESS_ID = "fd0ea450e8b5f53a4447cf3910e7e3b494ed6bace33da0055f64e77fd9049404"
CONFIGURATIONS = ("primary_reference", "independent_monitor_gate")
CASE_IDS = (
    "P00_nominal_feasibility",
    "P01_forced_collision",
    "P02_forced_keep_out_only",
    "P03_forced_corridor_departure",
    "P04_primary_navigation_bias",
    "P05_primary_navigation_dropout",
    "P06_monitor_navigation_bias",
    "P07_monitor_logic_false_trip",
    "P08_shared_navigation_bias",
    "P09_actuation_degradation",
    "P10_disturbance_burst",
)


@dataclass(frozen=True)
class PilotCase:
    id: str
    geometry_code: int
    fault_code: int
    case_code: int
    domain: str
    fixture: str
    fault: str
    intended_activation: str
    initial_state: tuple[float, ...] | None = None
    fixture_command_mps2: tuple[float, ...] | None = None

    def validate(self) -> None:
        if self.case_code != 100 * self.geometry_code + self.fault_code:
            raise ValueError(f"non-injective composite case code for {self.id}")
        if self.geometry_code < 0 or self.fault_code < 0:
            raise ValueError("case entropy codes must be non-negative")
        if self.fixture == "open_loop_exact_arc":
            if self.initial_state is None or len(self.initial_state) != 4:
                raise ValueError("forced fixture requires a four-state initial condition")
            if self.fixture_command_mps2 is None or len(self.fixture_command_mps2) != 2:
                raise ValueError("forced fixture requires a two-vector command")
        elif self.fixture != "stochastic_bounded_initial_state":
            raise ValueError("unknown pilot fixture kind")


@dataclass(frozen=True)
class PilotConfig:
    schema_version: str
    foundation_schema_version: str
    foundation_commit: str
    foundation_freeze_id: str
    foundation_readiness_id: str
    calibration_partition_code: int
    controller_fit_partition_code: int
    pilot_partition_code: int
    future_confirmatory_partition_code: int
    test_fixture_partition_code: int
    pilot_roots_per_case: int
    candidate_roots_per_case: tuple[int, ...]
    replay_roots_per_case: int
    case_count: int
    configuration_ids: tuple[str, ...]
    standard_horizon_s: float
    forced_fixture_horizon_s: float
    initial_state_bounds: dict[str, tuple[float, float]]
    fault_onset_range_s: tuple[float, float]
    bias_duration_s: float
    dropout_duration_s: float
    monitor_logic_duration_s: float
    navigation_bias: tuple[float, ...]
    actuation_onset_range_s: tuple[float, float]
    actuation_duration_s: float
    actuation_effectiveness: float
    actuator_uncertainty_sigma_mps2: float
    disturbance_bias_mps2: tuple[float, float]
    process_disturbance_clip_sigma: float
    maximum_infrastructure_failure_rate: float
    minimum_order_appearances_per_position_per_case: int
    analysis_mode: str
    scientific_hypothesis_defined: bool
    learned_policy_permitted: bool
    replacement_extension_or_retry_allowed: bool

    @property
    def pilot_blocks(self) -> int:
        return self.case_count * self.pilot_roots_per_case

    @property
    def pilot_episodes(self) -> int:
        return self.pilot_blocks * len(self.configuration_ids)

    @property
    def replay_blocks(self) -> int:
        return self.case_count * self.replay_roots_per_case

    @property
    def replay_episodes(self) -> int:
        return self.replay_blocks * len(self.configuration_ids)

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unexpected pilot schema")
        if self.foundation_schema_version != "experiment-004-planar-hcw-foundation-1.0":
            raise ValueError("unexpected foundation schema")
        if (
            self.foundation_commit,
            self.foundation_freeze_id,
            self.foundation_readiness_id,
        ) != (FOUNDATION_COMMIT, FOUNDATION_FREEZE_ID, FOUNDATION_READINESS_ID):
            raise ValueError("foundation identity changed")
        if (
            self.calibration_partition_code,
            self.controller_fit_partition_code,
            self.pilot_partition_code,
            self.future_confirmatory_partition_code,
            self.test_fixture_partition_code,
        ) != (41, 42, 43, 44, 941):
            raise ValueError("partition contract changed")
        if len({41, 42, 43, 44, 941}) != 5:
            raise ValueError("partition codes overlap")
        if self.configuration_ids != CONFIGURATIONS:
            raise ValueError("diagnostic configurations changed")
        if self.case_count != len(CASE_IDS) or self.pilot_roots_per_case != 4:
            raise ValueError("fixed pilot count changed")
        if self.candidate_roots_per_case != (2, 4, 6, 8):
            raise ValueError("sample-count selection candidates changed")
        if self.replay_roots_per_case != 1:
            raise ValueError("outcome-blind replay count changed")
        if self.minimum_order_appearances_per_position_per_case != 2:
            raise ValueError("order-balance requirement changed")
        if self.pilot_blocks != 44 or self.pilot_episodes != 88:
            raise ValueError("fixed block or episode count changed")
        if self.replay_blocks != 11 or self.replay_episodes != 22:
            raise ValueError("replay subset count changed")
        if self.standard_horizon_s != 300.0 or self.forced_fixture_horizon_s != 1.0:
            raise ValueError("pilot horizons changed")
        if self.analysis_mode != "descriptive_mechanistic_gate_only":
            raise ValueError("pilot analysis mode changed")
        if (
            self.scientific_hypothesis_defined
            or self.learned_policy_permitted
            or self.replacement_extension_or_retry_allowed
        ):
            raise ValueError("non-inferential pilot restrictions changed")
        if not 0.0 <= self.maximum_infrastructure_failure_rate <= 0.01:
            raise ValueError("infrastructure threshold is not bounded")
        if not 0.0 < self.actuation_effectiveness < 1.0:
            raise ValueError("actuation effectiveness must represent degradation")
        if len(self.navigation_bias) != 4 or len(self.disturbance_bias_mps2) != 2:
            raise ValueError("fault vectors have the wrong dimension")
        bounds = tuple(self.initial_state_bounds.values())
        if len(bounds) != 4 or any(
            len(pair) != 2
            or not np.all(np.isfinite(pair))
            or pair[0] >= pair[1]
            for pair in bounds
        ):
            raise ValueError("invalid initial-state envelope")


def _tuple_fields(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    for key in (
        "candidate_roots_per_case",
        "configuration_ids",
        "fault_onset_range_s",
        "navigation_bias",
        "actuation_onset_range_s",
        "disturbance_bias_mps2",
    ):
        normalized[key] = tuple(normalized[key])
    normalized["initial_state_bounds"] = {
        key: tuple(value) for key, value in normalized["initial_state_bounds"].items()
    }
    return normalized


def load_pilot_config(
    path: str | Path = "experiments/004-pilot/config.json",
) -> PilotConfig:
    config = PilotConfig(**_tuple_fields(json.loads(Path(path).read_text(encoding="utf-8"))))
    config.validate()
    return config


def load_case_matrix(
    path: str | Path = "experiments/004-pilot/case-matrix.json",
) -> tuple[PilotCase, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("case matrix schema changed")
    if [item.get("id") for item in payload.get("cases", [])] != list(CASE_IDS):
        raise ValueError("pilot case matrix changed")
    cases = []
    for item in payload["cases"]:
        value = dict(item)
        if "initial_state" in value:
            value["initial_state"] = tuple(value["initial_state"])
        if "fixture_command_mps2" in value:
            value["fixture_command_mps2"] = tuple(value["fixture_command_mps2"])
        case = PilotCase(**value)
        case.validate()
        cases.append(case)
    codes = {(case.geometry_code, case.fault_code) for case in cases}
    composite = {case.case_code for case in cases}
    if len(codes) != len(cases) or len(composite) != len(cases):
        raise ValueError("pilot case identities are not unique")
    return tuple(cases)
