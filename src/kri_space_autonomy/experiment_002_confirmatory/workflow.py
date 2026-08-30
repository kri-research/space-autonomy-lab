from __future__ import annotations

import argparse
import gzip
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

from .analysis import analyze_confirmatory
from .config import CONFIRMATORY_STRATA, load_confirmatory_config
from .runner import (
    load_episode_rows,
    run_confirmatory_block,
    run_confirmatory_campaign,
)
from .seeds import (
    validate_confirmatory_seed_manifest,
    validate_seed_contract,
    write_confirmatory_seed_manifest,
)

CONFIG_PATH = Path("experiments/002-confirmatory/config.json")
SEED_CONTRACT_PATH = Path("experiments/002-confirmatory/seed-contract.json")
PREREGISTRATION_PATH = Path("experiments/002-confirmatory/preregistration.md")
DESIGN_PATH = Path("docs/experiment-002-confirmatory.md")
VALIDATION_PATH = Path("experiments/002-confirmatory/validation-evidence.json")
FREEZE_PATH = Path("experiments/002-confirmatory/freeze-manifest.json")
SEEDS_DIR = Path("experiments/002-confirmatory/seeds")
PRODUCTION_CONFIG_PATH = Path("experiments/002/config.json")
POLICY_PATH = Path("artifacts/experiment-002/policy-primary.npz")
POLICY_MANIFEST_PATH = Path("artifacts/experiment-002/policy-primary.manifest.json")
CORRIDOR_PATH = Path("experiments/002/recovery-corridor.json")
RESERVATION_PATH = Path("experiments/002/seeds/future_confirmatory_reserved.json")
STRATUM_MAP_PATH = Path("experiments/002d/confirmatory-stratum-map.json")
POWER_RESOLUTION_PATH = Path("results/experiment-002d/analysis.json")
EPISODES_PATH = Path("results/experiment-002-confirmatory/episodes.jsonl")
EXECUTION_PATH = Path("results/experiment-002-confirmatory/execution-summary.json")
ANALYSIS_PATH = Path("results/experiment-002-confirmatory/analysis.json")
QC_PATH = Path("results/experiment-002-confirmatory/qc.json")
REPORT_PATH = Path("results/experiment-002-confirmatory/report.md")
REPRODUCIBILITY_PATH = Path("results/experiment-002-confirmatory/reproducibility.json")
RUN_MANIFEST_PATH = Path("results/experiment-002-confirmatory/run-manifest.json")
CHECKSUMS_PATH = Path("results/experiment-002-confirmatory/SHA256SUMS")

