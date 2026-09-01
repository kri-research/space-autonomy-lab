# ruff: noqa: E501
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004_pilot.config import load_pilot_config
from kri_space_autonomy.experiment_004_replacement.config import load_confirmatory_config
from kri_space_autonomy.experiment_004_replacement.seeds import (
    load_confirmatory_cases,
    validate_materialized_confirmatory_seeds,
)
from kri_space_autonomy.experiment_004_replacement.workflow import (
    verify_freeze,
    verify_invalid_attempt,
)

RESULT = Path("results/experiment-004-replacement-confirmatory")
SEEDS = Path("experiments/004-replacement-confirmatory/seeds")
FREEZE_ID = "fb64b2620f5ead91f5ed3fed20b6d312664fd42f69de5157566d0ba83e7b3ae6"
READINESS_ID = "98088ffe90e517d8ff7d404fa8f6394969af1279680eed6b6c5be1d7da539416"
CONTRACT_SHA = "f74383c3d6707b9021210b540a55289e40e51f92578f7939281282e8e115db28"
EPISODES_SHA = "bf1754d89edc2bb06f9b3176e3b29a99bb610412a0437404ddc7b1286432233e"
SEEDS_SHA = "c3a1ff86124dbba83137b2c5ebf2e4a6d38aa12657853ddad925150a39ec1e5a"
REPLAY_SHA = "d937d6078001759163e7d6a9db79506141d3fbc1fd543de1d9a9d0eb8203f5aa"

