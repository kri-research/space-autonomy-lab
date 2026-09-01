from __future__ import annotations

import json
import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
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

SHARD_SCHEMA_VERSION = "experiment-004-paired-block-shard-1.0"
CAMPAIGN_SCHEMA_VERSION = "experiment-004-checkpointed-campaign-1.0"
DEFAULT_WORKER_CAP = 8


def default_workers(cpu_count: int | None = None) -> int:
    """Reserve at least three CPUs and never exceed the measured 8-worker policy."""

    available = os.cpu_count() if cpu_count is None else cpu_count
    if available is None:
        return 1
    return max(1, min(DEFAULT_WORKER_CAP, available - 3 if available > 3 else 1))


def run_confirmatory_block(
    study: ConfirmatoryConfig,
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    scenario: PilotScenario,
    *,
    freeze_id: str,
) -> list[dict[str, Any]]:
    if scenario.partition_code == 44:
        raise ValueError("partition 44 is permanently retired and must never execute again")
    if scenario.partition_code != study.confirmatory_partition_code:
        raise ValueError("confirmatory runner requires the frozen replacement partition")
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


def _task_identity(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_index": task["block_index"],
        "case_id": task["case_id"],
        "configuration_run_order": list(task["configuration_run_order"]),
        "root_seed_id": task["root_seed_id"],
        "scenario_hash": task["scenario_hash"],
        "task_kind": task["task_kind"],
    }


def _execute_task(task: dict[str, Any]) -> list[dict[str, Any]]:
    if task["task_kind"] == "confirmatory":
        return run_confirmatory_block(
            task["study"],
            task["pilot"],
            task["foundation"],
            task["case"],
            task["scenario"],
            freeze_id=task["freeze_id"],
        )
    if task["task_kind"] == "pilot":
        return [
            episode.to_dict()
            for episode in run_block(
                task["pilot"], task["foundation"], task["case"], task["scenario"]
            )
        ]
    if task["task_kind"] == "numerical_fixture":
        value = int(task["block_index"]) + 1
        mask = (1 << 64) - 1
        for step in range(int(task["iterations"])):
            value = (value * 6364136223846793005 + 1442695040888963407 + step) & mask
            value ^= value >> 29
        return [
            {
                "case_id": task["case_id"],
                "configuration_id": configuration,
                "fixture_value": value,
                "root_seed_id": task["root_seed_id"],
                "scenario_hash": task["scenario_hash"],
            }
            for configuration in task["configuration_run_order"]
        ]
    raise ValueError("unknown block task kind")


def _atomic_write(path: Path, content: bytes, *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and path.exists():
            raise RuntimeError(f"refusing to replace completed file: {path.name}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _campaign_record(
    tasks: list[dict[str, Any]],
    *,
    campaign_kind: str,
    campaign_binding: dict[str, Any],
) -> dict[str, Any]:
    schedule = [_task_identity(task) for task in tasks]
    unsigned = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_kind": campaign_kind,
        "campaign_binding": campaign_binding,
        "block_count": len(tasks),
        "task_schedule_sha256": sha256_bytes(canonical_json(schedule)),
        "paired_block_is_work_unit": True,
        "resume_semantics": "verify completed shards and execute only missing frozen blocks",
        "completed_shards_recomputed": False,
        "canonical_assembly_order": "ascending frozen block_index",
    }
    return {**unsigned, "campaign_id": sha256_bytes(canonical_json(unsigned))}


def _prepare_checkpoint_directory(checkpoint_dir: Path, campaign: dict[str, Any]) -> None:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    for temporary in checkpoint_dir.glob(".*.tmp"):
        temporary.unlink()
    state_path = checkpoint_dir / "campaign.json"
    expected = canonical_json(campaign) + b"\n"
    if state_path.exists():
        if state_path.read_bytes() != expected:
            raise RuntimeError("checkpoint campaign identity mismatch")
        return
    if any(checkpoint_dir.iterdir()):
        raise RuntimeError("checkpoint directory lacks its frozen campaign identity")
    _atomic_write(state_path, expected, replace=False)


def _shard_path(checkpoint_dir: Path, block_index: int) -> Path:
    return checkpoint_dir / f"block-{block_index:06d}.json"


