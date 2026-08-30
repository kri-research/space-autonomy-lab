from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_002.config import PilotConfig, load_config


@dataclass(frozen=True)
class NumericalBounds:
    range_m: float
    velocity_mps: float
    achieved_acceleration_mps2: float
    propellant_fraction: float
    event_time_s: float
    dwell_fraction: float
    collision_residual_m: float
    depletion_residual_fraction: float

    def scaled(self, factor: float) -> NumericalBounds:
        return NumericalBounds(
            range_m=self.range_m * factor,
            velocity_mps=self.velocity_mps * factor,
            achieved_acceleration_mps2=self.achieved_acceleration_mps2 * factor,
            propellant_fraction=self.propellant_fraction * factor,
            event_time_s=self.event_time_s * factor,
            dwell_fraction=self.dwell_fraction * factor,
            collision_residual_m=self.collision_residual_m * factor,
            depletion_residual_fraction=self.depletion_residual_fraction * factor,
        )

    def to_dict(self) -> dict[str, float]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class NumericalAmendmentConfig:
    schema_version: str
    amends_schema_version: str
    historical_002b_freeze_id: str
    master_seed: int
    replay_partition_code: int
    replay_seeds_per_stratum: int
    command_period_s: float
    observation_period_s: float
    reference_fine_rtol: float
    reference_fine_atol: float
    reference_fine_max_step_fraction: float
    reference_coarse_rtol: float
    reference_coarse_atol: float
    reference_coarse_max_step_fraction: float
    convergence_bound_fraction: float
    simultaneous_event_tolerance_s: float
    replay_command_patterns: tuple[str, ...]
    acceptance_bounds: NumericalBounds

    @property
    def replay_cases(self) -> int:
        return 6 * self.replay_seeds_per_stratum * len(self.replay_command_patterns)

    def validate(self, production: PilotConfig) -> None:
        if self.schema_version != "experiment-002c-numerical-1.0":
            raise ValueError("unexpected Experiment 002c schema")
        if self.amends_schema_version != "experiment-002b-amendment-1.0":
            raise ValueError("002c must amend the frozen Experiment 002b amendment")
        if self.master_seed != production.master_seed:
            raise ValueError("002c retains the generator master seed and changes partition domain")
        if self.replay_partition_code != 24:
            raise ValueError("002c replay partition is prospectively frozen at code 24")
        if self.replay_seeds_per_stratum != 1 or self.replay_cases != 24:
            raise ValueError("002c is prospectively bounded at one seed/stratum and 24 traces")
        if self.command_period_s != 1.0 or self.observation_period_s != 1.0:
            raise ValueError("002c replays only the frozen 1.0 s operational command history")
        expected_patterns = (
            "pd_operational",
            "maximum_closing",
            "maximum_separating",
            "alternating_extrema",
        )
        if self.replay_command_patterns != expected_patterns:
            raise ValueError("unexpected 002c fixed-command replay patterns")
        if not (
            0.0 < self.reference_fine_atol < self.reference_coarse_atol
            and 0.0 < self.reference_fine_rtol < self.reference_coarse_rtol
        ):
            raise ValueError("fine reference tolerances must be tighter than coarse tolerances")
        if not (
            0.0 < self.reference_fine_max_step_fraction
            < self.reference_coarse_max_step_fraction
            <= 0.5
        ):
            raise ValueError("fine reference maximum step must be smaller than coarse")
        if self.convergence_bound_fraction != 0.25:
            raise ValueError(
                "reference convergence fraction must remain prospectively fixed at 25%"
            )
        if self.simultaneous_event_tolerance_s != 1e-12:
            raise ValueError("unexpected simultaneous-event tolerance")
        expected_bounds = NumericalBounds(
            range_m=1e-8,
            velocity_mps=1e-10,
            achieved_acceleration_mps2=1e-12,
            propellant_fraction=1e-10,
            event_time_s=2e-7,
            dwell_fraction=1e-10,
            collision_residual_m=1e-10,
            depletion_residual_fraction=1e-12,
        )
        if self.acceptance_bounds != expected_bounds:
            raise ValueError("002c acceptance bounds differ from the completed diagnosis")

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.__dict__)
        result["replay_command_patterns"] = list(self.replay_command_patterns)
        result["acceptance_bounds"] = self.acceptance_bounds.to_dict()
        return result


def load_numerical_amendment_config(
    path: str | Path,
    production_path: str | Path = "experiments/002/config.json",
) -> tuple[NumericalAmendmentConfig, PilotConfig]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["replay_command_patterns"] = tuple(data["replay_command_patterns"])
    data["acceptance_bounds"] = NumericalBounds(**data["acceptance_bounds"])
    amendment = NumericalAmendmentConfig(**data)
    production = load_config(production_path)
    amendment.validate(production)
    return amendment, production
