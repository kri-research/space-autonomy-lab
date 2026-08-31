from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_004_pilot.config import PilotCase, PilotConfig
from kri_space_autonomy.experiment_004_pilot.runner import _scenario_from_row, run_block
from kri_space_autonomy.experiment_004_pilot.seeds import (
    PilotScenario,
    canonical_json,
    sha256_bytes,
)

from .config import ConfirmatoryConfig


def run_confirmatory_block(
    study: ConfirmatoryConfig,
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    scenario: PilotScenario,
    *,
    freeze_id: str,
) -> list[dict[str, Any]]:
    if scenario.partition_code != study.confirmatory_partition_code:
        raise ValueError("confirmatory runner requires partition 44")
    if scenario.design_freeze_id != freeze_id:
        raise ValueError("confirmatory scenario is not bound to the exact design freeze")
    if scenario.case_id != case.id or case.id not in study.strata:
        raise ValueError("confirmatory scenario is outside the frozen stratum")
    if scenario.replicate >= study.roots_by_stratum[case.id]:
        raise ValueError("confirmatory scenario exceeds the frozen stratum count")
    rows = []
    for episode in run_block(pilot, foundation, case, scenario):
        row = episode.to_dict()
        row["schema_version"] = study.schema_version
        row["study_phase"] = "confirmatory_assurance"
        rows.append(row)
    return rows


def run_confirmatory_campaign(
    study: ConfirmatoryConfig,
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
    *,
    seed_manifest_path: str | Path,
    output_path: str | Path,
    freeze_id: str,
) -> dict[str, Any]:
    """Execute the frozen campaign once; never call during design freeze."""

    output = Path(output_path)
    if output.exists() or output.parent.exists():
        raise RuntimeError("refusing pre-existing confirmatory result path")
    scenarios = [
        _scenario_from_row(json.loads(line))
        for line in Path(seed_manifest_path).read_text(encoding="utf-8").splitlines()
    ]
    if len(scenarios) != study.planned_blocks:
        raise RuntimeError("confirmatory manifest root count drift")
    case_map = {case.id: case for case in cases}
    output.parent.mkdir(parents=True, exist_ok=False)
    started = time.time()
    episodes = 0
    with output.open("x", encoding="utf-8") as handle:
        for scenario in scenarios:
            case = case_map.get(scenario.case_id)
            if case is None:
                raise RuntimeError("confirmatory manifest contains an unknown stratum")
            for row in run_confirmatory_block(
                study,
                pilot,
                foundation,
                case,
                scenario,
                freeze_id=freeze_id,
            ):
                handle.write(canonical_json(row).decode() + "\n")
                episodes += 1
            handle.flush()
    if episodes != study.planned_episodes:
        raise RuntimeError("confirmatory episode count drift")
    return {
        "passed": True,
        "blocks": len(scenarios),
        "episodes": episodes,
        "elapsed_wall_s": time.time() - started,
        "episodes_sha256": sha256_bytes(output.read_bytes()),
        "campaign_executions": 1,
        "retry_replacement_or_extension": False,
    }


def load_episode_rows(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
    ]
