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

from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_003 import workflow as foundation_workflow
from kri_space_autonomy.experiment_003.config import ESTIMATOR_STRATA
from kri_space_autonomy.experiment_003.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_003.validation import run_numerical_checks

from .analysis import analyze_confirmatory
from .config import load_confirmatory_config
from .runner import load_episode_rows, run_confirmatory_block, run_confirmatory_campaign
from .seeds import (
    materialize_confirmatory_seed_manifest,
    validate_materialized_confirmatory_seeds,
    validate_seed_contract,
)

EXPECTED_BRANCH = "experiment-003-confirmatory-design"
EXPECTED_BASE = "bcc1085d15a997a1b82a639830ab689ffb8baff0"
CONFIG_PATH = Path("experiments/003-confirmatory/config.json")
PREREGISTRATION_PATH = Path("experiments/003-confirmatory/preregistration.md")
SEED_CONTRACT_PATH = Path("experiments/003-confirmatory/seed-contract.json")
VALIDATION_PATH = Path("experiments/003-confirmatory/validation-evidence.json")
FREEZE_PATH = Path("experiments/003-confirmatory/freeze-manifest.json")
READINESS_PATH = Path("experiments/003-confirmatory/readiness.json")
SEEDS_DIR = Path("experiments/003-confirmatory/seeds")
DOC_PATH = Path("docs/experiment-003-confirmatory.md")
FOUNDATION_CONFIG_PATH = Path("experiments/003/config.json")
PRODUCTION_CONFIG_PATH = Path("experiments/002/config.json")
FOUNDATION_FREEZE_PATH = Path("experiments/003/freeze-manifest.json")
FOUNDATION_ANALYSIS_PATH = Path("results/experiment-003/analysis.json")
FOUNDATION_QC_PATH = Path("results/experiment-003/qc.json")
FOUNDATION_REPRO_PATH = Path("results/experiment-003/reproducibility.json")
FOUNDATION_RUN_PATH = Path("results/experiment-003/run-manifest.json")
POLICY_PATH = Path("artifacts/experiment-002/policy-primary.npz")
POLICY_MANIFEST_PATH = Path("artifacts/experiment-002/policy-primary.manifest.json")
RESULTS_DIR = Path("results/experiment-003-confirmatory")
EPISODES_PATH = RESULTS_DIR / "confirmatory-episodes.jsonl"
EXECUTION_PATH = RESULTS_DIR / "execution-summary.json"
ANALYSIS_PATH = RESULTS_DIR / "analysis.json"
QC_PATH = RESULTS_DIR / "qc.json"
REPORT_PATH = RESULTS_DIR / "report.md"
REPRODUCIBILITY_PATH = RESULTS_DIR / "reproducibility.json"
RUN_MANIFEST_PATH = RESULTS_DIR / "run-manifest.json"
CHECKSUMS_PATH = RESULTS_DIR / "SHA256SUMS"
RESULT_OUTPUTS = (
    EPISODES_PATH,
    EXECUTION_PATH,
    ANALYSIS_PATH,
    QC_PATH,
    REPORT_PATH,
    REPRODUCIBILITY_PATH,
)
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_003_confirmatory/*.py",
    "tests/test_experiment_003_confirmatory_*.py",
    "experiments/003-confirmatory/config.json",
    "experiments/003-confirmatory/preregistration.md",
    "experiments/003-confirmatory/seed-contract.json",
    "docs/experiment-003-confirmatory.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
PHASE_EXCLUDED_TESTS = (
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


def _self_hashed_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    freeze_id = manifest.pop("freeze_id")
    if sha256_bytes(canonical_json(manifest)) != freeze_id:
        raise RuntimeError(f"freeze manifest self-hash mismatch: {path.as_posix()}")
    manifest["freeze_id"] = freeze_id
    return manifest


def _verify_checksum_file(directory: Path) -> list[str]:
    path = directory / "SHA256SUMS"
    if not path.is_file():
        return [f"missing:{path.as_posix()}"]
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            expected, name = line.split("  ", 1)
        except ValueError:
            errors.append("malformed_checksum_line")
            continue
        candidate = directory / name
        actual = sha256_bytes(candidate.read_bytes()) if candidate.is_file() else None
        if actual != expected:
            errors.append(name)
    return errors


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes()) for path in paths
    }


def _foundation_manifest(root: Path) -> dict[str, Any]:
    return _self_hashed_manifest(root / FOUNDATION_FREEZE_PATH)


def _relative_source_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    foundation = _foundation_manifest(root)
    paths.update(
        root / relative
        for relative in foundation["source_file_hashes"]
        if (root / relative).is_file()
    )
    paths.add(root / VALIDATION_PATH)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _runtime() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
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


def dependency_runtime_identity(root: Path) -> dict[str, Any]:
    foundation_runtime = _foundation_manifest(root)["runtime"]
    observed = _runtime()
    # Scientific/runtime dependencies are frozen across supported hosts. OS and
    # machine architecture are recorded as provenance, but are not a validity
    # gate: CI and later independent verification may run on another platform.
    identity_fields = (
        "python",
        "implementation",
        "numpy_version",
        "scipy_version",
    )
    platform_fields = ("os", "architecture")
    mismatches = [
        field for field in identity_fields if observed.get(field) != foundation_runtime.get(field)
    ]
    platform_mismatches = [
        field for field in platform_fields if observed.get(field) != foundation_runtime.get(field)
    ]
    dependency_paths = [root / "pyproject.toml", root / "uv.lock", root / ".python-version"]
    return {
        "passed": not mismatches and all(path.is_file() for path in dependency_paths),
        "mismatches": mismatches,
        "platform_mismatches": platform_mismatches,
        "platform_match_required": False,
        "observed": observed,
        "foundation_runtime": foundation_runtime,
        "dependency_file_hashes": _file_hashes(root, dependency_paths),
    }


def verify_foundation_and_pilot(root: Path) -> dict[str, Any]:
    foundation_freeze = foundation_workflow.verify_freeze(
        root,
        require_unmaterialized=False,
    )
    foundation_results = foundation_workflow.verify_results(root)
    analysis = json.loads((root / FOUNDATION_ANALYSIS_PATH).read_text(encoding="utf-8"))
    qc = json.loads((root / FOUNDATION_QC_PATH).read_text(encoding="utf-8"))
    reproducibility = json.loads((root / FOUNDATION_REPRO_PATH).read_text(encoding="utf-8"))
    run_manifest = json.loads((root / FOUNDATION_RUN_PATH).read_text(encoding="utf-8"))
    resolution = analysis.get("future_sample_size_resolution", {})
    candidates = resolution.get("candidate_results", [])
    selected = resolution.get("selected_roots_per_stratum")
    smallest_passing = next(
        (row.get("roots_per_stratum") for row in candidates if row.get("passes")),
        None,
    )
    pilot_checks = {
        "foundation_freeze": foundation_freeze["passed"],
        "foundation_results": foundation_results["passed"],
        "foundation_freeze_id": (
            foundation_freeze.get("freeze_id")
            == "d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297"
        ),
        "pilot_primary_hypotheses_not_tested": (
            analysis.get("primary_hypotheses_tested") is False
            and run_manifest.get("primary_hypotheses_tested") is False
        ),
        "pilot_direction_not_used": (
            analysis.get("primary_effect_direction_used_for_progression") is False
            and resolution.get("observed_pilot_effect_used_as_alternative") is False
        ),
        "pilot_complete_448_blocks_1792_episodes": (
            qc.get("overall_passed") is True
            and qc.get("cell_validation", {}).get("complete_blocks") == 448
            and qc.get("cell_validation", {}).get("rows") == 1792
        ),
        "pilot_same_platform_replay": (
            reproducibility.get("passed") is True
            and reproducibility.get("checks", {})
            .get("same_platform_replay", {})
            .get("episodes_checked")
            == 224
            and reproducibility.get("checks", {})
            .get("same_platform_replay", {})
            .get("mismatches")
            == 0
        ),
        "prospective_nuisance_resolution": (
            selected == 750
            and smallest_passing == 750
            and resolution.get("simulations") == 20_000
            and resolution.get("seed") == 300317
            and resolution.get("target_lower_bound") == 0.95
            and resolution.get("marginal_not_joint_power") is True
        ),
        "single_pilot_and_replay": (
            run_manifest.get("campaign_executions") == 1
            and run_manifest.get("replay_executions") == 1
        ),
        "progression_passed": (
            analysis.get("progression", {}).get("passed") is True
            and analysis.get("progression", {}).get("decision")
            == "ready_to_freeze_separate_confirmatory_design"
        ),
    }
    return {
        "passed": all(pilot_checks.values()),
        "checks": pilot_checks,
        "foundation_freeze": foundation_freeze,
        "foundation_results": foundation_results,
        "historical_experiment_002_evidence": foundation_freeze.get("historical_integrity"),
        "selected_roots_per_stratum": selected,
        "smallest_passing_candidate": smallest_passing,
        "pilot_direction_influence": (
            "none beyond the prospectively frozen nuisance-based sample-size resolution"
        ),
    }


def verify_unmaterialized_reservation(root: Path) -> dict[str, Any]:
    study, foundation, production = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH, root)
    return {
        **contract,
        "passed": bool(
            contract["passed"]
            and study.partition_code == foundation.confirmatory_partition_code == 32
            and study.planned_blocks == 5250
            and study.planned_episodes == 21000
            and study.replay_episodes == 840
            and production.horizon_s == 600.0
        ),
    }


def validate(root: Path) -> dict[str, Any]:
    study, foundation, production = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    full_test_command = ["uv", "run", "pytest", "-q"]
    for test in PHASE_EXCLUDED_TESTS:
        full_test_command.extend(["--deselect", test])
    commands = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(root, full_test_command, "phase_appropriate_full_tests"),
        _run(
            root,
            ["uv", "run", "pytest", "-q", "-k", "experiment_003_confirmatory"],
            "confirmatory_tests",
        ),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "stable_gate"),
        _run(root, ["git", "diff", "--check"], "diff_whitespace"),
    ]
    foundation_pilot = verify_foundation_and_pilot(root)
    numerical = run_numerical_checks(foundation, production)
    reservation = verify_unmaterialized_reservation(root)
    runtime_identity = dependency_runtime_identity(root)
    publication_scan = foundation_workflow.repository_publication_scan(root)
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    checks = [
        *commands,
        {
            "id": "requested_branch_base",
            "passed": branch == EXPECTED_BRANCH and head == EXPECTED_BASE,
            "observed": {"branch": branch, "head": head},
        },
        {
            "id": "frozen_foundation_pilot_and_historical_evidence",
            "passed": foundation_pilot["passed"],
            "observed": foundation_pilot,
        },
        {
            "id": "numerical_observability_covariance_interface_gates",
            "passed": numerical["passed"],
            "observed": numerical,
        },
        {
            "id": "confirmatory_partition_unmaterialized",
            "passed": reservation["passed"],
            "observed": reservation,
        },
        {
            "id": "dependency_runtime_identity",
            "passed": runtime_identity["passed"],
            "observed": runtime_identity,
        },
        {
            "id": "publication_privacy",
            "passed": publication_scan["passed"],
            "observed": publication_scan,
        },
    ]
    passed = all(bool(check["passed"]) for check in checks)
    result = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_confirmatory_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": passed,
        "status": "READY" if passed else "NOT_READY",
        "checks": checks,
        "phase_appropriate_exclusions": {
            "tests": list(PHASE_EXCLUDED_TESTS),
            "reason": (
                "historical pre-materialization assertions are superseded by their frozen "
                "result verifiers; partition 32 remains separately unmaterialized"
            ),
        },
        "pilot_direction_influenced_design": False,
        "pilot_use": "prospectively frozen nuisance-based N selection only",
        "confirmatory_seeds_materialized": False,
        "confirmatory_outcomes_executed": False,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def _validation_observed(validation: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(check["observed"] for check in validation["checks"] if check["id"] == check_id)


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite confirmatory freeze/readiness artifacts")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != EXPECTED_BASE:
        raise RuntimeError("confirmatory freeze requires the requested branch and base")
    validation = validate(root)
    if not validation["passed"]:
        readiness = {
            "schema_version": validation["schema_version"],
            "status": "NOT_READY",
            "freeze_id": None,
            "reason": "one or more fail-closed pre-outcome checks failed",
        }
        (root / READINESS_PATH).write_text(
            json.dumps(readiness, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise RuntimeError("Experiment 003 confirmatory validation is NOT READY")

    study, _, _ = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    source_hashes = _file_hashes(root, _relative_source_files(root))
    foundation_pilot = _validation_observed(
        validation,
        "frozen_foundation_pilot_and_historical_evidence",
    )
    numerical = _validation_observed(
        validation,
        "numerical_observability_covariance_interface_gates",
    )
    reservation = _validation_observed(validation, "confirmatory_partition_unmaterialized")
    runtime_identity = _validation_observed(validation, "dependency_runtime_identity")
    publication_scan = _validation_observed(validation, "publication_privacy")
    unsigned = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_confirmatory_freeze",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "one-time Experiment 003 seven-stratum confirmatory campaign",
        "source_identity": {
            "branch": branch,
            "base_commit": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "paths": "project-relative only",
        },
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "foundation_freeze_id": study.foundation_freeze_id,
        "foundation_and_pilot_evidence": foundation_pilot,
        "historical_experiment_002_evidence": foundation_pilot[
            "historical_experiment_002_evidence"
        ],
        "design": {
            "strata": list(ESTIMATOR_STRATA),
            "roots_per_stratum": study.roots_per_stratum,
            "stratum_weight": study.stratum_weight,
            "arms": list(study.arms),
            "paired_blocks": study.planned_blocks,
            "episodes": study.planned_episodes,
            "replay_roots_per_stratum": study.replay_roots_per_stratum,
            "replay_episodes": study.replay_episodes,
        },
        "analysis_contract": {
            "H1": "PD-D analysis_hazard superiority",
            "H2": "gatekept PD-D sustained_success noninferiority at -0.03",
            "bootstrap_replicates": study.bootstrap_replicates,
            "bootstrap_seed": study.bootstrap_seed,
            "secondary_family": "H3/H4/H5a/H5b one-sided Holm",
            "H5b_randomization_replicates": study.secondary_randomization_replicates,
            "H5b_randomization_seed": study.secondary_randomization_seed,
            "primary_sensitivities": list(study.primary_sensitivities),
        },
        "sample_size_resolution": {
            "selected_roots_per_stratum": 750,
            "selection_basis": "prospectively frozen nuisance-based marginal-power rule",
            "pilot_direction_influenced_design": False,
            "pilot_direction_influence_statement": (
                "Pilot direction did not influence the design beyond prospective "
                "nuisance-based N selection."
            ),
        },
        "seed_reservation": {
            **reservation,
            "state_at_freeze": "reserved_not_materialized_or_executed",
            "generator_available": True,
            "generator_invoked": False,
            "materialization_requires_confirmatory_freeze_verification": True,
        },
        "numerical_observability_covariance_interface_gates": numerical,
        "dependency_runtime_identity": runtime_identity,
        "publication_privacy_scan": publication_scan,
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "validation_status": validation["status"],
        "confirmatory_seeds_materialized": False,
        "confirmatory_outcomes_executed": False,
        "readiness_policy": "fail closed; no critical-check waiver",
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    readiness_unsigned = {
        "schema_version": study.schema_version,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY",
        "scope": "one-time 21,000-episode Experiment 003 confirmatory campaign",
        "partition_code": study.partition_code,
        "partition_state": "reserved_not_materialized_or_executed",
        "confirmatory_seeds_materialized": False,
        "confirmatory_outcomes_executed": False,
        "next_task": "one-time 21,000-episode Experiment 003 confirmatory campaign",
        "next_command": (
            "uv run python -m kri_space_autonomy.experiment_003_confirmatory.workflow "
            "materialize-confirmatory-seeds"
        ),
    }
    readiness_unsigned["readiness_id"] = sha256_bytes(canonical_json(readiness_unsigned))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness_unsigned, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError("confirmatory freeze failed its internal verification")
    return {**unsigned, "readiness": readiness_unsigned, "verification": verification}


def verify_freeze(root: Path, *, require_unmaterialized: bool = True) -> dict[str, Any]:
    manifest = _self_hashed_manifest(root / FREEZE_PATH)
    errors: list[str] = []
    for relative, expected in manifest["source_file_hashes"].items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    validation_path = root / VALIDATION_PATH
    if (
        not validation_path.is_file()
        or sha256_bytes(validation_path.read_bytes()) != manifest.get("validation_sha256")
    ):
        errors.append("validation_identity")
    foundation_pilot = verify_foundation_and_pilot(root)
    if not foundation_pilot["passed"]:
        errors.append("foundation_pilot_or_historical_evidence")
    study, foundation, production = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    numerical = run_numerical_checks(foundation, production)
    if not numerical["passed"]:
        errors.append("numerical_observability_covariance_interface_gates")
    runtime_identity = dependency_runtime_identity(root)
    if not runtime_identity["passed"]:
        errors.append("dependency_runtime_identity")
    if require_unmaterialized:
        reservation = verify_unmaterialized_reservation(root)
        if not reservation["passed"]:
            errors.append("confirmatory_partition_state")
    else:
        reservation = {
            "passed": True,
            "contract_sha256": sha256_bytes((root / SEED_CONTRACT_PATH).read_bytes()),
            "state": "materialization_permitted_after_verified_freeze",
        }
        expected_contract_hash = manifest.get("seed_reservation", {}).get("contract_sha256")
        if reservation["contract_sha256"] != expected_contract_hash:
            errors.append("seed_contract_identity")
    readiness_check: dict[str, Any] = {"present": (root / READINESS_PATH).is_file()}
    try:
        readiness = json.loads((root / READINESS_PATH).read_text(encoding="utf-8"))
        readiness_id = readiness.pop("readiness_id")
        readiness_check.update(
            {
                "passed": bool(
                    sha256_bytes(canonical_json(readiness)) == readiness_id
                    and readiness.get("freeze_id") == manifest["freeze_id"]
                    and readiness.get("status") == "READY"
                    and readiness.get("partition_code") == 32
                ),
                "readiness_id": readiness_id,
                "status": readiness.get("status"),
            }
        )
    except (OSError, KeyError, json.JSONDecodeError):
        readiness_check["passed"] = False
    if not readiness_check["passed"]:
        errors.append("readiness_identity")
    publication_scan = foundation_workflow.repository_publication_scan(root)
    if not publication_scan["passed"]:
        errors.append("publication_privacy_scan")
    return {
        "schema_version": study.schema_version,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "status": "READY" if not errors else "NOT_READY",
        "errors_preview": errors[:30],
        "freeze_id": manifest["freeze_id"],
        "source_files_verified": len(manifest["source_file_hashes"]),
        "foundation_pilot_and_historical_evidence": foundation_pilot,
        "numerical_observability_covariance_interface_gates": numerical,
        "dependency_runtime_identity": runtime_identity,
        "seed_contract": reservation,
        "readiness_identity": readiness_check,
        "publication_privacy_scan": publication_scan,
        "require_unmaterialized": require_unmaterialized,
    }


def materialize_seeds(root: Path) -> dict[str, Any]:
    verification = verify_freeze(root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError("confirmatory freeze verification failed before materialization")
    study, foundation, production = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    return materialize_confirmatory_seed_manifest(
        study,
        foundation,
        production,
        root=root,
        freeze_id=verification["freeze_id"],
        seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
    )


def execute(root: Path) -> dict[str, Any]:
    verification = verify_freeze(root, require_unmaterialized=False)
    if not verification["passed"]:
        raise RuntimeError("confirmatory freeze verification failed before execution")
    study, foundation, production = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    seeds = validate_materialized_confirmatory_seeds(
        study,
        foundation,
        production,
        root=root,
        freeze_id=verification["freeze_id"],
        seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
    )
    if not seeds["passed"]:
        raise RuntimeError("confirmatory seed verification failed")
    policy = FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production)
    result = run_confirmatory_campaign(
        study,
        foundation,
        production,
        policy,
        sha256_bytes((root / CONFIG_PATH).read_bytes()),
        root / SEEDS_DIR / "confirmatory.jsonl",
        root / EPISODES_PATH,
    )
    execution = {
        "schema_version": study.schema_version,
        "phase": "confirmatory_execution",
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": verification["freeze_id"],
        "seed_validation": seeds,
        **result,
    }
    (root / EXECUTION_PATH).write_text(
        json.dumps(execution, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return execution


def _replay_subset(
    root: Path,
    study: Any,
    foundation: Any,
    production: Any,
    policy: FrozenPolicy,
    rows: list[dict[str, Any]],
    config_hash: str,
) -> dict[str, Any]:
    replay = json.loads((root / SEEDS_DIR / "replay-subset.json").read_text(encoding="utf-8"))
    scenarios = {
        (row["stratum_id"], int(row["replicate"])): row
        for row in (
            json.loads(line)
            for line in (root / SEEDS_DIR / "confirmatory.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }
    observed = {
        (row["stratum_id"], int(row["replicate"]), row["arm"]): row for row in rows
    }
    mismatches: list[str] = []
    checked = 0
    for stratum, replicates in replay["replicates_by_stratum"].items():
        for replicate in replicates:
            value = dict(scenarios[(stratum, replicate)])
            value["arm_run_order"] = tuple(value["arm_run_order"])
            from kri_space_autonomy.experiment_003.seeds import Experiment003Scenario

            scenario = Experiment003Scenario(**value)
            for replayed in run_confirmatory_block(
                study,
                foundation,
                production,
                scenario,
                policy,
                config_hash,
            ):
                checked += 1
                expected = observed[(stratum, replicate, replayed.arm)]
                if canonical_json(replayed.to_dict()) != canonical_json(expected):
                    mismatches.append(f"{stratum}:{replicate}:{replayed.arm}")
    return {
        "passed": not mismatches and checked == study.replay_episodes,
        "episodes_checked": checked,
        "expected_episodes": study.replay_episodes,
        "mismatches": len(mismatches),
        "mismatches_preview": mismatches[:20],
    }


def _write_report(analysis: dict[str, Any], path: Path) -> None:
    gatekeeping = analysis["primary_gatekeeping"]
    text = "\n".join(
        [
            "# Experiment 003 confirmatory result",
            "",
            (
                "> Synthetic engineering stress test; not an estimate of operational "
                "prevalence or flight safety."
            ),
            "",
            f"- Decision: **{analysis['decision']}**",
            f"- H1 passed: `{gatekeeping['H1']['passed']}`",
            f"- H2 status: `{gatekeeping['H2']['status']}`",
            f"- H2 passed: `{gatekeeping['H2']['passed']}`",
            "- Exactly three preregistered primary sensitivities were reported.",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def analyze(root: Path) -> dict[str, Any]:
    for output in (ANALYSIS_PATH, QC_PATH, REPORT_PATH, REPRODUCIBILITY_PATH, RUN_MANIFEST_PATH):
        if (root / output).exists():
            raise RuntimeError(f"refusing pre-existing analysis output: {output.as_posix()}")
    verification = verify_freeze(root, require_unmaterialized=False)
    if not verification["passed"]:
        raise RuntimeError("confirmatory freeze verification failed before analysis")
    study, foundation, production = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    seeds = validate_materialized_confirmatory_seeds(
        study,
        foundation,
        production,
        root=root,
        freeze_id=verification["freeze_id"],
        seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
    )
    seed_rows = [
        json.loads(line)
        for line in (root / SEEDS_DIR / "confirmatory.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    rows = load_episode_rows(root / EPISODES_PATH)
    policy = FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production)
    config_hash = sha256_bytes((root / CONFIG_PATH).read_bytes())
    replay = _replay_subset(
        root,
        study,
        foundation,
        production,
        policy,
        rows,
        config_hash,
    )
    foundation_pilot = verify_foundation_and_pilot(root)
    execution = json.loads((root / EXECUTION_PATH).read_text(encoding="utf-8"))
    phase_chain = bool(
        execution.get("freeze_id") == verification["freeze_id"]
        and execution.get("episodes") == study.planned_episodes
        and execution.get("episodes_sha256") == sha256_bytes((root / EPISODES_PATH).read_bytes())
        and execution.get("campaign_executions") == 1
    )
    integrity = {
        "passed": bool(
            seeds["passed"] and replay["passed"] and foundation_pilot["passed"] and phase_chain
        ),
        "seed_validation": seeds,
        "same_platform_replay": replay,
        "foundation_pilot_and_historical_evidence": foundation_pilot,
        "phase_chain": phase_chain,
    }
    analysis_result, qc = analyze_confirmatory(
        study,
        rows,
        seed_rows,
        integrity,
        root / ANALYSIS_PATH,
        root / QC_PATH,
    )
    _write_report(analysis_result, root / REPORT_PATH)
    reproducibility = {
        "schema_version": study.schema_version,
        "freeze_id": verification["freeze_id"],
        "phase": "confirmatory_reproducibility",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "passed": integrity["passed"],
        "checks": integrity,
    }
    (root / REPRODUCIBILITY_PATH).write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    publication_scan = foundation_workflow.repository_publication_scan(root)
    if not publication_scan["passed"]:
        raise RuntimeError("publication/privacy scan failed after confirmatory analysis")
    output_hashes = {
        path.as_posix(): sha256_bytes((root / path).read_bytes()) for path in RESULT_OUTPUTS
    }
    run_manifest = {
        "schema_version": study.schema_version,
        "freeze_id": verification["freeze_id"],
        "phase": "confirmatory_analysis",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "paths": "project-relative only",
        "seed_manifest_sha256": seeds["manifest_sha256"],
        "output_hashes": output_hashes,
        "decision": analysis_result["decision"],
        "campaign_executions": 1,
        "replay_executions": 1,
        "episodes": study.planned_episodes,
        "publication_privacy_scan": publication_scan,
    }
    (root / RUN_MANIFEST_PATH).write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    checksum_paths = [*RESULT_OUTPUTS, RUN_MANIFEST_PATH]
    (root / CHECKSUMS_PATH).write_text(
        "\n".join(
            f"{sha256_bytes((root / path).read_bytes())}  {path.name}"
            for path in checksum_paths
        )
        + "\n",
        encoding="utf-8",
    )
    return {"passed": qc["overall_passed"], **analysis_result}


def verify_results(root: Path) -> dict[str, Any]:
    verification = verify_freeze(root, require_unmaterialized=False)
    run_manifest = json.loads((root / RUN_MANIFEST_PATH).read_text(encoding="utf-8"))
    errors: list[str] = []
    if not verification["passed"]:
        errors.append("confirmatory_freeze")
    if run_manifest.get("freeze_id") != verification.get("freeze_id"):
        errors.append("freeze_id")
    for relative, expected in run_manifest.get("output_hashes", {}).items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    errors.extend(_verify_checksum_file(root / RESULTS_DIR))
    study, foundation, production = load_confirmatory_config(
        root / CONFIG_PATH,
        root / FOUNDATION_CONFIG_PATH,
        root / PRODUCTION_CONFIG_PATH,
    )
    seeds = validate_materialized_confirmatory_seeds(
        study,
        foundation,
        production,
        root=root,
        freeze_id=verification["freeze_id"],
        seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
    )
    if not seeds["passed"]:
        errors.append("seed_validation")
    publication_scan = foundation_workflow.repository_publication_scan(root)
    if not publication_scan["passed"]:
        errors.append("publication_privacy_scan")
    return {
        "schema_version": study.schema_version,
        "passed": not errors,
        "errors_preview": errors[:30],
        "freeze_id": verification.get("freeze_id"),
        "result_files_verified": len(run_manifest.get("output_hashes", {})),
        "seed_validation": seeds,
        "publication_privacy_scan": publication_scan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 003 confirmatory workflow")
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "freeze",
            "verify-freeze",
            "materialize-confirmatory-seeds",
            "run-confirmatory",
            "analyze-confirmatory",
            "verify-results",
            "release-scan",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "validate":
        result = validate(root)
    elif args.command == "freeze":
        result = freeze(root)
    elif args.command == "verify-freeze":
        result = verify_freeze(root, require_unmaterialized=True)
    elif args.command == "materialize-confirmatory-seeds":
        result = materialize_seeds(root)
    elif args.command == "run-confirmatory":
        result = execute(root)
    elif args.command == "analyze-confirmatory":
        result = analyze(root)
    elif args.command == "verify-results":
        result = verify_results(root)
    else:
        result = foundation_workflow.repository_publication_scan(root)
    if not result.get("passed", True):
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
