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
from kri_space_autonomy.experiment_002.runner import load_recovery_corridor
from kri_space_autonomy.experiment_002.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_002c.workflow import repository_hygiene_scan

from .analysis import (
    analyze_002d,
    prospective_worst_case_power,
    replay_check,
    write_report,
)
from .config import load_combined_information_config
from .runner import (
    load_information_rows,
    run_information_block,
    run_information_study,
)
from .seeds import validate_seed_manifest_002d, write_seed_manifest_002d

CONFIG_PATH = Path("experiments/002d/config.json")
STRATUM_MAP_PATH = Path("experiments/002d/confirmatory-stratum-map.json")
PREREGISTRATION_PATH = Path("experiments/002d/preregistration.md")
AMENDMENT_PATH = Path("docs/experiment-002d.md")
VALIDATION_PATH = Path("experiments/002d/validation-evidence.json")
FREEZE_PATH = Path("experiments/002d/freeze-manifest.json")
SEEDS_DIR = Path("experiments/002d/seeds")
PRODUCTION_CONFIG_PATH = Path("experiments/002/config.json")
POLICY_PATH = Path("artifacts/experiment-002/policy-primary.npz")
POLICY_MANIFEST_PATH = Path("artifacts/experiment-002/policy-primary.manifest.json")
CORRIDOR_PATH = Path("experiments/002/recovery-corridor.json")
HISTORICAL_EPISODES_PATH = Path("results/experiment-002/episodes.jsonl")
EPISODES_PATH = Path("results/experiment-002d/combined-information-episodes.jsonl")
EXECUTION_PATH = Path("results/experiment-002d/execution-summary.json")
ANALYSIS_PATH = Path("results/experiment-002d/analysis.json")
QC_PATH = Path("results/experiment-002d/qc.json")
REPORT_PATH = Path("results/experiment-002d/report.md")
REPRODUCIBILITY_PATH = Path("results/experiment-002d/reproducibility.json")
RUN_MANIFEST_PATH = Path("results/experiment-002d/run-manifest.json")
CHECKSUMS_PATH = Path("results/experiment-002d/SHA256SUMS")

