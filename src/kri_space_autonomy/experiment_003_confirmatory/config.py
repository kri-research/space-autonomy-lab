from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_002.config import PilotConfig
from kri_space_autonomy.experiment_003.config import ARMS, ESTIMATOR_STRATA, Experiment003Config
from kri_space_autonomy.experiment_003.config import load_config as load_foundation_config

FOUNDATION_FREEZE_ID = "d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297"
FAULTED_STRATA = ESTIMATOR_STRATA[1:]
PRIMARY_SENSITIVITIES = (
    "worst_case_missing_primary_cells",
    "physical_hazard_only",
    "all_available_D_PD_pairs",
)


@dataclass(frozen=True)
class ConfirmatoryConfig:
    schema_version: str
    foundation_schema_version: str
    foundation_freeze_id: str
    master_seed: int
    partition_name: str
    partition_code: int
    roots_per_stratum: int
    stratum_count: int
    stratum_weight: float
    arms: tuple[str, ...]
    bootstrap_replicates: int
    bootstrap_seed: int
    secondary_randomization_replicates: int
    secondary_randomization_seed: int
    h1_two_sided_alpha: float
    h1_minimum_absolute_reduction: float
    h1_minimum_relative_reduction: float
    h2_one_sided_alpha: float
    h2_noninferiority_margin: float
    secondary_holm_alpha: float
    incomplete_block_limit: float
    replay_roots_per_stratum: int
    primary_sensitivities: tuple[str, ...]
    infrastructure_retry_allowlist: tuple[str, ...]

    @property
    def planned_blocks(self) -> int:
        return self.stratum_count * self.roots_per_stratum

    @property
    def planned_episodes(self) -> int:
        return self.planned_blocks * len(self.arms)

    @property
    def replay_episodes(self) -> int:
        return self.stratum_count * self.replay_roots_per_stratum * len(self.arms)

    def validate(self, foundation: Experiment003Config, production: PilotConfig) -> None:
        if self.schema_version != "experiment-003-confirmatory-1.0":
            raise ValueError("unexpected Experiment 003 confirmatory schema")
        if self.foundation_schema_version != foundation.schema_version:
            raise ValueError("foundation schema identity changed")
        if self.foundation_freeze_id != FOUNDATION_FREEZE_ID:
            raise ValueError("foundation freeze identity changed")
        if (self.master_seed, self.partition_name, self.partition_code) != (
            3003,
            "experiment_003_confirmatory_reserved",
            32,
        ):
            raise ValueError("confirmatory seed domain changed")
        if foundation.confirmatory_partition_code != self.partition_code:
            raise ValueError("partition 32 is not the frozen foundation reservation")
        if (self.roots_per_stratum, self.stratum_count) != (750, 7):
            raise ValueError("confirmation requires seven strata and 750 roots each")
        if self.stratum_count != len(ESTIMATOR_STRATA) or self.stratum_weight != 1.0 / 7.0:
            raise ValueError("confirmatory strata must retain equal 1/7 weights")
        if self.arms != ARMS or self.planned_blocks != 5250 or self.planned_episodes != 21000:
            raise ValueError("canonical size is 5,250 paired blocks / 21,000 episodes")
        if (self.bootstrap_replicates, self.bootstrap_seed) != (50_000, 300318):
            raise ValueError("paired bootstrap procedure changed")
        if (
            self.secondary_randomization_replicates,
            self.secondary_randomization_seed,
        ) != (200_000, 300319):
            raise ValueError("H5b randomization procedure changed")
        if (
            self.h1_two_sided_alpha,
            self.h1_minimum_absolute_reduction,
            self.h1_minimum_relative_reduction,
        ) != (0.05, 0.02, 0.25):
            raise ValueError("H1 rules changed")
        if (self.h2_one_sided_alpha, self.h2_noninferiority_margin) != (0.025, -0.03):
            raise ValueError("H2 rules changed")
        if self.secondary_holm_alpha != 0.05 or self.incomplete_block_limit != 0.01:
            raise ValueError("multiplicity or completeness rule changed")
        if self.replay_roots_per_stratum != 30 or self.replay_episodes != 840:
            raise ValueError("frozen replay subset must be 30 roots per stratum / 840 episodes")
        if self.primary_sensitivities != PRIMARY_SENSITIVITIES:
            raise ValueError("exactly the three frozen primary sensitivities are required")
        if self.infrastructure_retry_allowlist:
            raise ValueError("outcome-era retry allowlist must remain empty")
        if production.horizon_s != 600.0 or production.command_period_s != 1.0:
            raise ValueError("frozen Experiment 003 production schedule changed")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in self.__dict__.items()
        }


def load_confirmatory_config(
    path: str | Path,
    foundation_path: str | Path = "experiments/003/config.json",
    production_path: str | Path = "experiments/002/config.json",
) -> tuple[ConfirmatoryConfig, Experiment003Config, PilotConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("arms", "primary_sensitivities", "infrastructure_retry_allowlist"):
        data[key] = tuple(data[key])
    study = ConfirmatoryConfig(**data)
    foundation, production = load_foundation_config(foundation_path, production_path)
    study.validate(foundation, production)
    return study, foundation, production
