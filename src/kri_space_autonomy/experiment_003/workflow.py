from __future__ import annotations

import argparse
import gzip
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

from .analysis import analyze_pilot, load_episode_rows, write_report
from .config import EXPECTED_BASE_COMMIT, EXPECTED_BRANCH, load_config
from .runner import run_arm, run_pilot
from .seeds import (
    Experiment003Scenario,
    canonical_json,
    materialize_exogenous,
    materialize_pilot_seeds,
    sha256_bytes,
    validate_materialized_pilot,
    validate_seed_contract,
)
from .validation import run_numerical_checks

CONFIG_PATH = Path("experiments/003/config.json")
PREREGISTRATION_PATH = Path("experiments/003/preregistration.md")
SEED_CONTRACT_PATH = Path("experiments/003/seed-contract.json")
VALIDATION_PATH = Path("experiments/003/validation-evidence.json")
FREEZE_PATH = Path("experiments/003/freeze-manifest.json")
READINESS_PATH = Path("experiments/003/readiness.json")
SEEDS_DIR = Path("experiments/003/seeds")
DOC_PATH = Path("docs/experiment-003.md")
PRODUCTION_CONFIG_PATH = Path("experiments/002/config.json")
POLICY_PATH = Path("artifacts/experiment-002/policy-primary.npz")
POLICY_MANIFEST_PATH = Path("artifacts/experiment-002/policy-primary.manifest.json")
RESULTS_DIR = Path("results/experiment-003")
EPISODES_PATH = RESULTS_DIR / "pilot-episodes.jsonl"
EXECUTION_PATH = RESULTS_DIR / "execution-summary.json"
ANALYSIS_PATH = RESULTS_DIR / "analysis.json"
QC_PATH = RESULTS_DIR / "qc.json"
REPORT_PATH = RESULTS_DIR / "report.md"
REPRODUCIBILITY_PATH = RESULTS_DIR / "reproducibility.json"
RUN_MANIFEST_PATH = RESULTS_DIR / "run-manifest.json"
CHECKSUMS_PATH = RESULTS_DIR / "SHA256SUMS"

