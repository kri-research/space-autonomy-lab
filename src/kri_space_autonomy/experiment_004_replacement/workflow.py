from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_004_confirmatory.analysis import analyze_confirmatory_rows
from kri_space_autonomy.experiment_004_pilot.config import load_pilot_config
from kri_space_autonomy.experiment_004_pilot.runner import _scenario_from_row

from .benchmark import run_benchmark
from .config import load_confirmatory_config
from .runner import (
    _run_checkpointed_tasks,
    default_workers,
    load_episode_rows,
    run_confirmatory_campaign,
)
from .seeds import (
    MANIFEST_NAME,
    REPLAY_NAME,
    RESULT_DIRECTORY,
    SEED_DIRECTORY,
    load_confirmatory_cases,
    materialize_confirmatory_seeds,
    validate_materialized_confirmatory_seeds,
    validate_seed_contract,
)

CONFIG_PATH = Path("experiments/004-replacement-confirmatory/config.json")
STRATA_PATH = Path("experiments/004-replacement-confirmatory/strata.json")
SEED_CONTRACT_PATH = Path("experiments/004-replacement-confirmatory/seed-contract.json")
PREREG_PATH = Path("experiments/004-replacement-confirmatory/preregistration.md")
BENCHMARK_PATH = Path("experiments/004-replacement-confirmatory/parallel-benchmark.json")
FREEZE_PATH = Path("experiments/004-replacement-confirmatory/freeze-manifest.json")
READINESS_PATH = Path("experiments/004-replacement-confirmatory/readiness.json")
INVALID_AUDIT_PATH = Path("experiments/004-invalid-partition-44/audit.json")
PILOT_CONFIG_PATH = Path("experiments/004-pilot/config.json")
FOUNDATION_CONFIG_PATH = Path("experiments/004/config.json")
PILOT_MATRIX_PATH = Path("experiments/004-pilot/case-matrix.json")
EPISODES_PATH = RESULT_DIRECTORY / "confirmatory-episodes.jsonl"
CHECKPOINT_PATH = RESULT_DIRECTORY / "checkpoints"
EXECUTION_STATE_PATH = RESULT_DIRECTORY / "execution-state.json"
EXECUTION_SUMMARY_PATH = RESULT_DIRECTORY / "execution-summary.json"
ANALYSIS_PATH = RESULT_DIRECTORY / "analysis.json"
REPLAY_EPISODES_PATH = RESULT_DIRECTORY / "replay-episodes.jsonl"
REPLAY_CHECKPOINT_PATH = RESULT_DIRECTORY / "replay-checkpoints"
REPRODUCIBILITY_PATH = RESULT_DIRECTORY / "reproducibility.json"

ORIGINAL_FREEZE_ID = "f2632de9c371eeb4ce80ae7cdf054d49e9cf3f46a80fd30313b5e094c029d441"
ORIGINAL_READINESS_ID = "41a1ed95072721b382c215feef2a9042300a168e541c1365cf9cf05e8111865b"
INVALID_EPISODE_SHA256 = "8183195fcc64a00d29fb54aaaa480628161e23aad6ae081dd77ca919d0f54388"
INVALID_SEED_SHA256 = "f00b5166e790bf0f5c1bc27ddb13296171e9747cd670c66d77e50a17bb928991"
EXPECTED_BASE = "cfb56b2a5510916e5295ae9b654b3849f4a8d7e1"


def _self_hashed(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    if sha256_bytes(canonical_json(value)) != identity:
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def _source_paths(root: Path) -> list[Path]:
    paths = list((root / "src/kri_space_autonomy/experiment_004_replacement").glob("*.py"))
    paths += list(root.glob("tests/test_experiment_004_replacement*.py"))
    paths += [
        root / "docs/experiment-004-replacement-confirmatory.md",
        root / CONFIG_PATH,
        root / STRATA_PATH,
        root / SEED_CONTRACT_PATH,
        root / PREREG_PATH,
        root / BENCHMARK_PATH,
        root / INVALID_AUDIT_PATH,
        root / "experiments/004-confirmatory/config.json",
        root / "experiments/004-confirmatory/freeze-manifest.json",
        root / "experiments/004-confirmatory/readiness.json",
        root / "experiments/004-confirmatory/preregistration.md",
    ]
    return sorted((p for p in paths if p.is_file()), key=lambda p: p.as_posix())


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in _source_paths(root)
    }


