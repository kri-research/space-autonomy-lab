from __future__ import annotations

import argparse
import io
import json
import platform
import subprocess
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .analysis import analyze_pilot, write_markdown_report
from .config import load_config
from .policy import FrozenPolicy, policy_manifest_identity, train_and_freeze_policy
from .qc import build_qc_report, write_qc_subsets
from .runner import calibrate_recovery_corridor, load_recovery_corridor, run_pilot
from .seeds import canonical_json, sha256_bytes, write_seed_manifests

CONFIG_PATH = Path("experiments/002/config.json")
SEEDS_DIR = Path("experiments/002/seeds")
POLICY_PATH = Path("artifacts/experiment-002/policy-primary.npz")
POLICY_MANIFEST_PATH = Path("artifacts/experiment-002/policy-primary.manifest.json")
CORRIDOR_PATH = Path("experiments/002/recovery-corridor.json")
SUBSETS_PATH = Path("experiments/002/qc-subsets.json")
FREEZE_PATH = Path("experiments/002/freeze-manifest.json")
VALIDATION_PATH = Path("experiments/002/validation-evidence.json")
EPISODES_PATH = Path("results/experiment-002/episodes.jsonl")
QC_PATH = Path("results/experiment-002/qc.json")
ANALYSIS_PATH = Path("results/experiment-002/analysis.json")
REPORT_PATH = Path("results/experiment-002/report.md")
RUN_MANIFEST_PATH = Path("results/experiment-002/run-manifest.json")
CHECKSUMS_PATH = Path("results/experiment-002/SHA256SUMS")

SOURCE_GLOBS = (
    "src/**/*.py",
    "tests/**/*.py",
    "docs/experiment-002.md",
    "experiments/002/preregistration.md",
    "experiments/002/config.json",
    "experiments/002/deviations.md",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)


def _relative_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _file_hashes(root: Path, files: list[Path]) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes()) for path in files}


def _tree_hash(hashes: dict[str, str]) -> str:
    return sha256_bytes(canonical_json(hashes))


def _git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _numpy_math_identity() -> dict[str, Any]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        np.show_config()
    text = buffer.getvalue()
    selected = []
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if any(token in lowered for token in ("openblas", "accelerate", "lapack", "blas")):
            if not stripped.startswith(("lib directory", "include directory")):
                selected.append(stripped)
    return {
        "numpy_version": np.__version__,
        "blas_lapack_summary": selected[:20],
    }


def freeze(root: Path) -> dict[str, Any]:
    config = load_config(root / CONFIG_PATH)
    validation = json.loads((root / VALIDATION_PATH).read_text(encoding="utf-8"))
    if not validation.get("passed"):
        raise RuntimeError("pre-freeze validation evidence is not passing")
    source_hashes = _file_hashes(root, _relative_files(root))
    source_tree_hash = _tree_hash(source_hashes)
    commit = _git_output(root, "rev-parse", "HEAD")
    status = _git_output(root, "status", "--short")
    diff_hash = sha256_bytes(_git_output(root, "diff", "--binary").encode())
    source_identity = {
        "git_commit": commit,
        "working_tree_dirty": bool(status),
        "working_tree_diff_sha256": diff_hash,
        "source_tree_sha256": source_tree_hash,
        "paths": "project-relative only",
    }

    write_seed_manifests(config, root / SEEDS_DIR)
    train_and_freeze_policy(
        config,
        root / POLICY_PATH,
        root / POLICY_MANIFEST_PATH,
        source_identity,
    )
    policy = FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, config)
    config_hash = sha256_bytes((root / CONFIG_PATH).read_bytes())
    corridor = calibrate_recovery_corridor(config, policy, config_hash, root / CORRIDOR_PATH)
    write_qc_subsets(config, root / SUBSETS_PATH)

    frozen_paths = [
        CONFIG_PATH,
        Path("pyproject.toml"),
        Path("uv.lock"),
        Path(".python-version"),
        Path("docs/experiment-002.md"),
        Path("experiments/002/preregistration.md"),
        Path("experiments/002/deviations.md"),
        VALIDATION_PATH,
        POLICY_PATH,
        POLICY_MANIFEST_PATH,
        CORRIDOR_PATH,
        SUBSETS_PATH,
        *sorted(SEEDS_DIR.glob("*")),
    ]
    artifact_hashes = {
        path.as_posix(): sha256_bytes((root / path).read_bytes()) for path in frozen_paths
    }
    unsigned = {
        "schema_version": config.schema_version,
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "9,600-episode feasibility/design-validation pilot only",
        "confirmatory_campaign_executed": False,
        "source_identity": source_identity,
        "source_file_hashes": source_hashes,
        "source_tree_sha256": source_tree_hash,
        "artifact_hashes": artifact_hashes,
        "policy_identity": policy_manifest_identity(root / POLICY_MANIFEST_PATH),
        "recovery_corridor_sha256": corridor.calibration_sha256,
        "canonical_design": {
            "arms": ["R", "D", "PS", "PD"],
            "strata": [
                "P0 nominal",
                "P1 primary navigation (200 bias/200 dropout)",
                "P2 monitor-only (200 bias/200 dropout)",
                "P3 shared-cause navigation (200 bias/200 dropout)",
                "P4 persistent model upset",
                "P5 actuator degradation",
            ],
            "fixed_stratum_weight": "1/6",
            "seeds_per_stratum": 400,
            "blocks": 2400,
            "episodes": 9600,
        },
        "frozen_items": [
            "policy architecture, ordered features, missing-value rules and action transform",
            "training objective, optimizer budget and validation-only model-selection rule",
            "recovery precedence and calibration corridor",
            "seed manifests, named stream derivation and QC subsets",
            "pilot progression criteria and append-only amendment rules",
            "generator, endpoints, analysis and dependency lock",
        ],
        "runtime": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "os": platform.system(),
            "architecture": platform.machine(),
            **_numpy_math_identity(),
        },
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
        raise RuntimeError("freeze manifest self-hash mismatch")
    manifest["freeze_id"] = freeze_id
    errors = []
    for relative, expected in manifest["source_file_hashes"].items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    for relative, expected in manifest["artifact_hashes"].items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    if errors:
        raise RuntimeError(f"frozen input hash drift: {errors[:10]}")
    return manifest


