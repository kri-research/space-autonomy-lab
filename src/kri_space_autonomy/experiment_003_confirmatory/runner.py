from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_003.config import Experiment003Config
from kri_space_autonomy.experiment_003.runner import Experiment003Episode, run_arm
from kri_space_autonomy.experiment_003.seeds import (
    Experiment003Scenario,
    canonical_json,
    materialize_exogenous,
    sha256_bytes,
)

from .config import ConfirmatoryConfig


def scenario_from_dict(row: dict[str, Any]) -> Experiment003Scenario:
    value = dict(row)
    value["arm_run_order"] = tuple(value["arm_run_order"])
    return Experiment003Scenario(**value)


def run_block_for_partition(
    study: ConfirmatoryConfig,
    foundation: Experiment003Config,
    production: Any,
    scenario: Experiment003Scenario,
    policy: FrozenPolicy,
    config_hash: str,
    *,
    partition_code: int,
) -> list[Experiment003Episode]:
    """Thin phase wrapper around the frozen Experiment 003 arm runner."""

    streams, hashes = materialize_exogenous(
        foundation,
        production,
        scenario.stratum_id,
        scenario.replicate,
        partition_code=partition_code,
    )
    for name, value in hashes.items():
        if scenario.stream_hashes.get(name) != value:
            raise RuntimeError(f"exogenous hash drift for {scenario.root_seed_id}/{name}")
    if set(scenario.arm_run_order) != set(study.arms):
        raise RuntimeError("scenario arm order does not contain the frozen four arms")
    rows: list[Experiment003Episode] = []
    for run_order, arm in enumerate(scenario.arm_run_order, start=1):
        row, _ = run_arm(
            foundation,
            production,
            scenario,
            streams,
            arm,
            run_order,
            policy,
            config_hash,
        )
        rows.append(
            replace(
                row,
                schema_version=study.schema_version,
                study_phase="confirmatory",
            )
        )
    return rows


def run_confirmatory_block(
    study: ConfirmatoryConfig,
    foundation: Experiment003Config,
    production: Any,
    scenario: Experiment003Scenario,
    policy: FrozenPolicy,
    config_hash: str,
) -> list[Experiment003Episode]:
    return run_block_for_partition(
        study,
        foundation,
        production,
        scenario,
        policy,
        config_hash,
        partition_code=study.partition_code,
    )


def run_confirmatory_campaign(
    study: ConfirmatoryConfig,
    foundation: Experiment003Config,
    production: Any,
    policy: FrozenPolicy,
    config_hash: str,
    seed_manifest_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    if output.exists() or output.parent.exists():
        raise RuntimeError("refusing pre-existing Experiment 003 confirmatory result path")
    scenarios = [
        scenario_from_dict(json.loads(line))
        for line in Path(seed_manifest_path).read_text(encoding="utf-8").splitlines()
    ]
    if len(scenarios) != study.planned_blocks:
        raise RuntimeError("confirmatory seed manifest block count drifted")
    if len({scenario.root_seed_id for scenario in scenarios}) != study.planned_blocks:
        raise RuntimeError("confirmatory seed manifest root identities are not unique")

    output.parent.mkdir(parents=True, exist_ok=False)
    started = time.time()
    episodes = 0
    with output.open("x", encoding="utf-8") as handle:
        for scenario in scenarios:
            for row in run_confirmatory_block(
                study,
                foundation,
                production,
                scenario,
                policy,
                config_hash,
            ):
                handle.write(canonical_json(row.to_dict()).decode() + "\n")
                episodes += 1
            handle.flush()
    if episodes != study.planned_episodes:
        raise RuntimeError("confirmatory output episode count drifted")
    return {
        "passed": True,
        "blocks": len(scenarios),
        "episodes": episodes,
        "elapsed_wall_s": time.time() - started,
        "episodes_sha256": sha256_bytes(output.read_bytes()),
        "campaign_executions": 1,
    }


def load_episode_rows(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
