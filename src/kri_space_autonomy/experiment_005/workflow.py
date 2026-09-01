from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from kri_space_autonomy.experiment_003.workflow import repository_publication_scan
from kri_space_autonomy.experiment_004_closeout import PRE_OUTCOME_DESELECTS

from .config import EXPECTED_BASE_COMMIT, EXPECTED_BRANCH, load_config
from .seeds import canonical_json, sha256_bytes, validate_seed_contract
from .validation import run_foundation_checks

CONFIG_PATH = Path("experiments/005/config.json")
SEED_CONTRACT_PATH = Path("experiments/005/seed-contract.json")
PREREGISTRATION_PATH = Path("experiments/005/preregistration.md")
DESIGN_PATH = Path("docs/experiment-005.md")
VALIDATION_PATH = Path("experiments/005/validation-evidence.json")
FREEZE_PATH = Path("experiments/005/freeze-manifest.json")
READINESS_PATH = Path("experiments/005/readiness.json")
CI_PATH = Path(".github/workflows/ci.yml")
BASE_CHANGE_ALLOWLIST = {CI_PATH.as_posix()}
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_005/*.py",
    "tests/test_experiment_005_*.py",
    "experiments/005/config.json",
    "experiments/005/seed-contract.json",
    "experiments/005/preregistration.md",
    "docs/experiment-005.md",
    ".github/workflows/ci.yml",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
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


def _verify_e003_confirmatory_cross_platform(root: Path) -> dict[str, Any]:
    from kri_space_autonomy.experiment_003_confirmatory.workflow import (
        dependency_runtime_identity as e003_runtime_identity,
    )
    from kri_space_autonomy.experiment_003_confirmatory.workflow import (
        verify_freeze as verify_e003_freeze,
    )
    from kri_space_autonomy.experiment_003_confirmatory.workflow import (
        verify_results as verify_e003_results,
    )

    frozen = verify_e003_freeze(root, require_unmaterialized=False)
    result = verify_e003_results(root)
    mode = "native deterministic rederivation"
    passed = bool(frozen["passed"] and result["passed"])
    details: dict[str, Any] = {
        "freeze_passed": frozen["passed"],
        "results_passed": result["passed"],
    }
    if frozen["passed"] and not result["passed"]:
        runtime = e003_runtime_identity(root)
        seed = result.get("seed_validation", {})
        allowed_cross_platform = bool(
            result.get("errors_preview") == ["seed_validation"]
            and seed.get("errors_preview") == ["deterministic_rederivation"]
            and not runtime.get("mismatches")
            and bool(runtime.get("platform_mismatches"))
        )
        integrity_checks: list[bool] = []
        if allowed_cross_platform:
            freeze_manifest = json.loads(
                (root / "experiments/003-confirmatory/freeze-manifest.json").read_text()
            )
            index = json.loads(
                (root / "experiments/003-confirmatory/seeds/index.json").read_text()
            )
            execution = json.loads(
                (
                    root
                    / "results/experiment-003-confirmatory/execution-summary.json"
                ).read_text()
            )
            qc = json.loads(
                (root / "results/experiment-003-confirmatory/qc.json").read_text()
            )
            reproducibility = json.loads(
                (
                    root / "results/experiment-003-confirmatory/reproducibility.json"
                ).read_text()
            )
            run = json.loads(
                (
                    root / "results/experiment-003-confirmatory/run-manifest.json"
                ).read_text()
            )
            def digest(path: Path) -> str:
                return sha256_bytes(path.read_bytes())

            replay = reproducibility["checks"]["same_platform_replay"]
            source_seed = reproducibility["checks"]["seed_validation"]
            integrity_checks.extend(
                (
                    execution["freeze_id"]
                    == freeze_manifest["freeze_id"]
                    == run["freeze_id"],
                    execution["passed"] is True,
                    execution["blocks"] == 5250,
                    execution["episodes"] == 21000,
                    execution["campaign_executions"] == 1,
                    qc["overall_passed"] is True,
                    reproducibility["passed"] is True,
                    replay["passed"] is True,
                    replay["episodes_checked"] == 840,
                    replay["mismatches"] == 0,
                    source_seed["passed"] is True,
                    source_seed["deterministic_rederivation_errors"] == 0,
                    index["root_rows"] == 5250,
                    index["planned_episode_rows"] == 21000,
                    index["replay_root_rows"] == 210,
                    index["replay_episode_rows"] == 840,
                    digest(root / "experiments/003-confirmatory/seeds/confirmatory.jsonl")
                    == index["manifest_sha256"]
                    == run["seed_manifest_sha256"],
                    digest(root / "experiments/003-confirmatory/seeds/replay-subset.json")
                    == index["replay_subset_sha256"],
                )
            )
            integrity_checks.extend(
                digest(root / relative) == expected
                for relative, expected in freeze_manifest["source_file_hashes"].items()
            )
            integrity_checks.extend(
                digest(root / relative) == expected
                for relative, expected in run["output_hashes"].items()
            )
        passed = bool(allowed_cross_platform and integrity_checks and all(integrity_checks))
        mode = "cross-platform hashes and frozen same-platform replay"
        details = {
            **details,
            "allowed_cross_platform_seed_transform_difference": allowed_cross_platform,
            "independent_integrity_checks": len(integrity_checks),
            "independent_integrity_passed": bool(
                integrity_checks and all(integrity_checks)
            ),
            "platform_mismatches": runtime.get("platform_mismatches"),
        }
    return {
        "id": "experiment_003_confirmatory",
        "command": "cross-platform-aware frozen E003 confirmatory verification",
        "passed": passed,
        "returncode": 0 if passed else 1,
        "summary": mode,
        "details": details,
    }


def _base_blob_map(root: Path) -> dict[str, str]:
    raw = subprocess.run(
        ["git", "ls-tree", "-r", "-z", EXPECTED_BASE_COMMIT],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    result: dict[str, str] = {}
    for entry in (item for item in raw.split(b"\0") if item):
        metadata, raw_path = entry.split(b"\t", 1)
        _mode, object_type, object_id = metadata.decode().split(" ")
        path = raw_path.decode()
        if object_type == "blob" and path not in BASE_CHANGE_ALLOWLIST:
            result[path] = object_id
    return dict(sorted(result.items()))


def verify_historical_base_unchanged(root: Path) -> dict[str, Any]:
    """Protect every base-tracked byte except the explicitly phase-aware CI file."""

    expected = _base_blob_map(root)
    mismatches: list[str] = []
    for relative, object_id in expected.items():
        path = root / relative
        if not path.is_file():
            mismatches.append(relative)
            continue
        observed = _git(root, "hash-object", "--", relative)
        if observed != object_id:
            mismatches.append(relative)
    changed = set(_git(root, "diff", "--name-only", EXPECTED_BASE_COMMIT).splitlines())
    protected_changes = sorted(changed & set(expected))
    mismatches.extend(path for path in protected_changes if path not in mismatches)
    return {
        "passed": not mismatches,
        "base_commit": EXPECTED_BASE_COMMIT,
        "observed_head": _git(root, "rev-parse", "HEAD"),
        "protected_files": len(expected),
        "protected_blob_map_sha256": sha256_bytes(canonical_json(expected)),
        "allowed_base_file_changes": sorted(BASE_CHANGE_ALLOWLIST),
        "mismatches": len(mismatches),
        "mismatches_preview": mismatches[:30],
        "scope": "every file tracked at ce50129 except phase-aware CI",
        "historical_experiments_001_004_and_results_included": True,
        "protected_blob_ids": expected,
    }


def verify_historical_snapshot(root: Path, blob_map: dict[str, str]) -> dict[str, Any]:
    mismatches: list[str] = []
    for relative, object_id in blob_map.items():
        path = root / relative
        if not path.is_file():
            mismatches.append(relative)
            continue
        observed = _git(root, "hash-object", "--", relative)
        if observed != object_id:
            mismatches.append(relative)
    return {
        "passed": not mismatches,
        "protected_files": len(blob_map),
        "protected_blob_map_sha256": sha256_bytes(canonical_json(blob_map)),
        "mismatches": len(mismatches),
        "mismatches_preview": mismatches[:30],
        "shallow_checkout_safe": True,
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
            "experiment_002_freeze",
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
            "experiment_002_results",
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
                    "verify_freeze,verify_results; r=Path.cwd(); "
                    "assert verify_freeze(r,require_unmaterialized=False)['passed']; "
                    "assert verify_results(r)['passed']"
                ),
            ],
            "experiment_003_pilot",
        ),
        _verify_e003_confirmatory_cross_platform(root),
        _run(
            root,
            [
                "uv",
                "run",
                "python",
                "-m",
                "kri_space_autonomy.experiment_004_closeout",
                "verify",
            ],
            "experiment_004_closeout",
        ),
    ]
    return {"passed": all(item["passed"] for item in commands), "checks": commands}


def dependency_runtime_identity(root: Path) -> dict[str, Any]:
    expected = {
        "python": "3.11.16",
        "numpy_version": "2.4.6",
        "scipy_version": "1.17.0",
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
    mismatches = [key for key, value in expected.items() if observed.get(key) != value]
    files = (Path(".python-version"), Path("pyproject.toml"), Path("uv.lock"))
    return {
        "passed": not mismatches,
        "expected_versions": expected,
        "observed": observed,
        "mismatches": mismatches,
        "dependency_file_hashes": {
            path.as_posix(): sha256_bytes((root / path).read_bytes()) for path in files
        },
        "platform_match_required_for_future_replay": True,
    }


def _candidate_files(root: Path) -> list[Path]:
    raw = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    excluded = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    paths = {
        root / relative.decode()
        for relative in raw
        if relative and not any(part in excluded for part in Path(relative.decode()).parts)
    }
    return sorted(
        (path for path in paths if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def enhanced_publication_and_secret_scan(
    root: Path, *, base_paths: set[str] | None = None
) -> dict[str, Any]:
    baseline = repository_publication_scan(root)
    marker_names = (
        "api" + "_" + "key",
        "access" + "_" + "token",
        "client" + "_" + "secret",
        "pass" + "word",
    )
    assignment = re.compile(
        rb"(?i)(?:"
        + b"|".join(re.escape(name.encode()) for name in marker_names)
        + rb")[ \t]*[:=][ \t]*['\"]?[A-Za-z0-9_./+\-=]{12,}"
    )
    key_header = ("-----BEGIN " + "PRIVATE KEY-----").encode()
    bearer = ("Authorization: " + "Bearer ").encode().lower()
    matches: list[dict[str, str]] = []
    new_opaque: list[str] = []
    known_base_paths = set(_base_blob_map(root)) if base_paths is None else base_paths
    scanned = 0
    for path in _candidate_files(root):
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        lowered = raw.lower()
        if assignment.search(raw):
            matches.append({"path": relative, "rule": "credential-assignment"})
        if key_header.lower() in lowered:
            matches.append({"path": relative, "rule": "private-key-material"})
        if bearer in lowered:
            matches.append({"path": relative, "rule": "bearer-credential"})
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            if relative not in known_base_paths:
                new_opaque.append(relative)
        scanned += 1
    return {
        "passed": bool(baseline["passed"] and not matches and not new_opaque),
        "enumeration": "tracked plus untracked nonignored public files",
        "files_scanned": scanned,
        "provenance_privacy_scan": baseline,
        "secret_matches": len(matches),
        "secret_matches_preview": matches[:20],
        "new_opaque_files": len(new_opaque),
        "new_opaque_files_preview": new_opaque[:20],
        "base_opaque_files_grandfathered_by_ce50129_identity": True,
    }


def _source_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    paths.add(root / VALIDATION_PATH)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes()) for path in paths
    }


def _phase_pytest_command() -> list[str]:
    command = ["uv", "run", "pytest", "-q"]
    for test in PRE_OUTCOME_DESELECTS:
        command.extend(("--deselect", test))
    return command


def validate(root: Path) -> dict[str, Any]:
    config = load_config(root / CONFIG_PATH, root=root)
    mechanics = run_foundation_checks(config)
    seeds = validate_seed_contract(config, root / SEED_CONTRACT_PATH, root)
    historical_bytes = verify_historical_base_unchanged(root)
    historical_campaigns = verify_historical_campaigns(root)
    runtime = dependency_runtime_identity(root)
    scan = enhanced_publication_and_secret_scan(root)
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
            ],
            "experiment_005_focused_tests",
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
        {"id": "nonlinear_truth_foundation", "passed": mechanics["passed"], "observed": mechanics},
        {"id": "seed_partition_contract", "passed": seeds["passed"], "observed": seeds},
        {
            "id": "historical_base_byte_identity",
            "passed": historical_bytes["passed"],
            "observed": {
                key: value
                for key, value in historical_bytes.items()
                if key != "protected_blob_ids"
            },
        },
        {
            "id": "historical_campaign_result_integrity",
            "passed": historical_campaigns["passed"],
            "observed": historical_campaigns,
        },
        {"id": "dependency_runtime_identity", "passed": runtime["passed"], "observed": runtime},
        {"id": "publication_privacy_secrets", "passed": scan["passed"], "observed": scan},
    ]
    failed = [check["id"] for check in checks if not check["passed"]]
    blocker = mechanics.get("smallest_scientific_blocker") or (failed[0] if failed else None)
    result = {
        "schema_version": config.schema_version,
        "phase": "pre_outcome_nonlinear_truth_foundation_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": not failed,
        "status": "READY_FOR_DESIGN_VALIDATION_PILOT" if not failed else "NOT_READY",
        "smallest_scientific_blocker": blocker,
        "checks": checks,
        "phase_appropriate_exclusions": {
            "tests": list(PRE_OUTCOME_DESELECTS),
            "reason": (
                "historical pre-materialization assertions are phase-inapplicable after "
                "the completed frozen campaigns; result verifiers remain mandatory"
            ),
        },
        "experiment_004_outcomes_used_for_design": False,
        "experiment_005_calibration_partition_materialized": False,
        "experiment_005_pilot_partition_materialized": False,
        "experiment_005_confirmatory_partition_materialized": False,
        "outcome_campaign_executed": False,
        "scientific_findings_claimed": False,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def _self_hashed(path: Path, identity_field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(identity_field)
    if identity != sha256_bytes(canonical_json(value)):
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[identity_field] = identity
    return value


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 005 freeze/readiness artifacts")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != EXPECTED_BASE_COMMIT:
        raise RuntimeError("Experiment 005 freeze requires the requested branch and merged base")
    validation = validate(root)
    if not validation["passed"]:
        readiness = {
            "schema_version": validation["schema_version"],
            "status": "NOT_READY",
            "freeze_id": None,
            "smallest_scientific_blocker": validation["smallest_scientific_blocker"],
        }
        readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
        (root / READINESS_PATH).write_text(
            json.dumps(readiness, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raise RuntimeError(
            f"Experiment 005 foundation is NOT_READY: {validation['smallest_scientific_blocker']}"
        )
    config = load_config(root / CONFIG_PATH, root=root)
    historical = verify_historical_base_unchanged(root)
    historical_campaigns = verify_historical_campaigns(root)
    seeds = validate_seed_contract(config, root / SEED_CONTRACT_PATH, root)
    runtime = dependency_runtime_identity(root)
    scan = enhanced_publication_and_secret_scan(root)
    if not all(
        result["passed"]
        for result in (historical, historical_campaigns, seeds, runtime, scan)
    ):
        raise RuntimeError("freeze prerequisite changed after validation")
    source_hashes = _file_hashes(root, _source_files(root))
    mechanics_check = next(
        check for check in validation["checks"] if check["id"] == "nonlinear_truth_foundation"
    )["observed"]
    unsigned = {
        "schema_version": config.schema_version,
        "phase": "pre_outcome_nonlinear_truth_foundation_freeze",
        "status": "READY_FOR_DESIGN_VALIDATION_PILOT",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "Experiment 005 nonlinear two-body truth model-fidelity transfer foundation",
        "source_identity": {
            "branch": branch,
            "base_commit": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "commit_created": False,
            "paths": "project-relative only",
        },
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "historical_base_integrity": {
            key: value for key, value in historical.items() if key != "protected_blob_ids"
        },
        "historical_protected_blob_ids": historical["protected_blob_ids"],
        "historical_campaign_result_integrity": historical_campaigns,
        "truth_model": {
            "physical_truth": config.truth_model,
            "state": list(config.inertial_state_order),
            "chief_initial_orbit": "equatorial prograde circular Earth orbit",
            "reference_radius_m": config.reference_radius_m,
            "reference_altitude_m": config.reference_altitude_above_equatorial_radius_m,
            "gravitational_parameter_m3_s2": config.gravitational_parameter_m3_s2,
            "propagation": config.production_integrator,
            "maximum_step_s": config.production_max_step_s,
            "command_hold": (
                "LVLH components held per control interval and remapped at each RK4 stage"
            ),
            "Euler_truth_used": False,
            "reference_validation": config.reference_integrator,
        },
        "model_separation": {
            "controller_estimator_model": config.controller_estimator_model,
            "truth_model": config.truth_model,
            "truth_model_mismatch_hidden": False,
            "truth_geometry_returned_online": False,
        },
        "prospective_physics_envelope": mechanics_check["checks"][
            "local_hcw_limit_and_mismatch"
        ]["prospective_envelope"],
        "descriptive_model_mismatch": mechanics_check["checks"][
            "local_hcw_limit_and_mismatch"
        ],
        "truth_space_geometry": mechanics_check["checks"]["truth_space_event_geometry"],
        "future_runner_architecture": mechanics_check["checks"]["future_runner_fixture"],
        "seed_partition_contract": seeds,
        "dependency_runtime_identity": runtime,
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "publication_privacy_secrets_scan": scan,
        "experiment_004_outcomes_used_for_design": False,
        "experiment_005_calibration_partition_materialized": False,
        "experiment_005_pilot_partition_materialized": False,
        "experiment_005_confirmatory_partition_materialized": False,
        "pilot_generator_available": False,
        "confirmatory_generator_available": False,
        "outcome_campaign_executed": False,
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
        "scope": "separate non-inferential Experiment 005 design-validation pilot design",
        "mechanics_calibration_partition_code": config.mechanics_calibration_partition_code,
        "mechanics_calibration_partition_state": "reserved_not_materialized_or_executed",
        "pilot_partition_code": config.future_pilot_partition_code,
        "pilot_partition_state": "reserved_not_materialized_size_and_design_not_set",
        "future_confirmatory_partition_code": config.future_confirmatory_partition_code,
        "future_confirmatory_partition_state": (
            "reserved_not_materialized_size_hypothesis_and_design_not_set"
        ),
        "pilot_generator_available": False,
        "confirmatory_generator_available": False,
        "next_task": (
            "prospectively design one non-inferential model-fidelity transfer pilot using "
            "only partition-51 mechanics calibration; freeze cases and sample count before "
            "enabling partition 52; leave partition 53 untouched"
        ),
        "outcome_campaign_executed": False,
        "scientific_findings_claimed": False,
        "smallest_scientific_blocker": None,
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root)
    if not verification["passed"]:
        raise RuntimeError("Experiment 005 freeze failed internal verification")
    return {**unsigned, "readiness": readiness, "verification": verification}


def verify_freeze(root: Path) -> dict[str, Any]:
    manifest = _self_hashed(root / FREEZE_PATH, "freeze_id")
    errors: list[str] = []
    for relative, expected in manifest["source_file_hashes"].items():
        path = root / relative
        observed = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if observed != expected:
            errors.append(relative)
    validation = root / VALIDATION_PATH
    if (
        not validation.is_file()
        or sha256_bytes(validation.read_bytes()) != manifest["validation_sha256"]
    ):
        errors.append("validation_identity")
    snapshot = verify_historical_snapshot(root, manifest["historical_protected_blob_ids"])
    if not snapshot["passed"]:
        errors.append("historical_base_integrity")
    historical_campaigns = verify_historical_campaigns(root)
    if not historical_campaigns["passed"]:
        errors.append("historical_campaign_result_integrity")
    config = load_config(root / CONFIG_PATH, root=root)
    seeds = validate_seed_contract(config, root / SEED_CONTRACT_PATH, root)
    if not seeds["passed"]:
        errors.append("seed_partition_contract")
    runtime = dependency_runtime_identity(root)
    if not runtime["passed"]:
        errors.append("dependency_runtime_identity")
    protected_paths = set(manifest["historical_protected_blob_ids"])
    protected_paths.update(BASE_CHANGE_ALLOWLIST)
    scan = enhanced_publication_and_secret_scan(root, base_paths=protected_paths)
    if not scan["passed"]:
        errors.append("publication_privacy_secrets")
    try:
        readiness = _self_hashed(root / READINESS_PATH, "readiness_id")
        readiness_ok = bool(
            readiness["freeze_id"] == manifest["freeze_id"]
            and readiness["status"] == "READY_FOR_DESIGN_VALIDATION_PILOT"
            and readiness["pilot_generator_available"] is False
            and readiness["confirmatory_generator_available"] is False
            and readiness["smallest_scientific_blocker"] is None
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
        "smallest_scientific_blocker": errors[0] if errors else None,
        "freeze_id": manifest["freeze_id"],
        "readiness_id": readiness.get("readiness_id"),
        "source_files_verified": len(manifest["source_file_hashes"]),
        "errors_preview": errors[:30],
        "historical_snapshot": snapshot,
        "historical_campaign_result_integrity": historical_campaigns,
        "seed_partition_contract": seeds,
        "dependency_runtime_identity": runtime,
        "publication_privacy_secrets_scan": scan,
        "pilot_partition_materialized": False,
        "future_confirmatory_partition_materialized": False,
        "outcome_campaign_executed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 005 nonlinear-truth foundation")
    parser.add_argument(
        "command", choices=("validate", "freeze", "verify-freeze", "release-scan")
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
        result = enhanced_publication_and_secret_scan(root)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if not result.get("passed", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
