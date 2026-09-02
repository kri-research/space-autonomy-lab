from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_005.workflow import (
    dependency_runtime_identity,
    verify_historical_campaigns,
)
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    CASE_IDS,
    CONFIGURATIONS,
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import canonical_json
from kri_space_autonomy.experiment_005_transfer_pilot.validation import (
    information_boundary,
    partition_53_inert,
    publication_privacy,
)

FOUNDATION_FREEZE_ID = "921c481726d6f078621ff3a355a7803af803bdc61a8a2da07ffb974a433b3be8"
FOUNDATION_READINESS_ID = "9ec734543fd3580e9a2990a16dc56747a0f75334f76bd2c7ae1fdc3647732e67"
DESIGN_FREEZE_ID = "3fa9fd6e9e4d3146af6495c07599ed792cfb52ce16e90d0dca234ed64295be8b"
DESIGN_READINESS_ID = "ebc98c9eb9b14d2dc85351d68ca3c5c84791e050f2be038c7fdd9067ef6ce2f3"
SEED_MANIFEST_SHA256 = "0c1b50b37f2e588d263f958ed12666e0cf547ad114736b30342bb445219f525e"
REPLAY_SUBSET_SHA256 = "d1b890c268425d62fcde88af39677a121521a6e75c9396b57f129efffbf2c79a"
CAMPAIGN_SHA256 = "90ab09451bbe9d336b18212bfecb1828ef0fbc0bbc5181eb4e7d9726a6d227a4"
FAILURE_SHA256 = "50ece4ca8fbc71e0049c47b104b541bc32d93a8be1d176d36bce70c97ce2b2b2"
CAMPAIGN_ID = "7ffec887e937af837c3eef360cc861bd3fe456445e7210f7e6bd032e83b2fb4d"
FAILURE_ID = "07afccd053367767e5aa7b99db22974ee9722b492aa6589a592e945cee9f0474"

DESIGN_DIR = Path("experiments/005-transfer-pilot")
RESULT_DIR = Path("results/experiment-005-transfer-pilot")
SEED_DIR = RESULT_DIR / "materialized-seeds"
EVIDENCE_DIR = RESULT_DIR / "invalid-attempt-evidence"
CAMPAIGN_PATH = EVIDENCE_DIR / "campaign.json"
FAILURE_PATH = EVIDENCE_DIR / "terminal-failure.json"
AUDIT_PATH = RESULT_DIR / "invalid-attempt-audit.json"
LEDGER_PATH = RESULT_DIR / "execution-ledger.json"
ANALYSIS_PATH = RESULT_DIR / "analysis.json"
QC_PATH = RESULT_DIR / "qc.json"
REPRODUCIBILITY_PATH = RESULT_DIR / "reproducibility.json"
PHASE_PATH = RESULT_DIR / "phase-validation.json"
RELEASE_SCAN_PATH = RESULT_DIR / "release-scan.json"
VERIFICATION_PATH = RESULT_DIR / "result-verification.json"
REPORT_PATH = RESULT_DIR / "execution-report.md"
MANIFEST_PATH = RESULT_DIR / "manifest.json"
CHECKSUMS_PATH = RESULT_DIR / "checksums.sha256"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value) + b"\n":
        raise RuntimeError(f"noncanonical evidence: {path.name}")
    return value


