from __future__ import annotations

import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_005.config import Experiment005Config
from kri_space_autonomy.experiment_005.runner import default_workers
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    TransferCase,
    TransferPilotConfig,
)
from kri_space_autonomy.experiment_005_transfer_pilot.runner import (
    _acquire_lock,
    _assemble,
    _build_shard,
    _failure_path,
    _prepare_checkpoint_directory,
    _publish_no_clobber,
    _release_lock,
    _scan_shards,
    _shard_path,
    _task_identity,
    _terminal_failure,
    run_block,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    TransferScenario,
    canonical_json,
    sha256_bytes,
)

from .config import ConfirmatoryConfig

CAMPAIGN_SCHEMA_VERSION = "experiment-005-confirmatory-checkpoint-1.0"
CONFIRMATORY_PARTITION_CODE = 53
PROCESS_START_METHOD = "spawn"
MODULE_ENTRYPOINT = "kri_space_autonomy.experiment_005_confirmatory.workflow"


def run_confirmatory_block(
    study: ConfirmatoryConfig,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    scenario: TransferScenario,
    *,
    freeze_id: str,
) -> list[dict[str, Any]]:
    if scenario.partition_code != CONFIRMATORY_PARTITION_CODE:
        raise ValueError("confirmatory runner requires partition 53")
    if scenario.design_freeze_id != freeze_id:
        raise ValueError("confirmatory scenario is not bound to the exact design freeze")
    if scenario.case_id != case.id or case.id not in study.cases:
        raise ValueError("confirmatory scenario is outside the frozen case population")
    if scenario.replicate >= study.roots_by_case[case.id]:
        raise ValueError("confirmatory scenario exceeds the frozen case count")
    rows: list[dict[str, Any]] = []
    for episode in run_block(pilot, foundation, e004, case, scenario):
        row = episode.to_dict()
        row["schema_version"] = study.schema_version
        row["study_phase"] = "confirmatory_nonlinear_truth_assurance"
        rows.append(row)
    return rows


def _execute_confirmatory_cell(
    study: ConfirmatoryConfig,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    scenario: TransferScenario,
    freeze_id: str,
) -> list[dict[str, Any]]:
    return run_confirmatory_block(
        study,
        pilot,
        foundation,
        e004,
        case,
        scenario,
        freeze_id=freeze_id,
    )


def _campaign_record(scenarios: tuple[TransferScenario, ...]) -> dict[str, Any]:
    schedule = [_task_identity(index, scenario) for index, scenario in enumerate(scenarios)]
    unsigned = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "partition_code": CONFIRMATORY_PARTITION_CODE,
        "cell_count": len(scenarios),
        "ordered_schedule_sha256": sha256_bytes(canonical_json(schedule)),
        "canonical_assembly_order": "ascending frozen cell index and within-cell run order",
        "parallelism": "process pool with explicit spawn context",
        "process_start_method": PROCESS_START_METHOD,
        "importable_module_entrypoint": MODULE_ENTRYPOINT,
        "ephemeral_main_allowed": False,
        "resume_semantics": "validate all shards then execute missing unpublished cells only",
        "failure_semantics": "write immutable terminal failure record; never retry failed cell",
        "corrupt_shard_semantics": "fail closed without automatic recomputation",
        "maximum_retries": 0,
        "maximum_replacement_roots": 0,
    }
    return {**unsigned, "campaign_id": sha256_bytes(canonical_json(unsigned))}


