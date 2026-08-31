from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_004.workflow import verify_freeze as native_foundation_verify

from .analysis import analyze_pilot, load_episode_rows
from .calibration import calibrate, verify_calibration
from .config import (
    FOUNDATION_COMMIT,
    load_case_matrix,
    load_pilot_config,
)
from .runner import _scenario_from_row, run_block, run_pilot
from .seeds import (
    materialize_pilot_seeds,
    validate_materialized_pilot,
    validate_seed_contract,
)
from .validation import (
    foundation_identity,
    publication_privacy,
    run_design_checks,
    runtime_identity,
)

CONFIG_PATH = Path("experiments/004-pilot/config.json")
MATRIX_PATH = Path("experiments/004-pilot/case-matrix.json")
GATES_PATH = Path("experiments/004-pilot/gates.json")
SEED_CONTRACT_PATH = Path("experiments/004-pilot/seed-contract.json")
CALIBRATION_PATH = Path("experiments/004-pilot/calibration-evidence.json")
PREREGISTRATION_PATH = Path("experiments/004-pilot/preregistration.md")
VALIDATION_PATH = Path("experiments/004-pilot/validation-evidence.json")
FREEZE_PATH = Path("experiments/004-pilot/freeze-manifest.json")
READINESS_PATH = Path("experiments/004-pilot/readiness.json")
DOC_PATH = Path("docs/experiment-004-pilot.md")
SEEDS_DIR = Path("experiments/004-pilot/seeds")
RESULTS_DIR = Path("results/experiment-004-pilot")
EPISODES_PATH = RESULTS_DIR / "pilot-episodes.jsonl"
EXECUTION_PATH = RESULTS_DIR / "execution-summary.json"
ANALYSIS_PATH = RESULTS_DIR / "analysis.json"
QC_PATH = RESULTS_DIR / "qc.json"
EXPECTED_BRANCH = "experiment-004-pilot-design"
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_004_pilot/*.py",
    "tests/test_experiment_004_pilot_*.py",
    "experiments/004-pilot/config.json",
    "experiments/004-pilot/case-matrix.json",
    "experiments/004-pilot/gates.json",
    "experiments/004-pilot/seed-contract.json",
    "experiments/004-pilot/calibration-evidence.json",
    "experiments/004-pilot/calibration-attempt-001.json",
    "experiments/004-pilot/calibration-provenance.json",
    "experiments/004-pilot/preregistration.md",
    "docs/experiment-004-pilot.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
PHASE_INAPPLICABLE_TESTS = (
    (
        "tests/test_experiment_002_confirmatory_design.py::"
        "test_seed_contract_has_exact_eight_strata_without_materialized_roots"
    ),
    (
        "tests/test_experiment_002_confirmatory_workflow.py::"
        "test_freeze_phase_requires_partition_16_to_remain_unmaterialized"
    ),
    (
        "tests/test_experiment_003_design.py::"
        "test_seed_contract_reserves_outcome_partitions_without_materializing_them"
    ),
    (
        "tests/test_experiment_003_confirmatory_design.py::"
        "test_analysis_and_seed_contract_are_frozen_without_partition_32_materialization"
    ),
    (
        "tests/test_experiment_003_confirmatory_workflow.py::"
        "test_runtime_dependencies_match_frozen_foundation_and_partition_32_is_absent"
    ),
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
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
    if sha256_bytes(canonical_json(value)) != identity:
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def native_foundation_context_diagnosis(root: Path) -> dict[str, Any]:
    independent = foundation_identity(root)
    native = native_foundation_verify(root)
    expected_post_merge_limitation = bool(
        not native["passed"]
        and native.get("errors_preview") == ["merged_base_integrity"]
        and native.get("freeze_id") == independent.get("freeze_id")
        and native.get("readiness_id") == independent.get("readiness_id")
        and independent["passed"]
    )
    return {
        "passed": bool(native["passed"] or expected_post_merge_limitation),
        "native_verifier_passed": native["passed"],
        "native_errors": native.get("errors_preview", []),
        "expected_post_merge_context_limitation": expected_post_merge_limitation,
        "explanation": (
            "the foundation verifier was authored before its own additions were committed and "
            "treats those committed additions as diffs from the pre-foundation parent; exact "
            "self-hashes, source hashes, merged-commit anchor, and historical bytes are verified "
            "independently"
        ),
        "independent_foundation_identity": independent,
    }


def validate(root: Path) -> dict[str, Any]:
    pilot = load_pilot_config(root / CONFIG_PATH)
    cases = load_case_matrix(root / MATRIX_PATH)
    design = run_design_checks(root, pilot, cases, recompute_calibration=True)
    pytest_command = ["uv", "run", "pytest", "-q"]
    for test in PHASE_INAPPLICABLE_TESTS:
        pytest_command.extend(("--deselect", test))
    commands = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(root, pytest_command, "phase_appropriate_repository_tests"),
        _run(
            root,
            ["uv", "run", "pytest", "-q", "-k", "experiment_004"],
            "experiment_004_foundation_and_pilot_tests",
        ),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "stable_gate"),
        _run(root, ["git", "diff", "--check"], "diff_whitespace"),
    ]
    native_context = native_foundation_context_diagnosis(root)
    checks = [
        *commands,
        {"id": "pilot_design_fail_closed_checks", "passed": design["passed"], "observed": design},
        {
            "id": "foundation_native_verifier_context",
            "passed": native_context["passed"],
            "observed": native_context,
        },
    ]
    passed = all(bool(check["passed"]) for check in checks)
    result = {
        "schema_version": pilot.schema_version,
        "phase": "pre_partition_43_pilot_design_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": passed,
        "status": "READY_TO_FREEZE_PILOT_DESIGN" if passed else "NOT_READY",
        "checks": checks,
        "phase_appropriate_exclusions": {
            "tests": list(PHASE_INAPPLICABLE_TESTS),
            "reason": (
                "historical pre-materialization assertions are superseded by frozen completed-"
                "campaign result verifiers; no Experiment 004 pilot test is excluded"
            ),
        },
        "partition_41_use": "prospective_noninferential_mechanics_only",
        "partition_43_materialized": False,
        "partition_43_executed": False,
        "partition_44_materialized": False,
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
        raise RuntimeError("refusing to overwrite Experiment 004 pilot design freeze")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != FOUNDATION_COMMIT:
        raise RuntimeError(
            "pilot design freeze requires the requested branch and foundation commit"
        )
    calibration = verify_calibration(root, recompute=True)
    if not calibration["passed"]:
        raise RuntimeError("partition-41 calibration is not reproducibly valid")
    validation = validate(root)
    if not validation["passed"]:
        raise RuntimeError("pilot design validation is NOT_READY")
    pilot = load_pilot_config(root / CONFIG_PATH)
    cases = load_case_matrix(root / MATRIX_PATH)
    source_hashes = _file_hashes(root, _source_files(root))
    design = run_design_checks(root, pilot, cases, recompute_calibration=False)
    scan = publication_privacy(root)
    if not design["passed"] or not scan["passed"]:
        raise RuntimeError("pilot design freeze prerequisite changed after validation")
    unsigned = {
        "schema_version": pilot.schema_version,
        "phase": "pre_partition_43_pilot_design_freeze",
        "status": "READY_FOR_PILOT_EXECUTION",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "noninferential Experiment 004 planar HCW design-validation pilot",
        "source_identity": {
            "branch": branch,
            "head": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "commit_created": False,
            "paths": "project-relative only",
        },
        "foundation_identity": design["checks"]["foundation_freeze_readiness_identity"],
        "foundation_native_verifier_context": native_foundation_context_diagnosis(root),
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "calibration": calibration,
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
            "smallest candidate passing partition-41 mechanics and at least two appearances of "
            "each diagnostic configuration in each within-block order position; not power"
        ),
        "gates_sha256": sha256_bytes((root / GATES_PATH).read_bytes()),
        "seed_contract": validate_seed_contract(
            pilot,
            root / SEED_CONTRACT_PATH,
            root=root,
        ),
        "dependency_runtime_identity": runtime_identity(root),
        "historical_integrity": design["checks"][
            "historical_experiment_001_003_integrity"
        ],
        "publication_privacy_scan": scan,
        "controller_policy": {
            "family": (
                "frozen deterministic vector LQR reference and frozen vector "
                "monitor/fallback"
            ),
            "learned_policy_trained": False,
            "architecture_benefit_hypothesis_defined": False,
        },
        "analysis": {
            "mode": "descriptive_mechanistic_gate_only",
            "p_values_enabled": False,
            "superiority_noninferiority_enabled": False,
            "multiplicity_family_defined": False,
            "architecture_effect_claims_enabled": False,
        },
        "partition_states": {
            "41": "calibration_complete_noninferential_mechanics_only",
            "42": "reserved_unused",
            "43": "reserved_not_materialized_or_executed_write_once_generator_available",
            "44": "reserved_unmaterialized_hypothesis_and_sample_size_not_set_no_generator",
            "941": "deterministic_tests_only",
        },
        "partition_43_materialized": False,
        "partition_43_executed": False,
        "partition_44_materialized": False,
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
        "status": "READY_FOR_PILOT_EXECUTION",
        "scope": "one-time noninferential Experiment 004 design-validation pilot execution",
        "pilot_partition_code": pilot.pilot_partition_code,
        "pilot_partition_state": "reserved_not_materialized_or_executed",
        "pilot_root_rows": pilot.pilot_blocks,
        "pilot_complete_blocks": pilot.pilot_blocks,
        "pilot_episode_rows": pilot.pilot_episodes,
        "outcome_blind_replay_blocks": pilot.replay_blocks,
        "outcome_blind_replay_episodes": pilot.replay_episodes,
        "future_confirmatory_partition_code": pilot.future_confirmatory_partition_code,
        "future_confirmatory_partition_state": (
            "reserved_unmaterialized_hypothesis_and_sample_size_not_set"
        ),
        "future_confirmatory_generator_available": False,
        "next_task": (
            "one-time noninferential Experiment 004 design-validation pilot execution on "
            "partition 43"
        ),
        "partition_43_materialized": False,
        "partition_43_executed": False,
        "partition_44_materialized": False,
        "scientific_findings_claimed": False,
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root)
    if not verification["passed"]:
        raise RuntimeError("pilot design freeze failed internal verification")
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
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    validation = root / VALIDATION_PATH
    if (
        not validation.is_file()
        or sha256_bytes(validation.read_bytes()) != manifest.get("validation_sha256")
    ):
        errors.append("validation_identity")
    if (
        readiness.get("freeze_id") != manifest.get("freeze_id")
        or readiness.get("status") != "READY_FOR_PILOT_EXECUTION"
        or readiness.get("partition_43_materialized") is not False
        or readiness.get("future_confirmatory_generator_available") is not False
    ):
        errors.append("readiness_identity")
    pilot = load_pilot_config(root / CONFIG_PATH)
    cases = load_case_matrix(root / MATRIX_PATH)
    design = run_design_checks(root, pilot, cases, recompute_calibration=False)
    if not design["passed"]:
        errors.append("design_checks")
    runtime = runtime_identity(root)
    if runtime != manifest.get("dependency_runtime_identity"):
        errors.append("runtime_identity")
    scan = publication_privacy(root)
    if not scan["passed"]:
        errors.append("publication_privacy")
    return {
        "schema_version": pilot.schema_version,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "status": "READY_FOR_PILOT_EXECUTION" if not errors else "NOT_READY",
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "source_files_verified": len(manifest.get("source_file_hashes", {})),
        "errors_preview": errors[:30],
        "foundation_identity": design["checks"]["foundation_freeze_readiness_identity"],
        "calibration": design["checks"]["partition_41_calibration_provenance"],
        "seed_contract": design["checks"]["seed_domain_and_materialization_contract"],
        "historical_integrity": design["checks"][
            "historical_experiment_001_003_integrity"
        ],
        "publication_privacy_scan": scan,
        "partition_43_materialized": False,
        "partition_43_executed": False,
        "partition_44_materialized": False,
        "confirmatory_inference_enabled": False,
    }


def verify_replay(root: Path) -> dict[str, Any]:
    pilot = load_pilot_config(root / CONFIG_PATH)
    cases = load_case_matrix(root / MATRIX_PATH)
    case_map = {case.id: case for case in cases}
    replay = json.loads((root / SEEDS_DIR / "replay-subset.json").read_text(encoding="utf-8"))
    selected = set(replay["root_seed_ids"])
    scenarios = [
        _scenario_from_row(json.loads(line))
        for line in (root / SEEDS_DIR / "pilot.jsonl").read_text(encoding="utf-8").splitlines()
        if json.loads(line)["root_seed_id"] in selected
    ]
    original_rows = [
        row for row in load_episode_rows(root / EPISODES_PATH) if row["root_seed_id"] in selected
    ]
    replayed_rows = []
    foundation = load_config(root / "experiments/004/config.json")
    for scenario in scenarios:
        replayed_rows.extend(
            row.to_dict()
            for row in run_block(pilot, foundation, case_map[scenario.case_id], scenario)
        )
    first = sha256_bytes(canonical_json(original_rows))
    second = sha256_bytes(canonical_json(replayed_rows))
    return {
        "passed": bool(
            len(scenarios) == pilot.replay_blocks
            and len(original_rows) == len(replayed_rows) == pilot.replay_episodes
            and first == second
        ),
        "blocks": len(scenarios),
        "episodes": len(replayed_rows),
        "original_digest": first,
        "replay_digest": second,
    }


def analyze(root: Path) -> dict[str, Any]:
    if (root / ANALYSIS_PATH).exists() or (root / QC_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 004 pilot analysis")
    pilot = load_pilot_config(root / CONFIG_PATH)
    cases = load_case_matrix(root / MATRIX_PATH)
    rows = load_episode_rows(root / EPISODES_PATH)
    integrity = verify_freeze(root)
    replay = verify_replay(root)
    analysis, qc = analyze_pilot(rows, pilot, cases, integrity=integrity, replay=replay)
    (root / ANALYSIS_PATH).write_text(
        json.dumps(analysis, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (root / QC_PATH).write_text(
        json.dumps(qc, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {"analysis": analysis, "qc": qc}


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 004 noninferential pilot design")
    parser.add_argument(
        "command",
        choices=(
            "calibrate",
            "verify-calibration",
            "validate",
            "freeze",
            "verify-freeze",
            "materialize-pilot-seeds",
            "run-pilot",
            "analyze",
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
            load_pilot_config(root / CONFIG_PATH),
            load_config(root / "experiments/004/config.json"),
            load_case_matrix(root / MATRIX_PATH),
            root=root,
        )
    elif args.command == "run-pilot":
        verification = verify_freeze(root)
        if not verification["passed"]:
            raise RuntimeError("pilot execution requires verified design freeze")
        pilot = load_pilot_config(root / CONFIG_PATH)
        foundation = load_config(root / "experiments/004/config.json")
        cases = load_case_matrix(root / MATRIX_PATH)
        materialized = validate_materialized_pilot(
            pilot,
            foundation,
            cases,
            root=root,
            freeze_id=str(verification["freeze_id"]),
            readiness_id=str(verification["readiness_id"]),
        )
        if not materialized["passed"]:
            raise RuntimeError("partition-43 seed materialization failed validation")
        result = run_pilot(
            pilot,
            foundation,
            cases,
            seed_manifest_path=root / SEEDS_DIR / "pilot.jsonl",
            output_path=root / EPISODES_PATH,
        )
        (root / EXECUTION_PATH).write_text(
            json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    elif args.command == "analyze":
        result = analyze(root)
    else:
        result = publication_privacy(root)
    if not result.get("passed", result.get("qc", {}).get("overall_passed", True)):
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
