from __future__ import annotations

import argparse
import gzip
import io
import json
import platform
import subprocess
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_002.seeds import canonical_json, sha256_bytes

from .analysis import analyze_002b, write_report
from .config import load_amendment_config
from .numerical import run_fixed_command_replay
from .runner import run_operational_validation, run_rate_decomposition
from .seeds import validate_seed_manifests_002b, write_seed_manifests_002b

CONFIG_PATH = Path("experiments/002b/config.json")
PRODUCTION_CONFIG_PATH = Path("experiments/002/config.json")
PREREGISTRATION_PATH = Path("experiments/002b/preregistration.md")
AMENDMENT_PATH = Path("docs/experiment-002b.md")
VALIDATION_PATH = Path("experiments/002b/validation-evidence.json")
FREEZE_PATH = Path("experiments/002b/freeze-manifest.json")
SEEDS_DIR = Path("experiments/002b/seeds")
HISTORICAL_SEEDS_DIR = Path("experiments/002/seeds")
POLICY_PATH = Path("artifacts/experiment-002/policy-primary.npz")
POLICY_MANIFEST_PATH = Path("artifacts/experiment-002/policy-primary.manifest.json")
CORRIDOR_PATH = Path("experiments/002/recovery-corridor.json")
OPERATIONAL_PATH = Path("results/experiment-002b/operational-episodes.jsonl")
RATE_PATH = Path("results/experiment-002b/rate-decomposition-episodes.jsonl")
RATE_EVENTS_PATH = Path("results/experiment-002b/rate-command-events.jsonl.gz")
NUMERICAL_PATH = Path("results/experiment-002b/fixed-command-replay.json")
EXECUTION_PATH = Path("results/experiment-002b/execution-summary.json")
ANALYSIS_PATH = Path("results/experiment-002b/analysis.json")
QC_PATH = Path("results/experiment-002b/qc.json")
REPORT_PATH = Path("results/experiment-002b/report.md")
RUN_MANIFEST_PATH = Path("results/experiment-002b/run-manifest.json")
CHECKSUMS_PATH = Path("results/experiment-002b/SHA256SUMS")

HISTORICAL_EVIDENCE_PATHS = (
    Path("experiments/002/preregistration.md"),
    Path("experiments/002/freeze-manifest.json"),
    Path("experiments/002/deviations.md"),
    Path("results/experiment-002/analysis.json"),
    Path("results/experiment-002/qc.json"),
    Path("results/experiment-002/report.md"),
    Path("results/experiment-002/run-manifest.json"),
    Path("results/experiment-002/episodes.jsonl"),
)

SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_002b/*.py",
    "src/kri_space_autonomy/experiment_002/{config,dynamics,evaluator,monitor,policy,seeds}.py",
    "tests/test_experiment_002b*.py",
    "experiments/002b/config.json",
    "experiments/002b/preregistration.md",
    "docs/experiment-002b.md",
    "README.md",
    "Makefile",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)

EXCLUDED_SCAN_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
}


def _forbidden_terms() -> list[bytes]:
    fragments = [
        ("k-" + "dense-byok"),
        ("k-" + "dense"),
        ("k" + "dense"),
        ("ka" + "dy"),
        ("ca" + "dence"),
        ("ka" + "tie"),
    ]
    return [value.encode().lower() for value in fragments]


def _publishable_files(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_SCAN_PARTS for part in path.parts):
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def publication_boundary_scan(root: Path) -> dict[str, Any]:
    matches: list[dict[str, str]] = []
    absolute_prefixes = [
        ("/" + "users/").encode(),
        ("/" + "home/").encode(),
        ("c:\\" + "users\\").encode(),
    ]
    terms = _forbidden_terms()
    for path in _publishable_files(root):
        try:
            if path.suffix == ".gz":
                payload = gzip.decompress(path.read_bytes())
            else:
                payload = path.read_bytes()
        except (OSError, EOFError):
            payload = path.read_bytes()
        lowered = payload.lower()
        for term in terms:
            if term in lowered:
                matches.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "rule": "prohibited-name",
                    }
                )
        for prefix in absolute_prefixes:
            if prefix in lowered:
                matches.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "rule": "local-installation-path",
                    }
                )
    return {
        "passed": not matches,
        "files_scanned": len(_publishable_files(root)),
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


def validate(root: Path) -> dict[str, Any]:
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
    ]
    scan = publication_boundary_scan(root)
    checks.append(
        {
            "id": "publication_boundary_scan",
            "command": "bounded repository content scan",
            "passed": scan["passed"],
            "observed": scan,
        }
    )
    result = {
        "schema_version": "experiment-002b-amendment-1.0",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }
    (root / VALIDATION_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _relative_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        if "{" in pattern:
            prefix, options = pattern.split("{", 1)
            choices, suffix = options.split("}", 1)
            for choice in choices.split(","):
                files.update(path for path in root.glob(prefix + choice + suffix) if path.is_file())
        else:
            files.update(path for path in root.glob(pattern) if path.is_file())
    files.add(root / VALIDATION_PATH)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes()) for path in paths
    }


def _tree_hash(hashes: dict[str, str]) -> str:
    return sha256_bytes(canonical_json(hashes))


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _runtime() -> dict[str, Any]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        np.show_config()
    selected = [
        line.strip()
        for line in buffer.getvalue().splitlines()
        if any(value in line.lower() for value in ("blas", "lapack", "accelerate", "openblas"))
    ]
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "os": platform.system(),
        "architecture": platform.machine(),
        "numpy_version": np.__version__,
        "blas_lapack_summary": selected[:20],
    }


def freeze(root: Path) -> dict[str, Any]:
    amendment, production = load_amendment_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    validation_evidence = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    if not validation_evidence.get("passed"):
        raise RuntimeError("pre-outcome validation evidence is not passing")
    seed_index = write_seed_manifests_002b(
        amendment,
        production,
        root / SEEDS_DIR,
        root / HISTORICAL_SEEDS_DIR,
    )
    seed_validation = validate_seed_manifests_002b(
        amendment,
        production,
        root / SEEDS_DIR,
        root / HISTORICAL_SEEDS_DIR,
    )
    if not seed_validation["passed"]:
        raise RuntimeError("002b seed validation failed before freeze")
    source_hashes = _file_hashes(root, _relative_files(root))
    historical_hashes = _file_hashes(
        root, [root / path for path in HISTORICAL_EVIDENCE_PATHS]
    )
    seed_paths = sorted((root / SEEDS_DIR).glob("*"))
    seed_hashes = _file_hashes(root, [path for path in seed_paths if path.is_file()])
    frozen_artifacts = _file_hashes(
        root,
        [
            root / CONFIG_PATH,
            root / PREREGISTRATION_PATH,
            root / AMENDMENT_PATH,
            root / POLICY_PATH,
            root / POLICY_MANIFEST_PATH,
            root / CORRIDOR_PATH,
            root / PRODUCTION_CONFIG_PATH,
            root / VALIDATION_PATH,
            *seed_paths,
        ],
    )
    source_tree_hash = _tree_hash(source_hashes)
    source_identity = {
        "git_commit": _git(root, "rev-parse", "HEAD"),
        "working_tree_dirty": bool(_git(root, "status", "--short")),
        "working_tree_diff_sha256": sha256_bytes(
            _git(root, "diff", "--binary").encode()
        ),
        "source_tree_sha256": source_tree_hash,
        "paths": "project-relative only",
    }
    unsigned = {
        "schema_version": amendment.schema_version,
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "amendment_scope": (
            "corrective sampled-data validation; operational 1.0 s PD only; diagnostic "
            "0.5/0.25 s timing grid; no confirmatory campaign"
        ),
        "source_identity": source_identity,
        "source_file_hashes": source_hashes,
        "source_tree_sha256": source_tree_hash,
        "frozen_artifact_hashes": frozen_artifacts,
        "seed_manifest_hashes": seed_hashes,
        "seed_index": seed_index,
        "seed_validation": seed_validation,
        "historical_evidence_hashes": historical_hashes,
        "sample_size": {
            "operational_seeds_per_stratum": amendment.operational_seeds_per_stratum,
            "minimum_zero_event_n": amendment.minimum_zero_event_n,
            "one_sided_confidence": amendment.one_sided_confidence,
            "upper_margin": amendment.zero_event_upper_margin,
            "zero_event_upper_at_n": amendment.zero_event_upper_bound,
            "rate_feasibility_seeds_per_stratum": amendment.rate_seeds_per_stratum,
            "multi_rate_support_claim": False,
        },
        "acceptance": {
            "zero_controller_or_numerical_failures": True,
            "fixed_command_max_state_or_metric_error": amendment.numerical_error_tolerance,
            "fixed_command_classifications_identical": [
                "collision",
                "physical_hazard_observed",
                "propellant_depleted",
                "sustained_success",
            ],
            "operational_physical_hazards_per_stratum": 0,
            "operational_one_sided_hazard_upper_below": amendment.zero_event_upper_margin,
            "minimum_final_propellant": production.propellant_reserve,
            "rate_trajectory_identity_gate": False,
            "rate_success_identity_gate": False,
            "rate_absolute_fuel_or_range_identity_gate": False,
        },
        "runtime": _runtime(),
        "confirmatory_campaign_executed": False,
        "combined_fault_study_executed": False,
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return unsigned


def verify_freeze(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / FREEZE_PATH).read_text(encoding="utf-8"))
    freeze_id = manifest.pop("freeze_id")
    if sha256_bytes(canonical_json(manifest)) != freeze_id:
        raise RuntimeError("002b freeze manifest self-hash mismatch")
    manifest["freeze_id"] = freeze_id
    errors = []
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
    if errors:
        raise RuntimeError(f"frozen 002b input hash drift: {errors[:20]}")
    return manifest


def _load_policy(root: Path, production: Any) -> FrozenPolicy:
    return FrozenPolicy.load(
        root / POLICY_PATH, root / POLICY_MANIFEST_PATH, production
    )


def execute(root: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze(root)
    amendment, production = load_amendment_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    policy = _load_policy(root, production)
    config_hash = freeze_manifest["frozen_artifact_hashes"][CONFIG_PATH.as_posix()]
    for output in (OPERATIONAL_PATH, RATE_PATH, RATE_EVENTS_PATH, NUMERICAL_PATH):
        if (root / output).exists():
            raise RuntimeError(f"refusing to overwrite frozen-study output: {output}")
    operational = run_operational_validation(
        amendment, production, policy, config_hash, root / OPERATIONAL_PATH
    )
    rate = run_rate_decomposition(
        amendment,
        production,
        policy,
        config_hash,
        root / RATE_PATH,
        root / RATE_EVENTS_PATH,
    )
    numerical = run_fixed_command_replay(
        amendment, production, policy, config_hash, root / NUMERICAL_PATH
    )
    summary = {
        "schema_version": amendment.schema_version,
        "freeze_id": freeze_manifest["freeze_id"],
        "operational": operational,
        "rate_decomposition": rate,
        "fixed_command_cases": numerical["case_count"],
        "outputs_opened_by_execute": False,
    }
    (root / EXECUTION_PATH).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def analyze(root: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze(root)
    amendment, production = load_amendment_config(
        root / CONFIG_PATH, root / PRODUCTION_CONFIG_PATH
    )
    seed_validation = validate_seed_manifests_002b(
        amendment,
        production,
        root / SEEDS_DIR,
        root / HISTORICAL_SEEDS_DIR,
    )
    validation_evidence = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    analysis_result, qc = analyze_002b(
        amendment,
        root / OPERATIONAL_PATH,
        root / RATE_PATH,
        root / RATE_EVENTS_PATH,
        root / NUMERICAL_PATH,
        seed_validation,
        validation_evidence,
        True,
        root / ANALYSIS_PATH,
        root / QC_PATH,
    )
    write_report(analysis_result, root / REPORT_PATH)
    output_paths = [
        OPERATIONAL_PATH,
        RATE_PATH,
        RATE_EVENTS_PATH,
        NUMERICAL_PATH,
        EXECUTION_PATH,
        ANALYSIS_PATH,
        QC_PATH,
        REPORT_PATH,
    ]
    run_manifest = {
        "schema_version": amendment.schema_version,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "freeze_id": freeze_manifest["freeze_id"],
        "paths": "project-relative only",
        "runtime": freeze_manifest["runtime"],
        "command_lines": [
            "uv sync --frozen --extra dev",
            "uv run python -m kri_space_autonomy.experiment_002b.workflow validate",
            "uv run python -m kri_space_autonomy.experiment_002b.workflow freeze",
            "uv run python -m kri_space_autonomy.experiment_002b.workflow run",
            "uv run python -m kri_space_autonomy.experiment_002b.workflow analyze",
        ],
        "input_hashes": freeze_manifest["frozen_artifact_hashes"],
        "output_hashes": {
            path.as_posix(): sha256_bytes((root / path).read_bytes()) for path in output_paths
        },
        "decision": analysis_result["decision"],
        "qc_overall_passed": qc["overall_passed"],
        "multi_rate_support_claim": False,
        "operational_command_period_s": 1.0,
        "confirmatory_campaign_executed": False,
        "combined_fault_study_executed": False,
    }
    first_scan = publication_boundary_scan(root)
    if not first_scan["passed"]:
        raise RuntimeError(f"publication boundary scan failed: {first_scan['matches_preview']}")
    run_manifest["publication_boundary_scan"] = first_scan
    (root / RUN_MANIFEST_PATH).write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum_paths = [*output_paths, RUN_MANIFEST_PATH]
    (root / CHECKSUMS_PATH).write_text(
        "\n".join(
            f"{sha256_bytes((root / path).read_bytes())}  {path.name}"
            for path in checksum_paths
        )
        + "\n",
        encoding="utf-8",
    )
    final_scan = publication_boundary_scan(root)
    if not final_scan["passed"]:
        preview = final_scan["matches_preview"]
        raise RuntimeError(f"final publication boundary scan failed: {preview}")
    return analysis_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 002b corrective validation workflow")
    parser.add_argument(
        "command", choices=("validate", "freeze", "verify-freeze", "run", "analyze", "release-scan")
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
    else:
        result = publication_boundary_scan(root)
        if not result["passed"]:
            raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
