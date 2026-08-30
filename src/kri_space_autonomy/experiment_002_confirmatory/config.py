from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_002.config import PilotConfig, load_config

CONFIRMATORY_STRATA = (
    "F0_nominal",
    "F1_primary_range_bias",
    "F2_primary_dropout",
    "F3_monitor_channel_fault",
    "F4_shared_cause_navigation",
    "F5_persistent_model_upset",
    "F6_actuator_degradation",
    "F7_combined_primary_dropout_actuator_degradation",
)
MIXED_STRATA = ("F3_monitor_channel_fault", "F4_shared_cause_navigation")
FAULTED_STRATA = CONFIRMATORY_STRATA[1:]
HARM_CONTROL_STRATA = (
    "F3_monitor_channel_fault",
    "F4_shared_cause_navigation",
    "F6_actuator_degradation",
    "F7_combined_primary_dropout_actuator_degradation",
)
STRATUM_CODES = {name: index + 1 for index, name in enumerate(CONFIRMATORY_STRATA)}
EXPECTED_002D_FREEZE_ID = "0fc96ee320d25c2cec3c37ba9aa87467ca4a9ee62a138bd0bed37f3ad7dc053b"


@dataclass(frozen=True)
class ConfirmatoryConfig:
    schema_version: str
    amends_schema_version: str
    historical_002d_freeze_id: str
    master_seed: int
    partition_name: str
    partition_code: int
    seeds_per_stratum: int
    stratum_count: int
    stratum_weight: float
    arms: tuple[str, ...]
    bootstrap_replicates: int
    bootstrap_seed: int
    secondary_randomization_replicates: int
    secondary_randomization_seed: int
    h1_two_sided_alpha: float
    h2_one_sided_alpha: float
    h2_noninferiority_margin: float
    hazard_minimum_absolute_reduction: float
    hazard_minimum_relative_reduction: float
    secondary_holm_alpha: float
    harm_control_one_sided_family_alpha: float
    harm_control_margin: float
    incomplete_block_limit: float
    replay_blocks_per_stratum: int
    infrastructure_retry_allowlist: tuple[str, ...]

    @property
    def planned_blocks(self) -> int:
        return self.stratum_count * self.seeds_per_stratum

    @property
    def planned_episodes(self) -> int:
        return self.planned_blocks * len(self.arms)

    @property
    def harm_control_per_stratum_alpha(self) -> float:
        return self.harm_control_one_sided_family_alpha / len(HARM_CONTROL_STRATA)

    def validate(self, production: PilotConfig) -> None:
        if self.schema_version != "experiment-002-confirmatory-1.0":
            raise ValueError("unexpected final confirmatory schema")
        if self.amends_schema_version != "experiment-002d-combined-information-1.0":
            raise ValueError("final confirmation must follow the frozen 002d resolution")
        if self.historical_002d_freeze_id != EXPECTED_002D_FREEZE_ID:
            raise ValueError("historical 002d freeze identity changed")
        if self.master_seed != 2002:
            raise ValueError("confirmatory master seed must retain the Experiment 002 value")
        if self.partition_name != "future_confirmatory_reserved" or self.partition_code != 16:
            raise ValueError("final confirmation must use the existing reserved partition 16")
        if self.seeds_per_stratum != 1000 or self.stratum_count != 8:
            raise ValueError("final confirmation requires eight strata and 1,000 roots each")
        if self.stratum_count != len(CONFIRMATORY_STRATA) or self.stratum_weight != 0.125:
            raise ValueError("confirmatory strata must retain fixed equal 1/8 weights")
        if self.arms != ("R", "D", "PS", "PD"):
            raise ValueError("confirmatory arms must remain R/D/PS/PD")
        if self.planned_blocks != 8000 or self.planned_episodes != 32000:
            raise ValueError("canonical confirmatory size is 8,000 blocks / 32,000 episodes")
        if (self.bootstrap_replicates, self.bootstrap_seed) != (50000, 200217):
            raise ValueError("paired bootstrap count or seed changed")
        if (
            self.secondary_randomization_replicates,
            self.secondary_randomization_seed,
        ) != (200000, 200219):
            raise ValueError("secondary randomization procedure changed")
        if (self.h1_two_sided_alpha, self.h2_one_sided_alpha) != (0.05, 0.025):
            raise ValueError("H1/H2 alpha convention changed")
        if self.h2_noninferiority_margin != -0.03:
            raise ValueError("H2 noninferiority margin changed")
        if (
            self.hazard_minimum_absolute_reduction,
            self.hazard_minimum_relative_reduction,
        ) != (0.02, 0.25):
            raise ValueError("H1 decision effect thresholds changed")
        if self.secondary_holm_alpha != 0.05:
            raise ValueError("secondary Holm family alpha changed")
        if self.harm_control_one_sided_family_alpha != 0.05:
            raise ValueError("four-stratum harm family alpha changed")
        if self.harm_control_margin != 0.02:
            raise ValueError("stratum harm margin changed")
        if self.incomplete_block_limit != 0.01:
            raise ValueError("incomplete-block limit changed")
        if self.replay_blocks_per_stratum != 40:
            raise ValueError("same-platform replay subset changed")
        if self.infrastructure_retry_allowlist:
            raise ValueError("the final confirmatory infrastructure retry allowlist is empty")
        if production.horizon_s != 600.0 or production.command_period_s != 1.0:
            raise ValueError("confirmation requires corrected 600 s / 1 s production settings")
        if production.exogenous_period_s != 0.25 or production.evaluator_period_s != 1.0:
            raise ValueError("production exogenous/evaluator periods changed")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["arms"] = list(self.arms)
        data["infrastructure_retry_allowlist"] = list(
            self.infrastructure_retry_allowlist
        )
        return data


def load_confirmatory_config(
    path: str | Path,
    production_path: str | Path = "experiments/002/config.json",
) -> tuple[ConfirmatoryConfig, PilotConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["arms"] = tuple(data["arms"])
    data["infrastructure_retry_allowlist"] = tuple(
        data["infrastructure_retry_allowlist"]
    )
    study = ConfirmatoryConfig(**data)
    production = load_config(production_path)
    study.validate(production)
    return study, production