def _self_hashed(path: Path, field: str, expected: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    computed = hashlib.sha256(canonical_json(value)).hexdigest()
    if identity != computed or identity != expected:
        raise RuntimeError(f"frozen identity mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _write_text(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(value)


def frozen_identity(root: Path) -> dict[str, Any]:
    foundation = _self_hashed(
        root / "experiments/005/freeze-manifest.json",
        "freeze_id",
        FOUNDATION_FREEZE_ID,
    )
    foundation_readiness = _self_hashed(
        root / "experiments/005/readiness.json",
        "readiness_id",
        FOUNDATION_READINESS_ID,
    )
    design = _self_hashed(
        root / DESIGN_DIR / "freeze-manifest.json",
        "freeze_id",
        DESIGN_FREEZE_ID,
    )
    design_readiness = _self_hashed(
        root / DESIGN_DIR / "readiness.json",
        "readiness_id",
        DESIGN_READINESS_ID,
    )
    mismatches: list[str] = []
    for manifest in (foundation, design):
        for relative, expected in manifest["source_file_hashes"].items():
            path = root / relative
            if not path.is_file() or _sha(path) != expected:
                mismatches.append(relative)
    return {
        "passed": not mismatches,
        "foundation_freeze_id": foundation["freeze_id"],
        "foundation_readiness_id": foundation_readiness["readiness_id"],
        "design_freeze_id": design["freeze_id"],
        "design_readiness_id": design_readiness["readiness_id"],
        "source_files_verified": len(
            set(foundation["source_file_hashes"]) | set(design["source_file_hashes"])
        ),
        "source_mismatches": sorted(set(mismatches)),
    }


def seed_materialization(root: Path) -> dict[str, Any]:
    pilot = load_pilot_config(root=root)
    cases = load_case_matrix(root / DESIGN_DIR / "case-matrix.json")
    index = json.loads((root / SEED_DIR / "index.json").read_text(encoding="utf-8"))
    manifest_path = root / SEED_DIR / "pilot.jsonl"
    replay_path = root / SEED_DIR / "replay-subset.json"
    raw_rows = manifest_path.read_bytes().splitlines()
    rows = [json.loads(line) for line in raw_rows]
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    expected_order = [
        (case_id, replicate) for case_id in CASE_IDS for replicate in range(2)
    ]
    roots = [str(row.get("root_seed_id")) for row in rows]
    order_balanced = all(
        {
            tuple(row["configuration_run_order"])
            for row in rows
            if row["case_id"] == case_id
        }
        == {
            CONFIGURATIONS,
            tuple(reversed(CONFIGURATIONS)),
        }
        for case_id in CASE_IDS
    )
    expected_replay = [
        row["root_seed_id"] for row in rows if row.get("replicate") == 0
    ]
    checks = {
        "index_identity": bool(
            index.get("partition_code") == 52
            and index.get("root_rows") == 20
            and index.get("planned_episode_rows") == 40
            and index.get("generator_invocations") == 1
            and index.get("design_freeze_id") == DESIGN_FREEZE_ID
            and index.get("design_readiness_id") == DESIGN_READINESS_ID
            and index.get("replacement_extension_or_count_drift_allowed") is False
        ),
        "manifest_hash": _sha(manifest_path) == SEED_MANIFEST_SHA256,
        "replay_hash": _sha(replay_path) == REPLAY_SUBSET_SHA256,
        "canonical_rows": bool(
            len(rows) == 20
            and all(
                raw == canonical_json(row)
                for raw, row in zip(raw_rows, rows, strict=True)
            )
        ),
        "deterministic_order": [
            (row.get("case_id"), row.get("replicate")) for row in rows
        ]
        == expected_order,
        "unique_partition_roots": bool(
            len(roots) == len(set(roots)) == 20
            and all(root_id.startswith("experiment005:52:") for root_id in roots)
        ),
        "freeze_binding": all(
            row.get("design_freeze_id") == DESIGN_FREEZE_ID for row in rows
        ),
        "within_case_order_balance": order_balanced,
        "replay_selection": bool(
            replay.get("root_seed_ids") == expected_replay
            and replay.get("expected_blocks") == 10
            and replay.get("expected_episodes") == 20
        ),
        "frozen_counts": bool(
            pilot.pilot_blocks == 20
            and pilot.pilot_episodes == 40
            and pilot.replay_blocks == 10
            and pilot.replay_episodes == 20
            and len(cases) == 10
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "manifest_sha256": _sha(manifest_path),
        "replay_subset_sha256": _sha(replay_path),
        "root_rows": len(rows),
        "unique_roots": len(set(roots)),
        "planned_episode_rows": index.get("planned_episode_rows"),
        "generator_invocations": index.get("generator_invocations"),
    }


def failed_campaign(root: Path) -> dict[str, Any]:
    campaign_path = root / CAMPAIGN_PATH
    failure_path = root / FAILURE_PATH
    campaign = _canonical_file(campaign_path)
    failure = _canonical_file(failure_path)
    cell_shards = list((root / RESULT_DIR).glob("**/cell-*.json"))
    assembled = root / RESULT_DIR / "pilot-episodes.jsonl"
    transient_paths = [
        path.relative_to(root).as_posix()
        for path in (root / RESULT_DIR).glob("**/*")
        if path.name.endswith(".tmp") or path.name == ".campaign.lock"
    ]
    checks = {
        "campaign_hash": _sha(campaign_path) == CAMPAIGN_SHA256,
        "failure_hash": _sha(failure_path) == FAILURE_SHA256,
        "campaign_identity": bool(
            campaign.get("campaign_id") == CAMPAIGN_ID
            and campaign.get("partition_code") == 52
            and campaign.get("cell_count") == 20
            and campaign.get("maximum_retries") == 0
            and campaign.get("maximum_replacement_roots") == 0
            and campaign.get("failure_semantics")
            == "write immutable terminal failure record; never retry failed cell"
        ),
        "terminal_failure_identity": bool(
            failure.get("failure_id") == FAILURE_ID
            and failure.get("campaign_id") == CAMPAIGN_ID
            and failure.get("cell_index") == 0
            and failure.get("root_seed_id") == "experiment005:52:000:0000"
            and failure.get("attempt_number") == 1
            and failure.get("execution_began") is True
            and failure.get("exception_class") == "BrokenProcessPool"
            and failure.get("terminal_state") == "failed_no_retry_or_replacement"
        ),
        "no_completed_cells": len(cell_shards) == 0,
        "no_assembled_episode_output": not assembled.exists(),
        "no_transient_checkpoint_files": not transient_paths,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "campaign_sha256": _sha(campaign_path),
        "terminal_failure_sha256": _sha(failure_path),
        "campaign_id": campaign.get("campaign_id"),
        "failure_id": failure.get("failure_id"),
        "completed_blocks": 0,
        "durable_episode_rows": 0,
        "terminal_failures": 1,
        "transient_paths": transient_paths,
    }


def _run(root: Path, command: list[str], label: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    return {
        "id": label,
        "command": " ".join(command),
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
    }


def phase_checks(root: Path) -> dict[str, Any]:
    commands = [
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(
            root,
            [
                "uv",
                "run",
                "pytest",
                "-q",
                "--ignore=tests/test_experiment_005_transfer_pilot_closeout.py",
            ],
            "phase_appropriate_repository_tests",
        ),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "stable_gate"),
        _run(root, ["git", "diff", "--check"], "diff_whitespace"),
    ]
    return {
        "passed": all(item["passed"] for item in commands),
        "phase": "invalid_partition_52_terminal_infrastructure_closeout",
        "checks": commands,
        "e005_pre_materialization_tests_deselected": 5,
        "historical_phase_policy_applied": True,
        "reason": (
            "their absence assertions are false after the recorded write-once "
            "materialization"
        ),
    }


def _artifact_inventory(root: Path) -> list[dict[str, str]]:
    excluded = {MANIFEST_PATH, CHECKSUMS_PATH}
    paths = sorted(
        (
            path
            for path in (root / RESULT_DIR).rglob("*")
            if path.is_file() and path.relative_to(root) not in excluded
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    return [
        {"path": path.relative_to(root).as_posix(), "sha256": _sha(path)}
        for path in paths
    ]


def close(root: Path) -> dict[str, Any]:
    expected_new = (
        AUDIT_PATH,
        LEDGER_PATH,
        ANALYSIS_PATH,
        QC_PATH,
        REPRODUCIBILITY_PATH,
        PHASE_PATH,
        RELEASE_SCAN_PATH,
        VERIFICATION_PATH,
        REPORT_PATH,
        MANIFEST_PATH,
        CHECKSUMS_PATH,
    )
    present = [path.as_posix() for path in expected_new if (root / path).exists()]
    if present:
        raise RuntimeError(f"refusing to overwrite closeout artifact: {present[0]}")
    seeds = seed_materialization(root)
    failure = failed_campaign(root)
    frozen = frozen_identity(root)
    historical = verify_historical_campaigns(root)
    pilot = load_pilot_config(root=root)
    p53 = partition_53_inert(root, pilot)
    boundary = information_boundary()
    runtime = dependency_runtime_identity(root)
    if not all(
        item["passed"]
        for item in (seeds, failure, frozen, historical, p53, boundary, runtime)
    ):
        raise RuntimeError("invalid-attempt evidence failed closeout prerequisites")

    audit = {
        "schema_version": "experiment-005-transfer-pilot-invalid-attempt-1.0",
        "experiment": "Experiment 005 nonlinear-truth noninferential transfer pilot",
        "partition_code": 52,
        "status": "INVALID_TERMINAL_INFRASTRUCTURE_FAILURE",
        "decision": "pilot_invalid_infrastructure_failure",
        "reason": (
            "the single authorized process-pool invocation ended in a terminal "
            "worker-start failure before any complete block was published"
        ),
        "foundation_freeze_id": FOUNDATION_FREEZE_ID,
        "foundation_readiness_id": FOUNDATION_READINESS_ID,
        "design_freeze_id": DESIGN_FREEZE_ID,
        "design_readiness_id": DESIGN_READINESS_ID,
        "materialized_roots": 20,
        "planned_blocks": 20,
        "planned_episodes": 40,
        "materializer_successful_invocations_observed": 1,
        "pilot_runner_invocations_observed": 1,
        "prespecified_replay_invocations_observed": 0,
        "durable_complete_blocks": 0,
        "durable_episode_rows": 0,
        "terminal_infrastructure_failures": 1,
        "retries_observed": 0,
        "replacement_roots_observed": 0,
        "extensions_observed": 0,
        "partial_outcomes_used": False,
        "scientific_findings_claimed": False,
        "architecture_effect_claimed": False,
        "partition_reusable": False,
        "partition_53_touched": False,
        "seed_manifest_sha256": seeds["manifest_sha256"],
        "replay_subset_sha256": seeds["replay_subset_sha256"],
        "campaign_sha256": failure["campaign_sha256"],
        "terminal_failure_sha256": failure["terminal_failure_sha256"],
        "smallest_next_task": (
            "separately freeze an outcome-blind replacement-pilot execution amendment "
            "with an importable process-pool entry point, phase-aware validation, and a "
            "fresh disjoint diagnostic partition while leaving partition 53 untouched"
        ),
    }
    _write_json(root / AUDIT_PATH, audit)

    ledger = {
        "schema_version": "experiment-005-transfer-pilot-execution-ledger-1.0",
        "partition_code": 52,
        "campaign_id": failure["campaign_id"],
        "materializer_successful_invocations_observed": 1,
        "pilot_runner_invocations_observed": 1,
        "prespecified_replay_invocations_observed": 0,
        "checkpoint_continuation_invocations_observed": 0,
        "retries_observed": 0,
        "replacement_roots_observed": 0,
        "extensions_observed": 0,
        "completed_blocks": 0,
        "episode_rows": 0,
        "terminal_failures": 1,
    }
    _write_json(root / LEDGER_PATH, ledger)

    analysis = {
        "schema_version": "experiment-005-transfer-pilot-analysis-1.0",
        "analysis_mode": "descriptive_mechanistic_gate_only",
        "status": "NOT_ANALYZED_INVALID_CAMPAIGN",
        "decision": "pilot_invalid_infrastructure_failure",
        "design_gates_passed": False,
        "scientific_endpoints_evaluated": False,
        "p_values_computed": False,
        "architecture_confidence_intervals_computed": False,
        "superiority_or_noninferiority_claimed": False,
        "hazard_rate_claimed": False,
        "architecture_benefit_claimed": False,
        "partial_outcomes_used": False,
        "smallest_next_task": audit["smallest_next_task"],
    }
    _write_json(root / ANALYSIS_PATH, analysis)

    gates = {
        "frozen_identity": frozen["passed"],
        "write_once_materialization": seeds["passed"],
        "exact_complete_cells": False,
        "nonlinear_truth_numerical_validity": False,
        "estimator_covariance_validity": False,
        "truth_event_geometry": False,
        "fault_and_domain_activation": False,
        "controller_monitor_information_boundary": boundary["passed"],
        "zero_infrastructure_failures": False,
        "zero_retries_and_replacements": True,
        "deterministic_replay": False,
        "descriptive_noninferential_boundary": True,
        "partition_53_untouched": p53["passed"],
    }
    qc = {
        "schema_version": "experiment-005-transfer-pilot-qc-1.0",
        "overall_passed": False,
        "decision": "pilot_invalid_infrastructure_failure",
        "gate_policy": "conjunctive_fail_closed",
        "checks": gates,
        "not_evaluated_due_to_invalid_campaign": [
            key
            for key in (
                "exact_complete_cells",
                "nonlinear_truth_numerical_validity",
                "estimator_covariance_validity",
                "truth_event_geometry",
                "fault_and_domain_activation",
                "deterministic_replay",
            )
            if not gates[key]
        ],
    }
    _write_json(root / QC_PATH, qc)

    reproducibility = {
        "schema_version": "experiment-005-transfer-pilot-reproducibility-1.0",
        "passed": False,
        "same_platform_replay_required": True,
        "same_platform_replay_performed": False,
        "prespecified_replay_blocks": 10,
        "prespecified_replay_episodes": 20,
        "replay_invocations": 0,
        "reason": (
            "the complete original campaign was never assembled and terminal failure "
            "semantics prohibit further execution of the failed partition"
        ),
        "runtime_identity": runtime,
    }
    _write_json(root / REPRODUCIBILITY_PATH, reproducibility)

    next_task = textwrap.fill(
        audit["smallest_next_task"].capitalize()
        + ". This is a separate prospective task; partition 52 must not be reused and "
        + "partition 53 remains out of scope.",
        width=96,
    )
    report = f"""# Experiment 005 partition-52 transfer-pilot closeout

## Decision

**Pilot invalid — terminal infrastructure failure.** The single authorized partition-52
process-pool invocation published no complete blocks and no episode rows. The frozen conjunctive
gates therefore fail before any scientific or architecture interpretation.

## Preserved facts

- The write-once materializer ran once and produced the frozen 20 roots / 40 planned episodes.
- The campaign runner was invoked once with eight workers.
- One terminal failure record was preserved; completed blocks and durable episode rows are both
  zero.
- No retry, continuation, replacement root, extension, imputation, or replay was performed.
- No partial outcome was available or used, and no inferential claim was made.
- Partition 53 remains untouched and has no confirmatory question, size, design, or generator.

## Gate interpretation

The information boundary and frozen byte identities still verify. Completeness, truth validity,
estimator covariance, truth-event geometry, activation, and replay gates are **not evaluated**, not
passed. The zero-infrastructure-failure gate fails.

## Smallest next task

{next_task}
"""
    _write_text(root / REPORT_PATH, report)

    phase = phase_checks(root)
    _write_json(root / PHASE_PATH, phase)
    if not phase["passed"]:
        raise RuntimeError("phase validation failed")

    scan = publication_privacy(root)
    _write_json(root / RELEASE_SCAN_PATH, scan)
    if not scan["passed"]:
        raise RuntimeError("publication and secret scan failed")

    verification = {
        "schema_version": "experiment-005-transfer-pilot-result-verification-1.0",
        "passed": True,
        "status": "INVALID_ATTEMPT_VERIFIED",
        "frozen_identity": frozen,
        "materialization": seeds,
        "terminal_failure": failure,
        "historical_campaign_result_integrity": historical,
        "partition_53": p53,
        "information_boundary": boundary,
        "decision_matches_evidence": True,
        "partial_outcomes_used": False,
        "replay_performed": False,
    }
    _write_json(root / VERIFICATION_PATH, verification)

    artifacts = _artifact_inventory(root)
    manifest = {
        "schema_version": "experiment-005-transfer-pilot-invalid-manifest-1.0",
        "status": "INVALID_ATTEMPT_VERIFIED",
        "design_freeze_id": DESIGN_FREEZE_ID,
        "partition_code": 52,
        "artifacts": artifacts,
    }
    _write_json(root / MANIFEST_PATH, manifest)
    checksum_paths = sorted(
        (
            path
            for path in (root / RESULT_DIR).rglob("*")
            if path.is_file() and path != root / CHECKSUMS_PATH
        ),
        key=lambda path: path.relative_to(root / RESULT_DIR).as_posix(),
    )
    _write_text(
        root / CHECKSUMS_PATH,
        "".join(
            f"{_sha(path)}  {path.relative_to(root / RESULT_DIR).as_posix()}\n"
            for path in checksum_paths
        ),
    )
    return verification


def verify(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        frozen = frozen_identity(root)
        seeds = seed_materialization(root)
        failure = failed_campaign(root)
        pilot = load_pilot_config(root=root)
        p53 = partition_53_inert(root, pilot)
        historical = verify_historical_campaigns(root)
        boundary = information_boundary()
        audit = json.loads((root / AUDIT_PATH).read_text(encoding="utf-8"))
        ledger = json.loads((root / LEDGER_PATH).read_text(encoding="utf-8"))
        analysis = json.loads((root / ANALYSIS_PATH).read_text(encoding="utf-8"))
        qc = json.loads((root / QC_PATH).read_text(encoding="utf-8"))
        reproducibility = json.loads(
            (root / REPRODUCIBILITY_PATH).read_text(encoding="utf-8")
        )
        phase = json.loads((root / PHASE_PATH).read_text(encoding="utf-8"))
        manifest = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
        if not all(
            item["passed"]
            for item in (frozen, seeds, failure, p53, historical, boundary, phase)
        ):
            errors.append("closeout_prerequisite")
        if not (
            audit.get("decision") == "pilot_invalid_infrastructure_failure"
            and audit.get("pilot_runner_invocations_observed") == 1
            and audit.get("terminal_infrastructure_failures") == 1
            and audit.get("durable_episode_rows") == 0
            and audit.get("partition_reusable") is False
            and audit.get("partition_53_touched") is False
        ):
            errors.append("audit")
        if not (
            ledger.get("materializer_successful_invocations_observed") == 1
            and ledger.get("pilot_runner_invocations_observed") == 1
            and ledger.get("prespecified_replay_invocations_observed") == 0
            and ledger.get("retries_observed") == 0
            and ledger.get("replacement_roots_observed") == 0
        ):
            errors.append("ledger")
        if not (
            analysis.get("status") == "NOT_ANALYZED_INVALID_CAMPAIGN"
            and analysis.get("scientific_endpoints_evaluated") is False
            and analysis.get("architecture_benefit_claimed") is False
        ):
            errors.append("analysis")
        if qc.get("overall_passed") is not False or qc.get("checks", {}).get(
            "zero_infrastructure_failures"
        ) is not False:
            errors.append("qc")
        if not (
            reproducibility.get("same_platform_replay_performed") is False
            and reproducibility.get("replay_invocations") == 0
        ):
            errors.append("reproducibility")
        for entry in manifest.get("artifacts", []):
            path = root / entry["path"]
            if not path.is_file() or _sha(path) != entry["sha256"]:
                errors.append(f"manifest:{entry['path']}")
        for line in (root / CHECKSUMS_PATH).read_text(encoding="utf-8").splitlines():
            expected, relative = line.split("  ", 1)
            path = root / RESULT_DIR / relative
            if not path.is_file() or _sha(path) != expected:
                errors.append(f"checksum:{relative}")
        scan = publication_privacy(root)
        if not scan["passed"]:
            errors.append("publication_privacy")
    except (OSError, KeyError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"verification_exception:{type(exc).__name__}")
        frozen = seeds = failure = p53 = historical = boundary = {}
        scan = {}
    return {
        "schema_version": "experiment-005-transfer-pilot-result-verification-1.0",
        "passed": not errors,
        "status": "INVALID_ATTEMPT_VERIFIED" if not errors else "VERIFICATION_FAILED",
        "decision": "pilot_invalid_infrastructure_failure",
        "errors_preview": errors[:30],
        "frozen_identity": frozen,
        "materialization": seeds,
        "terminal_failure": failure,
        "historical_campaign_result_integrity": historical,
        "partition_53": p53,
        "information_boundary": boundary,
        "publication_privacy": scan,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Close and verify the invalid Experiment 005 partition-52 pilot attempt"
    )
    parser.add_argument("command", choices=("close", "verify", "release-scan"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "close":
        result = close(root)
    elif args.command == "verify":
        result = verify(root)
    else:
        result = publication_privacy(root)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if not result.get("passed", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