HISTORICAL_DIRS = (
    Path("experiments/002"),
    Path("experiments/002b"),
    Path("experiments/002c"),
    Path("experiments/002d"),
    Path("experiments/002-confirmatory"),
    Path("results/experiment-002"),
    Path("results/experiment-002b"),
    Path("results/experiment-002c"),
    Path("results/experiment-002d"),
    Path("results/experiment-002-confirmatory"),
    Path("artifacts/experiment-002"),
)
HISTORICAL_DOCS = (
    Path("docs/experiment-002.md"),
    Path("docs/experiment-002b.md"),
    Path("docs/experiment-002c.md"),
    Path("docs/experiment-002d.md"),
    Path("docs/experiment-002-confirmatory.md"),
    Path("docs/experiment-002-research-plan.md.gz"),
)
EXPECTED_FREEZE_IDS = {
    "002": "5c8da46ae99ab0951d017e4a28409efc0befb7c1fac8571c0876af82997ef1ce",
    "002b": "4bb93ac705f29108b06fc080fde5a8d944ebd3bac00137d60063128b5e79bfb7",
    "002c": "8157fefc06ea1aec4121b475d0ffa068576c8f98807406205c8f47f2120e479a",
    "002d": "0fc96ee320d25c2cec3c37ba9aa87467ca4a9ee62a138bd0bed37f3ad7dc053b",
    "002-confirmatory": "15eb6b3b552e130f7b983930fda10d7d1c0841943408ec8586b51619d9076c15",
}
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_003/*.py",
    "tests/test_experiment_003_*.py",
    "experiments/003/config.json",
    "experiments/003/preregistration.md",
    "experiments/003/seed-contract.json",
    "docs/experiment-003.md",
    "src/kri_space_autonomy/experiment_002/config.py",
    "src/kri_space_autonomy/experiment_002/dynamics.py",
    "src/kri_space_autonomy/experiment_002/evaluator.py",
    "src/kri_space_autonomy/experiment_002/policy.py",
    "src/kri_space_autonomy/controller_adapter/contract.py",
    "src/kri_space_autonomy/fault_suite/manifest.py",
    "src/kri_space_autonomy/assurance_report/policy.py",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
}
RESULT_OUTPUTS = (
    EPISODES_PATH,
    EXECUTION_PATH,
    ANALYSIS_PATH,
    QC_PATH,
    REPORT_PATH,
    REPRODUCIBILITY_PATH,
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


def _candidate_files(root: Path) -> list[Path]:
    tracked = _git(root, "ls-files", "-z").split("\0")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    files: set[Path] = set()
    for relative in (*tracked, *untracked):
        if not relative:
            continue
        path = root / relative
        if path.is_file() and not any(part in EXCLUDED_PARTS for part in path.parts):
            files.add(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def repository_publication_scan(root: Path) -> dict[str, Any]:
    prohibited_names = [
        ("k-" + "dense-byok").encode(),
        ("ka" + "dy").encode(),
    ]
    orchestration_names = [
        ("sub" + "agent").encode(),
        ("inter" + "view").encode(),
        ("note" + "book").encode(),
        ("web_" + "search").encode(),
        ("modal_" + "run").encode(),
    ]
    provider_names = [
        ("open" + "ai").encode(),
        ("anth" + "ropic").encode(),
        ("chat" + "gpt").encode(),
        ("gem" + "ini").encode(),
    ]
    assistance_phrases = [
        ("ai-" + "assisted").encode(),
        ("generated by " + "ai").encode(),
        ("language " + "model assistance").encode(),
    ]
    absolute_prefixes = [
        ("/" + "users/").encode(),
        ("/" + "home/").encode(),
        ("c:\\" + "users\\").encode(),
    ]
    credential_markers = [
        ("-----begin " + "private key-----").encode(),
        ("api_" + "key=").encode(),
        ("access_" + "token=").encode(),
        ("authorization: " + "bearer ").encode(),
    ]
    matches: list[dict[str, str]] = []
    opaque: list[str] = []
    files = _candidate_files(root)
    for path in files:
        relative = path.relative_to(root).as_posix()
        if path.name == ".env" or path.name.startswith(".env."):
            matches.append({"path": relative, "rule": "environment-file"})
            continue
        raw = path.read_bytes()
        if path.suffix == ".gz":
            try:
                expanded = gzip.decompress(raw)
            except (OSError, EOFError):
                matches.append({"path": relative, "rule": "unreadable-compressed-file"})
                continue
        else:
            expanded = raw
        lowered = expanded.lower()
        raw_lowered = raw.lower()
        for term in prohibited_names:
            if term in lowered:
                matches.append({"path": relative, "rule": "prohibited-platform-name"})
        for term in orchestration_names:
            if term in raw_lowered:
                matches.append({"path": relative, "rule": "workflow-tool-branding"})
        for term in provider_names:
            if term in lowered:
                matches.append({"path": relative, "rule": "model-provider-provenance"})
        for phrase in assistance_phrases:
            if phrase in lowered:
                matches.append({"path": relative, "rule": "assistance-wording"})
        for prefix in absolute_prefixes:
            if prefix in lowered:
                matches.append({"path": relative, "rule": "local-absolute-path"})
        for marker in credential_markers:
            if marker in lowered:
                matches.append({"path": relative, "rule": "credential-marker"})
        if b"\x00" in expanded and path.suffix not in {".npz", ".png", ".pdf"}:
            opaque.append(relative)
    return {
        "passed": not matches,
        "enumeration": "tracked plus untracked nonignored files",
        "files_scanned": len(files),
        "matches": len(matches),
        "matches_preview": matches[:30],
        "opaque_files": len(opaque),
        "opaque_files_preview": opaque[:20],
    }


def _verify_checksum_file(directory: Path) -> list[str]:
    path = directory / "SHA256SUMS"
    if not path.is_file():
        return [f"missing:{directory.as_posix()}/SHA256SUMS"]
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        candidate = directory / name
        actual = sha256_bytes(candidate.read_bytes()) if candidate.is_file() else None
        if actual != expected:
            errors.append(f"{directory.name}/{name}")
    return errors


def _verify_self_hash(path: Path) -> dict[str, Any]:
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


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in paths
    }


def verify_historical_evidence(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    observed_ids: dict[str, str] = {}
    for name, expected in EXPECTED_FREEZE_IDS.items():
        path = root / f"experiments/{name}/freeze-manifest.json"
        try:
            manifest = _verify_self_hash(path)
            observed_ids[name] = manifest["freeze_id"]
            if manifest["freeze_id"] != expected:
                errors.append(f"freeze_id:{name}")
        except (OSError, KeyError, RuntimeError, json.JSONDecodeError):
            errors.append(f"freeze_manifest:{name}")
    checksum_files = 0
    for name in ("002", "002b", "002c", "002d", "002-confirmatory"):
        directory = root / f"results/experiment-{name}"
        checksum_errors = _verify_checksum_file(directory)
        errors.extend(checksum_errors)
        if not checksum_errors:
            checksum_files += len(
                (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
            )
    final_run = json.loads(
        (root / "results/experiment-002-confirmatory/run-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    historical_map = final_run.get("historical_evidence_hashes", {})
    map_mismatches = []
    for relative, expected in historical_map.items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            map_mismatches.append(relative)
    errors.extend(f"historical_map:{value}" for value in map_mismatches)
    protected = [*(path.as_posix() for path in HISTORICAL_DIRS)]
    protected.extend(path.as_posix() for path in HISTORICAL_DOCS)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", *protected],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    errors.extend(f"historical_worktree:{line}" for line in status)
    final_freeze = _run(
        root,
        [
            "uv",
            "run",
            "python",
            "-m",
            "kri_space_autonomy.experiment_002_confirmatory.workflow",
            "verify-freeze",
        ],
        "final_confirmatory_freeze",
    )
    final_results = _run(
        root,
        [
            "uv",
            "run",
            "python",
            "-m",
            "kri_space_autonomy.experiment_002_confirmatory.workflow",
            "verify-results",
        ],
        "final_confirmatory_results",
    )
    if not final_freeze["passed"]:
        errors.append("final_confirmatory_freeze")
    if not final_results["passed"]:
        errors.append("final_confirmatory_results")
    return {
        "passed": not errors,
        "errors_preview": errors[:30],
        "freeze_ids": observed_ids,
        "published_checksum_files_verified": checksum_files,
        "historical_map_entries_verified": len(historical_map) - len(map_mismatches),
        "historical_map_mismatches": len(map_mismatches),
        "protected_paths_unchanged": not status,
        "supported_final_verifiers": [final_freeze, final_results],
        "historical_evidence_hashes": historical_map,
    }


def _relative_source_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
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


def validate(root: Path) -> dict[str, Any]:
    study, production = load_config(root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH)
    numerical = run_numerical_checks(study, production)
    seed_contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH, root)
    historical = verify_historical_evidence(root)
    scan = repository_publication_scan(root)
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
                "--deselect",
                (
                    "tests/test_experiment_002_confirmatory_design.py::"
                    "test_seed_contract_has_exact_eight_strata_without_materialized_roots"
                ),
                "--deselect",
                (
                    "tests/test_experiment_002_confirmatory_workflow.py::"
                    "test_freeze_phase_requires_partition_16_to_remain_unmaterialized"
                ),
            ],
            "phase_appropriate_pytest",
        ),
        _run(
            root,
            ["uv", "run", "pytest", "-q", "-k", "experiment_003"],
            "experiment_003_tests",
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
        {"id": "experiment_003_numerical", "passed": numerical["passed"], "observed": numerical},
        {"id": "seed_reservation", "passed": seed_contract["passed"], "observed": seed_contract},
        {"id": "historical_integrity", "passed": historical["passed"], "observed": historical},
        {"id": "publication_privacy", "passed": scan["passed"], "observed": scan},
    ]
    passed = all(bool(check["passed"]) for check in checks)
    result = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": passed,
        "status": "READY" if passed else "NOT_READY",
        "checks": checks,
        "known_phase_exclusions": {
            "tests": [
                (
                    "tests/test_experiment_002_confirmatory_design.py::"
                    "test_seed_contract_has_exact_eight_strata_without_materialized_roots"
                ),
                (
                    "tests/test_experiment_002_confirmatory_workflow.py::"
                    "test_freeze_phase_requires_partition_16_to_remain_unmaterialized"
                ),
            ],
            "reason": (
                "frozen pre-materialization assertions superseded by the completed campaign; "
                "current freeze/result verification is required instead"
            ),
            "baseline_phase_mismatch": True,
        },
        "outcome_campaign_executed": False,
        "outcome_seeds_materialized": False,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite Experiment 003 freeze/readiness artifacts")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != EXPECTED_BASE_COMMIT:
        raise RuntimeError("Experiment 003 freeze requires the requested branch and merged base")
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
        raise RuntimeError("Experiment 003 validation is NOT READY")
    study, production = load_config(root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH)
    source_hashes = _file_hashes(root, _relative_source_files(root))
    historical = verify_historical_evidence(root)
    if not historical["passed"]:
        raise RuntimeError("historical evidence verification failed during freeze")
    seed_contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH, root)
    scan = repository_publication_scan(root)
    if not seed_contract["passed"] or not scan["passed"]:
        raise RuntimeError("seed reservation or publication scan failed during freeze")
    tracked_diff = _git(root, "diff", "--binary")
    unsigned = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_freeze",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "Experiment 003 estimator-in-loop design-validation pilot foundation",
        "source_identity": {
            "branch": branch,
            "base_commit": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "tracked_diff_sha256": sha256_bytes(tracked_diff.encode()),
            "paths": "project-relative only",
        },
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "historical_freeze_ids": historical["freeze_ids"],
        "historical_evidence_hashes": historical["historical_evidence_hashes"],
        "historical_integrity": {
            key: value
            for key, value in historical.items()
            if key != "historical_evidence_hashes"
        },
        "design": {
            "arms": list(study.arms),
            "strata": list(study.strata),
            "fixed_stratum_weight": 1.0 / len(study.strata),
            "pilot_roots_per_stratum": study.pilot_roots_per_stratum,
            "pilot_blocks": study.pilot_blocks,
            "pilot_episodes": study.pilot_episodes,
            "inferential_unit": "stratum by root-seed four-arm block",
            "primary_H1": "PD-D adverse-coded analysis_hazard superiority",
            "gatekept_H2": "PD-D sustained-success noninferiority at -0.03",
            "dynamics": "corrected one-dimensional Experiment 002 plant",
            "estimator_state": list(study.state_order),
        },
        "seed_reservation": {
            **seed_contract,
            "state_at_freeze": "reserved_not_materialized_or_executed",
            "generator_available": True,
            "generator_invoked": False,
            "materialization_requires_internal_freeze_verification": True,
        },
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "validation_status": validation["status"],
        "publication_privacy_scan": scan,
        "runtime": _runtime(),
        "outcome_campaign_executed": False,
        "outcome_seeds_materialized": False,
        "readiness_policy": "fail closed; no critical-check waiver",
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root, require_unmaterialized=True)
    readiness_unsigned = {
        "schema_version": study.schema_version,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY" if verification["passed"] else "NOT_READY",
        "scope": "separate write-once Experiment 003 design-validation pilot execution",
        "outcome_seeds_materialized": False,
        "outcome_campaign_executed": False,
        "next_command": (
            "uv run python -m kri_space_autonomy.experiment_003.workflow "
            "materialize-pilot-seeds"
        ),
    }
    readiness_unsigned["readiness_id"] = sha256_bytes(canonical_json(readiness_unsigned))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness_unsigned, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {**unsigned, "readiness": readiness_unsigned, "verification": verification}


def verify_freeze(root: Path, *, require_unmaterialized: bool = True) -> dict[str, Any]:
    manifest = _verify_self_hash(root / FREEZE_PATH)
    errors: list[str] = []
    for relative, expected in manifest["source_file_hashes"].items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    historical = verify_historical_evidence(root)
    if not historical["passed"]:
        errors.append("historical_integrity")
    study, _ = load_config(root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH)
    if require_unmaterialized:
        contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH, root)
        if not contract["passed"]:
            errors.append("seed_reservation")
    else:
        contract = {
            "passed": True,
            "contract_sha256": sha256_bytes((root / SEED_CONTRACT_PATH).read_bytes()),
        }
    readiness_check: dict[str, Any] = {"present": (root / READINESS_PATH).is_file()}
    if (root / READINESS_PATH).is_file():
        try:
            readiness = json.loads((root / READINESS_PATH).read_text(encoding="utf-8"))
            readiness_id = readiness.pop("readiness_id")
            readiness_check.update(
                {
                    "passed": bool(
                        sha256_bytes(canonical_json(readiness)) == readiness_id
                        and readiness.get("freeze_id") == manifest["freeze_id"]
                        and readiness.get("status") == "READY"
                    ),
                    "readiness_id": readiness_id,
                    "status": readiness.get("status"),
                }
            )
        except (OSError, KeyError, json.JSONDecodeError):
            readiness_check["passed"] = False
        if not readiness_check["passed"]:
            errors.append("readiness_identity")
    else:
        readiness_check["passed"] = True
    scan = repository_publication_scan(root)
    if not scan["passed"]:
        errors.append("publication_privacy_scan")
    return {
        "schema_version": manifest["schema_version"],
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "status": "READY" if not errors else "NOT_READY",
        "errors_preview": errors[:30],
        "freeze_id": manifest["freeze_id"],
        "source_files_verified": len(manifest["source_file_hashes"]),
        "historical_integrity": historical,
        "seed_contract": contract,
        "readiness_identity": readiness_check,
        "publication_privacy_scan": scan,
        "require_unmaterialized": require_unmaterialized,
    }


def materialize_seeds(root: Path) -> dict[str, Any]:
    manifest = verify_freeze(root, require_unmaterialized=True)
    if not manifest["passed"]:
        raise RuntimeError("freeze verification failed before pilot seed materialization")
    study, production = load_config(root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH)
    return materialize_pilot_seeds(
        study,
        production,
        root=root,
        freeze_id=manifest["freeze_id"],
        seed_contract_sha256=manifest["seed_contract"]["contract_sha256"],
    )


def execute(root: Path) -> dict[str, Any]:
    manifest = verify_freeze(root, require_unmaterialized=False)
    if not manifest["passed"]:
        raise RuntimeError("freeze verification failed before pilot execution")
    study, production = load_config(root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH)
    seed_hash = sha256_bytes((root / SEED_CONTRACT_PATH).read_bytes())
    seed_validation = validate_materialized_pilot(
        study,
        production,
        root=root,
        freeze_id=manifest["freeze_id"],
        seed_contract_sha256=seed_hash,
    )
    if not seed_validation["passed"]:
        raise RuntimeError("pilot seed validation failed")
    policy = FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production)
    result = run_pilot(
        study,
        production,
        policy,
        sha256_bytes((root / CONFIG_PATH).read_bytes()),
        root / SEEDS_DIR / "pilot.jsonl",
        root / EPISODES_PATH,
    )
    execution = {
        "schema_version": study.schema_version,
        "phase": "design_validation_pilot_execution",
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": manifest["freeze_id"],
        "seed_validation": seed_validation,
        "campaign_executions": 1,
        **result,
    }
    (root / EXECUTION_PATH).write_text(
        json.dumps(execution, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return execution


def _replay_pilot_subset(
    root: Path,
    study,
    production,
    policy,
    rows: list[dict[str, Any]],
    config_hash: str,
) -> dict[str, Any]:
    replay = json.loads((root / SEEDS_DIR / "replay-subset.json").read_text(encoding="utf-8"))
    scenarios = {
        (row["stratum_id"], int(row["replicate"])): row
        for row in (
            json.loads(line)
            for line in (root / SEEDS_DIR / "pilot.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    observed = {
        (row["stratum_id"], int(row["replicate"]), row["arm"]): row for row in rows
    }
    mismatches = []
    checked = 0
    for stratum, replicates in replay["replicates_by_stratum"].items():
        for replicate in replicates:
            value = dict(scenarios[(stratum, replicate)])
            value["arm_run_order"] = tuple(value["arm_run_order"])
            scenario = Experiment003Scenario(**value)
            streams, _ = materialize_exogenous(
                study,
                production,
                stratum,
                replicate,
                partition_code=study.pilot_partition_code,
            )
            for run_order, arm in enumerate(scenario.arm_run_order, start=1):
                replayed, _ = run_arm(
                    study,
                    production,
                    scenario,
                    streams,
                    arm,
                    run_order,
                    policy,
                    config_hash,
                )
                checked += 1
                expected = observed[(stratum, replicate, arm)]
                if canonical_json(replayed.to_dict()) != canonical_json(expected):
                    mismatches.append(f"{stratum}:{replicate}:{arm}")
    return {
        "passed": not mismatches,
        "episodes_checked": checked,
        "expected_episodes": len(study.strata)
        * study.pilot_replay_roots_per_stratum
        * len(study.arms),
        "mismatches": len(mismatches),
        "mismatches_preview": mismatches[:20],
    }


def analyze(root: Path) -> dict[str, Any]:
    for output in (ANALYSIS_PATH, QC_PATH, REPORT_PATH, REPRODUCIBILITY_PATH, RUN_MANIFEST_PATH):
        if (root / output).exists():
            raise RuntimeError(f"refusing pre-existing analysis output: {output.as_posix()}")
    manifest = verify_freeze(root, require_unmaterialized=False)
    if not manifest["passed"]:
        raise RuntimeError("freeze verification failed before pilot analysis")
    study, production = load_config(root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH)
    seed_hash = sha256_bytes((root / SEED_CONTRACT_PATH).read_bytes())
    seeds = validate_materialized_pilot(
        study,
        production,
        root=root,
        freeze_id=manifest["freeze_id"],
        seed_contract_sha256=seed_hash,
    )
    policy = FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production)
    rows = load_episode_rows(root / EPISODES_PATH)
    config_hash = sha256_bytes((root / CONFIG_PATH).read_bytes())
    replay = _replay_pilot_subset(root, study, production, policy, rows, config_hash)
    historical = verify_historical_evidence(root)
    execution = json.loads((root / EXECUTION_PATH).read_text(encoding="utf-8"))
    phase_chain = bool(
        execution.get("freeze_id") == manifest["freeze_id"]
        and execution.get("episodes_sha256") == sha256_bytes((root / EPISODES_PATH).read_bytes())
    )
    integrity = {
        "passed": bool(
            seeds["passed"]
            and replay["passed"]
            and historical["passed"]
            and phase_chain
        ),
        "seed_validation": seeds,
        "same_platform_replay": replay,
        "historical_integrity": historical,
        "phase_chain": phase_chain,
    }
    analysis_result, qc = analyze_pilot(rows, study, integrity)
    (root / ANALYSIS_PATH).write_text(
        json.dumps(analysis_result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (root / QC_PATH).write_text(
        json.dumps(qc, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_report(analysis_result, root / REPORT_PATH)
    reproducibility = {
        "schema_version": study.schema_version,
        "freeze_id": manifest["freeze_id"],
        "phase": "pilot_reproducibility",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "passed": integrity["passed"],
        "checks": integrity,
    }
    (root / REPRODUCIBILITY_PATH).write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    scan = repository_publication_scan(root)
    if not scan["passed"]:
        raise RuntimeError("publication/privacy scan failed after pilot analysis")
    output_hashes = {
        path.as_posix(): sha256_bytes((root / path).read_bytes()) for path in RESULT_OUTPUTS
    }
    run_manifest = {
        "schema_version": study.schema_version,
        "freeze_id": manifest["freeze_id"],
        "phase": "pilot_analysis",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "paths": "project-relative only",
        "seed_manifest_sha256": seeds["manifest_sha256"],
        "output_hashes": output_hashes,
        "progression": analysis_result["progression"],
        "primary_hypotheses_tested": False,
        "campaign_executions": 1,
        "replay_executions": 1,
        "publication_privacy_scan": scan,
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
    return analysis_result


def verify_results(root: Path) -> dict[str, Any]:
    manifest = verify_freeze(root, require_unmaterialized=False)
    run_manifest = json.loads((root / RUN_MANIFEST_PATH).read_text(encoding="utf-8"))
    errors: list[str] = []
    if run_manifest.get("freeze_id") != manifest["freeze_id"]:
        errors.append("freeze_id")
    for relative, expected in run_manifest.get("output_hashes", {}).items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    errors.extend(_verify_checksum_file(root / RESULTS_DIR))
    scan = repository_publication_scan(root)
    if not scan["passed"]:
        errors.append("publication_privacy_scan")
    return {
        "schema_version": manifest["schema_version"],
        "passed": not errors,
        "errors_preview": errors[:20],
        "freeze_id": manifest["freeze_id"],
        "result_files_verified": len(run_manifest.get("output_hashes", {})),
        "publication_privacy_scan": scan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 003 estimator-in-loop workflow")
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "freeze",
            "verify-freeze",
            "materialize-pilot-seeds",
            "run-pilot",
            "analyze-pilot",
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
    elif args.command == "materialize-pilot-seeds":
        result = materialize_seeds(root)
    elif args.command == "run-pilot":
        result = execute(root)
    elif args.command == "analyze-pilot":
        result = analyze(root)
    elif args.command == "verify-results":
        result = verify_results(root)
    else:
        result = repository_publication_scan(root)
    if not result.get("passed", True):
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