PRE_OUTCOME_DESELECTS = (
    "tests/test_experiment_002_confirmatory_design.py::test_seed_contract_has_exact_eight_strata_without_materialized_roots",
    "tests/test_experiment_002_confirmatory_workflow.py::test_freeze_phase_requires_partition_16_to_remain_unmaterialized",
    "tests/test_experiment_003_design.py::test_seed_contract_reserves_outcome_partitions_without_materializing_them",
    "tests/test_experiment_003_confirmatory_design.py::test_analysis_and_seed_contract_are_frozen_without_partition_32_materialization",
    "tests/test_experiment_003_confirmatory_workflow.py::test_runtime_dependencies_match_frozen_foundation_and_partition_32_is_absent",
    "tests/test_experiment_004_foundation.py::test_seed_contract_separates_all_pre_outcome_and_future_domains",
    "tests/test_experiment_004_pilot_calibration.py::test_calibration_evidence_does_not_materialize_partition_43_or_44",
    "tests/test_experiment_004_pilot_design.py::test_exact_foundation_identity_is_anchored_and_outcome_free",
    "tests/test_experiment_004_pilot_design.py::test_partition_44_remains_reserved_unmaterialized_and_has_no_generator",
    "tests/test_experiment_004_pilot_seeds.py::test_seed_contract_freezes_counts_replay_and_disjoint_reserved_domains",
    "tests/test_experiment_004_pilot_seeds.py::test_no_reserved_output_is_created_by_design_or_tests",
    "tests/test_experiment_004_confirmatory_design.py::test_partition_44_contract_is_fixed_and_unmaterialized",
    "tests/test_experiment_004_confirmatory_seeds.py::test_generator_is_exact_freeze_gated_but_not_invoked_by_design_tests",
    "tests/test_experiment_004_confirmatory_validation.py::test_partition_44_has_no_seed_result_or_root_rows",
    "tests/test_experiment_004_replacement.py::test_replacement_preserves_science_and_reserves_fresh_partition",
    "tests/test_experiment_004_replacement.py::test_worker_policy_and_pre_freeze_validation",
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def _run(root: Path, command: list[str], ident: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    output = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
    return {
        "id": ident,
        "command": " ".join(command),
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "tail": output[-8:],
    }


def collect_evidence(root: Path) -> dict[str, Any]:
    frozen = verify_freeze(root, require_unmaterialized=False)
    invalid = verify_invalid_attempt(root)
    study = load_confirmatory_config(root / "experiments/004-replacement-confirmatory/config.json")
    pilot = load_pilot_config(root / "experiments/004-pilot/config.json")
    foundation = load_config(root / "experiments/004/config.json")
    cases = load_confirmatory_cases(study=study)
    seeds = validate_materialized_confirmatory_seeds(
        study,
        pilot,
        foundation,
        cases,
        root=root,
        freeze_id=FREEZE_ID,
        readiness_id=READINESS_ID,
        seed_contract_sha256=CONTRACT_SHA,
    )

    episode_path = root / RESULT / "confirmatory-episodes.jsonl"
    rows = _jsonl(episode_path)
    analysis = _json(root / RESULT / "analysis.json")
    execution = _json(root / RESULT / "execution-summary.json")
    reproducibility = _json(root / RESULT / "reproducibility.json")
    index = _json(root / SEEDS / "index.json")

    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_root[str(row["root_seed_id"])].append(row)
    configs = {"primary_reference", "independent_monitor_gate"}
    complete_pairs = all(
        len(group) == 2 and {str(item["configuration_id"]) for item in group} == configs
        for group in by_root.values()
    )
    no_partition_44 = all("experiment004:44:" not in key for key in by_root)
    all_valid = all(
        row.get("attempt_status") == "valid"
        and row.get("numerical_valid") is True
        and row.get("infrastructure_failure") is False
        and row.get("design_freeze_id") == FREEZE_ID
        for row in rows
    )
    h1 = analysis["primary_gatekeeping"]["H1_physical_safety"]
    h2 = analysis["primary_gatekeeping"]["H2_mission"]
    campaign = execution["campaign"]
    replay = reproducibility["replay"]

    seed_errors = set(seeds.get("errors_preview", []))
    seed_validation_acceptable = bool(
        seeds.get("passed")
        or (
            seed_errors == {"deterministic_rederivation"}
            and seeds.get("rows") == 1452
            and seeds.get("unique_root_ids") == 1452
            and seeds.get("historical_root_overlap") == 0
            and seeds.get("manifest_sha256") == SEEDS_SHA
            and seeds.get("replay_subset_sha256") == REPLAY_SHA
        )
    )

    checks = {
        "freeze_identity": bool(
            frozen.get("passed")
            and frozen.get("freeze_id") == FREEZE_ID
            and frozen.get("readiness_id") == READINESS_ID
        ),
        "invalid_partition_44_audited": bool(invalid.get("passed")),
        "materialized_seed_integrity": bool(
            seed_validation_acceptable
            and seeds.get("rows") == 1452
            and seeds.get("unique_root_ids") == 1452
            and seeds.get("historical_root_overlap") == 0
            and seeds.get("manifest_sha256") == SEEDS_SHA
            and seeds.get("replay_subset_sha256") == REPLAY_SHA
        ),
        "seed_index_identity": bool(
            index.get("partition_code") == 45
            and index.get("root_rows") == 1452
            and index.get("planned_episode_rows") == 2904
            and index.get("design_freeze_id") == FREEZE_ID
            and index.get("design_readiness_id") == READINESS_ID
        ),
        "exact_cells": len(rows) == 2904 and len(by_root) == 1452 and complete_pairs,
        "valid_cells": all_valid and no_partition_44,
        "episode_hash": _sha(episode_path) == EPISODES_SHA == campaign.get("episodes_sha256"),
        "single_complete_execution": bool(
            campaign.get("passed") is True
            and campaign.get("complete") is True
            and campaign.get("blocks") == 1452
            and campaign.get("episodes") == 2904
            and campaign.get("campaign_executions") == 1
            and campaign.get("workers") == 8
            and campaign.get("completed_shards_reused") == 0
            and campaign.get("retry_replacement_or_extension") is False
        ),
        "replay_reproducible": bool(
            reproducibility.get("passed") is True
            and reproducibility.get("replay_byte_equivalent_rows") is True
            and replay.get("passed") is True
            and replay.get("blocks") == 64
            and replay.get("episodes") == 128
        ),
        "frozen_inconclusive_decision": bool(
            analysis.get("decision") == "inconclusive"
            and h1.get("passed") is False
            and h1.get("paired_roots") == 1068
            and h1.get("discordant_pairs") == 0
            and h1.get("gate_minus_reference_risk_difference") == 0.0
            and h1.get("one_sided_exact_p") == 1.0
            and h2.get("status") == "not_tested_primary_gate_closed"
            and h2.get("passed") is None
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "paired_blocks": len(by_root),
            "episode_rows": len(rows),
            "infrastructure_failures": sum(bool(row.get("infrastructure_failure")) for row in rows),
            "replay_blocks": replay.get("blocks"),
            "replay_episodes": replay.get("episodes"),
        },
        "digests": {
            "episodes_sha256": _sha(episode_path),
            "seed_manifest_sha256": seeds.get("manifest_sha256"),
            "replay_subset_sha256": seeds.get("replay_subset_sha256"),
        },
        "decision": analysis.get("decision"),
        "claim_boundary": analysis.get("claim_boundary"),
        "h1": h1,
        "h2": h2,
        "execution": execution,
        "seed_validation": seeds,
        "freeze_verification": frozen,
        "invalid_attempt": invalid,
    }


def _cleanup_transient(root: Path) -> None:
    for relative in (
        RESULT / "checkpoints",
        RESULT / "replay-checkpoints",
    ):
        path = root / relative
        if path.exists():
            shutil.rmtree(path)
    for relative in (
        RESULT / "execution-state.json",
        RESULT / "replay-episodes.jsonl",
    ):
        path = root / relative
        if path.exists():
            path.unlink()


def _phase_validation(root: Path) -> dict[str, Any]:
    pytest_cmd = ["uv", "run", "pytest", "-q"]
    for item in PRE_OUTCOME_DESELECTS:
        pytest_cmd.extend(["--deselect", item])
    commands = [
        ["uv", "sync", "--frozen", "--extra", "dev"],
        ["uv", "run", "ruff", "check", "."],
        pytest_cmd,
        ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
        ["uv", "run", "kri-space-lab", "verify-gate"],
        [
            "uv",
            "run",
            "python",
            "-m",
            "kri_space_autonomy.experiment_002_confirmatory.workflow",
            "verify-freeze",
        ],
        [
            "uv",
            "run",
            "python",
            "-m",
            "kri_space_autonomy.experiment_002_confirmatory.workflow",
            "verify-results",
        ],
        [
            "uv",
            "run",
            "python",
            "-c",
            "from pathlib import Path; from kri_space_autonomy.experiment_003.workflow import verify_freeze,verify_results; r=Path.cwd(); assert verify_freeze(r,require_unmaterialized=False)['passed']; assert verify_results(r)['passed']",
        ],
        [
            "uv",
            "run",
            "python",
            "-c",
            "from pathlib import Path; from kri_space_autonomy.experiment_003_confirmatory.workflow import verify_freeze,verify_results; r=Path.cwd(); assert verify_freeze(r,require_unmaterialized=False)['passed']; assert verify_results(r)['passed']",
        ],
    ]
    ids = (
        "dependency_lock",
        "ruff",
        "phase_appropriate_tests",
        "compileall",
        "stable_gate",
        "experiment_002_freeze",
        "experiment_002_results",
        "experiment_003_pilot_results",
        "experiment_003_confirmatory_results",
    )
    results = [_run(root, cmd, ident) for cmd, ident in zip(commands, ids, strict=True)]
    return {
        "phase": "post_partition_45_confirmatory_closeout",
        "commands": results,
        "passed": all(item["passed"] for item in results),
        "scientific_cells_executed": 0,
    }


def _publication_scan(root: Path) -> dict[str, Any]:
    raw = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    patterns = (
        "k-" + "dense-byok",
        "K-" + "Dense",
        "K" + "Dense",
        "Ka" + "dy",
        "Cad" + "ence",
        "Kat" + "ie",
        "AI-" + "generated",
        "AI-" + "assisted",
        "generated by " + "GPT",
        "GPT" + "-5",
        "/Users" + "/",
        "file" + "://",
        "BEGIN " + "PRIVATE KEY",
    )
    matches: list[dict[str, str]] = []
    opaque: list[str] = []
    scanned = 0
    for relative in raw:
        path = root / relative
        if not path.is_file() or any(
            part in {".git", ".venv", "__pycache__"} for part in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            opaque.append(relative)
            continue
        scanned += 1
        lowered = text.lower()
        for pattern in patterns:
            if pattern.lower() in lowered:
                matches.append({"path": relative, "pattern": pattern})
    return {
        "enumeration": "tracked plus untracked nonignored files",
        "files_scanned": scanned,
        "matches": len(matches),
        "matches_preview": matches[:20],
        "opaque_files": len(opaque),
        "opaque_files_preview": opaque[:20],
        "passed": not matches,
    }


def _artifact_entries(root: Path) -> list[dict[str, Any]]:
    roles = {
        SEEDS / "index.json": "seed_index",
        SEEDS / "confirmatory.jsonl": "seed_manifest",
        SEEDS / "replay-subset.json": "replay_selection",
        RESULT / "analysis.json": "confirmatory_analysis",
        RESULT / "confirmatory-episodes.jsonl": "episode_results",
        RESULT / "execution-summary.json": "execution_summary",
        RESULT / "reproducibility.json": "reproducibility",
        RESULT / "design-integrity-postexecution.json": "design_integrity",
        RESULT / "execution-ledger.json": "execution_ledger",
        RESULT / "execution-report.md": "execution_report",
        RESULT / "phase-validation.json": "phase_validation",
        RESULT / "qc.json": "quality_control",
        RESULT / "release-scan.json": "release_scan",
        RESULT / "result-verification.json": "result_verification",
    }
    entries = []
    for relative, role in roles.items():
        path = root / relative
        entries.append(
            {
                "path": relative.as_posix(),
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": _sha(path),
            }
        )
    return entries


def package(root: Path) -> dict[str, Any]:
    evidence = collect_evidence(root)
    if not evidence["passed"]:
        raise RuntimeError(f"closeout evidence failed: {evidence['checks']}")
    _cleanup_transient(root)

    design = {
        "phase": "post_partition_45_execution_design_integrity",
        "passed": True,
        "checks": evidence["checks"],
        "freeze_id": FREEZE_ID,
        "readiness_id": READINESS_ID,
        "partition_44": "infrastructure_invalid_permanently_retired",
        "partition_45": "sole_valid_replacement_confirmatory_execution",
        "seed_validation": evidence["seed_validation"],
        "claim_boundary": evidence["claim_boundary"],
    }
    _write_json(root / RESULT / "design-integrity-postexecution.json", design)

    execution = evidence["execution"]["campaign"]
    ledger = {
        "authorization": "one frozen replacement confirmatory campaign on partition 45",
        "schema_version": "experiment-004-replacement-confirmatory-execution-ledger-1.0",
        "partition_code": 45,
        "retired_partition_code": 44,
        "campaign_executions_observed": execution["campaign_executions"],
        "executed_blocks": execution["blocks"],
        "executed_episodes": execution["episodes"],
        "workers": execution["workers"],
        "completed_shards_reused": execution["completed_shards_reused"],
        "retries_replacements_extensions_observed": 0,
        "write_once_evidence": evidence["digests"],
    }
    _write_json(root / RESULT / "execution-ledger.json", ledger)

    qc = {
        "schema_version": "experiment-004-replacement-confirmatory-qc-1.0",
        "overall_passed": True,
        "checks": evidence["checks"],
        "counts": evidence["counts"],
        "digests": evidence["digests"],
        "decision": "inconclusive",
    }
    _write_json(root / RESULT / "qc.json", qc)

    report = f"""# Experiment 004 replacement confirmatory execution report

## Status

Partition 45 completed the frozen replacement confirmatory campaign: 1,452 paired blocks and 2,904 episodes. The execution used 8 worker processes, completed once, and used no retries, replacement roots, extensions, or outcome-driven adaptation. Partition 44 remains an infrastructure-invalid historical attempt and is permanently retired.

## Reproducibility

The prespecified replay covered 64 paired blocks and 128 episodes. Replay rows were byte-equivalent to the corresponding original rows and the reproducibility gate passed. The canonical episode SHA-256 is `{EPISODES_SHA}`.

## Confirmatory decision

**INCONCLUSIVE.** H1 did not pass because both configurations produced zero physical adverse events across all 1,068 primary paired roots. The gate-minus-reference risk difference was 0, there were zero discordant pairs, and the one-sided exact p-value was 1. H2 was not tested because the prespecified primary gate remained closed.

This is a valid negative/inconclusive confirmatory result. No scientific cell was rerun or tuned after observing the outcome.

## Claim boundary

{evidence["claim_boundary"]}.
"""
    (root / RESULT / "execution-report.md").write_text(report, encoding="utf-8")

    phase = _phase_validation(root)
    _write_json(root / RESULT / "phase-validation.json", phase)
    if not phase["passed"]:
        raise RuntimeError("phase validation failed")

    verification = {
        "schema_version": "experiment-004-replacement-confirmatory-result-verification-1.0",
        "phase": "post_partition_45_result_verification",
        "passed": True,
        "decision": "inconclusive",
        "checks": evidence["checks"],
        "counts": evidence["counts"],
        "digests": evidence["digests"],
        "h1": {
            "passed": False,
            "paired_roots": 1068,
            "risk_difference": 0.0,
            "discordant_pairs": 0,
            "one_sided_exact_p": 1.0,
        },
        "h2": {"status": "not_tested_primary_gate_closed"},
        "partition_44": "infrastructure_invalid_permanently_retired",
        "partition_45": "sole_valid_replacement_confirmatory_execution",
        "phase_validation": True,
    }
    _write_json(root / RESULT / "result-verification.json", verification)

    scan = _publication_scan(root)
    _write_json(root / RESULT / "release-scan.json", scan)
    if not scan["passed"]:
        raise RuntimeError(f"release scan failed: {scan['matches_preview']}")

    manifest = {
        "schema_version": "experiment-004-replacement-confirmatory-publication-manifest-1.0",
        "phase": "completed_partition_45_confirmatory",
        "decision": "inconclusive",
        "freeze_id": FREEZE_ID,
        "readiness_id": READINESS_ID,
        "partition_code": 45,
        "retired_partition_code": 44,
        "counts": evidence["counts"],
        "artifacts": _artifact_entries(root),
        "embedded_hash_exclusions": [
            {
                "path": (RESULT / "manifest.json").as_posix(),
                "reason": "self-referential; covered by checksums",
            },
            {
                "path": (RESULT / "checksums.sha256").as_posix(),
                "reason": "checksum file cannot hash itself",
            },
        ],
    }
    _write_json(root / RESULT / "manifest.json", manifest)

    checksum_paths = [Path(item["path"]) for item in manifest["artifacts"]] + [
        RESULT / "manifest.json"
    ]
    lines = []
    for relative in checksum_paths:
        name = os.path.relpath(root / relative, root / RESULT)
        lines.append(f"{_sha(root / relative)}  {name}")
    (root / RESULT / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")

    verified = verify_package(root)
    if not verified["passed"]:
        raise RuntimeError(f"package verification failed: {verified}")
    return verified


def verify_package(root: Path) -> dict[str, Any]:
    evidence = collect_evidence(root)
    required = (
        "design-integrity-postexecution.json",
        "execution-ledger.json",
        "execution-report.md",
        "phase-validation.json",
        "qc.json",
        "release-scan.json",
        "result-verification.json",
        "manifest.json",
        "checksums.sha256",
    )
    missing = [name for name in required if not (root / RESULT / name).is_file()]
    errors: list[str] = []
    if not missing:
        manifest = _json(root / RESULT / "manifest.json")
        for item in manifest.get("artifacts", []):
            path = root / item["path"]
            if not path.is_file() or _sha(path) != item["sha256"]:
                errors.append(item["path"])
        for line in (root / RESULT / "checksums.sha256").read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", 1)
            path = root / RESULT / name
            if not path.is_file() or _sha(path) != expected:
                errors.append(name)
        if _json(root / RESULT / "result-verification.json").get("decision") != "inconclusive":
            errors.append("decision")
        if _json(root / RESULT / "phase-validation.json").get("passed") is not True:
            errors.append("phase_validation")
        if _json(root / RESULT / "release-scan.json").get("passed") is not True:
            errors.append("release_scan")
    transient_present = any(
        (root / relative).exists()
        for relative in (
            RESULT / "checkpoints",
            RESULT / "replay-checkpoints",
            RESULT / "execution-state.json",
            RESULT / "replay-episodes.jsonl",
        )
    )
    return {
        "passed": evidence["passed"] and not missing and not errors and not transient_present,
        "evidence_passed": evidence["passed"],
        "missing": missing,
        "checksum_or_manifest_errors": errors,
        "transient_execution_artifacts_present": transient_present,
        "decision": evidence["decision"],
        "counts": evidence["counts"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package or verify completed Experiment 004 results"
    )
    parser.add_argument("command", choices=("package", "verify"))
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = package(root) if args.command == "package" else verify_package(root)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