def _build_shard(
    task: dict[str, Any],
    rows: list[dict[str, Any]],
    campaign_id: str,
) -> dict[str, Any]:
    if len(rows) != 2:
        raise RuntimeError("paired block did not produce exactly two episode rows")
    configurations = [row.get("configuration_id") for row in rows]
    if configurations != list(task["configuration_run_order"]):
        raise RuntimeError("paired block configuration order drift")
    if any(
        row.get("root_seed_id") != task["root_seed_id"]
        or row.get("case_id") != task["case_id"]
        or row.get("scenario_hash") != task["scenario_hash"]
        for row in rows
    ):
        raise RuntimeError("paired block identity drift")
    unsigned = {
        "schema_version": SHARD_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        **_task_identity(task),
        "episode_rows": rows,
        "episode_rows_sha256": sha256_bytes(canonical_json(rows)),
    }
    return {**unsigned, "shard_id": sha256_bytes(canonical_json(unsigned))}


def _validate_shard(
    path: Path,
    task: dict[str, Any],
    campaign_id: str,
) -> dict[str, Any]:
    try:
        shard = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"corrupt checkpoint shard: {path.name}") from exc
    if not isinstance(shard, dict):
        raise RuntimeError(f"corrupt checkpoint shard: {path.name}")
    expected_bytes = canonical_json(shard) + b"\n"
    if path.read_bytes() != expected_bytes:
        raise RuntimeError(f"noncanonical checkpoint shard: {path.name}")
    unsigned = dict(shard)
    shard_id = unsigned.pop("shard_id", None)
    if shard_id != sha256_bytes(canonical_json(unsigned)):
        raise RuntimeError(f"checkpoint shard hash mismatch: {path.name}")
    if (
        shard.get("schema_version") != SHARD_SCHEMA_VERSION
        or shard.get("campaign_id") != campaign_id
        or any(shard.get(key) != value for key, value in _task_identity(task).items())
    ):
        raise RuntimeError(f"checkpoint shard identity mismatch: {path.name}")
    rows = shard.get("episode_rows")
    if not isinstance(rows, list) or shard.get("episode_rows_sha256") != sha256_bytes(
        canonical_json(rows)
    ):
        raise RuntimeError(f"checkpoint shard row hash mismatch: {path.name}")
    _build_shard(task, rows, campaign_id)
    return shard


def _scan_shards(
    checkpoint_dir: Path,
    tasks: list[dict[str, Any]],
    campaign_id: str,
) -> dict[int, dict[str, Any]]:
    expected_names = {_shard_path(checkpoint_dir, task["block_index"]).name for task in tasks}
    actual_names = {path.name for path in checkpoint_dir.iterdir() if path.name != "campaign.json"}
    unexpected = sorted(actual_names - expected_names)
    if unexpected:
        raise RuntimeError(f"unexpected or duplicate checkpoint shard: {unexpected[0]}")
    completed: dict[int, dict[str, Any]] = {}
    roots: set[str] = set()
    for task in tasks:
        path = _shard_path(checkpoint_dir, task["block_index"])
        if not path.exists():
            continue
        shard = _validate_shard(path, task, campaign_id)
        root = str(shard["root_seed_id"])
        if root in roots:
            raise RuntimeError("duplicate root identity across checkpoint shards")
        roots.add(root)
        completed[task["block_index"]] = shard
    return completed


def _validate_tasks(tasks: list[dict[str, Any]]) -> None:
    indexes = [task["block_index"] for task in tasks]
    roots = [task["root_seed_id"] for task in tasks]
    if indexes != list(range(len(tasks))):
        raise RuntimeError("frozen tasks must use contiguous canonical block indexes")
    if len(roots) != len(set(roots)):
        raise RuntimeError("frozen task schedule contains duplicate roots")


def _assemble(
    output_path: Path,
    checkpoint_dir: Path,
    tasks: list[dict[str, Any]],
    campaign_id: str,
) -> tuple[int, str]:
    shards = _scan_shards(checkpoint_dir, tasks, campaign_id)
    if len(shards) != len(tasks):
        raise RuntimeError("cannot assemble an incomplete frozen campaign")
    content = b"".join(
        canonical_json(row) + b"\n"
        for task in tasks
        for row in shards[task["block_index"]]["episode_rows"]
    )
    if output_path.exists():
        if output_path.read_bytes() != content:
            raise RuntimeError("existing final output does not match canonical shard assembly")
    else:
        _atomic_write(output_path, content, replace=False)
    return len(tasks) * 2, sha256_bytes(content)


