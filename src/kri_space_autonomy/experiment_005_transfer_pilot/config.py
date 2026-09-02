from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import SCHEMA_VERSION

FOUNDATION_COMMIT = "344dfe4251e6b7aa654fc57c4f0cf9af21f6c342"
FOUNDATION_FREEZE_ID = "921c481726d6f078621ff3a355a7803af803bdc61a8a2da07ffb974a433b3be8"
FOUNDATION_READINESS_ID = "9ec734543fd3580e9a2990a16dc56747a0f75334f76bd2c7ae1fdc3647732e67"
E004_PILOT_CONFIG_SHA256 = "5e0b2b5e275b433844fca7a7853557029d12800adf6a042d272cc1bd93e13f24"
E004_PILOT_MATRIX_SHA256 = "a79b267a4df216592ed4bf4008cb313229b1db8a2eaa46b8648d0b6e4508263f"
CONFIGURATIONS = ("primary_reference", "independent_monitor_gate")
CASE_IDS = (
    "T00_nominal_transfer",
    "T01_truth_model_mismatch_stress",
    "T02_truth_keep_out_crossing_fixture",
    "T03_primary_navigation_bias",
    "T04_primary_navigation_dropout",
    "T05_monitor_navigation_bias",
    "T06_monitor_logic_false_trip",
    "T07_shared_navigation_bias",
    "T08_actuation_degradation",
    "T09_disturbance_burst",
)


@dataclass(frozen=True)
class TransferCase:
    id: str
    geometry_code: int
    challenge_code: int
    case_code: int
    domain: str
    fixture: str
    horizon_kind: str
    fault: str
    mechanics_noise_enabled: bool
    navigation_noise_enabled: bool
    intended_activation: str
    initial_relative_state: tuple[float, ...] | None = None
    fixture_command_mps2: tuple[float, float] | None = None

    def validate(self) -> None:
        if self.case_code != 100 * self.geometry_code + self.challenge_code:
            raise ValueError(f"non-injective transfer case code for {self.id}")
        if self.geometry_code < 0 or self.challenge_code < 0:
            raise ValueError("case entropy coordinates must be non-negative")
        if self.fixture == "stochastic_bounded_initial_state":
            if self.initial_relative_state is not None or self.fixture_command_mps2 is not None:
                raise ValueError("stochastic transfer cases may not freeze a state or command")
        elif self.fixture == "fixed_transfer_envelope_corner":
            if self.initial_relative_state is None or len(self.initial_relative_state) != 6:
                raise ValueError("model-mismatch fixture requires a six-state relative condition")
            if self.fixture_command_mps2 is not None:
                raise ValueError("model-mismatch fixture uses the online command path")
            if self.mechanics_noise_enabled or self.navigation_noise_enabled:
                raise ValueError("model-mismatch fixture must isolate truth/model discrepancy")
        elif self.fixture == "open_loop_truth_arc":
            if self.initial_relative_state is None or len(self.initial_relative_state) != 6:
                raise ValueError("truth-event fixture requires a six-state relative condition")
            if self.fixture_command_mps2 is None or len(self.fixture_command_mps2) != 2:
                raise ValueError("truth-event fixture requires a planar command")
            if self.mechanics_noise_enabled or self.navigation_noise_enabled:
                raise ValueError("truth-event fixture must isolate event geometry")
        else:
            raise ValueError("unknown transfer-pilot fixture")
        if self.horizon_kind not in {"standard", "model_mismatch", "truth_event_fixture"}:
            raise ValueError("unknown transfer-pilot horizon kind")


