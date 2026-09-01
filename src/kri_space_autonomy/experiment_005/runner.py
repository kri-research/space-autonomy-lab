from __future__ import annotations

import errno
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

SHARD_SCHEMA_VERSION = "experiment-005-frozen-cell-shard-1.0"
CAMPAIGN_SCHEMA_VERSION = "experiment-005-checkpointed-fixture-1.0"
LOCK_NAME = ".campaign.lock"


def canonical_json(value: Any) -> bytes:
    import hashlib

    del hashlib
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def default_workers(cpu_count: int | None = None) -> int:
    available = os.cpu_count() if cpu_count is None else cpu_count
    if available is None or available <= 3:
        return 1
    return max(1, min(8, available - 3))


def fixture_tasks(task_count: int, iterations: int) -> list[dict[str, Any]]:
    if type(task_count) is not int or task_count < 1:
        raise ValueError("task_count must be a positive integer")
    if type(iterations) is not int or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    tasks = []
    for cell_index in range(task_count):
        identity = {
            "cell_index": cell_index,
            "cell_id": f"experiment005:951:fixture:{cell_index:04d}",
            "case_id": "outcome_blind_integer_fixture",
            "iterations": iterations + (task_count - cell_index) * 7,
            "row_order": ["fixture_a", "fixture_b"],
        }
        tasks.append({**identity, "cell_sha256": sha256_bytes(canonical_json(identity))})
    return tasks


def _task_identity(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: task[key]
        for key in (
            "cell_index",
            "cell_id",
            "case_id",
            "iterations",
            "row_order",
            "cell_sha256",
        )
    }


def _validate_tasks(tasks: list[dict[str, Any]]) -> None:
    indexes = [task.get("cell_index") for task in tasks]
    identifiers = [task.get("cell_id") for task in tasks]
    if indexes != list(range(len(tasks))):
        raise RuntimeError("frozen cells must have contiguous canonical indexes")
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("frozen cells contain duplicate identities")
    for task in tasks:
        identity = dict(_task_identity(task))
        observed = identity.pop("cell_sha256")
        if observed != sha256_bytes(canonical_json(identity)):
            raise RuntimeError("frozen cell identity hash mismatch")
        if task.get("row_order") != ["fixture_a", "fixture_b"]:
            raise RuntimeError("fixture row order changed")


