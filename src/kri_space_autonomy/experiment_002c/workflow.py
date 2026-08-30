from __future__ import annotations

import argparse
import io
import json
import locale
import os
import platform
import subprocess
import uuid
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import scipy

from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_002.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_002b.config import load_amendment_config
from kri_space_autonomy.experiment_002b.workflow import publication_boundary_scan

from .analysis import analyze_002c, write_report
from .config import load_numerical_amendment_config
from .numerical import run_fixed_command_replay
from .seeds import validate_seed_manifest_002c, write_seed_manifest_002c

CONFIG_PATH = Path("experiments/002c/config.json")
PRODUCTION_CONFIG_PATH = Path("experiments/002/config.json")
CONTROLLER_AMENDMENT_CONFIG_PATH = Path("experiments/002b/config.json")
PREREGISTRATION_PATH = Path("experiments/002c/preregistration.md")
AMENDMENT_PATH = Path("docs/experiment-002c.md")
VALIDATION_PATH = Path("experiments/002c/validation-evidence.json")
FREEZE_PATH = Path("experiments/002c/freeze-manifest.json")
SEEDS_DIR = Path("experiments/002c/seeds")
HISTORICAL_SEED_DIRS = (Path("experiments/002/seeds"), Path("experiments/002b/seeds"))
POLICY_PATH = Path("artifacts/experiment-002/policy-primary.npz")
POLICY_MANIFEST_PATH = Path("artifacts/experiment-002/policy-primary.manifest.json")
CORRIDOR_PATH = Path("experiments/002/recovery-corridor.json")
NUMERICAL_PATH = Path("results/experiment-002c/fixed-command-replay.json")
EXECUTION_PATH = Path("results/experiment-002c/execution-summary.json")
ANALYSIS_PATH = Path("results/experiment-002c/analysis.json")
QC_PATH = Path("results/experiment-002c/qc.json")
REPORT_PATH = Path("results/experiment-002c/report.md")
REPRODUCIBILITY_PATH = Path("results/experiment-002c/reproducibility.json")
RUN_MANIFEST_PATH = Path("results/experiment-002c/run-manifest.json")
CHECKSUMS_PATH = Path("results/experiment-002c/SHA256SUMS")
HISTORICAL_002B_NUMERICAL_PATH = Path(
    "results/experiment-002b/fixed-command-replay.json"
)
HISTORICAL_002B_ANALYSIS_PATH = Path("results/experiment-002b/analysis.json")

SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_002c/*.py",
    "src/kri_space_autonomy/experiment_002/dynamics.py",
    "src/kri_space_autonomy/experiment_002/config.py",
    "src/kri_space_autonomy/experiment_002/evaluator.py",
    "src/kri_space_autonomy/experiment_002/monitor.py",
    "src/kri_space_autonomy/experiment_002/policy.py",
    "src/kri_space_autonomy/experiment_002/seeds.py",
    "src/kri_space_autonomy/experiment_002b/config.py",
    "src/kri_space_autonomy/experiment_002b/runner.py",
    "src/kri_space_autonomy/experiment_002b/seeds.py",
    "tests/test_experiment_002c*.py",
    "experiments/002c/config.json",
    "experiments/002c/preregistration.md",
    "docs/experiment-002c.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)

RESULT_OUTPUTS = (
    NUMERICAL_PATH,
    EXECUTION_PATH,
    ANALYSIS_PATH,
    QC_PATH,
    REPORT_PATH,
    REPRODUCIBILITY_PATH,
)

EXCLUDED_SCAN_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
}


def _publishable_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_SCAN_PARTS for part in path.parts):
            continue
        if path.name == ".env" or path.suffix == ".env":
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def repository_hygiene_scan(root: Path) -> dict[str, Any]:
    base = publication_boundary_scan(root)
    forbidden_tool_terms = [
        ("sub" + "agent").encode(),
        ("inter" + "view").encode(),
        ("note" + "book").encode(),
        ("web_" + "search").encode(),
        ("fetch_" + "content").encode(),
        ("modal_" + "run").encode(),
    ]
    absolute_prefixes = [
        ("/" + "users/").encode(),
        ("/" + "home/").encode(),
        ("c:\\" + "users\\").encode(),
    ]
    secret_markers = [
        ("-----begin " + "private key-----").encode(),
        ("-----begin rsa " + "private key-----").encode(),
        ("api_" + "key=").encode(),
        ("access_" + "token=").encode(),
    ]
    matches: list[dict[str, str]] = []
    files = _publishable_files(root)
    for path in files:
        try:
            payload = path.read_bytes().lower()
        except OSError:
            continue
        for term in forbidden_tool_terms:
            if term in payload:
                matches.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "rule": "orchestration-tool-name",
                    }
                )
        for prefix in absolute_prefixes:
            if prefix in payload:
                matches.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "rule": "local-absolute-path",
                    }
                )
        for marker in secret_markers:
            if marker in payload:
                matches.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "rule": "credential-marker",
                    }
                )
    return {
        "passed": bool(base["passed"] and not matches),
        "files_scanned": len(files),
        "base_publication_scan": base,
        "additional_matches": len(matches),
        "additional_matches_preview": matches[:20],
    }


def _run(root: Path, command: list[str], label: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    summary = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
    return {
        "id": label,
        "command": " ".join(command),
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "summary": summary[-1] if summary else "",
    }


def _verify_checksum_file(directory: Path) -> list[str]:
    errors: list[str] = []
    checksum_path = directory / "SHA256SUMS"
    if not checksum_path.is_file():
        return [f"missing:{checksum_path.as_posix()}"]
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        path = directory / name
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(name)
    return errors


def _verify_manifest_self_hash(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    freeze_id = manifest.pop("freeze_id")
    passed = sha256_bytes(canonical_json(manifest)) == freeze_id
    manifest["freeze_id"] = freeze_id
    if not passed:
        raise RuntimeError(f"freeze manifest self-hash mismatch: {path.as_posix()}")
    return manifest


def verify_historical_records(root: Path) -> dict[str, Any]:
    experiment_002 = _verify_manifest_self_hash(
        root / "experiments/002/freeze-manifest.json"
    )
    experiment_002b = _verify_manifest_self_hash(
        root / "experiments/002b/freeze-manifest.json"
    )
    protected_paths = (
        "experiments/002",
        "artifacts/experiment-002",
        "results/experiment-002",
        "experiments/002b",
        "results/experiment-002b",
        "docs/experiment-002.md",
        "docs/experiment-002b.md",
    )
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *protected_paths],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    errors = [f"historical_worktree:{line}" for line in status]
    errors.extend(
        f"results/experiment-002/{name}"
        for name in _verify_checksum_file(root / "results/experiment-002")
    )
    errors.extend(
        f"results/experiment-002b/{name}"
        for name in _verify_checksum_file(root / "results/experiment-002b")
    )
    validation_relative = "experiments/002b/validation-evidence.json"
    validation_actual = sha256_bytes((root / validation_relative).read_bytes())
    validation_expected = experiment_002b["frozen_artifact_hashes"][validation_relative]
    known_inconsistencies = []
    if validation_actual != validation_expected:
        known_inconsistencies.append(
            {
                "path": validation_relative,
                "issue": "committed 002b validation hash does not match its earlier freeze entry",
                "current_committed_sha256": validation_actual,
                "freeze_expected_sha256": validation_expected,
            }
        )
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "experiment_002_freeze_id": experiment_002["freeze_id"],
        "experiment_002b_freeze_id": experiment_002b["freeze_id"],
        "protected_paths_match_committed_002b_baseline": not status,
        "known_preexisting_freeze_inconsistencies": known_inconsistencies,
        "source_hash_drift_expected_only_for_corrected_production_dynamics": True,
    }


def validate(root: Path) -> dict[str, Any]:
    if (root / VALIDATION_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 002c validation evidence")
    amendment, production = load_numerical_amendment_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    write_seed_manifest_002c(
        amendment,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
    )
    seed_validation = validate_seed_manifest_002c(
        amendment,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
    )
    historical = verify_historical_records(root)
    checks = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(root, ["uv", "run", "pytest"], "pytest"),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "legacy_gate"),
        _run(root, ["git", "diff", "--check"], "diff_whitespace"),
        {
            "id": "seed_manifest",
            "command": "deterministic seed-manifest validation",
            "passed": seed_validation["passed"],
            "observed": seed_validation,
        },
        {
            "id": "historical_integrity",
            "command": "historical freeze and checksum verification",
            "passed": historical["passed"],
            "observed": historical,
        },
    ]
    scan = repository_hygiene_scan(root)
    checks.append(
        {
            "id": "publication_privacy_scan",
            "command": "bounded repository publication/privacy scan",
            "passed": scan["passed"],
            "observed": scan,
        }
    )
    result = {
        "schema_version": amendment.schema_version,
        "study_instance_id": str(uuid.uuid4()),
        "phase": "validate",
        "phase_sequence": 1,
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _relative_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    files.add(root / VALIDATION_PATH)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in paths
    }


def _tree_hash(hashes: dict[str, str]) -> str:
    return sha256_bytes(canonical_json(hashes))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _runtime(root: Path) -> dict[str, Any]:
    numpy_config = io.StringIO()
    with redirect_stdout(numpy_config):
        np.show_config()
    selected_math = [
        line.strip()
        for line in numpy_config.getvalue().splitlines()
        if any(value in line.lower() for value in ("blas", "lapack", "accelerate", "openblas"))
        and not any(
            prefix in line.lower()
            for prefix in (("/" + "users/"), ("/" + "home/"))
        )
    ]
    uv_version = subprocess.run(
        ["uv", "--version"], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()
    thread_variables = {
        name: os.environ.get(name)
        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS",
        )
        if os.environ.get(name) is not None
    }
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "uv_version": uv_version,
        "locale": locale.getlocale(),
        "thread_variables": thread_variables,
        "blas_lapack_summary": selected_math[:20],
    }


def _historical_paths(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for directory in (
        "experiments/002",
        "artifacts/experiment-002",
        "results/experiment-002",
        "experiments/002b",
        "results/experiment-002b",
    ):
        paths.update(path for path in (root / directory).rglob("*") if path.is_file())
    paths.add(root / "docs/experiment-002.md")
    paths.add(root / "docs/experiment-002b.md")
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 002c freeze")
    amendment, production = load_numerical_amendment_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    if not validation.get("passed") or validation.get("phase_sequence") != 1:
        raise RuntimeError("pre-outcome validation evidence is not passing")
    seed_validation = validate_seed_manifest_002c(
        amendment,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
    )
    if not seed_validation["passed"]:
        raise RuntimeError("002c seed validation failed before freeze")
    historical = verify_historical_records(root)
    if not historical["passed"]:
        raise RuntimeError("historical Experiment 002/002b integrity check failed")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    amendment_base = _git(root, "rev-parse", "experiment-002b-amendment")
    if branch != "experiment-002c-numerical" or head != amendment_base:
        raise RuntimeError("002c must freeze on its requested branch at the committed 002b base")
    scan = repository_hygiene_scan(root)
    if not scan["passed"]:
        raise RuntimeError(f"pre-freeze publication/privacy scan failed: {scan}")
    source_hashes = _file_hashes(root, _relative_files(root))
    seed_paths = sorted(path for path in (root / SEEDS_DIR).glob("*") if path.is_file())
    seed_hashes = _file_hashes(root, seed_paths)
    historical_hashes = _file_hashes(root, _historical_paths(root))
    frozen_paths = [
        root / CONFIG_PATH,
        root / PREREGISTRATION_PATH,
        root / AMENDMENT_PATH,
        root / VALIDATION_PATH,
        root / PRODUCTION_CONFIG_PATH,
        root / CONTROLLER_AMENDMENT_CONFIG_PATH,
        root / POLICY_PATH,
        root / POLICY_MANIFEST_PATH,
        root / CORRIDOR_PATH,
        *seed_paths,
    ]
    frozen_artifacts = _file_hashes(root, frozen_paths)
    source_tree_hash = _tree_hash(source_hashes)
    git_status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    source_identity = {
        "git_commit": head,
        "branch": branch,
        "committed_002b_base": amendment_base,
        "working_tree_dirty": bool(git_status),
        "working_tree_status": git_status,
        "tracked_diff_sha256": sha256_bytes(
            _git(root, "diff", "--binary", "HEAD").encode()
        ),
        "source_tree_sha256": source_tree_hash,
        "source_files_individually_hashed": True,
        "paths": "project-relative only",
        "no_commit_created_by_experiment_002c": True,
    }
    validation_hash = sha256_bytes((root / VALIDATION_PATH).read_bytes())
    unsigned = {
        "schema_version": amendment.schema_version,
        "study_instance_id": validation["study_instance_id"],
        "phase": "freeze",
        "phase_sequence": 2,
        "previous_phase_artifact": VALIDATION_PATH.as_posix(),
        "previous_phase_sha256": validation_hash,
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "amendment_scope": (
            "numerical-only fixed-command replay; no operational, rate, combined-fault, "
            "or confirmatory campaign"
        ),
        "source_identity": source_identity,
        "source_file_hashes": source_hashes,
        "source_tree_sha256": source_tree_hash,
        "frozen_artifact_hashes": frozen_artifacts,
        "seed_manifest_hashes": seed_hashes,
        "seed_validation": seed_validation,
        "historical_evidence_hashes": historical_hashes,
        "historical_integrity": historical,
        "diagnostic_conclusion": {
            "reference_test_defect_primary": True,
            "universal_1e_10_threshold_unrealistically_strict": True,
            "smooth_production_state_propagation_accurate": True,
            "propellant_kink_integration_dominant_discrepancy": True,
            "depletion_reset_conditioning_amplified_error": True,
            "production_terminal_extrema_bug_corrected": True,
            "controller_defect_indicated": False,
        },
        "sample_size": {
            "root_scenarios": 6,
            "command_patterns": 4,
            "complete_traces": amendment.replay_cases,
            "population_rate_claim": False,
            "adaptive_enlargement_allowed": False,
        },
        "acceptance": {
            "identical_event_ordering": True,
            "identical_classifications": [
                "collision",
                "physical_hazard_observed",
                "propellant_depleted",
                "sustained_success",
            ],
            "identical_braking_unreachable": True,
            "bounds": amendment.acceptance_bounds.to_dict(),
            "reference_coarse_fine_fraction": amendment.convergence_bound_fraction,
        },
        "reference": {
            "fine": {
                "rtol": amendment.reference_fine_rtol,
                "atol": amendment.reference_fine_atol,
                "max_step_fraction": amendment.reference_fine_max_step_fraction,
            },
            "coarse": {
                "rtol": amendment.reference_coarse_rtol,
                "atol": amendment.reference_coarse_atol,
                "max_step_fraction": amendment.reference_coarse_max_step_fraction,
            },
            "acceleration_zero_event_split": True,
            "shared_evaluator": False,
        },
        "runtime": _runtime(root),
        "historical_operational_rate_evidence_carried_by_reference_only": True,
        "operational_campaign_rerun": False,
        "rate_campaign_rerun": False,
        "confirmatory_campaign_executed": False,
        "combined_fault_study_executed": False,
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return unsigned


def verify_freeze(root: Path) -> dict[str, Any]:
    manifest = _verify_manifest_self_hash(root / FREEZE_PATH)
    errors: list[str] = []
    for section in (
        "source_file_hashes",
        "frozen_artifact_hashes",
        "seed_manifest_hashes",
        "historical_evidence_hashes",
    ):
        for relative, expected in manifest[section].items():
            path = root / relative
            actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
            if actual != expected:
                errors.append(relative)
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    if manifest["study_instance_id"] != validation["study_instance_id"]:
        errors.append("study_instance_id")
    if manifest["previous_phase_sha256"] != sha256_bytes(
        (root / VALIDATION_PATH).read_bytes()
    ):
        errors.append(VALIDATION_PATH.as_posix())
    if errors:
        raise RuntimeError(f"frozen 002c input hash drift: {errors[:20]}")
    return manifest


def _load_policy(root: Path, production: Any) -> FrozenPolicy:
    return FrozenPolicy.load(
        root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production
    )


def execute(root: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze(root)
    for output in (NUMERICAL_PATH, EXECUTION_PATH):
        if (root / output).exists():
            raise RuntimeError(f"refusing to overwrite Experiment 002c output: {output}")
    amendment, production = load_numerical_amendment_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    controller_amendment, _ = load_amendment_config(
        root / CONTROLLER_AMENDMENT_CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    policy = _load_policy(root, production)
    config_hash = freeze_manifest["frozen_artifact_hashes"][CONFIG_PATH.as_posix()]
    numerical = run_fixed_command_replay(
        amendment,
        controller_amendment,
        production,
        policy,
        config_hash,
        root / NUMERICAL_PATH,
    )
    summary = {
        "schema_version": amendment.schema_version,
        "study_instance_id": freeze_manifest["study_instance_id"],
        "phase": "execute",
        "phase_sequence": 3,
        "previous_phase_artifact": FREEZE_PATH.as_posix(),
        "previous_phase_sha256": sha256_bytes((root / FREEZE_PATH).read_bytes()),
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": freeze_manifest["freeze_id"],
        "fixed_command_cases": numerical["case_count"],
        "elapsed_wall_s": numerical["elapsed_wall_s"],
        "numerical_output_sha256": sha256_bytes((root / NUMERICAL_PATH).read_bytes()),
        "outputs_opened_by_execute": False,
        "operational_campaign_rerun": False,
        "rate_campaign_rerun": False,
        "confirmatory_campaign_executed": False,
        "combined_fault_study_executed": False,
    }
    (root / EXECUTION_PATH).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _pre_manifest_reproducibility(
    root: Path,
    freeze_manifest: dict[str, Any],
    seed_validation: dict[str, Any],
) -> dict[str, Any]:
    numerical = json.loads((root / NUMERICAL_PATH).read_text(encoding="utf-8"))
    execution = json.loads((root / EXECUTION_PATH).read_text(encoding="utf-8"))
    analysis = json.loads((root / ANALYSIS_PATH).read_text(encoding="utf-8"))
    case_keys = [
        (case["root_seed_id"], case["pattern"]) for case in numerical["cases"]
    ]
    checks = [
        {
            "id": "freeze_verified",
            "passed": verify_freeze(root)["freeze_id"] == freeze_manifest["freeze_id"],
        },
        {"id": "seed_manifest_rederived", "passed": seed_validation["passed"]},
        {
            "id": "case_identity_complete",
            "passed": bool(
                len(case_keys) == 24
                and len(set(case_keys)) == 24
                and numerical["case_count"] == 24
            ),
        },
        {
            "id": "phase_chain",
            "passed": bool(
                execution["study_instance_id"] == freeze_manifest["study_instance_id"]
                and analysis["schema_version"] == freeze_manifest["schema_version"]
                and execution["phase_sequence"] == 3
                and execution["previous_phase_sha256"]
                == sha256_bytes((root / FREEZE_PATH).read_bytes())
            ),
        },
        {
            "id": "primary_output_identity",
            "passed": execution["numerical_output_sha256"]
            == sha256_bytes((root / NUMERICAL_PATH).read_bytes()),
        },
        {
            "id": "campaign_exclusions",
            "passed": bool(
                not analysis["operational_campaign_rerun"]
                and not analysis["rate_campaign_rerun"]
                and not analysis["confirmatory_campaign_executed"]
                and not analysis["combined_fault_study_executed"]
            ),
        },
    ]
    return {
        "schema_version": freeze_manifest["schema_version"],
        "study_instance_id": freeze_manifest["study_instance_id"],
        "phase": "reproducibility_check",
        "phase_sequence": 5,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "method": (
            "read-only freeze, seed rederivation, case identity, phase-chain, output-hash, "
            "and campaign-exclusion checks; replay outcomes were not rerun"
        ),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }


def analyze(root: Path) -> dict[str, Any]:
    for output in (
        ANALYSIS_PATH,
        QC_PATH,
        REPORT_PATH,
        REPRODUCIBILITY_PATH,
        RUN_MANIFEST_PATH,
        CHECKSUMS_PATH,
    ):
        if (root / output).exists():
            raise RuntimeError(f"refusing to overwrite Experiment 002c analysis: {output}")
    freeze_manifest = verify_freeze(root)
    amendment, production = load_numerical_amendment_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    seed_validation = validate_seed_manifest_002c(
        amendment,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
    )
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    analysis_result, qc = analyze_002c(
        amendment,
        root / NUMERICAL_PATH,
        root / HISTORICAL_002B_NUMERICAL_PATH,
        root / HISTORICAL_002B_ANALYSIS_PATH,
        seed_validation,
        validation,
        True,
        root / ANALYSIS_PATH,
        root / QC_PATH,
    )
    write_report(analysis_result, root / REPORT_PATH)
    reproducibility = _pre_manifest_reproducibility(
        root, freeze_manifest, seed_validation
    )
    if not reproducibility["passed"]:
        raise RuntimeError("Experiment 002c reproducibility checks failed")
    (root / REPRODUCIBILITY_PATH).write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    scan = repository_hygiene_scan(root)
    if not scan["passed"]:
        raise RuntimeError(f"publication/privacy scan failed: {scan}")
    output_hashes = {
        path.as_posix(): sha256_bytes((root / path).read_bytes())
        for path in RESULT_OUTPUTS
    }
    run_manifest = {
        "schema_version": amendment.schema_version,
        "study_instance_id": freeze_manifest["study_instance_id"],
        "phase": "analyze",
        "phase_sequence": 4,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": freeze_manifest["freeze_id"],
        "paths": "project-relative only",
        "runtime": freeze_manifest["runtime"],
        "command_lines": [
            "uv sync --frozen --extra dev",
            "uv run python -m kri_space_autonomy.experiment_002c.workflow validate",
            "uv run python -m kri_space_autonomy.experiment_002c.workflow freeze",
            "uv run python -m kri_space_autonomy.experiment_002c.workflow verify-freeze",
            "uv run python -m kri_space_autonomy.experiment_002c.workflow run",
            "uv run python -m kri_space_autonomy.experiment_002c.workflow analyze",
            "uv run python -m kri_space_autonomy.experiment_002c.workflow verify-results",
        ],
        "input_hashes": freeze_manifest["frozen_artifact_hashes"],
        "historical_evidence_hashes": freeze_manifest[
            "historical_evidence_hashes"
        ],
        "output_hashes": output_hashes,
        "decision": analysis_result["decision"],
        "numerical_blocker_resolved": analysis_result[
            "numerical_blocker_resolved"
        ],
        "qc_overall_passed": qc["overall_passed"],
        "publication_privacy_scan": scan,
        "replay_executions": 1,
        "operational_campaign_rerun": False,
        "rate_campaign_rerun": False,
        "confirmatory_campaign_executed": False,
        "combined_fault_study_executed": False,
    }
    (root / RUN_MANIFEST_PATH).write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n",
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
    final_scan = repository_hygiene_scan(root)
    if not final_scan["passed"]:
        raise RuntimeError(f"final publication/privacy scan failed: {final_scan}")
    return analysis_result


def verify_results(root: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze(root)
    run_manifest = json.loads((root / RUN_MANIFEST_PATH).read_text(encoding="utf-8"))
    errors: list[str] = []
    if run_manifest["freeze_id"] != freeze_manifest["freeze_id"]:
        errors.append("freeze_id")
    for relative, expected in run_manifest["output_hashes"].items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    errors.extend(_verify_checksum_file(root / "results/experiment-002c"))
    reproducibility = json.loads(
        (root / REPRODUCIBILITY_PATH).read_text(encoding="utf-8")
    )
    if not reproducibility["passed"]:
        errors.append(REPRODUCIBILITY_PATH.as_posix())
    scan = repository_hygiene_scan(root)
    if not scan["passed"]:
        errors.append("publication_privacy_scan")
    return {
        "schema_version": freeze_manifest["schema_version"],
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "errors_preview": errors[:20],
        "freeze_id": freeze_manifest["freeze_id"],
        "result_files_verified": len(run_manifest["output_hashes"]),
        "replay_rerun": False,
        "publication_privacy_scan": scan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 002c numerical-only corrective amendment"
    )
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "freeze",
            "verify-freeze",
            "run",
            "analyze",
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
        result = verify_freeze(root)
    elif args.command == "run":
        result = execute(root)
    elif args.command == "analyze":
        result = analyze(root)
    elif args.command == "verify-results":
        result = verify_results(root)
        if not result["passed"]:
            raise SystemExit(1)
    else:
        result = repository_hygiene_scan(root)
        if not result["passed"]:
            raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