def run_spawn_checkpointed_confirmatory_campaign(
    directory: str | Path,
    *,
    study: ConfirmatoryConfig,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
    scenarios: tuple[TransferScenario, ...],
    freeze_id: str,
    workers: int | None = None,
) -> dict[str, Any]:
    """Run the frozen partition-53 schedule with fail-closed checkpoints."""

    if not scenarios:
        raise ValueError("checkpoint campaign requires frozen scenarios")
    if {scenario.partition_code for scenario in scenarios} != {CONFIRMATORY_PARTITION_CODE}:
        raise ValueError("confirmatory checkpoint campaign accepts only partition 53")
    if any(scenario.design_freeze_id != freeze_id for scenario in scenarios):
        raise ValueError("confirmatory schedule freeze identity changed")
    if len(scenarios) not in {study.planned_blocks, study.replay_blocks}:
        raise ValueError("confirmatory schedule block count changed")
    if len({scenario.root_seed_id for scenario in scenarios}) != len(scenarios):
        raise ValueError("confirmatory checkpoint campaign contains duplicate roots")
    worker_count = default_workers() if workers is None else workers
    if type(worker_count) is not int or worker_count < 1:
        raise ValueError("workers must be a positive integer")
    case_map = {case.id: case for case in cases}
    if any(scenario.case_id not in case_map for scenario in scenarios):
        raise ValueError("confirmatory schedule contains an unknown case")

    root = Path(directory)
    checkpoint_dir = root / "shards"
    output_path = root / "confirmatory-episodes.jsonl"
    campaign = _campaign_record(scenarios)
    lock_path, lock_descriptor = _acquire_lock(checkpoint_dir)
    try:
        _prepare_checkpoint_directory(checkpoint_dir, campaign)
        completed = _scan_shards(checkpoint_dir, scenarios, campaign["campaign_id"])
        reused = len(completed)
        missing = [index for index in range(len(scenarios)) if index not in completed]

        def persist(index: int, rows: list[dict[str, Any]]) -> None:
            identity = _task_identity(index, scenarios[index])
            shard = _build_shard(identity, rows, campaign["campaign_id"])
            _publish_no_clobber(
                _shard_path(checkpoint_dir, index), canonical_json(shard) + b"\n"
            )

        if worker_count == 1:
            for index in missing:
                try:
                    rows = _execute_confirmatory_cell(
                        study,
                        pilot,
                        foundation,
                        e004,
                        case_map[scenarios[index].case_id],
                        scenarios[index],
                        freeze_id,
                    )
                except BaseException as exc:
                    failure = _terminal_failure(
                        _task_identity(index, scenarios[index]),
                        campaign["campaign_id"],
                        exc,
                    )
                    _publish_no_clobber(
                        _failure_path(checkpoint_dir, index),
                        canonical_json(failure) + b"\n",
                    )
                    raise
                persist(index, rows)
        else:
            context = multiprocessing.get_context(PROCESS_START_METHOD)
            with ProcessPoolExecutor(max_workers=worker_count, mp_context=context) as executor:
                futures = {
                    executor.submit(
                        _execute_confirmatory_cell,
                        study,
                        pilot,
                        foundation,
                        e004,
                        case_map[scenarios[index].case_id],
                        scenarios[index],
                        freeze_id,
                    ): index
                    for index in missing
                }
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        rows = future.result()
                    except BaseException as exc:
                        failure = _terminal_failure(
                            _task_identity(index, scenarios[index]),
                            campaign["campaign_id"],
                            exc,
                        )
                        _publish_no_clobber(
                            _failure_path(checkpoint_dir, index),
                            canonical_json(failure) + b"\n",
                        )
                        for pending in futures:
                            pending.cancel()
                        raise
                    persist(index, rows)

        completed = _scan_shards(checkpoint_dir, scenarios, campaign["campaign_id"])
        complete = len(completed) == len(scenarios)
        rows_written = None
        digest = None
        if complete:
            rows_written, digest = _assemble(
                output_path,
                checkpoint_dir,
                scenarios,
                campaign["campaign_id"],
            )
        return {
            "passed": complete,
            "complete": complete,
            "campaign_id": campaign["campaign_id"],
            "partition_code": CONFIRMATORY_PARTITION_CODE,
            "cells": len(completed),
            "planned_cells": len(scenarios),
            "rows": rows_written,
            "output_sha256": digest,
            "workers": worker_count,
            "process_start_method": PROCESS_START_METHOD,
            "module_entrypoint": MODULE_ENTRYPOINT,
            "completed_shards_reused": reused,
            "new_shards_written": len(missing),
            "remaining_cells": len(scenarios) - len(completed),
            "infrastructure_failures": 0,
            "retries": 0,
            "replacement_roots": 0,
            "canonical_assembly": True,
        }
    finally:
        _release_lock(lock_path, lock_descriptor)
