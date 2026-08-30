from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_002.config import PilotConfig, load_config

COMBINED_STRATUM = "F7_combined_primary_dropout_actuator_degradation"
INFORMATION_ARMS = ("D", "PD")


@dataclass(frozen=True)
class CombinedInformationConfig:
    schema_version: str
    amends_schema_version: str
    historical_002c_freeze_id: str
    master_seed: int
    information_partition_code: int
    combined_stratum_code: int
    information_seeds: int
    arms: tuple[str, ...]
    replay_blocks: int
    one_sided_confidence: float
    incomplete_block_limit: float
    power_target: float
    power_simulations: int
    power_seed: int
    candidate_confirmatory_seeds_per_stratum: tuple[int, ...]
    confirmatory_strata: int
    h1_two_sided_alpha: float
    h2_one_sided_alpha: float
    h2_noninferiority_margin: float
    hazard_minimum_absolute_reduction: float
    hazard_minimum_relative_reduction: float
    dropout_onset_min_s: float
    dropout_onset_max_s: float
    dropout_duration_min_s: float
    dropout_duration_max_s: float
    actuator_onset_gap_min_s: float
    actuator_onset_gap_max_s: float
    actuator_duration_min_s: float
    actuator_duration_max_s: float
    actuator_effectiveness_min: float
    actuator_effectiveness_max: float

    @property
    def planned_blocks(self) -> int:
        return self.information_seeds

    @property
    def planned_episodes(self) -> int:
        return self.information_seeds * len(self.arms)

    def validate(self, production: PilotConfig) -> None:
        if self.information_partition_code <= 24:
            raise ValueError("002d partition must be disjoint from historical codes through 24")
        if self.information_partition_code == 16:
            raise ValueError("002d cannot consume the reserved confirmatory partition")
        if self.combined_stratum_code != 8:
            raise ValueError("combined information stratum must retain the original F7 code")
        if self.information_seeds != 299:
            raise ValueError("Experiment 002d is frozen at 299 root seeds")
        if self.information_seeds > 400:
            raise ValueError("Experiment 002d cannot exceed 400 root seeds")
        if self.arms != INFORMATION_ARMS:
            raise ValueError("Experiment 002d runs only the paired D and PD arms")
        if self.planned_episodes != 598:
            raise ValueError("Experiment 002d must contain exactly 598 episodes")
        zero_event_upper = 1.0 - (1.0 - self.one_sided_confidence) ** (
            1.0 / self.information_seeds
        )
        previous_upper = 1.0 - (1.0 - self.one_sided_confidence) ** (
            1.0 / (self.information_seeds - 1)
        )
        if not zero_event_upper < self.incomplete_block_limit <= previous_upper:
            raise ValueError("299 must remain the minimum exact zero-incomplete information size")
        if self.replay_blocks != 20 or self.replay_blocks >= self.information_seeds:
            raise ValueError("002d replay subset must remain fixed at 20 blocks")
        if self.confirmatory_strata != 8:
            raise ValueError("the original confirmatory estimand has eight equal strata")
        if self.candidate_confirmatory_seeds_per_stratum != (1000, 1500, 2000):
            raise ValueError("confirmatory candidate sizes must remain 1,000/1,500/2,000")
        if self.power_target != 0.95 or self.power_simulations != 200_000:
            raise ValueError("002d power target/simulation count changed")
        if self.h1_two_sided_alpha != 0.05 or self.h2_one_sided_alpha != 0.025:
            raise ValueError("002d must preserve the original 1.96 critical-value convention")
        if self.h2_noninferiority_margin != -0.03:
            raise ValueError("H2 noninferiority margin changed")
        if self.hazard_minimum_absolute_reduction != 0.02:
            raise ValueError("H1 absolute reduction requirement changed")
        if self.hazard_minimum_relative_reduction != 0.25:
            raise ValueError("H1 relative reduction requirement changed")
        if production.horizon_s != 600.0 or production.command_period_s != 1.0:
            raise ValueError("002d must use the corrected 600 s / 1 s production configuration")
        if not (
            self.dropout_onset_min_s < self.dropout_onset_max_s
            and self.dropout_duration_min_s < self.dropout_duration_max_s
            and self.actuator_onset_gap_min_s < self.actuator_onset_gap_max_s
            and self.actuator_duration_min_s < self.actuator_duration_max_s
            and 0.0
            < self.actuator_effectiveness_min
            < self.actuator_effectiveness_max
            <= 1.0
        ):
            raise ValueError("invalid combined-fault distribution bounds")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["arms"] = list(self.arms)
        data["candidate_confirmatory_seeds_per_stratum"] = list(
            self.candidate_confirmatory_seeds_per_stratum
        )
        return data


def load_combined_information_config(
    path: str | Path,
    production_path: str | Path = "experiments/002/config.json",
) -> tuple[CombinedInformationConfig, PilotConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["arms"] = tuple(data["arms"])
    data["candidate_confirmatory_seeds_per_stratum"] = tuple(
        data["candidate_confirmatory_seeds_per_stratum"]
    )
    config = CombinedInformationConfig(**data)
    production = load_config(production_path)
    config.validate(production)
    return config, production