@dataclass(frozen=True)
class TransferPilotConfig:
    schema_version: str
    foundation_schema_version: str
    foundation_commit: str
    foundation_freeze_id: str
    foundation_readiness_id: str
    experiment_004_pilot_design_config_sha256: str
    experiment_004_pilot_case_matrix_sha256: str
    calibration_partition_code: int
    pilot_partition_code: int
    future_confirmatory_partition_code: int
    test_fixture_partition_code: int
    pilot_roots_per_case: int
    candidate_roots_per_case: tuple[int, ...]
    replay_roots_per_case: int
    case_count: int
    configuration_ids: tuple[str, ...]
    standard_horizon_s: float
    model_mismatch_horizon_s: float
    truth_event_fixture_horizon_s: float
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
    maximum_infrastructure_failures: int
    maximum_retries: int
    maximum_replacement_roots: int
    minimum_order_appearances_per_position_per_case: int
    analysis_mode: str
    scientific_hypothesis_defined: bool
    architecture_comparison_permitted: bool
    learned_policy_permitted: bool
    outcome_dependent_design_change_permitted: bool

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

    def horizon_for(self, case: TransferCase) -> float:
        return {
            "standard": self.standard_horizon_s,
            "model_mismatch": self.model_mismatch_horizon_s,
            "truth_event_fixture": self.truth_event_fixture_horizon_s,
        }[case.horizon_kind]

    def validate(self, *, root: str | Path = ".") -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unexpected transfer-pilot schema")
        if self.foundation_schema_version != "experiment-005-nonlinear-truth-foundation-1.0":
            raise ValueError("unexpected Experiment 005 foundation schema")
        identity = (
            self.foundation_commit,
            self.foundation_freeze_id,
            self.foundation_readiness_id,
        )
        if identity != (FOUNDATION_COMMIT, FOUNDATION_FREEZE_ID, FOUNDATION_READINESS_ID):
            raise ValueError("Experiment 005 foundation identity changed")
        if (
            self.experiment_004_pilot_design_config_sha256,
            self.experiment_004_pilot_case_matrix_sha256,
        ) != (E004_PILOT_CONFIG_SHA256, E004_PILOT_MATRIX_SHA256):
            raise ValueError("transferred E004 design-input identity changed")
        project = Path(root)
        transferred = {
            "experiments/004-pilot/config.json": E004_PILOT_CONFIG_SHA256,
            "experiments/004-pilot/case-matrix.json": E004_PILOT_MATRIX_SHA256,
        }
        for relative, expected in transferred.items():
            path = project / relative
            observed = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            if observed != expected:
                raise ValueError(f"transferred E004 design input changed: {relative}")
        if (
            self.calibration_partition_code,
            self.pilot_partition_code,
            self.future_confirmatory_partition_code,
            self.test_fixture_partition_code,
        ) != (51, 52, 53, 951):
            raise ValueError("Experiment 005 transfer partition contract changed")
        if len({51, 52, 53, 951}) != 4:
            raise ValueError("Experiment 005 transfer partitions overlap")
        if self.configuration_ids != CONFIGURATIONS:
            raise ValueError("diagnostic configurations changed")
        if self.case_count != len(CASE_IDS) or self.pilot_roots_per_case != 2:
            raise ValueError("frozen transfer-pilot coverage count changed")
        if self.candidate_roots_per_case != (1, 2, 4):
            raise ValueError("outcome-blind root-count candidates changed")
        if self.replay_roots_per_case != 1:
            raise ValueError("replay root count changed")
        if (self.pilot_blocks, self.pilot_episodes) != (20, 40):
            raise ValueError("transfer-pilot block or episode count changed")
        if (self.replay_blocks, self.replay_episodes) != (10, 20):
            raise ValueError("transfer-pilot replay count changed")
        if (
            self.standard_horizon_s,
            self.model_mismatch_horizon_s,
            self.truth_event_fixture_horizon_s,
        ) != (300.0, 120.0, 1.0):
            raise ValueError("transfer-pilot horizons changed")
        expected_bounds = {
            "x_radial_m": (-2.0, 2.0),
            "y_alongtrack_m": (-100.0, -95.0),
            "vx_radial_mps": (-0.02, 0.02),
            "vy_alongtrack_mps": (0.10, 0.14),
        }
        if self.initial_state_bounds != expected_bounds:
            raise ValueError("ordinary initial-state transfer envelope changed")
        if self.minimum_order_appearances_per_position_per_case != 1:
            raise ValueError("within-block order coverage changed")
        if self.analysis_mode != "descriptive_mechanistic_gate_only":
            raise ValueError("noninferential analysis boundary changed")
        if any(
            (
                self.scientific_hypothesis_defined,
                self.architecture_comparison_permitted,
                self.learned_policy_permitted,
                self.outcome_dependent_design_change_permitted,
            )
        ):
            raise ValueError("inferential or outcome-dependent transfer design was enabled")
        if (
            self.maximum_infrastructure_failures,
            self.maximum_retries,
            self.maximum_replacement_roots,
        ) != (0, 0, 0):
            raise ValueError("strict infrastructure limits changed")
        positive = (
            self.bias_duration_s,
            self.dropout_duration_s,
            self.monitor_logic_duration_s,
            self.actuation_duration_s,
            self.actuator_uncertainty_sigma_mps2,
            self.process_disturbance_clip_sigma,
        )
        if not all(np.isfinite(value) and value > 0.0 for value in positive):
            raise ValueError("transfer challenge values must be finite and positive")
        if not 0.0 < self.actuation_effectiveness < 1.0:
            raise ValueError("actuation effectiveness must represent degradation")
        if len(self.navigation_bias) != 4 or len(self.disturbance_bias_mps2) != 2:
            raise ValueError("transferred challenge vectors have wrong dimensions")


def _normalize_config(data: dict[str, Any]) -> dict[str, Any]:
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
    path: str | Path = "experiments/005-transfer-pilot/config.json",
    *,
    root: str | Path = ".",
) -> TransferPilotConfig:
    config = TransferPilotConfig(**_normalize_config(json.loads(Path(path).read_text())))
    config.validate(root=root)
    return config


def load_case_matrix(
    path: str | Path = "experiments/005-transfer-pilot/case-matrix.json",
) -> tuple[TransferCase, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("transfer case-matrix schema changed")
    if [item.get("id") for item in payload.get("cases", [])] != list(CASE_IDS):
        raise ValueError("transfer case matrix changed")
    cases: list[TransferCase] = []
    for item in payload["cases"]:
        value = dict(item)
        if value.get("initial_relative_state") is not None:
            value["initial_relative_state"] = tuple(value["initial_relative_state"])
        if value.get("fixture_command_mps2") is not None:
            value["fixture_command_mps2"] = tuple(value["fixture_command_mps2"])
        case = TransferCase(**value)
        case.validate()
        cases.append(case)
    coordinates = {(case.geometry_code, case.challenge_code) for case in cases}
    codes = {case.case_code for case in cases}
    if len(coordinates) != len(cases) or len(codes) != len(cases):
        raise ValueError("transfer case identities are not unique")
    return tuple(cases)