def verify_invalid_attempt(root: Path) -> dict[str, Any]:
    audit = json.loads((root / INVALID_AUDIT_PATH).read_text(encoding="utf-8"))
    expected = {
        "partition_code": 44,
        "original_freeze_id": ORIGINAL_FREEZE_ID,
        "original_readiness_id": ORIGINAL_READINESS_ID,
        "status": "INVALID_PARTIAL_INFRASTRUCTURE_INTERRUPTION",
        "decision": "inconclusive_invalid",
        "materialized_roots": 1452,
        "materialization_invocations": 1,
        "campaign_invocations": 1,
        "durable_episode_rows": 602,
        "complete_paired_blocks": 301,
        "partial_paired_blocks": 0,
        "replay_invocations": 0,
        "retry_resume_replacement_extension_imputation_invocations": 0,
        "H1_status": "not_tested",
        "H2_status": "not_tested",
        "partial_outcomes_used_for_inference": False,
        "partial_outcomes_used_for_replacement_design": False,
        "partition_reusable": False,
        "seed_manifest_sha256": INVALID_SEED_SHA256,
        "partial_episode_file_sha256": INVALID_EPISODE_SHA256,
    }
    errors = [key for key, value in expected.items() if audit.get(key) != value]
    return {"passed": not errors, "errors": errors, "observed": audit}


def science_unchanged(root: Path) -> dict[str, Any]:
    original = json.loads((root / "experiments/004-confirmatory/config.json").read_text())
    replacement = json.loads((root / CONFIG_PATH).read_text())
    allowed = {"schema_version", "base_commit", "confirmatory_partition_code"}
    keys = sorted(set(original) | set(replacement))
    drift = [
        key for key in keys if key not in allowed and original.get(key) != replacement.get(key)
    ]
    expected_identity = (
        replacement.get("confirmatory_partition_code") == 45
        and replacement.get("master_seed") == original.get("master_seed") == 4004
        and replacement.get("base_commit") == EXPECTED_BASE
    )
    return {
        "passed": not drift and expected_identity,
        "scientific_field_drift": drift,
        "changed_execution_identity_fields": sorted(allowed),
    }


def partition_45_unmaterialized(root: Path) -> dict[str, Any]:
    paths_present = [
        str(path.relative_to(root))
        for path in (root / SEED_DIRECTORY, root / RESULT_DIRECTORY)
        if path.exists()
    ]
    matches: list[str] = []
    for path in root.glob("experiments/*/seeds/*.jsonl"):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "experiment004:45:" in line:
                matches.append(f"{path.relative_to(root)}:{line_number}")
                if len(matches) >= 20:
                    break
    return {
        "passed": not paths_present and not matches,
        "seed_or_result_paths_present": paths_present,
        "historical_partition_45_rows": matches,
        "state": "reserved_not_materialized_or_executed",
    }