def _execute_fixture(task: dict[str, Any]) -> list[dict[str, Any]]:
    value = int(task["cell_index"]) + 1
    mask = (1 << 64) - 1
    for step in range(int(task["iterations"])):
        value = (value * 6364136223846793005 + 1442695040888963407 + step) & mask
        value ^= value >> 29
    return [
        {
            "case_id": task["case_id"],
            "cell_id": task["cell_id"],
            "fixture_value": value,
            "row_id": row_id,
        }
        for row_id in task["row_order"]
    ]


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _publish_no_clobber(path: Path, content: bytes) -> None:
    """Atomically publish one durable file without replacing an existing path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise RuntimeError(f"refusing to replace completed file: {path.name}") from exc
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise RuntimeError(f"refusing to replace completed file: {path.name}") from exc
            raise
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _acquire_lock(checkpoint_dir: Path) -> tuple[Path, int]:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    lock_path = checkpoint_dir / LOCK_NAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("checkpoint campaign is locked or requires stale-lock review") from exc
    metadata = canonical_json({"pid": os.getpid(), "schema": CAMPAIGN_SCHEMA_VERSION}) + b"\n"
    os.write(descriptor, metadata)
    os.fsync(descriptor)
    _fsync_directory(checkpoint_dir)
    return lock_path, descriptor


def _release_lock(lock_path: Path, descriptor: int) -> None:
    os.close(descriptor)
    lock_path.unlink(missing_ok=False)
    _fsync_directory(lock_path.parent)


def _campaign_record(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    schedule = [_task_identity(task) for task in tasks]
    unsigned = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_kind": "non_outcome_deterministic_fixture",
        "fixture_partition_code": 951,
        "cell_count": len(tasks),
        "ordered_schedule_sha256": sha256_bytes(canonical_json(schedule)),
        "canonical_assembly_order": "ascending frozen cell_index",
        "parallelism": "process pool when workers exceed one",
        "resume_semantics": "validate all shards then execute missing frozen cells only",
        "corrupt_shard_semantics": "fail closed without automatic recomputation",
        "outcome_partition_access": False,
    }
    return {**unsigned, "campaign_id": sha256_bytes(canonical_json(unsigned))}


def _prepare_checkpoint_directory(checkpoint_dir: Path, campaign: dict[str, Any]) -> None:
    for temporary in checkpoint_dir.glob(".*.tmp"):
        temporary.unlink()
    state_path = checkpoint_dir / "campaign.json"
    expected = canonical_json(campaign) + b"\n"
    if state_path.exists():
        if state_path.read_bytes() != expected:
            raise RuntimeError("checkpoint campaign identity mismatch")
        return
    remaining = [path for path in checkpoint_dir.iterdir() if path.name != LOCK_NAME]
    if remaining:
        raise RuntimeError("checkpoint directory lacks its frozen campaign identity")
    _publish_no_clobber(state_path, expected)


def _shard_path(checkpoint_dir: Path, cell_index: int) -> Path:
    return checkpoint_dir / f"cell-{cell_index:06d}.json"


def _build_shard(
    task: dict[str, Any], rows: list[dict[str, Any]], campaign_id: str
) -> dict[str, Any]:
    if len(rows) != 2:
        raise RuntimeError("fixture cell did not produce exactly two rows")
    if [row.get("row_id") for row in rows] != task["row_order"]:
        raise RuntimeError("fixture cell row order drift")
    if any(
        row.get("cell_id") != task["cell_id"] or row.get("case_id") != task["case_id"]
        for row in rows
    ):
        raise RuntimeError("fixture cell row identity drift")
    unsigned = {
        "schema_version": SHARD_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        **_task_identity(task),
        "rows": rows,
        "rows_sha256": sha256_bytes(canonical_json(rows)),
    }
    return {**unsigned, "shard_id": sha256_bytes(canonical_json(unsigned))}


def _validate_shard(
    path: Path, task: dict[str, Any], campaign_id: str
) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        shard = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"corrupt checkpoint shard: {path.name}") from exc
    if not isinstance(shard, dict) or raw != canonical_json(shard) + b"\n":
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
    rows = shard.get("rows")
    if not isinstance(rows, list) or shard.get("rows_sha256") != sha256_bytes(
        canonical_json(rows)
    ):
        raise RuntimeError(f"checkpoint shard row hash mismatch: {path.name}")
    _build_shard(task, rows, campaign_id)
    return shard


def _scan_shards(
    checkpoint_dir: Path, tasks: list[dict[str, Any]], campaign_id: str
) -> dict[int, dict[str, Any]]:
    expected = {_shard_path(checkpoint_dir, task["cell_index"]).name for task in tasks}
    ignored = {"campaign.json", LOCK_NAME}
    actual = {path.name for path in checkpoint_dir.iterdir() if path.name not in ignored}
    unexpected = sorted(actual - expected)
    if unexpected:
        raise RuntimeError(f"unexpected or duplicate checkpoint shard: {unexpected[0]}")
    completed: dict[int, dict[str, Any]] = {}
    identifiers: set[str] = set()
    for task in tasks:
        path = _shard_path(checkpoint_dir, task["cell_index"])
        if not path.exists():
            continue
        shard = _validate_shard(path, task, campaign_id)
        cell_id = str(shard["cell_id"])
        if cell_id in identifiers:
            raise RuntimeError("duplicate cell identity across checkpoint shards")
        identifiers.add(cell_id)
        completed[int(task["cell_index"])] = shard
    return completed


def _assemble(
    output_path: Path,
    checkpoint_dir: Path,
    tasks: list[dict[str, Any]],
    campaign_id: str,
) -> tuple[int, str]:
    shards = _scan_shards(checkpoint_dir, tasks, campaign_id)
    if len(shards) != len(tasks):
        raise RuntimeError("cannot assemble an incomplete frozen fixture")
    content = b"".join(
        canonical_json(row) + b"\n"
        for task in tasks
        for row in shards[int(task["cell_index"])]["rows"]
    )
    if output_path.exists():
        if output_path.read_bytes() != content:
            raise RuntimeError("existing output conflicts with canonical shard assembly")
    else:
        _publish_no_clobber(output_path, content)
    return len(tasks) * 2, sha256_bytes(content)


def run_checkpointed_fixture(
    directory: str | Path,
    *,
    workers: int,
    task_count: int = 8,
    iterations: int = 200,
    stop_after_for_test: int | None = None,
) -> dict[str, Any]:
    """Exercise the exact future campaign orchestration path without scientific cells."""

    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if stop_after_for_test is not None and (
        type(stop_after_for_test) is not int or stop_after_for_test < 0
    ):
        raise ValueError("stop_after_for_test must be a non-negative integer")
    root = Path(directory)
    checkpoint_dir = root / "shards"
    output_path = root / "fixture-rows.jsonl"
    tasks = fixture_tasks(task_count, iterations)
    _validate_tasks(tasks)
    campaign = _campaign_record(tasks)
    lock_path, lock_descriptor = _acquire_lock(checkpoint_dir)
    try:
        _prepare_checkpoint_directory(checkpoint_dir, campaign)
        completed = _scan_shards(checkpoint_dir, tasks, campaign["campaign_id"])
        reused = len(completed)
        missing = [task for task in tasks if task["cell_index"] not in completed]
        if stop_after_for_test is not None:
            missing = missing[:stop_after_for_test]

        def persist(task: dict[str, Any], rows: list[dict[str, Any]]) -> None:
            shard = _build_shard(task, rows, campaign["campaign_id"])
            _publish_no_clobber(
                _shard_path(checkpoint_dir, int(task["cell_index"])),
                canonical_json(shard) + b"\n",
            )

        if workers == 1:
            for task in missing:
                persist(task, _execute_fixture(task))
        else:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(_execute_fixture, task): task for task in missing}
                for future in as_completed(futures):
                    task = futures[future]
                    persist(task, future.result())
        completed = _scan_shards(checkpoint_dir, tasks, campaign["campaign_id"])
        complete = len(completed) == len(tasks)
        rows = None
        digest = None
        if complete:
            rows, digest = _assemble(output_path, checkpoint_dir, tasks, campaign["campaign_id"])
        return {
            "passed": complete,
            "complete": complete,
            "campaign_id": campaign["campaign_id"],
            "cells": len(completed),
            "planned_cells": len(tasks),
            "rows": rows,
            "output_sha256": digest,
            "workers": workers,
            "completed_shards_reused": reused,
            "new_shards_written": len(missing),
            "remaining_cells": len(tasks) - len(completed),
            "canonical_assembly": True,
            "scientific_partition_accessed": False,
        }
    finally:
        _release_lock(lock_path, lock_descriptor)