HISTORICAL_SEED_DIRS = (
    Path("experiments/002/seeds"),
    Path("experiments/002b/seeds"),
    Path("experiments/002c/seeds"),
    Path("experiments/002d/seeds"),
)
HISTORICAL_DIRS = (
    Path("experiments/002"),
    Path("artifacts/experiment-002"),
    Path("results/experiment-002"),
    Path("experiments/002b"),
    Path("results/experiment-002b"),
    Path("experiments/002c"),
    Path("results/experiment-002c"),
    Path("experiments/002d"),
    Path("results/experiment-002d"),
)
HISTORICAL_DOCS = (
    Path("docs/experiment-002.md"),
    Path("docs/experiment-002b.md"),
    Path("docs/experiment-002c.md"),
    Path("docs/experiment-002d.md"),
    Path("docs/experiment-002-research-plan.md.gz"),
)
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_002_confirmatory/*.py",
    "src/kri_space_autonomy/experiment_002/analysis.py",
    "src/kri_space_autonomy/experiment_002/config.py",
    "src/kri_space_autonomy/experiment_002/dynamics.py",
    "src/kri_space_autonomy/experiment_002/evaluator.py",
    "src/kri_space_autonomy/experiment_002/monitor.py",
    "src/kri_space_autonomy/experiment_002/policy.py",
    "src/kri_space_autonomy/experiment_002/runner.py",
    "src/kri_space_autonomy/experiment_002/seeds.py",
    "tests/test_experiment_002_confirmatory*.py",
    "experiments/002-confirmatory/config.json",
    "experiments/002-confirmatory/seed-contract.json",
    "experiments/002-confirmatory/preregistration.md",
    "docs/experiment-002-confirmatory.md",
    "Makefile",
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
EXPECTED_BRANCH = "experiment-002-confirmatory"
EXPECTED_BASE = "2a16735050ec636e58f02658641d79f39b151924"
ORIGINAL_DESIGN_SHA256 = "ffd1dba3195edd583797181702125cff4a81456502dba5c2a652ce1aaa75b590"
EXPECTED_FREEZE_IDS = {
    "002": "5c8da46ae99ab0951d017e4a28409efc0befb7c1fac8571c0876af82997ef1ce",
    "002b": "4bb93ac705f29108b06fc080fde5a8d944ebd3bac00137d60063128b5e79bfb7",
    "002c": "8157fefc06ea1aec4121b475d0ffa068576c8f98807406205c8f47f2120e479a",
    "002d": "0fc96ee320d25c2cec3c37ba9aa87467ca4a9ee62a138bd0bed37f3ad7dc053b",
}
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
    prohibited_names = [
        ("k-" + "dense-byok").encode(),
        ("k-" + "dense").encode(),
        ("k" + "dense").encode(),
        ("ka" + "dy").encode(),
        ("ca" + "dence").encode(),
        ("ka" + "tie").encode(),
    ]
    workflow_terms = [
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
        raw_payload = path.read_bytes()
        try:
            expanded_payload = (
                gzip.decompress(raw_payload) if path.suffix == ".gz" else raw_payload
            )
        except (OSError, EOFError):
            expanded_payload = raw_payload
        lowered = expanded_payload.lower()
        raw_lowered = raw_payload.lower()
        for term in prohibited_names:
            if term in lowered:
                matches.append(
                    {"path": path.relative_to(root).as_posix(), "rule": "prohibited-name"}
                )
        for term in workflow_terms:
            if term in raw_lowered:
                matches.append(
                    {"path": path.relative_to(root).as_posix(), "rule": "workflow-tool-name"}
                )
        for prefix in absolute_prefixes:
            if prefix in lowered:
                matches.append(
                    {"path": path.relative_to(root).as_posix(), "rule": "local-absolute-path"}
                )
        for marker in secret_markers:
            if marker in lowered:
                matches.append(
                    {"path": path.relative_to(root).as_posix(), "rule": "credential-marker"}
                )
    return {
        "passed": not matches,
        "files_scanned": len(files),
        "matches": len(matches),
        "matches_preview": matches[:20],
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


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _verify_checksum_file(directory: Path) -> list[str]:
    errors: list[str] = []
    checksum_path = directory / "SHA256SUMS"
    if not checksum_path.is_file():
        return [f"missing:{checksum_path.relative_to(directory.parent).as_posix()}"]
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
        raise RuntimeError(f"freeze manifest self-hash mismatch: {path.name}")
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
        name: _verify_manifest_self_hash(
            root / f"experiments/{name}/freeze-manifest.json"
        )
        for name in ("002", "002b", "002c", "002d")
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
    for name, expected in EXPECTED_FREEZE_IDS.items():
        if manifests[name]["freeze_id"] != expected:
            errors.append(f"freeze_id:{name}")
        errors.extend(
            f"results/experiment-{name}/{item}"
            for item in _verify_checksum_file(root / f"results/experiment-{name}")
        )
    source_snapshot = gzip.decompress(
        (root / "docs/experiment-002-research-plan.md.gz").read_bytes()
    )
    if sha256_bytes(source_snapshot) != ORIGINAL_DESIGN_SHA256:
        errors.append("original_design_source_hash")
    numerical = json.loads(
        (root / "results/experiment-002c/analysis.json").read_text(encoding="utf-8")
    )
    if numerical.get("decision") != "pass" or not numerical.get(
        "numerical_blocker_resolved"
    ):
        errors.append("002c_numerical_resolution")
    power = json.loads((root / POWER_RESOLUTION_PATH).read_text(encoding="utf-8"))
    if (
        power.get("decision") != "resolved_freeze_confirmatory_design"
        or power.get("power", {}).get("recommended_confirmatory_seeds_per_stratum")
        != 1000
        or power.get("power", {}).get("recommended_confirmatory_episodes") != 32000
        or power.get("reserved_confirmatory_partition_materialized") is not False
        or power.get("confirmatory_campaign_executed") is not False
    ):
        errors.append("002d_power_resolution")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "protected_paths_unchanged": not status,
        "freeze_ids": {name: manifests[name]["freeze_id"] for name in manifests},
        "original_design_sha256": ORIGINAL_DESIGN_SHA256,
        "original_design_source_verified": sha256_bytes(source_snapshot)
        == ORIGINAL_DESIGN_SHA256,
        "experiment_002c_numerical_decision": numerical.get("decision"),
        "experiment_002d_decision": power.get("decision"),
        "recommended_confirmatory_seeds_per_stratum": power.get("power", {}).get(
            "recommended_confirmatory_seeds_per_stratum"
        ),
        "recommended_confirmatory_episodes": power.get("power", {}).get(
            "recommended_confirmatory_episodes"
        ),
    }


def verify_unmaterialized_reservation(root: Path) -> dict[str, Any]:
    reservation = json.loads((root / RESERVATION_PATH).read_text(encoding="utf-8"))
    errors: list[str] = []
    if reservation.get("partition") != "future_confirmatory_reserved":
        errors.append("partition_name")
    if reservation.get("partition_code") != 16:
        errors.append("partition_code")
    if reservation.get("status") != "reserved_not_materialized_or_executed":
        errors.append("reservation_status")
    if (root / SEEDS_DIR).exists():
        errors.append("confirmatory_seed_directory_exists")
    if (root / EPISODES_PATH.parent).exists():
        errors.append("confirmatory_result_directory_exists")
    return {
        "passed": not errors,
        "errors_preview": errors,
        "partition": reservation.get("partition"),
        "partition_code": reservation.get("partition_code"),
        "status": reservation.get("status"),
        "reservation_sha256": sha256_bytes((root / RESERVATION_PATH).read_bytes()),
        "confirmatory_seed_directory_exists": (root / SEEDS_DIR).exists(),
        "confirmatory_result_directory_exists": (root / EPISODES_PATH.parent).exists(),
    }


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


def validate(root: Path) -> dict[str, Any]:
    if (root / VALIDATION_PATH).exists():
        raise RuntimeError("refusing to overwrite confirmatory validation evidence")
    study, production = load_confirmatory_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH)
    historical = verify_historical_records(root)
    reservation = verify_unmaterialized_reservation(root)
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
            "id": "seed_contract",
            "command": "read-only seed materialization contract validation",
            "passed": contract["passed"],
            "observed": contract,
        },
        {
            "id": "historical_integrity",
            "command": "historical freeze, checksum, numerical, and power verification",
            "passed": historical["passed"],
            "observed": historical,
        },
        {
            "id": "reservation_unmaterialized",
            "command": "read-only partition reservation and output-absence verification",
            "passed": reservation["passed"],
            "observed": reservation,
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
        "reserved_partition_materialized": False,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "planned_blocks": study.planned_blocks,
        "planned_episodes": study.planned_episodes,
        "production_horizon_s": production.horizon_s,
        "production_command_period_s": production.command_period_s,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists():
        raise RuntimeError("refusing to overwrite final confirmatory freeze")
    study, production = load_confirmatory_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    if not validation.get("passed") or validation.get("phase_sequence") != 1:
        raise RuntimeError("pre-outcome validation evidence is not passing")
    historical = verify_historical_records(root)
    reservation = verify_unmaterialized_reservation(root)
    contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH)
    if not historical["passed"] or not reservation["passed"] or not contract["passed"]:
        raise RuntimeError("historical, reservation, or seed-contract verification failed")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != EXPECTED_BASE:
        raise RuntimeError("confirmatory freeze requires the requested branch and merged base")
    scan = repository_hygiene_scan(root)
    if not scan["passed"]:
        raise RuntimeError(f"pre-freeze publication/privacy scan failed: {scan}")
    source_hashes = _file_hashes(root, _relative_files(root))
    historical_hashes = _file_hashes(root, _historical_paths(root))
    frozen_paths = [
        root / CONFIG_PATH,
        root / SEED_CONTRACT_PATH,
        root / PREREGISTRATION_PATH,
        root / DESIGN_PATH,
        root / VALIDATION_PATH,
        root / PRODUCTION_CONFIG_PATH,
        root / POLICY_PATH,
        root / POLICY_MANIFEST_PATH,
        root / CORRIDOR_PATH,
        root / RESERVATION_PATH,
        root / STRATUM_MAP_PATH,
        root / POWER_RESOLUTION_PATH,
    ]
    source_tree_hash = _tree_hash(source_hashes)
    git_status = _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    power = json.loads((root / POWER_RESOLUTION_PATH).read_text(encoding="utf-8"))
    unsigned = {
        "schema_version": study.schema_version,
        "study_instance_id": validation["study_instance_id"],
        "phase": "freeze",
        "phase_sequence": 2,
        "previous_phase_artifact": VALIDATION_PATH.as_posix(),
        "previous_phase_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "final eight-stratum confirmatory design; campaign not executed",
        "source_identity": {
            "git_commit": head,
            "branch": branch,
            "working_tree_dirty": bool(git_status),
            "working_tree_status": git_status,
            "tracked_diff_sha256": sha256_bytes(
                _git(root, "diff", "--binary", "HEAD").encode()
            ),
            "source_tree_sha256": source_tree_hash,
            "source_files_individually_hashed": True,
            "paths": "project-relative only",
            "no_commit_created_by_confirmatory_freeze": True,
        },
        "source_file_hashes": source_hashes,
        "source_tree_sha256": source_tree_hash,
        "frozen_artifact_hashes": _file_hashes(root, frozen_paths),
        "historical_evidence_hashes": historical_hashes,
        "historical_integrity": historical,
        "design": {
            "strata": list(CONFIRMATORY_STRATA),
            "fixed_weight_per_stratum": study.stratum_weight,
            "roots_per_stratum": study.seeds_per_stratum,
            "arms": list(study.arms),
            "blocks": study.planned_blocks,
            "episodes": study.planned_episodes,
            "paired_analysis_unit": "stratum by root-seed four-arm block",
        },
        "power_resolution": {
            "source": POWER_RESOLUTION_PATH.as_posix(),
            "decision": power["decision"],
            "recommended_roots_per_stratum": power["power"][
                "recommended_confirmatory_seeds_per_stratum"
            ],
            "recommended_episodes": power["power"][
                "recommended_confirmatory_episodes"
            ],
            "endpoint_power_interpretation": "marginal, not joint",
        },
        "primary_analysis": {
            "H1": "PD-D adverse-coded analysis_hazard superiority; two-sided 95% upper bound <0",
            "H2": (
                "gatekept PD-D sustained-success noninferiority; one-sided 97.5% "
                "lower bound >-0.03"
            ),
            "bootstrap_replicates": study.bootstrap_replicates,
            "bootstrap_seed": study.bootstrap_seed,
            "secondary_family": "H3, H4, H5a, H5b; one-sided Holm alpha 0.05",
            "recovery_weights": "equal 1/7 over F1-F7",
            "predeclared_sensitivities": [
                "worst-case missing primary cells",
                "physical-hazard-only",
                "all available D/PD pairs",
            ],
        },
        "corrected_production": {
            "dynamics_source": "src/kri_space_autonomy/experiment_002/dynamics.py",
            "experiment_002c_decision": "pass",
            "horizon_s": production.horizon_s,
            "command_period_s": production.command_period_s,
            "multi_rate_gate_included": False,
        },
        "policy": {
            "artifact": POLICY_PATH.as_posix(),
            "refit_allowed": False,
            "controller_redesign_allowed": False,
        },
        "seed_materialization": {
            "state_at_freeze": "reserved_not_materialized_or_executed",
            "partition_code": study.partition_code,
            "contract": SEED_CONTRACT_PATH.as_posix(),
            "contract_sha256": contract["contract_sha256"],
            "generator_invoked_during_validation_or_freeze": False,
            "requires_internal_freeze_verification": True,
            "materialization_command": (
                "uv run python -m "
                "kri_space_autonomy.experiment_002_confirmatory.workflow materialize-seeds"
            ),
            "replacement_or_extension_allowed": False,
        },
        "reservation_verification": reservation,
        "runtime": _runtime(root),
        "confirmatory_campaign_executed": False,
        "reserved_confirmatory_partition_materialized": False,
        "confirmatory_outcomes_opened": False,
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
        "historical_evidence_hashes",
    ):
        for relative, expected in manifest[section].items():
            path = root / relative
            actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
            if actual != expected:
                errors.append(relative)
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    if manifest["study_instance_id"] != validation.get("study_instance_id"):
        errors.append("study_instance_id")
    if manifest["previous_phase_sha256"] != sha256_bytes(
        (root / VALIDATION_PATH).read_bytes()
    ):
        errors.append(VALIDATION_PATH.as_posix())
    if (root / SEEDS_DIR / "index.json").is_file():
        seed_index = json.loads(
            (root / SEEDS_DIR / "index.json").read_text(encoding="utf-8")
        )
        if seed_index.get("freeze_id") != manifest["freeze_id"]:
            errors.append("seed_index_freeze_id")
    if errors:
        raise RuntimeError(f"frozen confirmatory input hash drift: {errors[:20]}")
    return manifest


def materialize_seeds(root: Path) -> dict[str, Any]:
    manifest = verify_freeze(root)
    if (root / SEEDS_DIR).exists() or (root / EPISODES_PATH.parent).exists():
        raise RuntimeError("refusing pre-existing confirmatory seed or result path")
    study, production = load_confirmatory_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH)
    historical = verify_historical_records(root)
    reservation = verify_unmaterialized_reservation(root)
    if not contract["passed"] or not historical["passed"] or not reservation["passed"]:
        raise RuntimeError("materialization prerequisites failed")
    index = write_confirmatory_seed_manifest(
        study,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
        manifest["freeze_id"],
        contract["contract_sha256"],
    )
    seed_validation = validate_confirmatory_seed_manifest(
        study,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
        manifest["freeze_id"],
        contract["contract_sha256"],
    )
    if not seed_validation["passed"]:
        raise RuntimeError(f"materialized seed validation failed: {seed_validation}")
    return {
        "schema_version": study.schema_version,
        "phase": "materialize_seeds",
        "phase_sequence": 3,
        "freeze_id": manifest["freeze_id"],
        "freeze_verified_before_generator_invocation": True,
        "index": index,
        "seed_validation": seed_validation,
        "outcomes_opened": False,
        "confirmatory_campaign_executed": False,
    }


def _load_policy(root: Path, production: Any) -> FrozenPolicy:
    return FrozenPolicy.load(
        root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production
    )


def execute(root: Path) -> dict[str, Any]:
    manifest = verify_freeze(root)
    if (root / EPISODES_PATH.parent).exists():
        raise RuntimeError("refusing pre-existing confirmatory result directory")
    study, production = load_confirmatory_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH)
    seed_validation = validate_confirmatory_seed_manifest(
        study,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
        manifest["freeze_id"],
        contract["contract_sha256"],
    )
    if not seed_validation["passed"]:
        raise RuntimeError("confirmatory seed manifest is absent or invalid")
    policy = _load_policy(root, production)
    corridor = load_recovery_corridor(root / CORRIDOR_PATH)
    study_hash = manifest["frozen_artifact_hashes"][CONFIG_PATH.as_posix()]
    production_hash = manifest["frozen_artifact_hashes"][
        PRODUCTION_CONFIG_PATH.as_posix()
    ]
    run = run_confirmatory_campaign(
        study,
        production,
        policy,
        corridor,
        study_hash,
        production_hash,
        manifest["freeze_id"],
        root / EPISODES_PATH,
    )
    summary = {
        "schema_version": study.schema_version,
        "study_instance_id": manifest["study_instance_id"],
        "phase": "execute",
        "phase_sequence": 4,
        "previous_phase_artifact": FREEZE_PATH.as_posix(),
        "previous_phase_sha256": sha256_bytes((root / FREEZE_PATH).read_bytes()),
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": manifest["freeze_id"],
        **run,
        "campaign_executions": 1,
    }
    (root / EXECUTION_PATH).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def _replay_check(
    root: Path,
    manifest: dict[str, Any],
    study: Any,
    production: Any,
    policy: FrozenPolicy,
    corridor: Any,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    replay = json.loads(
        (root / SEEDS_DIR / "replay-subset.json").read_text(encoding="utf-8")
    )
    expected = {
        (str(row["stratum_id"]), int(row["replicate"]), str(row["arm"])): row
        for row in rows
    }
    study_hash = manifest["frozen_artifact_hashes"][CONFIG_PATH.as_posix()]
    production_hash = manifest["frozen_artifact_hashes"][
        PRODUCTION_CONFIG_PATH.as_posix()
    ]
    failures: list[dict[str, Any]] = []
    compared = 0
    for stratum in CONFIRMATORY_STRATA:
        for replicate in replay["replicates_by_stratum"][stratum]:
            rerun = run_confirmatory_block(
                study,
                production,
                stratum,
                int(replicate),
                policy,
                corridor,
                study_hash,
                production_hash,
                manifest["freeze_id"],
            )
            for item in rerun:
                key = (stratum, int(replicate), item.arm)
                compared += 1
                if expected.get(key) != item.to_dict():
                    failures.append(
                        {"stratum": stratum, "replicate": replicate, "arm": item.arm}
                    )
    expected_count = len(CONFIRMATORY_STRATA) * study.replay_blocks_per_stratum * len(
        study.arms
    )
    return {
        "passed": not failures and compared == expected_count,
        "episodes_compared": compared,
        "expected_episodes": expected_count,
        "failures_preview": failures[:20],
    }


def _write_report(analysis: dict[str, Any], path: Path) -> None:
    primary = analysis["primary_gatekeeping"]
    lines = [
        "# Experiment 002 confirmatory campaign",
        "",
        "> **Evidence boundary:** confirmatory evidence for the frozen synthetic generator only;",
        "> not flight-safety evidence or operational fault prevalence.",
        "",
        "## Decision",
        "",
        f"**`{analysis['decision']}`**.",
        "",
        "## Primary gatekeeping",
        "",
        f"- H1 passed: `{str(primary['H1']['passed']).lower()}`; PD-D analysis-hazard "
        f"estimate `{primary['H1']['estimate']:.6f}`.",
        f"- H2 status: `{primary['H2']['status']}`; passed: "
        f"`{str(primary['H2']['passed']).lower()}`.",
        "- H1/H2 are marginal endpoints in a serial gatekeeping sequence.",
        "",
        "Complete machine-readable estimates, strata, secondary tests, sensitivities, and QC are",
        "in `analysis.json` and `qc.json`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


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
            raise RuntimeError(f"refusing pre-existing confirmatory analysis output: {output}")
    manifest = verify_freeze(root)
    study, production = load_confirmatory_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    contract = validate_seed_contract(study, root / SEED_CONTRACT_PATH)
    seed_validation = validate_confirmatory_seed_manifest(
        study,
        production,
        root / SEEDS_DIR,
        tuple(root / path for path in HISTORICAL_SEED_DIRS),
        manifest["freeze_id"],
        contract["contract_sha256"],
    )
    historical = verify_historical_records(root)
    policy = _load_policy(root, production)
    corridor = load_recovery_corridor(root / CORRIDOR_PATH)
    rows = load_episode_rows(root / EPISODES_PATH)
    replay = _replay_check(
        root, manifest, study, production, policy, corridor, rows
    )
    execution = json.loads((root / EXECUTION_PATH).read_text(encoding="utf-8"))
    phase_chain = bool(
        execution.get("study_instance_id") == manifest["study_instance_id"]
        and execution.get("freeze_id") == manifest["freeze_id"]
        and execution.get("episodes_sha256")
        == sha256_bytes((root / EPISODES_PATH).read_bytes())
    )
    integrity = {
        "passed": bool(
            historical["passed"]
            and seed_validation["passed"]
            and replay["passed"]
            and phase_chain
        ),
        "historical_integrity": historical,
        "seed_validation": seed_validation,
        "same_platform_replay": replay,
        "phase_chain": phase_chain,
    }
    seed_rows = [
        json.loads(line)
        for line in (root / SEEDS_DIR / "confirmatory.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
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
        "study_instance_id": manifest["study_instance_id"],
        "phase": "reproducibility_check",
        "phase_sequence": 6,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "method": (
            "freeze, deterministic seed rederivation, phase chain, output hash, "
            "and frozen-root replay"
        ),
        "passed": integrity["passed"],
        "checks": integrity,
    }
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
        "schema_version": study.schema_version,
        "study_instance_id": manifest["study_instance_id"],
        "phase": "analyze",
        "phase_sequence": 5,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": manifest["freeze_id"],
        "paths": "project-relative only",
        "runtime": manifest["runtime"],
        "input_hashes": manifest["frozen_artifact_hashes"],
        "historical_evidence_hashes": manifest["historical_evidence_hashes"],
        "seed_manifest_sha256": seed_validation["manifest_sha256"],
        "output_hashes": output_hashes,
        "decision": analysis_result["decision"],
        "qc_overall_passed": qc["overall_passed"],
        "publication_privacy_scan": scan,
        "campaign_executions": 1,
        "replay_executions": 1,
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
    return analysis_result


def verify_results(root: Path) -> dict[str, Any]:
    manifest = verify_freeze(root)
    run_manifest = json.loads((root / RUN_MANIFEST_PATH).read_text(encoding="utf-8"))
    errors: list[str] = []
    if run_manifest.get("freeze_id") != manifest["freeze_id"]:
        errors.append("freeze_id")
    for relative, expected in run_manifest.get("output_hashes", {}).items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    errors.extend(_verify_checksum_file(root / EPISODES_PATH.parent))
    scan = repository_hygiene_scan(root)
    if not scan["passed"]:
        errors.append("publication_privacy_scan")
    return {
        "schema_version": manifest["schema_version"],
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "errors_preview": errors[:20],
        "freeze_id": manifest["freeze_id"],
        "result_files_verified": len(run_manifest.get("output_hashes", {})),
        "publication_privacy_scan": scan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 002 final eight-stratum confirmatory campaign"
    )
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "freeze",
            "verify-freeze",
            "materialize-seeds",
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
    elif args.command == "materialize-seeds":
        result = materialize_seeds(root)
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
