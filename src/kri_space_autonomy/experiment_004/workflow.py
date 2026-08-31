from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from kri_space_autonomy.experiment_003.workflow import repository_publication_scan

from .config import EXPECTED_BASE_COMMIT, EXPECTED_BRANCH, load_config
from .seeds import canonical_json, sha256_bytes, validate_seed_contract
from .validation import run_foundation_checks

CONFIG_PATH = Path("experiments/004/config.json")
SEED_CONTRACT_PATH = Path("experiments/004/seed-contract.json")
PREREGISTRATION_PATH = Path("experiments/004/preregistration.md")
DESIGN_PATH = Path("docs/experiment-004.md")
VALIDATION_PATH = Path("experiments/004/validation-evidence.json")
FREEZE_PATH = Path("experiments/004/freeze-manifest.json")
READINESS_PATH = Path("experiments/004/readiness.json")
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_004/*.py",
    "tests/test_experiment_004_*.py",
    "experiments/004/config.json",
    "experiments/004/seed-contract.json",
    "experiments/004/preregistration.md",
    "docs/experiment-004.md",
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


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in paths
    }


def _source_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    paths.add(root / VALIDATION_PATH)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def verify_merged_base_unchanged(root: Path) -> dict[str, Any]:
    """Verify every file tracked at the merged base byte-for-byte via Git blobs."""

    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", f"{EXPECTED_BASE_COMMIT}^{{tree}}")
    raw = subprocess.run(
        ["git", "ls-tree", "-r", "-z", EXPECTED_BASE_COMMIT],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    entries = [entry for entry in raw.split(b"\0") if entry]
    mismatches: list[str] = []
    baseline_records: list[tuple[str, str]] = []
    for entry in entries:
        metadata, raw_path = entry.split(b"\t", 1)
        _mode, object_type, raw_sha = metadata.decode().split(" ")
        relative = raw_path.decode()
        expected = raw_sha
        path = root / relative
        if object_type != "blob" or not path.is_file():
            mismatches.append(relative)
            continue
        actual = subprocess.run(
            ["git", "hash-object", "--", relative],
            cwd=root,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        if actual != expected:
            mismatches.append(relative)
        baseline_records.append((relative, expected))
    tracked_diff = _git(root, "diff", "--name-only", EXPECTED_BASE_COMMIT).splitlines()
    mismatches.extend(path for path in tracked_diff if path not in mismatches)
    aggregate = sha256_bytes(canonical_json(baseline_records))
    return {
        "passed": bool(head == EXPECTED_BASE_COMMIT and not mismatches),
        "base_commit": EXPECTED_BASE_COMMIT,
        "observed_head": head,
        "base_tree_git_id": tree,
        "base_tracked_files_verified": len(entries) - len(mismatches),
        "base_tracked_files_total": len(entries),
        "base_blob_map_sha256": aggregate,
        "mismatches": len(mismatches),
        "mismatches_preview": mismatches[:30],
        "scope": "every file tracked at merged main commit bef9bb4",
        "historical_experiments_001_003_included": True,
    }


def verify_historical_campaigns(root: Path) -> dict[str, Any]:
    commands = [
        _run(
            root,
            [
                "uv",
                "run",
                "python",
                "-m",
                "kri_space_autonomy.experiment_002_confirmatory.workflow",
                "verify-freeze",
            ],
            "experiment_002_final_freeze",
        ),
        _run(
            root,
            [
                "uv",
                "run",
                "python",
                "-m",
                "kri_space_autonomy.experiment_002_confirmatory.workflow",
                "verify-results",
            ],
            "experiment_002_final_results",
        ),
        _run(
            root,
            [
                "uv",
                "run",
                "python",
                "-c",
                (
                    "from pathlib import Path; "
                    "from kri_space_autonomy.experiment_003.workflow import "
                    "verify_freeze, verify_results; "
                    "r=Path.cwd(); "
                    "assert verify_freeze(r, require_unmaterialized=False)['passed']; "
                    "assert verify_results(r)['passed']"
                ),
            ],
            "experiment_003_pilot_freeze_and_results",
        ),
        _run(
            root,
            [
                "uv",
                "run",
                "python",
                "-c",
                (
                    "from pathlib import Path; "
                    "from kri_space_autonomy.experiment_003_confirmatory.workflow import "
                    "verify_freeze, verify_results; "
                    "r=Path.cwd(); "
                    "assert verify_freeze(r, require_unmaterialized=False)['passed']; "
                    "assert verify_results(r)['passed']"
                ),
            ],
            "experiment_003_confirmatory_freeze_and_results",
        ),
    ]
    return {
        "passed": all(command["passed"] for command in commands),
        "checks": commands,
    }


def verified_scientific_context(root: Path) -> dict[str, Any]:
    experiment_002 = json.loads(
        (root / "results/experiment-002-confirmatory/analysis.json").read_text(
            encoding="utf-8"
        )
    )
    experiment_003 = json.loads(
        (root / "results/experiment-003-confirmatory/analysis.json").read_text(
            encoding="utf-8"
        )
    )
    summaries = experiment_003["arm_summaries"]
    zero_d_pd_hazards = all(
        summaries[stratum][arm]["analysis_hazard"]["events"] == 0
        for stratum in summaries
        for arm in ("D", "PD")
    )
    h1 = experiment_003["primary_gatekeeping"]["H1"]
    h2 = experiment_003["primary_gatekeeping"]["H2"]
    context = {
        "experiment_002_final": {
            "decision": experiment_002["decision"],
            "H1_passed": experiment_002["primary_gatekeeping"]["H1"]["passed"],
            "H2_passed": experiment_002["primary_gatekeeping"]["H2"]["passed"],
        },
        "experiment_003_final": {
            "decision": experiment_003["decision"],
            "D_and_PD_zero_analysis_hazard_in_every_stratum": zero_d_pd_hazards,
            "H1_PD_minus_D_estimate": h1["estimate"],
            "H1_two_sided_95_interval": h1["two_sided_95_interval"],
            "H2_status": h2["status"],
            "descriptive_PD_minus_D_sustained_success": h2["estimate"],
            "E5_descriptive_sustained_success_difference": h2["stratum_estimates"][
                "E5_monitor_range_bias"
            ],
            "E6_descriptive_sustained_success_difference": h2["stratum_estimates"][
                "E6_shared_range_bias"
            ],
        },
    }
    passed = bool(
        context["experiment_002_final"]
        == {"decision": "favorable", "H1_passed": True, "H2_passed": True}
        and context["experiment_003_final"]["decision"] == "inconclusive"
        and zero_d_pd_hazards
        and h1["estimate"] == 0.0
        and h1["two_sided_95_interval"] == [0.0, 0.0]
        and h2["status"] == "not_tested_gate_closed"
        and h2["estimate"] == -0.184
        and h2["stratum_estimates"]["E5_monitor_range_bias"] < -0.6
        and h2["stratum_estimates"]["E6_shared_range_bias"] < -0.6
    )
    return {"passed": passed, **context}


def dependency_runtime_identity(root: Path) -> dict[str, Any]:
    dependency_files = (Path(".python-version"), Path("pyproject.toml"), Path("uv.lock"))
    hashes = {
        path.as_posix(): sha256_bytes((root / path).read_bytes())
        for path in dependency_files
    }
    observed = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "os": platform.system(),
        "architecture": platform.machine(),
        "thread_variables": {
            name: os.environ.get(name)
            for name in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
            )
            if os.environ.get(name) is not None
        },
    }
    expected_versions = {
        "python": "3.11.16",
        "numpy_version": "2.4.6",
        "scipy_version": "1.17.0",
    }
    mismatches = [
        key for key, value in expected_versions.items() if observed.get(key) != value
    ]
    return {
        "passed": not mismatches,
        "dependency_file_hashes": hashes,
        "expected_versions": expected_versions,
        "observed": observed,
        "mismatches": mismatches,
        "platform_match_required_for_future_replay": True,
    }


def validate(root: Path) -> dict[str, Any]:
    config = load_config(root / CONFIG_PATH)
    numerical = run_foundation_checks(config)
    seeds = validate_seed_contract(config, root / SEED_CONTRACT_PATH, root)
    base = verify_merged_base_unchanged(root)
    historical_campaigns = verify_historical_campaigns(root)
    context = verified_scientific_context(root)
    runtime = dependency_runtime_identity(root)
    scan = repository_publication_scan(root)
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
            "experiment_004_tests",
        ),
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
        {"id": "hcw_foundation_numerical", "passed": numerical["passed"], "observed": numerical},
        {"id": "seed_partition_contract", "passed": seeds["passed"], "observed": seeds},
        {"id": "merged_base_byte_identity", "passed": base["passed"], "observed": base},
        {
            "id": "historical_final_verifiers",
            "passed": historical_campaigns["passed"],
            "observed": historical_campaigns,
        },
        {
            "id": "historical_scientific_context",
            "passed": context["passed"],
            "observed": context,
        },
        {"id": "dependency_runtime_identity", "passed": runtime["passed"], "observed": runtime},
        {"id": "publication_privacy", "passed": scan["passed"], "observed": scan},
    ]
    passed = all(bool(check["passed"]) for check in checks)
    result = {
        "schema_version": config.schema_version,
        "phase": "pre_outcome_foundation_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": passed,
        "status": "READY_FOR_DESIGN_VALIDATION_PILOT" if passed else "NOT_READY",
        "checks": checks,
        "phase_appropriate_exclusions": {
            "tests": list(PHASE_INAPPLICABLE_TESTS),
            "reason": (
                "historical pre-materialization assertions are superseded by the frozen "
                "completed-campaign result verifiers"
            ),
        },
        "experiment_004_outcome_campaign_executed": False,
        "pilot_seeds_materialized": False,
        "future_confirmatory_partition_materialized": False,
        "future_confirmatory_hypothesis_frozen": False,
        "scientific_findings_claimed": False,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def _self_hashed_manifest(path: Path, identity_field: str) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    identity = manifest.pop(identity_field)
    if sha256_bytes(canonical_json(manifest)) != identity:
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    manifest[identity_field] = identity
    return manifest


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 004 freeze/readiness artifacts")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != EXPECTED_BASE_COMMIT:
        raise RuntimeError("Experiment 004 freeze requires the requested branch and merged base")
    validation = validate(root)
    if not validation["passed"]:
        readiness = {
            "schema_version": validation["schema_version"],
            "status": "NOT_READY",
            "freeze_id": None,
            "reason": "one or more fail-closed pre-outcome checks failed",
        }
        readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
        (root / READINESS_PATH).write_text(
            json.dumps(readiness, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError("Experiment 004 foundation validation is NOT_READY")
    config = load_config(root / CONFIG_PATH)
    source_hashes = _file_hashes(root, _source_files(root))
    base = verify_merged_base_unchanged(root)
    historical_campaigns = verify_historical_campaigns(root)
    context = verified_scientific_context(root)
    seeds = validate_seed_contract(config, root / SEED_CONTRACT_PATH, root)
    runtime = dependency_runtime_identity(root)
    scan = repository_publication_scan(root)
    if not all(
        item["passed"]
        for item in (base, historical_campaigns, context, seeds, runtime, scan)
    ):
        raise RuntimeError("freeze prerequisite changed after validation")
    unsigned = {
        "schema_version": config.schema_version,
        "phase": "pre_outcome_foundation_freeze",
        "status": "READY_FOR_DESIGN_VALIDATION_PILOT",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "Experiment 004 planar HCW pre-outcome foundation",
        "source_identity": {
            "branch": branch,
            "base_commit": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "paths": "project-relative only",
            "commit_created": False,
        },
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "merged_base_integrity": base,
        "historical_final_verifiers": historical_campaigns,
        "historical_scientific_context": context,
        "orbital_model": {
            "model": "planar linear Hill-Clohessy-Wiltshire relative motion",
            "central_body": config.central_body,
            "gravitational_parameter_m3_s2": config.gravitational_parameter_m3_s2,
            "reference_radius_m": config.reference_radius_m,
            "mean_motion_rad_s": config.mean_motion_rad_s,
            "orbital_period_s": config.orbital_period_s,
            "coordinate_frame": config.coordinate_frame,
            "x_axis_convention": config.x_axis_convention,
            "y_axis_convention": config.y_axis_convention,
            "state_order": list(config.state_order),
            "action_order": list(config.action_order),
            "propagation": "exact zero-order-hold augmented matrix exponential",
            "limitation": "local circular-orbit linear model; not nonlinear orbital mechanics",
        },
        "geometry": {
            "hard_body_radius_m": config.hard_body_radius_m,
            "hard_body_definition": "closed center-to-center separation threshold",
            "keep_out_radius_m": config.keep_out_radius_m,
            "hold_center_m": list(config.hold_center_m),
            "hold_position_halfwidth_m": list(config.hold_position_halfwidth_m),
            "hold_max_speed_mps": config.hold_max_speed_mps,
            "approach_y_bounds_m": list(config.approach_y_bounds_m),
            "approach_radial_halfwidth_m": list(
                config.approach_radial_halfwidth_m
            ),
            "event_semantics": "exact HCW arcs split at intervals no longer than one second",
        },
        "navigation_and_control": {
            "measurement_order": list(config.measurement_order),
            "measurement_covariance_shape": [4, 4],
            "fixed_lag_s": config.maximum_packet_lag_s,
            "filter_state": list(config.state_order),
            "reference_controller": "deterministic bounded discrete LQR hold controller",
            "reference_only_not_fitted": True,
            "product_scalar_contract_changed": False,
            "future_inferential_arm_family_frozen": False,
        },
        "outcome_domains": {
            "physical": ["collision", "unauthorized_keep_out_entry", "corridor_departure"],
            "mission": ["hold_acquired", "hold_dwell", "safe_incomplete"],
            "technical": [
                "primary_estimator_fault",
                "monitor_estimator_fault",
                "monitor_logic_fault",
                "shared_cause_fault",
                "controller_fault",
                "invalid_action",
                "numerical_failure",
            ],
            "aggregate_primary_endpoint_frozen": False,
        },
        "seed_partition_contract": seeds,
        "dependency_runtime_identity": runtime,
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "publication_privacy_scan": scan,
        "experiment_004_outcome_campaign_executed": False,
        "pilot_seeds_materialized": False,
        "future_confirmatory_partition_materialized": False,
        "future_confirmatory_hypothesis_frozen": False,
        "scientific_findings_claimed": False,
        "readiness_policy": "fail closed; no critical-check waiver",
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    readiness = {
        "schema_version": config.schema_version,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY_FOR_DESIGN_VALIDATION_PILOT",
        "scope": "separate non-inferential Experiment 004 design-validation pilot design",
        "pilot_partition_code": config.pilot_partition_code,
        "pilot_partition_state": "reserved_not_materialized_or_executed",
        "future_confirmatory_partition_code": config.future_confirmatory_partition_code,
        "future_confirmatory_partition_state": (
            "reserved_not_materialized_size_and_hypothesis_not_set"
        ),
        "next_task": (
            "freeze one non-inferential pilot matrix and sample count using only "
            "partition-41 calibration; validate nominal feasibility, forced event coding, "
            "channel topology, actuation cases, completeness, and replay before enabling "
            "a partition-43 generator"
        ),
        "pilot_generator_available": False,
        "outcome_campaign_executed": False,
        "scientific_findings_claimed": False,
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root)
    if not verification["passed"]:
        raise RuntimeError("Experiment 004 freeze failed internal verification")
    return {**unsigned, "readiness": readiness, "verification": verification}


def verify_freeze(root: Path) -> dict[str, Any]:
    manifest = _self_hashed_manifest(root / FREEZE_PATH, "freeze_id")
    errors: list[str] = []
    for relative, expected in manifest["source_file_hashes"].items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    validation_path = root / VALIDATION_PATH
    if (
        not validation_path.is_file()
        or sha256_bytes(validation_path.read_bytes()) != manifest["validation_sha256"]
    ):
        errors.append("validation_identity")
    base = verify_merged_base_unchanged(root)
    historical = verify_historical_campaigns(root)
    context = verified_scientific_context(root)
    config = load_config(root / CONFIG_PATH)
    seeds = validate_seed_contract(config, root / SEED_CONTRACT_PATH, root)
    runtime = dependency_runtime_identity(root)
    scan = repository_publication_scan(root)
    for label, result in (
        ("merged_base_integrity", base),
        ("historical_final_verifiers", historical),
        ("historical_scientific_context", context),
        ("seed_partition_contract", seeds),
        ("dependency_runtime_identity", runtime),
        ("publication_privacy", scan),
    ):
        if not result["passed"]:
            errors.append(label)
    try:
        readiness = _self_hashed_manifest(root / READINESS_PATH, "readiness_id")
        readiness_ok = bool(
            readiness["freeze_id"] == manifest["freeze_id"]
            and readiness["status"] == "READY_FOR_DESIGN_VALIDATION_PILOT"
            and readiness["pilot_generator_available"] is False
        )
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError):
        readiness = {}
        readiness_ok = False
    if not readiness_ok:
        errors.append("readiness_identity")
    return {
        "schema_version": manifest["schema_version"],
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "status": "READY_FOR_DESIGN_VALIDATION_PILOT" if not errors else "NOT_READY",
        "freeze_id": manifest["freeze_id"],
        "readiness_id": readiness.get("readiness_id"),
        "source_files_verified": len(manifest["source_file_hashes"]),
        "errors_preview": errors[:30],
        "merged_base_integrity": base,
        "historical_final_verifiers": historical,
        "historical_scientific_context": context,
        "seed_partition_contract": seeds,
        "dependency_runtime_identity": runtime,
        "publication_privacy_scan": scan,
        "experiment_004_outcome_campaign_executed": False,
        "future_confirmatory_partition_materialized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 004 planar HCW foundation")
    parser.add_argument(
        "command",
        choices=("validate", "freeze", "verify-freeze", "release-scan"),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "validate":
        result = validate(root)
    elif args.command == "freeze":
        result = freeze(root)
    elif args.command == "verify-freeze":
        result = verify_freeze(root)
    else:
        result = repository_publication_scan(root)
    if not result.get("passed", True):
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
