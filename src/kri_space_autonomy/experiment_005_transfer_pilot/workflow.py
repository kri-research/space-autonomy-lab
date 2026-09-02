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

from .calibration import calibrate, verify_calibration
from .config import (
    FOUNDATION_COMMIT,
    load_case_matrix,
    load_pilot_config,
)
from .seeds import (
    canonical_json,
    materialize_pilot_seeds,
    sha256_bytes,
    validate_seed_contract,
)
from .validation import (
    foundation_identity,
    historical_snapshot,
    information_boundary,
    matrix_and_gates,
    partition_52_authorization,
    partition_53_inert,
    publication_privacy,
    run_design_checks,
)

DESIGN_DIRECTORY = Path("experiments/005-transfer-pilot")
CONFIG_PATH = DESIGN_DIRECTORY / "config.json"
MATRIX_PATH = DESIGN_DIRECTORY / "case-matrix.json"
GATES_PATH = DESIGN_DIRECTORY / "gates.json"
SEED_CONTRACT_PATH = DESIGN_DIRECTORY / "seed-contract.json"
CALIBRATION_PATH = DESIGN_DIRECTORY / "calibration-evidence.json"
PREREGISTRATION_PATH = DESIGN_DIRECTORY / "preregistration.md"
VALIDATION_PATH = DESIGN_DIRECTORY / "validation-evidence.json"
FREEZE_PATH = DESIGN_DIRECTORY / "freeze-manifest.json"
READINESS_PATH = DESIGN_DIRECTORY / "readiness.json"
DOC_PATH = Path("docs/experiment-005-transfer-pilot.md")
EXPECTED_BRANCH = "experiment-005-transfer-pilot-design"
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_005_transfer_pilot/*.py",
    "tests/test_experiment_005_transfer_pilot_*.py",
    "experiments/005-transfer-pilot/config.json",
    "experiments/005-transfer-pilot/case-matrix.json",
    "experiments/005-transfer-pilot/gates.json",
    "experiments/005-transfer-pilot/seed-contract.json",
    "experiments/005-transfer-pilot/calibration-attempt-*.json",
    "experiments/005-transfer-pilot/calibration-provenance*.json",
    "experiments/005-transfer-pilot/calibration-evidence.json",
    "experiments/005-transfer-pilot/preregistration.md",
    "docs/experiment-005-transfer-pilot.md",
    ".python-version",
    "pyproject.toml",
    "uv.lock",
)


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
    for test in PRE_OUTCOME_DESELECTS:
        command.extend(("--deselect", test))
    return command


def validate(root: Path) -> dict[str, Any]:
    pilot = load_pilot_config(root / CONFIG_PATH, root=root)
    cases = load_case_matrix(root / MATRIX_PATH)
    design = run_design_checks(
        root, pilot, cases, recompute_calibration=True
    )
    commands = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(
            root,
            [
                "uv",
                "run",
                "pytest",
                "-q",
                "tests/test_experiment_005_dynamics.py",
                "tests/test_experiment_005_geometry.py",
                "tests/test_experiment_005_runner.py",
                "tests/test_experiment_005_foundation.py",
                "tests/test_experiment_005_transfer_pilot_design.py",
                "tests/test_experiment_005_transfer_pilot_calibration.py",
                "tests/test_experiment_005_transfer_pilot_seeds.py",
                "tests/test_experiment_005_transfer_pilot_runner.py",
                "tests/test_experiment_005_transfer_pilot_workflow.py",
            ],
            "experiment_005_foundation_and_transfer_pilot_tests",
        ),
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
            "id": "transfer_pilot_design_fail_closed_checks",
            "passed": design["passed"],
            "observed": design,
        },
    ]
    failed = [check["id"] for check in checks if not check["passed"]]
    result = {
        "schema_version": pilot.schema_version,
        "phase": "post_partition_51_pre_partition_52_design_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": not failed,
        "status": "READY_TO_FREEZE_TRANSFER_PILOT_DESIGN" if not failed else "NOT_READY",
        "smallest_blocker": failed[0] if failed else None,
        "checks": checks,
        "phase_appropriate_exclusions": {
            "tests": list(PRE_OUTCOME_DESELECTS),
            "reason": (
                "completed historical campaigns supersede their pre-materialization absence "
                "assertions; all frozen result verifiers remain mandatory"
            ),
        },
        "foundation_source_hashes_unchanged": design["checks"][
            "frozen_foundation_identity_and_phase_transition"
        ]["source_mismatches"]
        == [],
        "experiment_004_outcomes_used_for_design": False,
        "partition_51_calibration_complete": True,
        "partition_52_materialized": False,
        "partition_52_executed": False,
        "partition_53_touched": False,
        "confirmatory_inference_enabled": False,
        "scientific_findings_claimed": False,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 005 transfer-pilot freeze")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != FOUNDATION_COMMIT:
        raise RuntimeError(
            "transfer-pilot freeze requires the requested branch at merged foundation commit"
        )
    validation = validate(root)
    if not validation["passed"]:
        raise RuntimeError(f"transfer-pilot design is NOT_READY: {validation['smallest_blocker']}")
    pilot = load_pilot_config(root / CONFIG_PATH, root=root)
    cases = load_case_matrix(root / MATRIX_PATH)
    calibration = verify_calibration(root, recompute=False)
    design = next(
        check["observed"]
        for check in validation["checks"]
        if check["id"] == "transfer_pilot_design_fail_closed_checks"
    )
    scan = publication_privacy(root)
    if not calibration["passed"] or not design["passed"] or not scan["passed"]:
        raise RuntimeError("design-freeze prerequisite changed after validation")
    source_hashes = _file_hashes(root, _source_files(root))
    unsigned = {
        "schema_version": pilot.schema_version,
        "phase": "post_partition_51_pre_partition_52_design_freeze",
        "status": "READY_FOR_PARTITION_52_EXECUTION",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "noninferential Experiment 005 nonlinear-truth transfer-pilot design",
        "source_identity": {
            "branch": branch,
            "head": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "commit_created": False,
            "paths": "project-relative only",
        },
        "foundation_identity": foundation_identity(root),
        "foundation_phase_transition": {
            "foundation_bytes_modified": False,
            "foundation_readiness_retained_as_historical_identity": True,
            "partition_51_current_state_owned_by_transfer_design": True,
        },
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "calibration": calibration,
        "calibration_attempts": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
                "status": json.loads(path.read_text())["status"],
            }
            for path in sorted(
                (root / DESIGN_DIRECTORY).glob("calibration-attempt-*.json")
            )
        ],
        "matrix": {
            "case_ids": [case.id for case in cases],
            "configuration_ids": list(pilot.configuration_ids),
            "roots_per_case": pilot.pilot_roots_per_case,
            "complete_blocks": pilot.pilot_blocks,
            "episodes": pilot.pilot_episodes,
            "replay_blocks": pilot.replay_blocks,
            "replay_episodes": pilot.replay_episodes,
        },
        "sample_count_basis": (
            "smallest outcome-blind count covering every case and placing both diagnostic "
            "configurations once in each within-block order position; not statistical power"
        ),
        "gates_sha256": sha256_bytes((root / GATES_PATH).read_bytes()),
        "seed_contract": validate_seed_contract(
            pilot, root / SEED_CONTRACT_PATH, root=root
        ),
        "dependency_runtime_identity": dependency_runtime_identity(root),
        "publication_privacy_secrets_scan": scan,
        "analysis": {
            "mode": "descriptive_mechanistic_gate_only",
            "model_mismatch_absolute_endpoint": None,
            "p_values_enabled": False,
            "superiority_noninferiority_enabled": False,
            "hazard_rate_claims_enabled": False,
            "architecture_effect_claims_enabled": False,
        },
        "infrastructure_limits": {
            "failures": 0,
            "retries": 0,
            "replacement_roots": 0,
            "missing_unpublished_cell_checkpoint_continuation": True,
        },
        "partition_states": {
            "51": "mechanics_calibration_complete_noninferential_attempts_preserved",
            "52": "reserved_unmaterialized_unexecuted_write_once_generator_authorized",
            "53": "reserved_untouched_unmaterialized_no_hypothesis_size_design_or_generator",
            "951": "deterministic_tests_only",
        },
        "partition_52_generator_authorized": True,
        "partition_52_generator_invoked": False,
        "partition_52_materialized": False,
        "partition_52_executed": False,
        "partition_53_touched": False,
        "confirmatory_inference_enabled": False,
        "scientific_findings_claimed": False,
        "readiness_policy": "fail closed; no critical-check waiver",
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    readiness = {
        "schema_version": pilot.schema_version,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY_FOR_PARTITION_52_EXECUTION",
        "scope": "one future noninferential Experiment 005 transfer-pilot execution",
        "calibration_partition_code": 51,
        "calibration_partition_state": "mechanics_calibration_complete_attempts_preserved",
        "pilot_partition_code": 52,
        "pilot_partition_state": "reserved_not_materialized_or_executed",
        "pilot_root_rows": pilot.pilot_blocks,
        "pilot_complete_blocks": pilot.pilot_blocks,
        "pilot_episode_rows": pilot.pilot_episodes,
        "outcome_blind_replay_blocks": pilot.replay_blocks,
        "outcome_blind_replay_episodes": pilot.replay_episodes,
        "pilot_generator_authorized": True,
        "pilot_generator_invoked": False,
        "future_confirmatory_partition_code": 53,
        "future_confirmatory_partition_state": (
            "reserved_untouched_unmaterialized_hypothesis_sample_size_and_design_not_set"
        ),
        "future_confirmatory_generator_available": False,
        "next_task": (
            "separate one-time partition-52 materialization and noninferential checkpointed "
            "pilot execution; partition 53 remains out of scope"
        ),
        "partition_52_materialized": False,
        "partition_52_executed": False,
        "partition_53_touched": False,
        "scientific_findings_claimed": False,
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root)
    if not verification["passed"]:
        raise RuntimeError("transfer-pilot design freeze failed internal verification")
    return {**unsigned, "readiness": readiness, "verification": verification}


def verify_freeze(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = _self_hashed(root / FREEZE_PATH, "freeze_id")
        readiness = _self_hashed(root / READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {
            "passed": False,
            "status": "NOT_READY",
            "freeze_id": None,
            "readiness_id": None,
            "errors_preview": [f"freeze_load:{exc}"],
        }
    for relative, expected in manifest.get("source_file_hashes", {}).items():
        path = root / relative
        observed = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if observed != expected:
            errors.append(relative)
    validation = root / VALIDATION_PATH
    if (
        not validation.is_file()
        or sha256_bytes(validation.read_bytes()) != manifest.get("validation_sha256")
    ):
        errors.append("validation_identity")
    pilot = load_pilot_config(root / CONFIG_PATH, root=root)
    cases = load_case_matrix(root / MATRIX_PATH)
    foundation = foundation_identity(root)
    calibration = verify_calibration(root, recompute=False)
    seed_contract = validate_seed_contract(
        pilot, root / SEED_CONTRACT_PATH, root=root
    )
    lightweight_checks = {
        "foundation": foundation,
        "calibration": calibration,
        "seed_contract": seed_contract,
        "matrix_and_gates": matrix_and_gates(root, pilot, cases),
        "information_boundary": information_boundary(),
        "partition_52_authorization": partition_52_authorization(root, pilot),
        "partition_53_inert": partition_53_inert(root, pilot),
        "historical_snapshot": historical_snapshot(root),
    }
    if not all(check["passed"] for check in lightweight_checks.values()):
        errors.append("frozen_design_checks")
    if (
        readiness.get("freeze_id") != manifest.get("freeze_id")
        or readiness.get("status") != "READY_FOR_PARTITION_52_EXECUTION"
        or readiness.get("pilot_generator_authorized") is not True
        or readiness.get("pilot_generator_invoked") is not False
        or readiness.get("partition_52_materialized") is not False
        or readiness.get("future_confirmatory_generator_available") is not False
        or readiness.get("partition_53_touched") is not False
    ):
        errors.append("readiness_identity")
    runtime = dependency_runtime_identity(root)
    if runtime != manifest.get("dependency_runtime_identity"):
        errors.append("runtime_identity")
    scan = publication_privacy(root)
    if not scan["passed"]:
        errors.append("publication_privacy")
    return {
        "schema_version": pilot.schema_version,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "status": "READY_FOR_PARTITION_52_EXECUTION" if not errors else "NOT_READY",
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "source_files_verified": len(manifest.get("source_file_hashes", {})),
        "errors_preview": errors[:30],
        "foundation_identity": foundation,
        "calibration": calibration,
        "seed_contract": seed_contract,
        "partition_52_generator_authorized": True,
        "partition_52_generator_invoked": False,
        "partition_52_materialized": False,
        "partition_52_executed": False,
        "partition_53_touched": False,
        "confirmatory_inference_enabled": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 005 noninferential nonlinear-truth transfer-pilot design"
    )
    parser.add_argument(
        "command",
        choices=(
            "calibrate",
            "verify-calibration",
            "validate",
            "freeze",
            "verify-freeze",
            "materialize-pilot-seeds",
            "release-scan",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "calibrate":
        result = calibrate(root)
    elif args.command == "verify-calibration":
        result = verify_calibration(root, recompute=True)
    elif args.command == "validate":
        result = validate(root)
    elif args.command == "freeze":
        result = freeze(root)
    elif args.command == "verify-freeze":
        result = verify_freeze(root)
    elif args.command == "materialize-pilot-seeds":
        result = materialize_pilot_seeds(
            load_pilot_config(root / CONFIG_PATH, root=root),
            load_e005_config(root / "experiments/005/config.json", root=root),
            load_e004_config(root / "experiments/004/config.json"),
            load_case_matrix(root / MATRIX_PATH),
            root=root,
        )
    else:
        result = publication_privacy(root)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if not result.get("passed", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
