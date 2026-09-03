from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_004_closeout import PRE_OUTCOME_DESELECTS
from kri_space_autonomy.experiment_005.config import load_config as load_e005_config
from kri_space_autonomy.experiment_005.workflow import dependency_runtime_identity
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.runner import _publish_no_clobber
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    canonical_json,
    scenario_from_row,
    sha256_bytes,
)
from kri_space_autonomy.experiment_005_transfer_pilot.validation import publication_privacy

from .analysis import validate_fixed_cells
from .config import BASE_COMMIT, load_confirmatory_config
from .runner import run_spawn_checkpointed_confirmatory_campaign
from .seeds import (
    CONTRACT_PATH,
    DESIGN_DIRECTORY,
    INDEX_NAME,
    MANIFEST_NAME,
    REPLAY_NAME,
    RESULT_DIRECTORY,
    SEED_DIRECTORY,
    load_confirmatory_cases,
    materialize_confirmatory_seeds,
    partition_53_unmaterialized,
    validate_materialized_confirmatory_seeds,
    validate_seed_contract,
)
from .validation import run_design_checks

CONFIG_PATH = DESIGN_DIRECTORY / "config.json"
MATRIX_PATH = DESIGN_DIRECTORY / "case-matrix.json"
PREREGISTRATION_PATH = DESIGN_DIRECTORY / "preregistration.md"
LINEAGE_AUDIT_PATH = DESIGN_DIRECTORY / "lineage-audit.json"
VALIDATION_PATH = DESIGN_DIRECTORY / "validation-evidence.json"
FREEZE_PATH = DESIGN_DIRECTORY / "freeze-manifest.json"
READINESS_PATH = DESIGN_DIRECTORY / "readiness.json"
DOC_PATH = Path("docs/experiment-005-confirmatory.md")
EXPECTED_BRANCH = "experiment-005-confirmatory-design-v2"
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_005_confirmatory/*.py",
    "tests/test_experiment_005_confirmatory_*.py",
    "experiments/005-confirmatory/config.json",
    "experiments/005-confirmatory/case-matrix.json",
    "experiments/005-confirmatory/seed-contract.json",
    "experiments/005-confirmatory/lineage-audit.json",
    "experiments/005-confirmatory/preregistration.md",
    "docs/experiment-005-confirmatory.md",
    "docs/experiment-005-confirmatory-design-blocker.md",
    ".github/workflows/ci.yml",
    ".python-version",
    "pyproject.toml",
    "uv.lock",
)
E005_PHASE_INAPPLICABLE_TESTS = (
    "tests/test_experiment_005_transfer_pilot_workflow.py::"
    "test_partition_53_is_untouched_and_has_no_generator_or_roots",
    "tests/test_experiment_005_transfer_pilot_closeout.py::"
    "test_invalid_partition_52_attempt_is_preserved_and_verified",
    "tests/test_experiment_005_transfer_pilot_replacement.py::"
    "test_amendment_preserves_invalid_closeout_and_scientific_design",
    "tests/test_experiment_005_transfer_pilot_replacement_closeout.py::"
    "test_partition_54_execution_and_frozen_gates_validate",
    "tests/test_experiment_005_transfer_pilot_replacement_closeout.py::"
    "test_closeout_is_descriptive_and_leaves_partition_53_untouched",
    "tests/test_experiment_005_transfer_pilot_replacement_closeout.py::"
    "test_public_closeout_package_verifies_when_materialized",
)
PHASE_INAPPLICABLE_TESTS = tuple(PRE_OUTCOME_DESELECTS) + E005_PHASE_INAPPLICABLE_TESTS


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _run(root: Path, command: list[str], label: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    lines = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
    return {
        "id": label,
        "command": " ".join(command),
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "summary": lines[-1] if lines else "",
    }


def _source_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    paths.add(root / VALIDATION_PATH)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in paths
    }


def _self_hashed(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    if identity != sha256_bytes(canonical_json(value)):
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def _phase_pytest_command() -> list[str]:
    command = ["uv", "run", "pytest", "-q"]
    for test in PHASE_INAPPLICABLE_TESTS:
        command.extend(("--deselect", test))
    return command


def _focused_tests() -> list[str]:
    return [
        "uv",
        "run",
        "pytest",
        "-q",
        "tests/test_experiment_005_dynamics.py",
        "tests/test_experiment_005_geometry.py",
        "tests/test_experiment_005_runner.py",
        "tests/test_experiment_005_confirmatory_design.py",
        "tests/test_experiment_005_confirmatory_analysis.py",
        "tests/test_experiment_005_confirmatory_seeds.py",
        "tests/test_experiment_005_confirmatory_validation.py",
    ]


def validate(root: Path) -> dict[str, Any]:
    study = load_confirmatory_config(root / CONFIG_PATH)
    design = run_design_checks(root, study)
    commands = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(root, _focused_tests(), "experiment_005_confirmatory_focused_tests"),
        _run(root, _phase_pytest_command(), "phase_appropriate_repository_tests"),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "stable_gate"),
        _run(root, ["git", "diff", "--check"], "diff_whitespace"),
    ]
    checks = [
        *commands,
        {
            "id": "confirmatory_design_fail_closed_checks",
            "passed": design["passed"],
            "observed": design,
        },
    ]
    failed = [check["id"] for check in checks if not check["passed"]]
    result = {
        "schema_version": study.schema_version,
        "phase": "pre_partition_53_confirmatory_design_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": not failed,
        "status": "READY_TO_FREEZE_PARTITION_53_DESIGN" if not failed else "NOT_READY",
        "smallest_blocker": failed[0] if failed else None,
        "checks": checks,
        "phase_appropriate_exclusions": {
            "tests": list(PHASE_INAPPLICABLE_TESTS),
            "reason": (
                "historical absence assertions are superseded by the prospective design phase; "
                "immutable source, result, replay, and checksum identities remain mandatory"
            ),
        },
        "partition_54_use": (
            "mechanics, feasibility, process launch, checkpoint, replay, and integrity only"
        ),
        "partition_54_outcomes_used_for_design": False,
        "partition_53_generator_invoked": False,
        "partition_53_materialized": False,
        "partition_53_executed": False,
        "scientific_findings_claimed": False,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 005 confirmatory freeze")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != BASE_COMMIT:
        raise RuntimeError(
            "confirmatory freeze requires the requested branch at merged integrity repair"
        )
    validation = validate(root)
    if not validation["passed"]:
        raise RuntimeError(f"confirmatory design is NOT_READY: {validation['smallest_blocker']}")
    study = load_confirmatory_config(root / CONFIG_PATH)
    design = next(
        check["observed"]
        for check in validation["checks"]
        if check["id"] == "confirmatory_design_fail_closed_checks"
    )
    scan = publication_privacy(root)
    partition = partition_53_unmaterialized(root)
    if not design["passed"] or not scan["passed"] or not partition["passed"]:
        raise RuntimeError("confirmatory freeze prerequisite changed after validation")
    source_hashes = _file_hashes(root, _source_files(root))
    sample = design["checks"]["sample_size_and_analysis"]
    lineage = design["checks"]["complete_experiment_005_lineage"]
    seed_contract = validate_seed_contract(
        study,
        root / CONTRACT_PATH,
        root=root,
        require_unmaterialized=True,
    )
    unsigned = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_partition_53_confirmatory_design_freeze",
        "status": "READY_FOR_PARTITION_53_EXECUTION",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "two-case synthetic nonlinear-truth independent-monitor assurance comparison",
        "source_identity": {
            "branch": branch,
            "base_commit": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "commit_created": False,
            "paths": "project-relative only",
        },
        "complete_experiment_005_lineage": lineage,
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "seed_contract": seed_contract,
        "seed_contract_sha256": seed_contract["contract_sha256"],
        "scientific_question": (
            "Does the independent-monitor gate reduce paired physical adverse-event risk in "
            "the equal-weight primary-bias/dropout nonlinear-truth population while keeping "
            "gate-induced hold loss below 0.05?"
        ),
        "estimands": {
            "primary": (
                "equal-weight gate-minus-reference risk difference for collision OR unauthorized "
                "keep-out entry OR corridor departure"
            ),
            "mission": "probability of reference hold acquisition with gated hold loss",
        },
        "design": {
            "cases": list(study.cases),
            "case_weights": study.case_weights,
            "configurations": list(study.configurations),
            "paired_blocks": study.planned_blocks,
            "episodes": study.planned_episodes,
            "replay_blocks": study.replay_blocks,
            "replay_episodes": study.replay_episodes,
            "standard_horizon_s": study.standard_horizon_s,
        },
        "validity_gates": {
            "minimum_covariance_eigenvalue": (
                study.minimum_covariance_eigenvalue_lower_bound
            ),
            "maximum_covariance_trace_exclusive": (
                study.maximum_covariance_trace_exclusive_upper_bound
            ),
            "T03_primary_fault_active_packets_per_episode": 30,
            "T04_primary_fault_active_packets_per_episode": 6,
            "monitor_fault_active_packets_per_episode": 0,
            "nonlinear_truth_numerical_valid_required": True,
        },
        "analysis_contract": {
            "H1": (
                "exact one-sided paired-discordance test at alpha 0.025 plus observed "
                "gate-minus-reference risk difference <= -0.05"
            ),
            "H2": (
                "after H1 only, exact one-sided gate-induced hold-loss risk below 0.05 at "
                "alpha 0.025"
            ),
            "secondary_inferential_family": None,
            "gatekeeping": "fixed sequence H1 then H2",
            "valid_null_harmful_or_inconclusive_result_allowed": True,
        },
        "sample_size": sample,
        "execution_protocol": {
            "entrypoint": (
                "uv run python -m kri_space_autonomy.experiment_005_confirmatory.workflow "
                "execute --workers 8"
            ),
            "process_start_method": "spawn",
            "work_unit": "complete paired root block",
            "completed_block_storage": "atomic campaign-bound content-hashed shard",
            "checkpoint_continuation": (
                "validate completed shards and execute missing unpublished blocks only"
            ),
            "completed_valid_blocks_recomputed": False,
            "maximum_infrastructure_failures": 0,
            "maximum_retries": 0,
            "maximum_replacement_roots": 0,
            "corrupt_duplicate_foreign_or_incomplete_evidence": "fail closed",
        },
        "dependency_runtime_identity": dependency_runtime_identity(root),
        "publication_privacy_secrets_scan": scan,
        "partition_states": {
            "51": "mechanics_calibration_complete_noninferential",
            "52": "invalid_infrastructure_attempt_permanently_retired",
            "53": "reserved_unmaterialized_unexecuted_generator_authorized",
            "54": "valid_noninferential_replacement_pilot_closed",
            "951": "deterministic_tests_only",
        },
        "partition_53_generator_authorized": True,
        "partition_53_generator_invoked": False,
        "partition_53_materialized": False,
        "partition_53_executed": False,
        "partition_54_outcomes_used_for_design": False,
        "scientific_findings_claimed": False,
        "readiness_policy": "conjunctive fail closed; no critical-check waiver",
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    readiness = {
        "schema_version": study.schema_version,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY_FOR_PARTITION_53_EXECUTION",
        "decision": "READY",
        "scope": "one write-once 2,136-episode partition-53 confirmatory campaign",
        "partition_code": 53,
        "partition_state": "reserved_not_materialized_or_executed",
        "paired_blocks": study.planned_blocks,
        "episode_rows": study.planned_episodes,
        "replay_blocks": study.replay_blocks,
        "replay_episode_rows": study.replay_episodes,
        "generator_authorized": True,
        "generator_invoked": False,
        "confirmatory_seeds_materialized": False,
        "confirmatory_outcomes_executed": False,
        "maximum_retries": 0,
        "maximum_replacement_roots": 0,
        "next_command": (
            "uv run python -m kri_space_autonomy.experiment_005_confirmatory.workflow "
            "execute --workers 8"
        ),
        "next_task": "one write-once partition-53 confirmatory execution after independent review",
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError(
            f"confirmatory design freeze failed verification: {verification['errors_preview']}"
        )
    return {"freeze": unsigned, "readiness": readiness, "verification": verification}


def verify_freeze(root: Path, *, require_unmaterialized: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = _self_hashed(root / FREEZE_PATH, "freeze_id")
        readiness = _self_hashed(root / READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {
            "passed": False,
            "status": "NOT_READY",
            "errors_preview": [f"freeze_load:{type(exc).__name__}"],
        }
    for relative, expected in manifest.get("source_file_hashes", {}).items():
        path = root / relative
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected:
            errors.append(f"source:{relative}")
    if sha256_bytes((root / VALIDATION_PATH).read_bytes()) != manifest.get(
        "validation_sha256"
    ):
        errors.append("validation_identity")
    study = load_confirmatory_config(root / CONFIG_PATH)
    from .validation import (
        execution_protocol_contract,
        lineage_integrity,
        matrix_and_outcome_boundary,
        sample_size_and_analysis_contract,
    )

    chain = lineage_integrity(root)
    matrix = matrix_and_outcome_boundary(root, study)
    sample = sample_size_and_analysis_contract(study)
    execution = execution_protocol_contract()
    boundary = publication_privacy(root)
    seed_contract = validate_seed_contract(
        study,
        root / CONTRACT_PATH,
        root=root,
        require_unmaterialized=require_unmaterialized,
    )
    for name, check in (
        ("lineage", chain),
        ("matrix", matrix),
        ("sample", sample),
        ("execution", execution),
        ("seed_contract", seed_contract),
        ("publication", boundary),
    ):
        if not check["passed"]:
            errors.append(name)
    if not (
        readiness.get("freeze_id") == manifest.get("freeze_id")
        and readiness.get("status") == "READY_FOR_PARTITION_53_EXECUTION"
        and readiness.get("partition_code") == 53
        and readiness.get("generator_authorized") is True
        and readiness.get("generator_invoked") is False
        and readiness.get("confirmatory_seeds_materialized") is False
        and readiness.get("confirmatory_outcomes_executed") is False
        and manifest.get("partition_53_generator_invoked") is False
        and manifest.get("partition_54_outcomes_used_for_design") is False
    ):
        errors.append("readiness_identity")
    if dependency_runtime_identity(root) != manifest.get("dependency_runtime_identity"):
        errors.append("runtime_identity")
    return {
        "schema_version": study.schema_version,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "status": "READY_FOR_PARTITION_53_EXECUTION" if not errors else "NOT_READY",
        "errors_preview": errors[:30],
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "require_unmaterialized": require_unmaterialized,
        "source_files_verified": len(manifest.get("source_file_hashes", {})),
        "lineage": chain,
        "seed_contract": seed_contract,
        "partition_53_generator_authorized": True,
        "partition_53_generator_invoked": False,
        "partition_53_materialized": False if require_unmaterialized else None,
        "partition_53_executed": False if require_unmaterialized else None,
    }


def _load_seed_scenarios(root: Path) -> tuple[Any, ...]:
    return tuple(
        scenario_from_row(json.loads(line))
        for line in (root / SEED_DIRECTORY / MANIFEST_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
    )


def _materialize(root: Path) -> dict[str, Any]:
    study = load_confirmatory_config(root / CONFIG_PATH)
    pilot = load_pilot_config(
        root / "experiments/005-transfer-pilot/config.json", root=root
    )
    verification = verify_freeze(root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError("confirmatory design freeze is not ready")
    return materialize_confirmatory_seeds(
        study,
        pilot,
        load_e005_config(root / "experiments/005/config.json", root=root),
        load_e004_config(root / "experiments/004/config.json"),
        load_confirmatory_cases(
            root / "experiments/005-transfer-pilot/case-matrix.json", study=study
        ),
        root=root,
        freeze_id=verification["freeze_id"],
        readiness_id=verification["readiness_id"],
        seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
    )


def execute(root: Path, workers: int | None) -> dict[str, Any]:
    first_start = not (root / SEED_DIRECTORY).exists()
    if first_start:
        _materialize(root)
    verification = verify_freeze(root, require_unmaterialized=False)
    if not verification["passed"]:
        raise RuntimeError("confirmatory design identity is not valid for execution")
    study = load_confirmatory_config(root / CONFIG_PATH)
    pilot = load_pilot_config(
        root / "experiments/005-transfer-pilot/config.json", root=root
    )
    foundation = load_e005_config(root / "experiments/005/config.json", root=root)
    e004 = load_e004_config(root / "experiments/004/config.json")
    cases = load_confirmatory_cases(
        root / "experiments/005-transfer-pilot/case-matrix.json", study=study
    )
    seed_index = json.loads((root / SEED_DIRECTORY / INDEX_NAME).read_text())
    seed_validation = validate_materialized_confirmatory_seeds(
        study,
        pilot,
        foundation,
        e004,
        cases,
        root=root,
        freeze_id=verification["freeze_id"],
        readiness_id=verification["readiness_id"],
        seed_contract_sha256=seed_index["seed_contract_sha256"],
    )
    if not seed_validation["passed"]:
        raise RuntimeError("partition-53 materialized schedule failed validation")
    scenarios = _load_seed_scenarios(root)
    campaign = run_spawn_checkpointed_confirmatory_campaign(
        root / RESULT_DIRECTORY / "campaign",
        study=study,
        pilot=pilot,
        foundation=foundation,
        e004=e004,
        cases=cases,
        scenarios=scenarios,
        freeze_id=verification["freeze_id"],
        workers=workers,
    )
    if not campaign["complete"]:
        return {"passed": False, "status": "INCOMPLETE_FAIL_CLOSED", "campaign": campaign}
    output_path = root / RESULT_DIRECTORY / "campaign/confirmatory-episodes.jsonl"
    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    seed_rows = [
        json.loads(line)
        for line in (root / SEED_DIRECTORY / MANIFEST_NAME).read_text().splitlines()
    ]
    cells = validate_fixed_cells(rows, seed_rows, study)
    if not cells["passed"]:
        raise RuntimeError("partition-53 fixed-cell validity gate failed")
    replay_spec = json.loads((root / SEED_DIRECTORY / REPLAY_NAME).read_text())
    selected = set(replay_spec["root_seed_ids"])
    replay_scenarios = tuple(
        scenario for scenario in scenarios if scenario.root_seed_id in selected
    )
    replay = run_spawn_checkpointed_confirmatory_campaign(
        root / RESULT_DIRECTORY / "replay",
        study=study,
        pilot=pilot,
        foundation=foundation,
        e004=e004,
        cases=cases,
        scenarios=replay_scenarios,
        freeze_id=verification["freeze_id"],
        workers=workers,
    )
    replay_path = root / RESULT_DIRECTORY / "replay/confirmatory-episodes.jsonl"
    original_subset = b"".join(
        canonical_json(row) + b"\n" for row in rows if row["root_seed_id"] in selected
    )
    replay_equivalent = replay_path.read_bytes() == original_subset
    summary = {
        "schema_version": study.schema_version,
        "design_freeze_id": verification["freeze_id"],
        "design_readiness_id": verification["readiness_id"],
        "partition_code": 53,
        "campaign": campaign,
        "complete_cell_validation": cells,
        "replay": replay,
        "replay_byte_equivalent": replay_equivalent,
        "retries": 0,
        "replacement_roots": 0,
        "status": "EXECUTION_COMPLETE_PENDING_FROZEN_CONFIRMATORY_ANALYSIS",
    }
    summary_path = root / RESULT_DIRECTORY / "execution-summary.json"
    content = (
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    )
    if summary_path.exists():
        if summary_path.read_bytes() != content:
            raise RuntimeError("existing execution summary conflicts with frozen campaign")
    else:
        _publish_no_clobber(summary_path, content)
    return {
        "passed": bool(cells["passed"] and replay["passed"] and replay_equivalent),
        "status": summary["status"],
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 005 partition-53 confirmatory design and execution"
    )
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "freeze",
            "verify-freeze",
            "materialize-seeds",
            "execute",
            "release-scan",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "validate":
        result = validate(root)
    elif args.command == "freeze":
        result = freeze(root)
    elif args.command == "verify-freeze":
        result = verify_freeze(root, require_unmaterialized=True)
    elif args.command == "materialize-seeds":
        result = _materialize(root)
    elif args.command == "execute":
        result = execute(root, args.workers)
    else:
        result = publication_privacy(root)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if not result.get("passed", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