def _run_checkpointed_tasks(
    tasks: list[dict[str, Any]],
    *,
    checkpoint_dir: Path,
    output_path: Path,
    workers: int,
    campaign_kind: str,
    campaign_binding: dict[str, Any],
    progress: bool,
    stop_after_for_test: int | None = None,
) -> dict[str, Any]:
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if stop_after_for_test is not None and campaign_kind != "nonconfirmatory_numerical_fixture":
        raise ValueError("test interruption is forbidden for confirmatory execution")
    _validate_tasks(tasks)
    campaign = _campaign_record(
        tasks,
        campaign_kind=campaign_kind,
        campaign_binding=campaign_binding,
    )
    _prepare_checkpoint_directory(checkpoint_dir, campaign)
    completed = _scan_shards(checkpoint_dir, tasks, campaign["campaign_id"])
    reused_count = len(completed)
    missing = [task for task in tasks if task["block_index"] not in completed]
    if stop_after_for_test is not None:
        missing = missing[:stop_after_for_test]
    started = time.perf_counter()

    def persist(task: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        shard = _build_shard(task, rows, campaign["campaign_id"])
        _atomic_write(
            _shard_path(checkpoint_dir, task["block_index"]),
            canonical_json(shard) + b"\n",
            replace=False,
        )
        if progress:
            done = len(completed) + 1
            print(f"[{done}/{len(tasks)}] completed {task['root_seed_id']}", flush=True)
        completed[task["block_index"]] = shard

    if workers == 1:
        for task in missing:
            persist(task, _execute_task(task))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_tasks = {executor.submit(_execute_task, task): task for task in missing}
            for future in as_completed(future_tasks):
                task = future_tasks[future]
                persist(task, future.result())

    completed = _scan_shards(checkpoint_dir, tasks, campaign["campaign_id"])
    complete = len(completed) == len(tasks)
    episodes = None
    digest = None
    if complete:
        episodes, digest = _assemble(
            output_path,
            checkpoint_dir,
            tasks,
            campaign["campaign_id"],
        )
    return {
        "passed": complete,
        "complete": complete,
        "campaign_id": campaign["campaign_id"],
        "blocks": len(completed),
        "planned_blocks": len(tasks),
        "episodes": episodes,
        "elapsed_wall_s": time.perf_counter() - started,
        "episodes_sha256": digest,
        "workers": workers,
        "completed_shards_reused": reused_count,
        "new_shards_written": len(missing),
        "remaining_blocks": len(tasks) - len(completed),
        "canonical_assembly": True,
    }


def run_confirmatory_campaign(
    study: ConfirmatoryConfig,
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
    *,
    seed_manifest_path: str | Path,
    checkpoint_dir: str | Path,
    output_path: str | Path,
    freeze_id: str,
    readiness_id: str,
    workers: int | None = None,
    progress: bool = True,
) -> dict[str, Any]:
    """Execute or safely continue the one frozen partition-45 campaign."""

    selected_workers = default_workers() if workers is None else workers
    manifest_path = Path(seed_manifest_path)
    scenarios = [
        _scenario_from_row(json.loads(line))
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    if len(scenarios) != study.planned_blocks:
        raise RuntimeError("confirmatory manifest root count drift")
    if any(scenario.partition_code == 44 for scenario in scenarios):
        raise RuntimeError("refusing to touch retired partition 44")
    case_map = {case.id: case for case in cases}
    tasks = []
    for block_index, scenario in enumerate(scenarios):
        case = case_map.get(scenario.case_id)
        if case is None:
            raise RuntimeError("confirmatory manifest contains an unknown stratum")
        tasks.append(
            {
                "task_kind": "confirmatory",
                "block_index": block_index,
                "case_id": scenario.case_id,
                "root_seed_id": scenario.root_seed_id,
                "scenario_hash": scenario.scenario_hash,
                "configuration_run_order": scenario.configuration_run_order,
                "study": study,
                "pilot": pilot,
                "foundation": foundation,
                "case": case,
                "scenario": scenario,
                "freeze_id": freeze_id,
            }
        )
    result = _run_checkpointed_tasks(
        tasks,
        checkpoint_dir=Path(checkpoint_dir),
        output_path=Path(output_path),
        workers=selected_workers,
        campaign_kind="replacement_confirmatory_partition_45",
        campaign_binding={
            "freeze_id": freeze_id,
            "readiness_id": readiness_id,
            "seed_manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "partition_code": study.confirmatory_partition_code,
        },
        progress=progress,
    )
    if result["complete"] and result["episodes"] != study.planned_episodes:
        raise RuntimeError("confirmatory episode count drift")
    return {
        **result,
        "campaign_executions": 1,
        "safe_orchestration_continuation": result["completed_shards_reused"] > 0,
        "retry_replacement_or_extension": False,
    }


def numerical_fixture_tasks(task_count: int, iterations: int) -> list[dict[str, Any]]:
    tasks = []
    for block_index in range(task_count):
        root = f"experiment004:numerical-fixture:{block_index:04d}"
        scenario_hash = sha256_bytes(
            canonical_json({"block_index": block_index, "iterations": iterations})
        )
        tasks.append(
            {
                "task_kind": "numerical_fixture",
                "block_index": block_index,
                "case_id": "outcome_blind_cpu_fixture",
                "root_seed_id": root,
                "scenario_hash": scenario_hash,
                "configuration_run_order": ("fixture_a", "fixture_b"),
                "iterations": iterations,
            }
        )
    return tasks


def benchmark_worker_counts(
    worker_counts: tuple[int, ...],
    *,
    task_count: int,
    iterations: int,
) -> dict[str, Any]:
    """Benchmark the exact checkpoint/assembly path on outcome-blind CPU fixtures."""

    measurements = []
    output_hashes = set()
    with tempfile.TemporaryDirectory(prefix="experiment-004-parallel-benchmark-") as temporary:
        root = Path(temporary)
        tasks = numerical_fixture_tasks(task_count, iterations)
        for workers in worker_counts:
            result = _run_checkpointed_tasks(
                tasks,
                checkpoint_dir=root / f"workers-{workers}" / "shards",
                output_path=root / f"workers-{workers}" / "episodes.jsonl",
                workers=workers,
                campaign_kind="nonconfirmatory_numerical_fixture",
                campaign_binding={
                    "fixture": "integer_cpu_loop",
                    "task_count": task_count,
                    "iterations": iterations,
                },
                progress=False,
            )
            output_hashes.add(result["episodes_sha256"])
            measurements.append(
                {
                    "workers": workers,
                    "elapsed_wall_s": result["elapsed_wall_s"],
                    "output_sha256": result["episodes_sha256"],
                    "blocks": result["blocks"],
                    "episodes": result["episodes"],
                    "passed": result["passed"],
                }
            )
    serial = next(item["elapsed_wall_s"] for item in measurements if item["workers"] == 1)
    for item in measurements:
        item["speedup_vs_serial"] = serial / item["elapsed_wall_s"]
    return {
        "passed": all(item["passed"] for item in measurements) and len(output_hashes) == 1,
        "fixture": "outcome-blind deterministic integer CPU fixture",
        "partition_44_outcomes_used": False,
        "confirmatory_outcomes_used": False,
        "task_count": task_count,
        "iterations_per_task": iterations,
        "measurements": measurements,
        "canonical_output_sha256": next(iter(output_hashes)),
        "worker_count_invariant": len(output_hashes) == 1,
    }


def checkpoint_fixture_run(
    directory: Path,
    *,
    workers: int,
    task_count: int = 6,
    iterations: int = 100,
    stop_after_for_test: int | None = None,
) -> dict[str, Any]:
    tasks = numerical_fixture_tasks(task_count, iterations)
    return _run_checkpointed_tasks(
        tasks,
        checkpoint_dir=directory / "shards",
        output_path=directory / "episodes.jsonl",
        workers=workers,
        campaign_kind="nonconfirmatory_numerical_fixture",
        campaign_binding={
            "fixture": "integer_cpu_loop",
            "task_count": task_count,
            "iterations": iterations,
        },
        progress=False,
        stop_after_for_test=stop_after_for_test,
    )


def load_episode_rows(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
