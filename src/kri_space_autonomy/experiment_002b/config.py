from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_002.config import PilotConfig, load_config


@dataclass(frozen=True)
class AmendmentConfig:
    schema_version: str
    amends_schema_version: str
    historical_freeze_id: str
    master_seed: int
    operational_partition_code: int
    rate_partition_code: int
    replay_partition_code: int
    operational_seeds_per_stratum: int
    rate_seeds_per_stratum: int
    replay_seeds_per_stratum: int
    operational_command_period_s: float
    operational_observation_period_s: float
    diagnostic_command_periods_s: tuple[float, ...]
    diagnostic_observation_periods_s: tuple[float, ...]
    one_sided_confidence: float
    zero_event_upper_margin: float
    numerical_error_tolerance: float
    reference_rtol: float
    reference_atol: float
    replay_command_patterns: tuple[str, ...]

    @property
    def operational_blocks(self) -> int:
        return 6 * self.operational_seeds_per_stratum

    @property
    def rate_blocks(self) -> int:
        return 6 * self.rate_seeds_per_stratum

    @property
    def rate_episodes(self) -> int:
        return (
            self.rate_blocks
            * len(self.diagnostic_command_periods_s)
            * len(self.diagnostic_observation_periods_s)
        )

    @property
    def replay_cases(self) -> int:
        return 6 * self.replay_seeds_per_stratum * len(self.replay_command_patterns)

    @property
    def zero_event_upper_bound(self) -> float:
        return 1.0 - (1.0 - self.one_sided_confidence) ** (
            1.0 / self.operational_seeds_per_stratum
        )

    @property
    def minimum_zero_event_n(self) -> int:
        alpha = 1.0 - self.one_sided_confidence
        return math.ceil(math.log(alpha) / math.log(1.0 - self.zero_event_upper_margin))

    def validate(self, production: PilotConfig) -> None:
        if self.schema_version != "experiment-002b-amendment-1.0":
            raise ValueError("unexpected Experiment 002b schema")
        if self.amends_schema_version != production.schema_version:
            raise ValueError("amended schema does not match the production Experiment 002 config")
        if self.master_seed != production.master_seed:
            raise ValueError("002b retains the generator master seed and changes partition domains")
        partition_codes = {
            self.operational_partition_code,
            self.rate_partition_code,
            self.replay_partition_code,
        }
        if len(partition_codes) != 3 or min(partition_codes) <= 19:
            raise ValueError("002b partition codes must be unique and disjoint from Experiment 002")
        if self.operational_seeds_per_stratum != 150:
            raise ValueError("operational validation is frozen at 150 seeds per stratum")
        if self.operational_seeds_per_stratum < self.minimum_zero_event_n:
            raise ValueError("operational sample does not establish the frozen zero-event margin")
        if self.zero_event_upper_bound >= self.zero_event_upper_margin:
            raise ValueError("zero-event upper bound must be strictly below the frozen margin")
        if self.operational_seeds_per_stratum % 2 or self.rate_seeds_per_stratum % 2:
            raise ValueError("mixed strata require even sample sizes for exact subtype balance")
        if self.rate_seeds_per_stratum != 12:
            raise ValueError("rate-decomposition feasibility sample is frozen at 12/stratum")
        if self.replay_seeds_per_stratum != 1:
            raise ValueError("fixed-command suite is frozen at one seed/stratum")
        if (
            self.operational_command_period_s != 1.0
            or self.operational_observation_period_s != 1.0
        ):
            raise ValueError("only the 1.0 s/1.0 s configuration is operationally qualified")
        expected_periods = (1.0, 0.5, 0.25)
        if self.diagnostic_command_periods_s != expected_periods:
            raise ValueError("unexpected diagnostic command-period grid")
        if self.diagnostic_observation_periods_s != expected_periods:
            raise ValueError("unexpected diagnostic observation-period grid")
        for period in (*expected_periods, self.operational_observation_period_s):
            ratio = period / production.exogenous_period_s
            if abs(ratio - round(ratio)) > 1e-12:
                raise ValueError("periods must align with the frozen exogenous grid")
        if not 0.0 < self.reference_atol < self.numerical_error_tolerance:
            raise ValueError("reference absolute tolerance must be below the replay gate")
        if not 0.0 < self.reference_rtol < self.numerical_error_tolerance:
            raise ValueError("reference relative tolerance must be below the replay gate")
        if self.numerical_error_tolerance != 1e-10:
            raise ValueError("fixed-command replay tolerance must remain 1e-10")
        expected_patterns = (
            "pd_operational",
            "maximum_closing",
            "maximum_separating",
            "alternating_extrema",
        )
        if self.replay_command_patterns != expected_patterns:
            raise ValueError("unexpected fixed-command replay patterns")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["diagnostic_command_periods_s"] = list(self.diagnostic_command_periods_s)
        data["diagnostic_observation_periods_s"] = list(
            self.diagnostic_observation_periods_s
        )
        data["replay_command_patterns"] = list(self.replay_command_patterns)
        return data


def load_amendment_config(
    path: str | Path,
    production_path: str | Path = "experiments/002/config.json",
) -> tuple[AmendmentConfig, PilotConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in (
        "diagnostic_command_periods_s",
        "diagnostic_observation_periods_s",
        "replay_command_patterns",
    ):
        data[key] = tuple(data[key])
    amendment = AmendmentConfig(**data)
    production = load_config(production_path)
    amendment.validate(production)
    return amendment, production