def validate(root: Path) -> dict[str, Any]:
    study = load_confirmatory_config(root / CONFIG_PATH)
    audit = verify_invalid_attempt(root)
    science = science_unchanged(root)
    partition = partition_45_unmaterialized(root)
    seed_contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH, root=root)
    benchmark = json.loads((root / BENCHMARK_PATH).read_text(encoding="utf-8"))
    original_freeze = _self_hashed(
        root / "experiments/004-confirmatory/freeze-manifest.json", "freeze_id"
    )
    original_ready = _self_hashed(
        root / "experiments/004-confirmatory/readiness.json", "readiness_id"
    )
    checks = {
        "invalid_partition_44_record": audit["passed"],
        "scientific_design_unchanged": science["passed"],
        "partition_45_unmaterialized": partition["passed"],
        "seed_contract": seed_contract["passed"],
        "parallel_benchmark": benchmark.get("passed") is True,
        "serial_parallel_science_bytes_identical": benchmark.get(
            "scientific_serial_parallel_equivalence", {}
        ).get("byte_identical")
        is True,
        "selected_workers_match_runner": (
            benchmark.get("selected_default_workers") == default_workers(15) == 8
        ),
        "original_freeze_identity": original_freeze.get("freeze_id") == ORIGINAL_FREEZE_ID,
        "original_readiness_identity": original_ready.get("readiness_id") == ORIGINAL_READINESS_ID,
    }
    return {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_replacement_confirmatory",
        "passed": all(checks.values()),
        "status": "READY_TO_FREEZE" if all(checks.values()) else "NOT_READY",
        "checks": checks,
        "invalid_attempt": audit,
        "science_unchanged": science,
        "partition_45": partition,
        "seed_contract": seed_contract,
        "benchmark": benchmark,
    }


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite replacement freeze/readiness")
    validation = validate(root)
    if not validation["passed"]:
        raise RuntimeError("replacement confirmatory design is not ready to freeze")
    study = load_confirmatory_config(root / CONFIG_PATH)
    source_hashes = _file_hashes(root)
    unsigned = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_replacement_confirmatory_freeze",
        "status": "READY_FOR_FRESH_PARALLEL_CONFIRMATORY_EXECUTION",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "base_commit": EXPECTED_BASE,
        "original_invalid_attempt": {
            "partition": 44,
            "freeze_id": ORIGINAL_FREEZE_ID,
            "decision": "inconclusive_invalid",
            "partial_outcomes_used": False,
            "reusable": False,
        },
        "replacement_partition": 45,
        "replacement_partition_state": "reserved_not_materialized_or_executed",
        "scientific_design_unchanged": True,
        "paired_blocks": study.planned_blocks,
        "episodes": study.planned_episodes,
        "replay_blocks": study.replay_blocks,
        "replay_episodes": study.replay_episodes,
        "execution_protocol": {
            "work_unit": "paired root block",
            "parallelism": "process pool",
            "default_workers_on_validation_host": 8,
            "completed_block_storage": "atomic content-hashed shard",
            "final_assembly": "canonical ascending frozen block index",
            "checkpoint_continuation": "verify existing shards; execute missing blocks only",
            "completed_valid_blocks_recomputed": False,
            "finite_outer_shell_timeout_allowed": False,
            "outcome_driven_retry_or_replacement_allowed": False,
        },
        "analysis_contract": {
            "copied_without_scientific_change_from": ORIGINAL_FREEZE_ID,
            "H1_H2_unchanged": True,
            "sample_size_unchanged": True,
            "case_matrix_unchanged": True,
            "thresholds_unchanged": True,
        },
        "benchmark_sha256": sha256_bytes((root / BENCHMARK_PATH).read_bytes()),
        "invalid_attempt_audit_sha256": sha256_bytes((root / INVALID_AUDIT_PATH).read_bytes()),
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    readiness = {
        "schema_version": study.schema_version,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY_FOR_FRESH_PARALLEL_CONFIRMATORY_EXECUTION",
        "partition_code": 45,
        "partition_state": "reserved_not_materialized_or_executed",
        "paired_blocks": study.planned_blocks,
        "episodes": study.planned_episodes,
        "replay_blocks": study.replay_blocks,
        "replay_episodes": study.replay_episodes,
        "default_workers": 8,
        "next_command": (
            "uv run python -m kri_space_autonomy.experiment_004_replacement.workflow "
            "execute --workers 8"
        ),
        "outer_shell_timeout": None,
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError(f"replacement freeze failed verification: {verification['errors']}")
    return {"freeze": unsigned, "readiness": readiness, "verification": verification}


def verify_freeze(root: Path, *, require_unmaterialized: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = _self_hashed(root / FREEZE_PATH, "freeze_id")
        readiness = _self_hashed(root / READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors": [f"freeze_load:{exc}"]}
    for relative, expected in manifest.get("source_file_hashes", {}).items():
        path = root / relative
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected:
            errors.append(relative)
    if manifest.get("status") != "READY_FOR_FRESH_PARALLEL_CONFIRMATORY_EXECUTION":
        errors.append("freeze_status")
    if readiness.get("freeze_id") != manifest.get("freeze_id"):
        errors.append("readiness_binding")
    if readiness.get("partition_code") != 45 or readiness.get("default_workers") != 8:
        errors.append("readiness_execution_identity")
    if not verify_invalid_attempt(root)["passed"]:
        errors.append("invalid_attempt_audit")
    if not science_unchanged(root)["passed"]:
        errors.append("scientific_design_drift")
    study = load_confirmatory_config(root / CONFIG_PATH)
    seed_contract = None
    if require_unmaterialized:
        partition = partition_45_unmaterialized(root)
        seed_contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH, root=root)
        if not partition["passed"]:
            errors.append("partition_45_state")
        if not seed_contract["passed"]:
            errors.append("seed_contract")
    return {
        "passed": not errors,
        "status": (
            "READY_FOR_FRESH_PARALLEL_CONFIRMATORY_EXECUTION" if not errors else "NOT_READY"
        ),
        "errors": errors,
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "seed_contract": seed_contract,
        "require_unmaterialized": require_unmaterialized,
    }


def _load_seed_rows(root: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (root / SEED_DIRECTORY / MANIFEST_NAME).read_text().splitlines()
    ]


def _replay_tasks(
    root: Path, study: Any, pilot: Any, foundation: Any, cases: Any, freeze_id: str
) -> list[dict[str, Any]]:
    replay = json.loads((root / SEED_DIRECTORY / REPLAY_NAME).read_text())
    selected = set(replay["root_seed_ids"])
    case_map = {case.id: case for case in cases}
    tasks = []
    for row in _load_seed_rows(root):
        if row["root_seed_id"] not in selected:
            continue
        scenario = _scenario_from_row(row)
        tasks.append(
            {
                "task_kind": "confirmatory",
                "block_index": len(tasks),
                "case_id": scenario.case_id,
                "root_seed_id": scenario.root_seed_id,
                "scenario_hash": scenario.scenario_hash,
                "configuration_run_order": scenario.configuration_run_order,
                "study": study,
                "pilot": pilot,
                "foundation": foundation,
                "case": case_map[scenario.case_id],
                "scenario": scenario,
                "freeze_id": freeze_id,
            }
        )
    return tasks


def execute(root: Path, workers: int | None) -> dict[str, Any]:
    study = load_confirmatory_config(root / CONFIG_PATH)
    pilot = load_pilot_config(root / PILOT_CONFIG_PATH)
    foundation = load_config(root / FOUNDATION_CONFIG_PATH)
    cases = load_confirmatory_cases(root / PILOT_MATRIX_PATH, study=study)
    first_start = not (root / SEED_DIRECTORY).exists()
    verification = verify_freeze(root, require_unmaterialized=first_start)
    if not verification["passed"]:
        raise RuntimeError(f"replacement freeze verification failed: {verification['errors']}")
    if first_start:
        seed_index = materialize_confirmatory_seeds(
            study,
            pilot,
            foundation,
            cases,
            root=root,
            freeze_id=verification["freeze_id"],
            readiness_id=verification["readiness_id"],
            seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
        )
    else:
        seed_index = json.loads((root / SEED_DIRECTORY / "index.json").read_text())
    seed_validation = validate_materialized_confirmatory_seeds(
        study,
        pilot,
        foundation,
        cases,
        root=root,
        freeze_id=verification["freeze_id"],
        readiness_id=verification["readiness_id"],
        seed_contract_sha256=seed_index["seed_contract_sha256"],
    )
    if not seed_validation["passed"]:
        raise RuntimeError("replacement seed schedule failed validation")
    selected_workers = default_workers() if workers is None else workers
    RESULT_DIRECTORY_PATH = root / RESULT_DIRECTORY
    RESULT_DIRECTORY_PATH.mkdir(parents=True, exist_ok=True)
    state_path = root / EXECUTION_STATE_PATH
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state.get("freeze_id") != verification["freeze_id"]:
            raise RuntimeError("execution state belongs to another frozen campaign")
    else:
        state = {"freeze_id": verification["freeze_id"], "orchestration_invocations": 0}
    state["orchestration_invocations"] += 1
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    campaign = run_confirmatory_campaign(
        study,
        pilot,
        foundation,
        cases,
        seed_manifest_path=root / SEED_DIRECTORY / MANIFEST_NAME,
        checkpoint_dir=root / CHECKPOINT_PATH,
        output_path=root / EPISODES_PATH,
        freeze_id=verification["freeze_id"],
        readiness_id=verification["readiness_id"],
        workers=selected_workers,
        progress=True,
    )
    if not campaign["complete"]:
        return {"passed": False, "status": "CHECKPOINTED_INCOMPLETE", "campaign": campaign}
    rows = load_episode_rows(root / EPISODES_PATH)
    seed_rows = _load_seed_rows(root)
    analysis = analyze_confirmatory_rows(rows, seed_rows, study)
    (root / ANALYSIS_PATH).write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    replay_tasks = _replay_tasks(root, study, pilot, foundation, cases, verification["freeze_id"])
    replay = _run_checkpointed_tasks(
        replay_tasks,
        checkpoint_dir=root / REPLAY_CHECKPOINT_PATH,
        output_path=root / REPLAY_EPISODES_PATH,
        workers=selected_workers,
        campaign_kind="replacement_confirmatory_replay_partition_45",
        campaign_binding={"freeze_id": verification["freeze_id"], "selection": "frozen replay"},
        progress=True,
    )
    selected_roots = {task["root_seed_id"] for task in replay_tasks}
    original_subset = [row for row in rows if row["root_seed_id"] in selected_roots]
    replay_rows = load_episode_rows(root / REPLAY_EPISODES_PATH)
    replay_equal = canonical_json(original_subset) == canonical_json(replay_rows)
    reproducibility = {
        "passed": bool(replay["passed"] and replay_equal and seed_validation["passed"]),
        "seed_validation": seed_validation,
        "replay": replay,
        "replay_byte_equivalent_rows": replay_equal,
    }
    (root / REPRODUCIBILITY_PATH).write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n"
    )
    summary = {
        "schema_version": study.schema_version,
        "freeze_id": verification["freeze_id"],
        "readiness_id": verification["readiness_id"],
        "partition_code": 45,
        "workers": selected_workers,
        "campaign": campaign,
        "analysis_decision": analysis["decision"],
        "reproducibility_passed": reproducibility["passed"],
        "scientific_cells": study.planned_episodes,
        "outcome_driven_retry_replacement_extension": False,
        "checkpoint_continuation_allowed": True,
    }
    (root / EXECUTION_SUMMARY_PATH).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return {
        "passed": bool(analysis["validity"]["passed"] and reproducibility["passed"]),
        "status": "COMPLETE" if analysis["validity"]["passed"] else "INVALID",
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 004 replacement confirmatory workflow")
    parser.add_argument(
        "command", choices=("validate", "benchmark", "freeze", "verify-freeze", "execute")
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "validate":
        result = validate(root)
    elif args.command == "benchmark":
        result = run_benchmark(root)
        (root / BENCHMARK_PATH).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    elif args.command == "freeze":
        result = freeze(root)
    elif args.command == "verify-freeze":
        result = verify_freeze(root, require_unmaterialized=True)
    else:
        result = execute(root, args.workers)
    if not result.get("passed", True):
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
