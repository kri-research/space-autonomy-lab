from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION

BASE_COMMIT = "46c6de41afa46e7e43b1c6074e59ba54dd3d99b8"
FOUNDATION_FREEZE_ID = "921c481726d6f078621ff3a355a7803af803bdc61a8a2da07ffb974a433b3be8"
FOUNDATION_READINESS_ID = "9ec734543fd3580e9a2990a16dc56747a0f75334f76bd2c7ae1fdc3647732e67"
TRANSFER_FREEZE_ID = "3fa9fd6e9e4d3146af6495c07599ed792cfb52ce16e90d0dca234ed64295be8b"
TRANSFER_READINESS_ID = "ebc98c9eb9b14d2dc85351d68ca3c5c84791e050f2be038c7fdd9067ef6ce2f3"
AMENDMENT_FREEZE_ID = "01504ff16ccf8a79dad67f88c4d40920be39dfa929169ccb72fdfcede18b34c1"
AMENDMENT_READINESS_ID = "3181e1a9b40c3ab32b684934d8c975b3eeeee44c2b38cd9dc80e0f0c589328c0"
CLOSEOUT_MANIFEST_SHA256 = "5c33237028e0ea23f52413c19fe419aa1bead2fbc7378c2e8f1b30d904d1d804"
RESULT_VERIFICATION_SHA256 = "5e3cbf07d78f4d02b2f5c95e26b5d7e6fe0932e68b7bd5382231346890fec782"
CONFIGURATIONS = ("primary_reference", "independent_monitor_gate")
PRIMARY_CASES = ("T03_primary_navigation_bias", "T04_primary_navigation_dropout")
CASE_WEIGHTS = {name: 0.5 for name in PRIMARY_CASES}
ROOTS_BY_CASE = {name: 534 for name in PRIMARY_CASES}


@dataclass(frozen=True)
class ConfirmatoryConfig:
    schema_version: str
    base_commit: str
    foundation_freeze_id: str
    foundation_readiness_id: str
    transfer_pilot_freeze_id: str
    transfer_pilot_readiness_id: str
    replacement_amendment_freeze_id: str
    replacement_amendment_readiness_id: str
    partition_54_closeout_manifest_sha256: str
    partition_54_result_verification_sha256: str
    master_seed: int
    confirmatory_partition_code: int
    test_fixture_partition_code: int
    configurations: tuple[str, ...]
    cases: tuple[str, ...]
    case_weights: dict[str, float]
    roots_by_case: dict[str, int]
    standard_horizon_s: float
    minimum_covariance_eigenvalue_lower_bound: float
    maximum_covariance_trace_exclusive_upper_bound: float
    primary_one_sided_alpha: float
    primary_planning_net_reduction: float
    primary_minimum_reportable_net_reduction: float
    primary_target_power: float
    mission_harm_margin: float
    mission_harm_planning_rate: float
    replay_roots_per_case: int
    maximum_infrastructure_failures: int
    maximum_retries: int
    maximum_replacement_roots: int
    secondary_inferential_family_defined: bool
    outcome_dependent_design_change_permitted: bool
    partition_54_outcomes_used_for_design: bool
    learned_policy_claim_allowed: bool

    @property
    def primary_roots(self) -> int:
        return sum(self.roots_by_case[name] for name in self.cases)

    @property
    def planned_blocks(self) -> int:
        return self.primary_roots

    @property
    def planned_episodes(self) -> int:
        return self.planned_blocks * len(self.configurations)

    @property
    def replay_blocks(self) -> int:
        return len(self.cases) * self.replay_roots_per_case

    @property
    def replay_episodes(self) -> int:
        return self.replay_blocks * len(self.configurations)

    def validate(self) -> None:
        observed_identity = (
            self.schema_version,
            self.base_commit,
            self.foundation_freeze_id,
            self.foundation_readiness_id,
            self.transfer_pilot_freeze_id,
            self.transfer_pilot_readiness_id,
            self.replacement_amendment_freeze_id,
            self.replacement_amendment_readiness_id,
            self.partition_54_closeout_manifest_sha256,
            self.partition_54_result_verification_sha256,
        )
        expected_identity = (
            SCHEMA_VERSION,
            BASE_COMMIT,
            FOUNDATION_FREEZE_ID,
            FOUNDATION_READINESS_ID,
            TRANSFER_FREEZE_ID,
            TRANSFER_READINESS_ID,
            AMENDMENT_FREEZE_ID,
            AMENDMENT_READINESS_ID,
            CLOSEOUT_MANIFEST_SHA256,
            RESULT_VERIFICATION_SHA256,
        )
        if observed_identity != expected_identity:
            raise ValueError("Experiment 005 confirmatory evidence identity changed")
        partition_identity = (
            self.master_seed,
            self.confirmatory_partition_code,
            self.test_fixture_partition_code,
        )
        if partition_identity != (5005, 53, 951):
            raise ValueError("Experiment 005 confirmatory seed domain changed")
        if self.configurations != CONFIGURATIONS:
            raise ValueError("confirmatory configurations changed")
        if self.cases != PRIMARY_CASES:
            raise ValueError("confirmatory case population changed")
        if self.case_weights != CASE_WEIGHTS or self.roots_by_case != ROOTS_BY_CASE:
            raise ValueError("confirmatory weights or allocation changed")
        if sum(self.case_weights.values()) != 1.0:
            raise ValueError("confirmatory case weights must sum to one")
        if self.standard_horizon_s != 300.0:
            raise ValueError("confirmatory horizon changed")
        if (
            self.minimum_covariance_eigenvalue_lower_bound,
            self.maximum_covariance_trace_exclusive_upper_bound,
        ) != (-1e-12, 1_000_000.0):
            raise ValueError("confirmatory covariance validity bounds changed")
        if (
            self.primary_one_sided_alpha,
            self.primary_planning_net_reduction,
            self.primary_minimum_reportable_net_reduction,
            self.primary_target_power,
        ) != (0.025, 0.10, 0.05, 0.90):
            raise ValueError("primary analysis contract changed")
        if (self.mission_harm_margin, self.mission_harm_planning_rate) != (0.05, 0.01):
            raise ValueError("mission-harm contract changed")
        if self.primary_roots != 1068:
            raise ValueError("primary sample size must remain 1,068 paired roots")
        if (self.planned_blocks, self.planned_episodes) != (1068, 2136):
            raise ValueError("confirmatory block or episode count changed")
        if (self.replay_roots_per_case, self.replay_blocks, self.replay_episodes) != (
            8,
            16,
            32,
        ):
            raise ValueError("outcome-blind replay contract changed")
        if any(count % 2 for count in self.roots_by_case.values()):
            raise ValueError("case counts must permit balanced two-position order")
        restrictions = (
            self.maximum_infrastructure_failures,
            self.maximum_retries,
            self.maximum_replacement_roots,
            self.secondary_inferential_family_defined,
            self.outcome_dependent_design_change_permitted,
            self.partition_54_outcomes_used_for_design,
            self.learned_policy_claim_allowed,
        )
        if restrictions != (0, 0, 0, False, False, False, False):
            raise ValueError("fail-closed confirmatory restrictions changed")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        }


def load_confirmatory_config(
    path: str | Path = "experiments/005-confirmatory/config.json",
) -> ConfirmatoryConfig:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("configurations", "cases"):
        value[key] = tuple(value[key])
    value["case_weights"] = {
        str(key): float(weight) for key, weight in value["case_weights"].items()
    }
    value["roots_by_case"] = {
        str(key): int(count) for key, count in value["roots_by_case"].items()
    }
    config = ConfirmatoryConfig(**value)
    config.validate()
    return config
