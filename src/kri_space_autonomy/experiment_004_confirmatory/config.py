from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION

EXPECTED_BASE = "57c1a272136e2e5a30afd01eea6f6adc45007bb3"
FOUNDATION_FREEZE_ID = "54a0f1a8dc985fba02973c09ac994fbc76a2ef1abbc7dfe5def82585c85aaa14"
FOUNDATION_READINESS_ID = "fd0ea450e8b5f53a4447cf3910e7e3b494ed6bace33da0055f64e77fd9049404"
PILOT_FREEZE_ID = "8f0867a4eaa34c3fb1aef1d8fff62fb579e3099391c5c722b87a3dc6b0746079"
PILOT_READINESS_ID = "5c39bbdc231f7355b9afc79387816b604dbca2f16015e0d179b48f77b6d0d809"
CONFIGURATIONS = ("primary_reference", "independent_monitor_gate")
PRIMARY_STRATA = (
    "P04_primary_navigation_bias",
    "P05_primary_navigation_dropout",
)
ASSURANCE_STRATA = (
    "P00_nominal_feasibility",
    *PRIMARY_STRATA,
    "P06_monitor_navigation_bias",
    "P07_monitor_logic_false_trip",
    "P08_shared_navigation_bias",
    "P09_actuation_degradation",
    "P10_disturbance_burst",
)
ROOTS_BY_STRATUM = {
    "P00_nominal_feasibility": 64,
    "P04_primary_navigation_bias": 534,
    "P05_primary_navigation_dropout": 534,
    "P06_monitor_navigation_bias": 64,
    "P07_monitor_logic_false_trip": 64,
    "P08_shared_navigation_bias": 64,
    "P09_actuation_degradation": 64,
    "P10_disturbance_burst": 64,
}


@dataclass(frozen=True)
class ConfirmatoryConfig:
    schema_version: str
    base_commit: str
    foundation_freeze_id: str
    foundation_readiness_id: str
    pilot_freeze_id: str
    pilot_readiness_id: str
    master_seed: int
    confirmatory_partition_code: int
    test_fixture_partition_code: int
    configurations: tuple[str, ...]
    strata: tuple[str, ...]
    primary_strata: tuple[str, ...]
    roots_by_stratum: dict[str, int]
    standard_horizon_s: float
    primary_one_sided_alpha: float
    primary_planning_net_reduction: float
    primary_minimum_reportable_net_reduction: float
    primary_target_power: float
    mission_harm_margin: float
    mission_harm_planning_rate: float
    replay_roots_per_stratum: int
    maximum_infrastructure_failures: int
    secondary_inferential_family_defined: bool
    replacement_extension_or_retry_allowed: bool
    learned_policy_claim_allowed: bool

    @property
    def primary_roots(self) -> int:
        return sum(self.roots_by_stratum[name] for name in self.primary_strata)

    @property
    def planned_blocks(self) -> int:
        return sum(self.roots_by_stratum.values())

    @property
    def planned_episodes(self) -> int:
        return self.planned_blocks * len(self.configurations)

    @property
    def replay_blocks(self) -> int:
        return len(self.strata) * self.replay_roots_per_stratum

    @property
    def replay_episodes(self) -> int:
        return self.replay_blocks * len(self.configurations)

    def validate(self) -> None:
        identities = (
            self.schema_version,
            self.base_commit,
            self.foundation_freeze_id,
            self.foundation_readiness_id,
            self.pilot_freeze_id,
            self.pilot_readiness_id,
        )
        expected = (
            SCHEMA_VERSION,
            EXPECTED_BASE,
            FOUNDATION_FREEZE_ID,
            FOUNDATION_READINESS_ID,
            PILOT_FREEZE_ID,
            PILOT_READINESS_ID,
        )
        if identities != expected:
            raise ValueError("Experiment 004 evidence-chain identity changed")
        partition_identity = (
            self.master_seed,
            self.confirmatory_partition_code,
            self.test_fixture_partition_code,
        )
        if partition_identity != (4004, 44, 941):
            raise ValueError("confirmatory seed domain changed")
        if self.configurations != CONFIGURATIONS:
            raise ValueError("confirmatory configurations changed")
        if self.strata != ASSURANCE_STRATA or self.primary_strata != PRIMARY_STRATA:
            raise ValueError("confirmatory stratum registry changed")
        if self.roots_by_stratum != ROOTS_BY_STRATUM:
            raise ValueError("confirmatory root allocation changed")
        if self.standard_horizon_s != 300.0:
            raise ValueError("confirmatory horizon changed")
        if (
            self.primary_one_sided_alpha,
            self.primary_planning_net_reduction,
            self.primary_minimum_reportable_net_reduction,
            self.primary_target_power,
        ) != (0.025, 0.10, 0.05, 0.90):
            raise ValueError("primary analysis contract changed")
        if (self.mission_harm_margin, self.mission_harm_planning_rate) != (0.05, 0.01):
            raise ValueError("mission-performance contract changed")
        if self.primary_roots != 1068:
            raise ValueError("primary sample size must remain 1,068 paired roots")
        if (self.planned_blocks, self.planned_episodes) != (1452, 2904):
            raise ValueError("confirmatory block or episode count changed")
        if (self.replay_roots_per_stratum, self.replay_blocks, self.replay_episodes) != (
            8,
            64,
            128,
        ):
            raise ValueError("outcome-blind replay contract changed")
        if any(value < self.replay_roots_per_stratum for value in self.roots_by_stratum.values()):
            raise ValueError("replay count exceeds a stratum count")
        if any(value % 2 for value in self.roots_by_stratum.values()):
            raise ValueError("every stratum must permit balanced two-position run order")
        if (
            self.maximum_infrastructure_failures != 0
            or self.secondary_inferential_family_defined
            or self.replacement_extension_or_retry_allowed
            or self.learned_policy_claim_allowed
        ):
            raise ValueError("fail-closed confirmatory restrictions changed")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        }


def load_confirmatory_config(
    path: str | Path = "experiments/004-confirmatory/config.json",
) -> ConfirmatoryConfig:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("configurations", "strata", "primary_strata"):
        value[key] = tuple(value[key])
    value["roots_by_stratum"] = {
        str(key): int(count) for key, count in value["roots_by_stratum"].items()
    }
    config = ConfirmatoryConfig(**value)
    config.validate()
    return config