HISTORICAL_SEED_DIRS = (
    Path("experiments/002/seeds"),
    Path("experiments/002b/seeds"),
    Path("experiments/002c/seeds"),
)
HISTORICAL_DIRS = (
    Path("experiments/002"),
    Path("artifacts/experiment-002"),
    Path("results/experiment-002"),
    Path("experiments/002b"),
    Path("results/experiment-002b"),
    Path("experiments/002c"),
    Path("results/experiment-002c"),
)
HISTORICAL_DOCS = (
    Path("docs/experiment-002.md"),
    Path("docs/experiment-002b.md"),
    Path("docs/experiment-002c.md"),
)
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_002d/*.py",
    "src/kri_space_autonomy/experiment_002/dynamics.py",
    "src/kri_space_autonomy/experiment_002/evaluator.py",
    "src/kri_space_autonomy/experiment_002/monitor.py",
    "src/kri_space_autonomy/experiment_002/policy.py",
    "src/kri_space_autonomy/experiment_002/analysis.py",
    "tests/test_experiment_002d*.py",
    "experiments/002d/config.json",
    "experiments/002d/confirmatory-stratum-map.json",
    "experiments/002d/preregistration.md",
    "docs/experiment-002d.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
RESULT_OUTPUTS = (
    EPISODES_PATH,
    EXECUTION_PATH,
    ANALYSIS_PATH,
    QC_PATH,
    REPORT_PATH,
    REPRODUCIBILITY_PATH,
)
ORIGINAL_DESIGN_SHA256 = "ffd1dba3195edd583797181702125cff4a81456502dba5c2a652ce1aaa75b590"


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
    if sha256_bytes(canonical_json(manifest)) != freeze_id:
        raise RuntimeError(f"freeze manifest self-hash mismatch: {path.as_posix()}")
    manifest["freeze_id"] = freeze_id
    return manifest


def _historical_paths(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for directory in HISTORICAL_DIRS:
        paths.update(path for path in (root / directory).rglob("*") if path.is_file())
    paths.update(root / path for path in HISTORICAL_DOCS)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def verify_historical_records(root: Path) -> dict[str, Any]:
    manifests = {
        "experiment_002": _verify_manifest_self_hash(
            root / "experiments/002/freeze-manifest.json"
        ),
        "experiment_002b": _verify_manifest_self_hash(
            root / "experiments/002b/freeze-manifest.json"
        ),
        "experiment_002c": _verify_manifest_self_hash(
            root / "experiments/002c/freeze-manifest.json"
        ),
    }
    protected = [*(path.as_posix() for path in HISTORICAL_DIRS)]
    protected.extend(path.as_posix() for path in HISTORICAL_DOCS)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *protected],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    errors = [f"historical_worktree:{line}" for line in status]
    for experiment in ("experiment-002", "experiment-002b", "experiment-002c"):
        errors.extend(
            f"results/{experiment}/{name}"
            for name in _verify_checksum_file(root / "results" / experiment)
        )
    expected_002c = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))[
        "historical_002c_freeze_id"
    ]
    if manifests["experiment_002c"]["freeze_id"] != expected_002c:
        errors.append("experiment_002c_freeze_id")
    stratum_map = json.loads((root / STRATUM_MAP_PATH).read_text(encoding="utf-8"))
    if stratum_map["source_document_sha256"] != ORIGINAL_DESIGN_SHA256:
        errors.append("original_design_source_hash")
    external_source = root.parent / "experiment-002-research-plan.md"
    external_verified = bool(
        external_source.is_file()
        and sha256_bytes(external_source.read_bytes()) == ORIGINAL_DESIGN_SHA256
    )
    if not external_verified:
        errors.append("original_design_source_unavailable_or_drifted")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "protected_paths_unchanged": not status,
        "experiment_002_freeze_id": manifests["experiment_002"]["freeze_id"],
        "experiment_002b_freeze_id": manifests["experiment_002b"]["freeze_id"],
        "experiment_002c_freeze_id": manifests["experiment_002c"]["freeze_id"],
        "original_design_sha256": ORIGINAL_DESIGN_SHA256,
        "original_design_source_verified_before_freeze": external_verified,
    }


def validate(root: Path) -> dict[str, Any]:
    if (root / VALIDATION_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 002d validation evidence")
    study, production = load_combined_information_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    write_seed_manifest_002d(
        study,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
    )
    seed_validation = validate_seed_manifest_002d(
        study,
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
            "command": "deterministic disjoint seed-manifest validation",
            "passed": seed_validation["passed"],
            "observed": seed_validation,
        },
        {
            "id": "historical_integrity",
            "command": "historical freeze, checksum, and source-map verification",
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
        "schema_version": study.schema_version,
        "study_instance_id": str(uuid.uuid4()),
        "phase": "validate",
        "phase_sequence": 1,
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "outcomes_opened": False,
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
        and not any(prefix in line.lower() for prefix in (("/" + "users/"), ("/" + "home/")))
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


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 002d freeze")
    study, production = load_combined_information_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    if not validation.get("passed") or validation.get("phase_sequence") != 1:
        raise RuntimeError("pre-outcome validation evidence is not passing")
    seed_validation = validate_seed_manifest_002d(
        study,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
    )
    historical = verify_historical_records(root)
    if not seed_validation["passed"] or not historical["passed"]:
        raise RuntimeError("seed or historical verification failed before freeze")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != "experiment-002d-combined-fault-info" or head != (
        "4da0adee11163a6919ec69f86cfade81371e00ac"
    ):
        raise RuntimeError("002d must freeze on the requested branch at merged base 4da0ade")
    scan = repository_hygiene_scan(root)
    if not scan["passed"]:
        raise RuntimeError(f"pre-freeze publication/privacy scan failed: {scan}")
    worst_case_power = prospective_worst_case_power(study, root / HISTORICAL_EPISODES_PATH)
    worst_candidates = worst_case_power["candidate_confirmatory_seeds_per_stratum"]
    if not any(
        item["meets_target_by_monte_carlo_lower_bounds"]
        for item in worst_candidates.values()
    ):
        raise RuntimeError("pre-outcome least-favorable power sensitivity did not pass")
    source_hashes = _file_hashes(root, _relative_files(root))
    seed_paths = sorted(path for path in (root / SEEDS_DIR).glob("*") if path.is_file())
    historical_hashes = _file_hashes(root, _historical_paths(root))
    frozen_paths = [
        root / CONFIG_PATH,
        root / STRATUM_MAP_PATH,
        root / PREREGISTRATION_PATH,
        root / AMENDMENT_PATH,
        root / VALIDATION_PATH,
        root / PRODUCTION_CONFIG_PATH,
        root / POLICY_PATH,
        root / POLICY_MANIFEST_PATH,
        root / CORRIDOR_PATH,
        *seed_paths,
    ]
    source_tree_hash = _tree_hash(source_hashes)
    git_status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    source_identity = {
        "git_commit": head,
        "branch": branch,
        "working_tree_dirty": bool(git_status),
        "working_tree_status": git_status,
        "tracked_diff_sha256": sha256_bytes(_git(root, "diff", "--binary", "HEAD").encode()),
        "source_tree_sha256": source_tree_hash,
        "source_files_individually_hashed": True,
        "paths": "project-relative only",
        "no_commit_created_by_experiment_002d": True,
    }
    unsigned = {
        "schema_version": study.schema_version,
        "study_instance_id": validation["study_instance_id"],
        "phase": "freeze",
        "phase_sequence": 2,
        "previous_phase_artifact": VALIDATION_PATH.as_posix(),
        "previous_phase_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "amendment_scope": (
            "299-root F7 paired D/PD nuisance study only; no confirmatory campaign"
        ),
        "source_identity": source_identity,
        "source_file_hashes": source_hashes,
        "source_tree_sha256": source_tree_hash,
        "frozen_artifact_hashes": _file_hashes(root, frozen_paths),
        "seed_manifest_hashes": _file_hashes(root, seed_paths),
        "seed_validation": seed_validation,
        "historical_evidence_hashes": historical_hashes,
        "historical_integrity": historical,
        "original_design_sha256": ORIGINAL_DESIGN_SHA256,
        "prospective_worst_case_power": worst_case_power,
        "sample_size": {
            "combined_fault_root_seeds": study.information_seeds,
            "arms": list(study.arms),
            "episodes": study.planned_episodes,
            "minimum_exact_zero_incomplete_upper_below_one_percent": True,
            "adaptive_enlargement_allowed": False,
            "maximum_permitted_roots_not_exceeded": True,
        },
        "runtime": _runtime(root),
        "corrected_production_dynamics": {
            "source": "src/kri_space_autonomy/experiment_002/dynamics.py",
            "merged_base": "4da0ade",
            "experiment_002c_numerical_decision": "pass",
        },
        "confirmatory_campaign_executed": False,
        "reserved_confirmatory_partition_materialized": False,
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
        raise RuntimeError(f"frozen 002d input hash drift: {errors[:20]}")
    return manifest


def _load_policy(root: Path, production: Any) -> FrozenPolicy:
    return FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production)


def execute(root: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze(root)
    for output in (EPISODES_PATH, EXECUTION_PATH):
        if (root / output).exists():
            raise RuntimeError(f"refusing to overwrite Experiment 002d output: {output}")
    study, production = load_combined_information_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    policy = _load_policy(root, production)
    study_config_hash = freeze_manifest["frozen_artifact_hashes"][CONFIG_PATH.as_posix()]
    production_config_hash = freeze_manifest["frozen_artifact_hashes"][
        PRODUCTION_CONFIG_PATH.as_posix()
    ]
    run = run_information_study(
        study,
        production,
        policy,
        study_config_hash,
        production_config_hash,
        root / EPISODES_PATH,
    )
    summary = {
        "schema_version": study.schema_version,
        "study_instance_id": freeze_manifest["study_instance_id"],
        "phase": "execute",
        "phase_sequence": 3,
        "previous_phase_artifact": FREEZE_PATH.as_posix(),
        "previous_phase_sha256": sha256_bytes((root / FREEZE_PATH).read_bytes()),
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": freeze_manifest["freeze_id"],
        **run,
        "confirmatory_campaign_executed": False,
        "reserved_confirmatory_partition_materialized": False,
    }
    (root / EXECUTION_PATH).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


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
            raise RuntimeError(f"refusing to overwrite Experiment 002d analysis: {output}")
    freeze_manifest = verify_freeze(root)
    study, production = load_combined_information_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    policy = _load_policy(root, production)
    load_recovery_corridor(root / CORRIDOR_PATH)
    seed_validation = validate_seed_manifest_002d(
        study,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
    )
    historical = verify_historical_records(root)
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    execution = json.loads((root / EXECUTION_PATH).read_text(encoding="utf-8"))
    rows = load_information_rows(root / EPISODES_PATH)
    replay_payload = json.loads(
        (root / SEEDS_DIR / "replay_subset.json").read_text(encoding="utf-8")
    )
    study_config_hash = freeze_manifest["frozen_artifact_hashes"][CONFIG_PATH.as_posix()]
    production_config_hash = freeze_manifest["frozen_artifact_hashes"][
        PRODUCTION_CONFIG_PATH.as_posix()
    ]

    def rerun(replicate: int) -> list[dict[str, Any]]:
        return [
            item.to_dict()
            for item in run_information_block(
                study,
                production,
                replicate,
                policy,
                study_config_hash,
                production_config_hash,
            )
        ]

    replay = replay_check(rows, replay_payload["replicates"], rerun)
    analysis_result, qc = analyze_002d(
        study,
        root / EPISODES_PATH,
        root / HISTORICAL_EPISODES_PATH,
        validation,
        seed_validation,
        historical,
        True,
        replay,
        root / ANALYSIS_PATH,
        root / QC_PATH,
    )
    write_report(analysis_result, root / REPORT_PATH)
    reproducibility_checks = [
        {
            "id": "phase_chain",
            "passed": bool(
                execution["study_instance_id"] == freeze_manifest["study_instance_id"]
                and execution["previous_phase_sha256"]
                == sha256_bytes((root / FREEZE_PATH).read_bytes())
            ),
        },
        {
            "id": "primary_output_identity",
            "passed": execution["episodes_sha256"]
            == sha256_bytes((root / EPISODES_PATH).read_bytes()),
        },
        {"id": "seed_manifest_rederived", "passed": seed_validation["passed"]},
        {"id": "same_platform_replay", "passed": replay["passed"]},
        {
            "id": "campaign_exclusions",
            "passed": bool(
                not analysis_result["confirmatory_campaign_executed"]
                and not analysis_result["reserved_confirmatory_partition_materialized"]
            ),
        },
    ]
    reproducibility = {
        "schema_version": study.schema_version,
        "study_instance_id": freeze_manifest["study_instance_id"],
        "phase": "reproducibility_check",
        "phase_sequence": 5,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "method": "freeze, seed rederivation, phase-chain, output-hash, and frozen-root replay",
        "passed": all(check["passed"] for check in reproducibility_checks),
        "checks": reproducibility_checks,
    }
    (root / REPRODUCIBILITY_PATH).write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not reproducibility["passed"] or not qc["overall_passed"]:
        analysis_result["information_requirement_resolved"] = False
    scan = repository_hygiene_scan(root)
    if not scan["passed"]:
        raise RuntimeError(f"publication/privacy scan failed: {scan}")
    output_hashes = {
        path.as_posix(): sha256_bytes((root / path).read_bytes())
        for path in RESULT_OUTPUTS
    }
    run_manifest = {
        "schema_version": study.schema_version,
        "study_instance_id": freeze_manifest["study_instance_id"],
        "phase": "analyze",
        "phase_sequence": 4,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": freeze_manifest["freeze_id"],
        "paths": "project-relative only",
        "runtime": freeze_manifest["runtime"],
        "command_lines": [
            "uv sync --frozen --extra dev",
            "uv run python -m kri_space_autonomy.experiment_002d.workflow validate",
            "uv run python -m kri_space_autonomy.experiment_002d.workflow freeze",
            "uv run python -m kri_space_autonomy.experiment_002d.workflow verify-freeze",
            "uv run python -m kri_space_autonomy.experiment_002d.workflow run",
            "uv run python -m kri_space_autonomy.experiment_002d.workflow analyze",
            "uv run python -m kri_space_autonomy.experiment_002d.workflow verify-results",
        ],
        "input_hashes": freeze_manifest["frozen_artifact_hashes"],
        "historical_evidence_hashes": freeze_manifest["historical_evidence_hashes"],
        "output_hashes": output_hashes,
        "decision": analysis_result["decision"],
        "information_requirement_resolved": analysis_result[
            "information_requirement_resolved"
        ],
        "qc_overall_passed": qc["overall_passed"],
        "publication_privacy_scan": scan,
        "information_executions": 1,
        "replay_executions": 1,
        "confirmatory_campaign_executed": False,
        "reserved_confirmatory_partition_materialized": False,
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
    errors.extend(_verify_checksum_file(root / "results/experiment-002d"))
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
        "publication_privacy_scan": scan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 002d bounded combined-fault information amendment"
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