def execute(root: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze(root)
    config = load_config(root / CONFIG_PATH)
    policy = FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, config)
    corridor = load_recovery_corridor(root / CORRIDOR_PATH)
    config_hash = freeze_manifest["artifact_hashes"][CONFIG_PATH.as_posix()]
    return run_pilot(
        config,
        policy,
        corridor,
        config_hash,
        root / EPISODES_PATH,
    )


def analyze(root: Path) -> dict[str, Any]:
    freeze_manifest = verify_freeze(root)
    config = load_config(root / CONFIG_PATH)
    policy = FrozenPolicy.load(root / POLICY_PATH, root / POLICY_MANIFEST_PATH, config)
    corridor = load_recovery_corridor(root / CORRIDOR_PATH)
    config_hash = freeze_manifest["artifact_hashes"][CONFIG_PATH.as_posix()]
    qc = build_qc_report(
        root / EPISODES_PATH,
        root / SEEDS_DIR / "pilot.jsonl",
        root / SUBSETS_PATH,
        root / VALIDATION_PATH,
        config,
        policy,
        corridor,
        config_hash,
        root / QC_PATH,
    )
    metadata = {
        "freeze_id": freeze_manifest["freeze_id"],
        "git_commit": freeze_manifest["source_identity"]["git_commit"],
        "source_tree_sha256": freeze_manifest["source_tree_sha256"],
        "config_sha256": config_hash,
        "policy_model_identity": policy.model_identity,
        "policy_artifact_sha256": freeze_manifest["policy_identity"]["artifact_sha256"],
        "seed_manifest_sha256": freeze_manifest["artifact_hashes"][
            "experiments/002/seeds/pilot.jsonl"
        ],
        "episodes_sha256": sha256_bytes((root / EPISODES_PATH).read_bytes()),
        "analysis_code_sha256": freeze_manifest["source_file_hashes"][
            "src/kri_space_autonomy/experiment_002/analysis.py"
        ],
    }
    analysis_result = analyze_pilot(
        root / EPISODES_PATH,
        config,
        metadata,
        qc,
        root / ANALYSIS_PATH,
    )
    write_markdown_report(analysis_result, root / REPORT_PATH)
    run_manifest = {
        "schema_version": config.schema_version,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "command_lines": [
            "uv sync --frozen --extra dev",
            "uv run python -m kri_space_autonomy.experiment_002.workflow freeze",
            "uv run python -m kri_space_autonomy.experiment_002.workflow run",
            "uv run python -m kri_space_autonomy.experiment_002.workflow analyze",
        ],
        "paths": "project-relative only",
        "freeze_id": freeze_manifest["freeze_id"],
        "runtime": freeze_manifest["runtime"],
        "hashes": {
            **metadata,
            "qc_sha256": sha256_bytes((root / QC_PATH).read_bytes()),
            "analysis_sha256": sha256_bytes((root / ANALYSIS_PATH).read_bytes()),
            "report_sha256": sha256_bytes((root / REPORT_PATH).read_bytes()),
        },
        "qc_overall_passed": qc["overall_passed"],
        "progression": analysis_result["progression"],
        "confirmatory_campaign_executed": False,
    }
    (root / RUN_MANIFEST_PATH).write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum_paths = [
        EPISODES_PATH,
        QC_PATH,
        ANALYSIS_PATH,
        REPORT_PATH,
        RUN_MANIFEST_PATH,
    ]
    checksum_lines = [
        (
            f"{sha256_bytes((root / path).read_bytes())}  "
            f"{path.relative_to(Path('results/experiment-002')).as_posix()}"
        )
        for path in checksum_paths
    ]
    (root / CHECKSUMS_PATH).write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return analysis_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 002 frozen pilot workflow")
    parser.add_argument("command", choices=("freeze", "verify-freeze", "run", "analyze"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "freeze":
        result = freeze(root)
    elif args.command == "verify-freeze":
        result = verify_freeze(root)
    elif args.command == "run":
        result = execute(root)
    else:
        result = analyze(root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
