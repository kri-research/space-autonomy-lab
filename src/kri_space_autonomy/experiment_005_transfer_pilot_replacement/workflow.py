from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import tempfile
from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_005.config import load_config as load_e005_config
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    TransferPilotConfig,
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.runner import (
    _publish_no_clobber,
    validate_complete_cells,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    canonical_json,
    scenario_from_row,
    sha256_bytes,
    test_fixture_scenario,
)
from kri_space_autonomy.experiment_005_transfer_pilot.validation import (
    publication_privacy,
)
from kri_space_autonomy.experiment_005_transfer_pilot_closeout import (
    CAMPAIGN_SHA256,
    DESIGN_FREEZE_ID,
    DESIGN_READINESS_ID,
    FAILURE_SHA256,
)
from kri_space_autonomy.experiment_005_transfer_pilot_closeout import (
    verify as verify_invalid_closeout,
)

from . import SCHEMA_VERSION
from .runner import (
    MODULE_ENTRYPOINT,
    PROCESS_START_METHOD,
    REPLACEMENT_PARTITION_CODE,
    RESERVED_CONFIRMATORY_PARTITION_CODE,
    RETIRED_PARTITION_CODE,
    TEST_FIXTURE_PARTITION_CODE,
    run_spawn_checkpointed_campaign,
)
from .seeds import (
    AMENDMENT_DIRECTORY,
    CONTRACT_PATH,
    INDEX_NAME,
    MANIFEST_NAME,
    REPLAY_NAME,
    RESULT_DIRECTORY,
    SEED_DIRECTORY,
    materialize_replacement_seeds,
    partition_54_unmaterialized,
    replacement_pilot_config,
    validate_materialized_replacement_seeds,
    validate_seed_contract,
)

BASE_COMMIT = "90de438624556f4890444105fe3c0c19667d5bfa"
EXPECTED_BRANCH = "experiment-005-transfer-pilot-replacement"
CONFIG_PATH = AMENDMENT_DIRECTORY / "config.json"
PREREGISTRATION_PATH = AMENDMENT_DIRECTORY / "preregistration.md"
FIXTURE_VALIDATION_PATH = AMENDMENT_DIRECTORY / "fixture-validation.json"
VALIDATION_PATH = AMENDMENT_DIRECTORY / "validation-evidence.json"
FREEZE_PATH = AMENDMENT_DIRECTORY / "freeze-manifest.json"
READINESS_PATH = AMENDMENT_DIRECTORY / "readiness.json"
DOC_PATH = Path("docs/experiment-005-transfer-pilot-replacement.md")
ORIGINAL_DIRECTORY = Path("experiments/005-transfer-pilot")
INVALID_RESULT_DIRECTORY = Path("results/experiment-005-transfer-pilot")
REPLACEMENT_TEST_PATH = Path(
    "tests/test_experiment_005_transfer_pilot_replacement.py"
)


def _sha(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _github_ci_lineage(root: Path, head: str) -> dict[str, Any]:
    """Validate a shallow GitHub Actions checkout using its signed event context."""

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event_name = os.environ.get("GITHUB_EVENT_NAME")
    github_sha = os.environ.get("GITHUB_SHA")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not event_path:
        return {
            "passed": False,
            "mode": "shallow_checkout_without_ci_identity",
            "head": head,
            "base_commit": BASE_COMMIT,
        }
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "passed": False,
            "mode": "invalid_ci_event_payload",
            "head": head,
            "base_commit": BASE_COMMIT,
        }
    if github_sha != head:
        return {
            "passed": False,
            "mode": "ci_head_identity_mismatch",
            "head": head,
            "base_commit": BASE_COMMIT,
        }
    if event_name == "pull_request":
        pull_request = event.get("pull_request", {})
        base_sha = pull_request.get("base", {}).get("sha")
        pr_head_sha = pull_request.get("head", {}).get("sha")
        subject = _git(root, "log", "-1", "--format=%s")
        passed = bool(
            isinstance(base_sha, str)
            and len(base_sha) == 40
            and isinstance(pr_head_sha, str)
            and len(pr_head_sha) == 40
            and base_sha in subject
            and pr_head_sha in subject
        )
        return {
            "passed": passed,
            "mode": "github_pull_request_synthetic_merge",
            "head": head,
            "base_commit": BASE_COMMIT,
            "event_base_sha": base_sha,
            "event_head_sha": pr_head_sha,
        }
    if event_name == "push":
        after = event.get("after")
        ref = event.get("ref")
        passed = bool(after == head and isinstance(ref, str) and ref.startswith("refs/heads/"))
        return {
            "passed": passed,
            "mode": "github_push_checkout",
            "head": head,
            "base_commit": BASE_COMMIT,
            "event_after_sha": after,
            "event_ref": ref,
        }
    return {
        "passed": False,
        "mode": "unsupported_shallow_ci_event",
        "head": head,
        "base_commit": BASE_COMMIT,
        "event_name": event_name,
    }


def _source_lineage(root: Path) -> dict[str, Any]:
    """Bind the frozen package to its base while remaining valid on later descendants."""

    head = _git(root, "rev-parse", "HEAD")
    if head == BASE_COMMIT:
        return {
            "passed": True,
            "mode": "pre_commit_freeze",
            "head": head,
            "base_commit": BASE_COMMIT,
        }
    shallow = _git(root, "rev-parse", "--is-shallow-repository") == "true"
    if shallow:
        return _github_ci_lineage(root, head)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_COMMIT, head],
        cwd=root,
        text=True,
        capture_output=True,
    )
    return {
        "passed": ancestry.returncode == 0,
        "mode": "full_history_descendant",
        "head": head,
        "base_commit": BASE_COMMIT,
    }


def _run(root: Path, command: list[str], label: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=root, text=True, capture_output=True)
    return {
        "id": label,
        "command": " ".join(command),
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
    }


def _write_json(path: Path, value: dict[str, Any], *, replace: bool) -> None:
    content = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
        return
    path.write_text(content, encoding="utf-8")


def _self_hashed(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    if identity != sha256_bytes(canonical_json(value)):
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def _load_amendment_config(root: Path) -> dict[str, Any]:
    config = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    expected = {
        "schema_version": SCHEMA_VERSION,
        "base_commit": BASE_COMMIT,
        "original_design_freeze_id": DESIGN_FREEZE_ID,
        "original_design_readiness_id": DESIGN_READINESS_ID,
        "invalid_attempt_decision": "pilot_invalid_infrastructure_failure",
        "invalid_partition_code": RETIRED_PARTITION_CODE,
        "future_confirmatory_partition_code": RESERVED_CONFIRMATORY_PARTITION_CODE,
        "replacement_partition_code": REPLACEMENT_PARTITION_CODE,
        "test_fixture_partition_code": TEST_FIXTURE_PARTITION_CODE,
        "process_start_method": PROCESS_START_METHOD,
        "module_entrypoint": MODULE_ENTRYPOINT,
        "default_worker_cap": 8,
        "worker_policy": "max(1, min(8, logical_cpu_count - 3))",
    }
    errors = [key for key, value in expected.items() if config.get(key) != value]
    if errors or set(config) != set(expected):
        raise RuntimeError(f"replacement amendment config drift: {errors[:5]}")
    return config


def verify_invalid_attempt(root: Path) -> dict[str, Any]:
    closeout = verify_invalid_closeout(root)
    audit_path = root / INVALID_RESULT_DIRECTORY / "invalid-attempt-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    checks = {
        "closeout_verifier": closeout["passed"],
        "decision": audit.get("decision") == "pilot_invalid_infrastructure_failure",
        "retired_partition": (
            audit.get("partition_code") == RETIRED_PARTITION_CODE
            and audit.get("partition_reusable") is False
        ),
        "zero_completed_blocks": audit.get("durable_complete_blocks") == 0,
        "zero_episode_rows": audit.get("durable_episode_rows") == 0,
        "one_terminal_infrastructure_failure": (
            audit.get("terminal_infrastructure_failures") == 1
        ),
        "no_retries_replacements_or_extensions": all(
            audit.get(key) == 0
            for key in (
                "retries_observed",
                "replacement_roots_observed",
                "extensions_observed",
            )
        ),
        "no_partial_outcomes_used": audit.get("partial_outcomes_used") is False,
        "no_scientific_claims": (
            audit.get("scientific_findings_claimed") is False
            and audit.get("architecture_effect_claimed") is False
        ),
        "campaign_identity": audit.get("campaign_sha256") == CAMPAIGN_SHA256,
        "failure_identity": audit.get("terminal_failure_sha256") == FAILURE_SHA256,
        "partition_53_untouched": (
            audit.get("partition_53_touched") is False
            and closeout.get("partition_53", {}).get("passed") is True
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "audit_sha256": _sha(audit_path),
        "campaign_sha256": audit.get("campaign_sha256"),
        "terminal_failure_sha256": audit.get("terminal_failure_sha256"),
        "completed_blocks": audit.get("durable_complete_blocks"),
        "durable_episode_rows": audit.get("durable_episode_rows"),
        "scientific_endpoints_evaluated": False,
        "outcomes_used_for_amendment": False,
    }


def science_unchanged(root: Path) -> dict[str, Any]:
    original = load_pilot_config(root / ORIGINAL_DIRECTORY / "config.json", root=root)
    replacement = replacement_pilot_config(root)
    changed = [
        field.name
        for field in fields(TransferPilotConfig)
        if getattr(original, field.name) != getattr(replacement, field.name)
    ]
    protected = {
        "config": root / ORIGINAL_DIRECTORY / "config.json",
        "case_matrix": root / ORIGINAL_DIRECTORY / "case-matrix.json",
        "gates": root / ORIGINAL_DIRECTORY / "gates.json",
        "seed_contract": root / ORIGINAL_DIRECTORY / "seed-contract.json",
        "preregistration": root / ORIGINAL_DIRECTORY / "preregistration.md",
    }
    design_manifest = _self_hashed(
        root / ORIGINAL_DIRECTORY / "freeze-manifest.json", "freeze_id"
    )
    design_readiness = _self_hashed(
        root / ORIGINAL_DIRECTORY / "readiness.json", "readiness_id"
    )
    expected_hashes = design_manifest.get("source_file_hashes", {})
    hash_checks = {
        name: expected_hashes.get(path.relative_to(root).as_posix()) == _sha(path)
        for name, path in protected.items()
    }
    scientific_fields = [
        field.name for field in fields(TransferPilotConfig) if field.name != "pilot_partition_code"
    ]
    return {
        "passed": bool(
            changed == ["pilot_partition_code"]
            and all(hash_checks.values())
            and design_manifest.get("freeze_id") == DESIGN_FREEZE_ID
            and design_readiness.get("readiness_id") == DESIGN_READINESS_ID
        ),
        "changed_execution_identity_fields": changed,
        "scientific_field_count_compared": len(scientific_fields),
        "scientific_field_drift": [
            name
            for name in scientific_fields
            if getattr(original, name) != getattr(replacement, name)
        ],
        "protected_design_hashes": hash_checks,
        "original_design_freeze_id": DESIGN_FREEZE_ID,
        "original_design_readiness_id": DESIGN_READINESS_ID,
        "cases": original.case_count,
        "complete_blocks": original.pilot_blocks,
        "episodes": original.pilot_episodes,
        "replay_blocks": original.replay_blocks,
        "replay_episodes": original.replay_episodes,
        "metrics_thresholds_gates_changed": False,
        "scientific_claims_enabled": False,
    }


def _fixture_scenarios(root: Path) -> tuple[Any, Any, Any, Any, Any]:
    pilot = load_pilot_config(root / ORIGINAL_DIRECTORY / "config.json", root=root)
    foundation = load_e005_config(root / "experiments/005/config.json", root=root)
    e004 = load_e004_config(root / "experiments/004/config.json")
    cases = load_case_matrix(root / ORIGINAL_DIRECTORY / "case-matrix.json")
    case = next(item for item in cases if item.id == "T02_truth_keep_out_crossing_fixture")
    scenarios = tuple(
        test_fixture_scenario(pilot, foundation, e004, case, replicate)[0]
        for replicate in range(2)
    )
    return pilot, foundation, e004, cases, scenarios


def run_fixture_validation(root: Path) -> dict[str, Any]:
    pilot, foundation, e004, cases, scenarios = _fixture_scenarios(root)
    with tempfile.TemporaryDirectory(prefix="experiment-005-spawn-fixture-") as temporary:
        base = Path(temporary)
        serial = run_spawn_checkpointed_campaign(
            base / "serial",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=1,
        )
        parallel = run_spawn_checkpointed_campaign(
            base / "parallel",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=2,
        )
        interrupted = run_spawn_checkpointed_campaign(
            base / "resume",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=1,
            stop_after_for_test=1,
        )
        resumed = run_spawn_checkpointed_campaign(
            base / "resume",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=2,
        )
        replay = run_spawn_checkpointed_campaign(
            base / "replay",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=2,
        )
        run_spawn_checkpointed_campaign(
            base / "corrupt",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=1,
            stop_after_for_test=1,
        )
        (base / "corrupt/shards/cell-000000.json").write_text(
            "{}\n", encoding="utf-8"
        )
        corrupt_failed_closed = False
        try:
            run_spawn_checkpointed_campaign(
                base / "corrupt",
                pilot=pilot,
                foundation=foundation,
                e004=e004,
                cases=cases,
                scenarios=scenarios,
                workers=2,
            )
        except RuntimeError as exc:
            corrupt_failed_closed = "checkpoint shard" in str(exc)

        serial_bytes = (base / "serial/pilot-episodes.jsonl").read_bytes()
        parallel_bytes = (base / "parallel/pilot-episodes.jsonl").read_bytes()
        resumed_bytes = (base / "resume/pilot-episodes.jsonl").read_bytes()
        replay_bytes = (base / "replay/pilot-episodes.jsonl").read_bytes()
        serial_rows = [json.loads(line) for line in serial_bytes.splitlines()]

    expected_row_order = [
        (scenario.root_seed_id, configuration)
        for scenario in scenarios
        for configuration in scenario.configuration_run_order
    ]
    observed_row_order = [
        (row.get("root_seed_id"), row.get("configuration_id")) for row in serial_rows
    ]
    checks = {
        "fixture_partition_only": all(
            scenario.partition_code == TEST_FIXTURE_PARTITION_CODE
            for scenario in scenarios
        ),
        "replacement_partition_not_accessed": all(
            scenario.partition_code != REPLACEMENT_PARTITION_CODE
            for scenario in scenarios
        ),
        "partition_52_not_accessed": all(
            scenario.partition_code != RETIRED_PARTITION_CODE for scenario in scenarios
        ),
        "partition_53_not_accessed": all(
            scenario.partition_code != RESERVED_CONFIRMATORY_PARTITION_CODE
            for scenario in scenarios
        ),
        "serial_complete": serial["passed"],
        "parallel_spawn_complete": parallel["passed"],
        "serial_parallel_scientific_bytes_identical": serial_bytes == parallel_bytes,
        "deterministic_replay_bytes_identical": serial_bytes == replay_bytes,
        "interruption_incomplete": bool(
            not interrupted["complete"]
            and interrupted["cells"] == 1
            and interrupted["remaining_cells"] == 1
        ),
        "checkpoint_continuation_missing_only": bool(
            resumed["passed"]
            and resumed["completed_shards_reused"] == 1
            and resumed["new_shards_written"] == 1
        ),
        "checkpoint_continuation_byte_identical": resumed_bytes == serial_bytes,
        "canonical_block_and_episode_order": observed_row_order == expected_row_order,
        "corrupt_checkpoint_fails_closed": corrupt_failed_closed,
        "strict_zero_retry_and_replacement_counts": all(
            result["retries"] == 0
            and result["replacement_roots"] == 0
            and result["infrastructure_failures"] == 0
            for result in (serial, parallel, resumed, replay)
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "passed": all(checks.values()),
        "status": "FIXTURE_SPAWN_VALIDATED" if all(checks.values()) else "NOT_READY",
        "validation_scope": "partition-951 non-outcome deterministic fixtures only",
        "invocation_mode": "importable_module_cli",
        "module_entrypoint": MODULE_ENTRYPOINT,
        "process_start_method": parallel["process_start_method"],
        "python": platform.python_version(),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "fixture_partition_code": TEST_FIXTURE_PARTITION_CODE,
        "fixture_blocks": len(scenarios),
        "fixture_episode_rows": len(serial_rows),
        "serial_output_sha256": serial["output_sha256"],
        "parallel_output_sha256": parallel["output_sha256"],
        "resumed_output_sha256": resumed["output_sha256"],
        "replay_output_sha256": replay["output_sha256"],
        "checks": checks,
        "scientific_endpoints_evaluated": False,
        "outcomes_used_for_design_or_acceptance_changes": False,
        "replacement_partition_materialized": False,
        "replacement_partition_executed": False,
    }


def _fixture_evidence_valid(root: Path) -> dict[str, Any]:
    path = root / FIXTURE_VALIDATION_PATH
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))
        observed = run_fixture_validation(root)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        return {"passed": False, "error": type(exc).__name__}
    return {
        "passed": bool(
            recorded == observed
            and recorded.get("passed") is True
            and recorded.get("process_start_method") == PROCESS_START_METHOD
            and recorded.get("replacement_partition_materialized") is False
            and recorded.get("replacement_partition_executed") is False
        ),
        "fixture_validation_sha256": _sha(path),
        "recorded_matches_fresh_validation": recorded == observed,
        "evidence": recorded,
    }


def _source_paths(root: Path) -> list[Path]:
    paths = list(
        (root / "src/kri_space_autonomy/experiment_005_transfer_pilot_replacement").glob(
            "*.py"
        )
    )
    paths += [
        root / DOC_PATH,
        root / CONFIG_PATH,
        root / CONTRACT_PATH,
        root / PREREGISTRATION_PATH,
        root / FIXTURE_VALIDATION_PATH,
        root / VALIDATION_PATH,
        root / REPLACEMENT_TEST_PATH,
        root / ORIGINAL_DIRECTORY / "config.json",
        root / ORIGINAL_DIRECTORY / "case-matrix.json",
        root / ORIGINAL_DIRECTORY / "gates.json",
        root / ORIGINAL_DIRECTORY / "seed-contract.json",
        root / ORIGINAL_DIRECTORY / "preregistration.md",
        root / ORIGINAL_DIRECTORY / "freeze-manifest.json",
        root / ORIGINAL_DIRECTORY / "readiness.json",
        root / "src/kri_space_autonomy/experiment_005_transfer_pilot/config.py",
        root / "src/kri_space_autonomy/experiment_005_transfer_pilot/runner.py",
        root / "src/kri_space_autonomy/experiment_005_transfer_pilot/seeds.py",
        root / "src/kri_space_autonomy/experiment_005_transfer_pilot_closeout.py",
        root / INVALID_RESULT_DIRECTORY / "checksums.sha256",
        root / INVALID_RESULT_DIRECTORY / "manifest.json",
        root / INVALID_RESULT_DIRECTORY / "invalid-attempt-audit.json",
        root / INVALID_RESULT_DIRECTORY / "invalid-attempt-evidence/campaign.json",
        root / INVALID_RESULT_DIRECTORY / "invalid-attempt-evidence/terminal-failure.json",
        root / ".python-version",
        root / "pyproject.toml",
        root / "uv.lock",
    ]
    return sorted(
        (path for path in paths if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha(path) for path in _source_paths(root)
    }


def validate(root: Path) -> dict[str, Any]:
    config = _load_amendment_config(root)
    pilot = replacement_pilot_config(root)
    invalid = verify_invalid_attempt(root)
    science = science_unchanged(root)
    partition = partition_54_unmaterialized(root)
    seed_contract = validate_seed_contract(pilot, root / CONTRACT_PATH, root=root)
    fixture = _fixture_evidence_valid(root)
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    commands = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(root, ["uv", "run", "pytest", "-q"], "phase_appropriate_repository_tests"),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "stable_gate"),
        _run(root, ["git", "diff", "--check"], "diff_whitespace"),
    ]
    privacy = publication_privacy(root)
    checks = {
        "requested_branch": branch == EXPECTED_BRANCH,
        "merged_closeout_base": head == config["base_commit"] == BASE_COMMIT,
        "invalid_partition_52_closeout": invalid["passed"],
        "scientific_design_unchanged": science["passed"],
        "partition_54_reserved_unmaterialized": partition["passed"],
        "partition_53_untouched": invalid["checks"]["partition_53_untouched"],
        "seed_contract": seed_contract["passed"],
        "fixture_spawn_validation": fixture["passed"],
        "phase_commands": all(command["passed"] for command in commands),
        "publication_privacy_and_secret_scan": privacy["passed"],
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "phase": "pre_materialization_replacement_pilot_amendment",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": all(checks.values()),
        "status": "READY_TO_FREEZE" if all(checks.values()) else "NOT_READY",
        "decision": "READY" if all(checks.values()) else "NOT_READY",
        "smallest_blocker": next(
            (name for name, passed in checks.items() if not passed), None
        ),
        "checks": checks,
        "commands": commands,
        "source_identity": {"branch": branch, "head": head},
        "invalid_attempt": invalid,
        "scientific_design": science,
        "replacement_partition": partition,
        "seed_contract": seed_contract,
        "fixture_validation": fixture,
        "publication_privacy": privacy,
        "partition_52_reused": False,
        "partition_53_touched": False,
        "partition_54_materialized": False,
        "partition_54_executed": False,
        "scientific_endpoints_evaluated": False,
        "outcomes_used_for_amendment": False,
    }
    _write_json(root / VALIDATION_PATH, result, replace=True)
    return result


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite replacement amendment freeze")
    if (
        _git(root, "branch", "--show-current") != EXPECTED_BRANCH
        or _git(root, "rev-parse", "HEAD") != BASE_COMMIT
    ):
        raise RuntimeError("replacement amendment freeze requires requested branch and base")
    validation = validate(root)
    if not validation["passed"]:
        raise RuntimeError(
            f"replacement amendment is NOT READY: {validation['smallest_blocker']}"
        )
    _load_amendment_config(root)
    pilot = replacement_pilot_config(root)
    source_hashes = _file_hashes(root)
    fixture = validation["fixture_validation"]["evidence"]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "phase": "pre_materialization_replacement_pilot_amendment_freeze",
        "status": "READY_FOR_PROSPECTIVE_REPLACEMENT_PILOT_EXECUTION",
        "decision": "READY",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "base_commit": BASE_COMMIT,
        "source_identity": {
            "branch": EXPECTED_BRANCH,
            "head": BASE_COMMIT,
            "commit_created": False,
            "paths": "project-relative only",
        },
        "invalid_attempt": {
            "partition": RETIRED_PARTITION_CODE,
            "decision": "pilot_invalid_infrastructure_failure",
            "completed_blocks": 0,
            "durable_episode_rows": 0,
            "terminal_failure_class": "BrokenProcessPool",
            "scientific_endpoints_evaluated": False,
            "partial_outcomes_used": False,
            "reusable": False,
            "audit_sha256": validation["invalid_attempt"]["audit_sha256"],
            "campaign_sha256": CAMPAIGN_SHA256,
            "terminal_failure_sha256": FAILURE_SHA256,
        },
        "partition_selection": {
            "replacement_partition": REPLACEMENT_PARTITION_CODE,
            "state": "reserved_not_materialized_or_executed",
            "rule": (
                "next unused disjoint numeric partition after the retired pilot while "
                "skipping reserved partition 53"
            ),
            "repository_precedent": "retired partition 44 was replaced prospectively by 45",
            "outcomes_used": False,
            "partition_53_touched": False,
        },
        "scientific_design": {
            "copied_without_scientific_change_from": DESIGN_FREEZE_ID,
            "original_readiness_id": DESIGN_READINESS_ID,
            "cases": pilot.case_count,
            "configurations": list(pilot.configuration_ids),
            "roots_per_case": pilot.pilot_roots_per_case,
            "complete_blocks": pilot.pilot_blocks,
            "episodes": pilot.pilot_episodes,
            "replay_blocks": pilot.replay_blocks,
            "replay_episodes": pilot.replay_episodes,
            "metrics_unchanged": True,
            "thresholds_unchanged": True,
            "acceptance_gates_unchanged": True,
            "scientific_claims_enabled": False,
        },
        "execution_protocol": {
            "entrypoint": (
                "uv run python -m "
                "kri_space_autonomy.experiment_005_transfer_pilot_replacement.workflow "
                "execute --workers 8"
            ),
            "ephemeral_main_allowed": False,
            "process_start_method": PROCESS_START_METHOD,
            "parallelism": "multi-core process pool",
            "work_unit": "complete paired root block",
            "completed_block_storage": "atomic content-hashed checkpoint shard",
            "final_assembly": "canonical frozen block and within-block episode order",
            "checkpoint_continuation": (
                "validate completed shards and execute missing unpublished blocks only"
            ),
            "completed_valid_blocks_recomputed": False,
            "maximum_retries": 0,
            "maximum_replacement_roots": 0,
            "seed_or_root_substitution_allowed": False,
            "corrupt_duplicate_foreign_or_incomplete_evidence": "fail closed",
        },
        "fixture_validation": {
            "partition": TEST_FIXTURE_PARTITION_CODE,
            "non_outcome_only": True,
            "process_start_method": fixture["process_start_method"],
            "serial_output_sha256": fixture["serial_output_sha256"],
            "parallel_output_sha256": fixture["parallel_output_sha256"],
            "resumed_output_sha256": fixture["resumed_output_sha256"],
            "replay_output_sha256": fixture["replay_output_sha256"],
            "serial_parallel_equivalent": fixture["checks"][
                "serial_parallel_scientific_bytes_identical"
            ],
            "deterministic_replay": fixture["checks"][
                "deterministic_replay_bytes_identical"
            ],
            "checkpoint_continuation_equivalent": fixture["checks"][
                "checkpoint_continuation_byte_identical"
            ],
            "corruption_fails_closed": fixture["checks"][
                "corrupt_checkpoint_fails_closed"
            ],
            "replacement_partition_accessed": False,
        },
        "validation_sha256": _sha(root / VALIDATION_PATH),
        "seed_contract_sha256": _sha(root / CONTRACT_PATH),
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "partition_52_reused": False,
        "partition_53_touched": False,
        "partition_54_materialized": False,
        "partition_54_executed": False,
        "scientific_endpoints_evaluated": False,
        "outcomes_used_for_amendment": False,
        "readiness_policy": "conjunctive fail closed; no critical-check waiver",
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    _write_json(root / FREEZE_PATH, unsigned, replace=False)
    readiness = {
        "schema_version": SCHEMA_VERSION,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY_FOR_PROSPECTIVE_REPLACEMENT_PILOT_EXECUTION",
        "decision": "READY",
        "invalid_partition_code": RETIRED_PARTITION_CODE,
        "invalid_partition_reusable": False,
        "future_confirmatory_partition_code": RESERVED_CONFIRMATORY_PARTITION_CODE,
        "future_confirmatory_partition_state": "reserved_untouched",
        "replacement_partition_code": REPLACEMENT_PARTITION_CODE,
        "replacement_partition_state": "reserved_not_materialized_or_executed",
        "replacement_generator_authorized": True,
        "replacement_generator_invoked": False,
        "complete_blocks": pilot.pilot_blocks,
        "episode_rows": pilot.pilot_episodes,
        "replay_blocks": pilot.replay_blocks,
        "replay_episode_rows": pilot.replay_episodes,
        "process_start_method": PROCESS_START_METHOD,
        "default_workers": min(8, max(1, (__import__("os").cpu_count() or 1) - 3)),
        "next_command": (
            "uv run python -m "
            "kri_space_autonomy.experiment_005_transfer_pilot_replacement.workflow "
            "execute --workers 8"
        ),
        "partition_54_materialized": False,
        "partition_54_executed": False,
        "scientific_endpoints_evaluated": False,
        "scientific_claims_supported": False,
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    _write_json(root / READINESS_PATH, readiness, replace=False)
    verification = verify_freeze(root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError(
            f"replacement amendment freeze failed verification: {verification['errors']}"
        )
    return {"freeze": unsigned, "readiness": readiness, "verification": verification}


def verify_freeze(root: Path, *, require_unmaterialized: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = _self_hashed(root / FREEZE_PATH, "freeze_id")
        readiness = _self_hashed(root / READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {
            "passed": False,
            "status": "NOT_READY",
            "errors": [f"freeze_load:{type(exc).__name__}"],
        }
    for relative, expected in manifest.get("source_file_hashes", {}).items():
        path = root / relative
        if not path.is_file() or _sha(path) != expected:
            errors.append(relative)
    if _sha(root / VALIDATION_PATH) != manifest.get("validation_sha256"):
        errors.append("validation_identity")
    if _sha(root / CONTRACT_PATH) != manifest.get("seed_contract_sha256"):
        errors.append("seed_contract_identity")
    invalid = verify_invalid_attempt(root)
    science = science_unchanged(root)
    pilot = replacement_pilot_config(root)
    partition = (
        partition_54_unmaterialized(root)
        if require_unmaterialized
        else {
            "passed": True,
            "partition_code": REPLACEMENT_PARTITION_CODE,
            "state": "materialization_state_not_required",
        }
    )
    seed_contract = validate_seed_contract(
        pilot,
        root / CONTRACT_PATH,
        root=root,
        require_unmaterialized=require_unmaterialized,
    )
    fixture = json.loads((root / FIXTURE_VALIDATION_PATH).read_text(encoding="utf-8"))
    if not invalid["passed"]:
        errors.append("invalid_attempt")
    if not science["passed"]:
        errors.append("scientific_design")
    if not partition["passed"]:
        errors.append("partition_54_state")
    if not seed_contract["passed"]:
        errors.append("seed_contract")
    if not (
        fixture.get("passed") is True
        and fixture.get("process_start_method") == PROCESS_START_METHOD
        and fixture.get("replacement_partition_materialized") is False
        and fixture.get("replacement_partition_executed") is False
    ):
        errors.append("fixture_validation")
    if not (
        manifest.get("status") == "READY_FOR_PROSPECTIVE_REPLACEMENT_PILOT_EXECUTION"
        and readiness.get("freeze_id") == manifest.get("freeze_id")
        and readiness.get("status")
        == "READY_FOR_PROSPECTIVE_REPLACEMENT_PILOT_EXECUTION"
        and readiness.get("replacement_partition_code") == REPLACEMENT_PARTITION_CODE
        and readiness.get("future_confirmatory_partition_code")
        == RESERVED_CONFIRMATORY_PARTITION_CODE
        and readiness.get("replacement_generator_invoked") is False
        and readiness.get("partition_54_materialized") is False
        and readiness.get("partition_54_executed") is False
    ):
        errors.append("readiness_identity")
    source_lineage = _source_lineage(root)
    if not source_lineage["passed"]:
        errors.append("source_lineage")
    privacy = publication_privacy(root)
    if not privacy["passed"]:
        errors.append("publication_privacy")
    return {
        "passed": not errors,
        "status": (
            "READY_FOR_PROSPECTIVE_REPLACEMENT_PILOT_EXECUTION"
            if not errors
            else "NOT_READY"
        ),
        "decision": "READY" if not errors else "NOT_READY",
        "errors": errors,
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "require_unmaterialized": require_unmaterialized,
        "invalid_attempt": invalid,
        "scientific_design": science,
        "partition_54": partition,
        "seed_contract": seed_contract,
        "source_lineage": source_lineage,
        "partition_53_untouched": invalid["checks"]["partition_53_untouched"],
        "partition_54_materialized": False if require_unmaterialized else None,
        "partition_54_executed": False if require_unmaterialized else None,
    }


def _load_seed_scenarios(root: Path) -> tuple[Any, ...]:
    return tuple(
        scenario_from_row(json.loads(line))
        for line in (root / SEED_DIRECTORY / MANIFEST_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
    )


def execute(root: Path, workers: int | None) -> dict[str, Any]:
    first_start = not (root / SEED_DIRECTORY).exists()
    verification = verify_freeze(root, require_unmaterialized=first_start)
    if not verification["passed"]:
        raise RuntimeError(f"replacement amendment is not ready: {verification['errors']}")
    pilot = replacement_pilot_config(root)
    foundation = load_e005_config(root / "experiments/005/config.json", root=root)
    e004 = load_e004_config(root / "experiments/004/config.json")
    cases = load_case_matrix(root / ORIGINAL_DIRECTORY / "case-matrix.json")
    if first_start:
        materialize_replacement_seeds(
            pilot,
            foundation,
            e004,
            cases,
            root=root,
            freeze_id=verification["freeze_id"],
            readiness_id=verification["readiness_id"],
            seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
        )
    seed_index = json.loads((root / SEED_DIRECTORY / INDEX_NAME).read_text(encoding="utf-8"))
    seed_validation = validate_materialized_replacement_seeds(
        pilot,
        foundation,
        e004,
        cases,
        root=root,
        freeze_id=verification["freeze_id"],
        readiness_id=verification["readiness_id"],
        seed_contract_sha256=seed_index["seed_contract_sha256"],
    )
    if not seed_validation["passed"]:
        raise RuntimeError("partition-54 materialized schedule failed validation")
    scenarios = _load_seed_scenarios(root)
    if any(
        scenario.partition_code != REPLACEMENT_PARTITION_CODE
        or scenario.design_freeze_id != verification["freeze_id"]
        for scenario in scenarios
    ):
        raise RuntimeError("partition-54 schedule identity drift")
    campaign = run_spawn_checkpointed_campaign(
        root / RESULT_DIRECTORY / "campaign",
        pilot=pilot,
        foundation=foundation,
        e004=e004,
        cases=cases,
        scenarios=scenarios,
        workers=workers,
    )
    if not campaign["complete"]:
        return {
            "passed": False,
            "status": "INCOMPLETE_FAIL_CLOSED",
            "campaign": campaign,
        }
    output_path = root / RESULT_DIRECTORY / "campaign/pilot-episodes.jsonl"
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    complete_cells = validate_complete_cells(rows, pilot, cases)
    if not complete_cells["passed"]:
        raise RuntimeError("partition-54 complete-cell gate failed")
    replay_spec = json.loads(
        (root / SEED_DIRECTORY / REPLAY_NAME).read_text(encoding="utf-8")
    )
    selected = set(replay_spec["root_seed_ids"])
    replay_scenarios = tuple(
        scenario for scenario in scenarios if scenario.root_seed_id in selected
    )
    replay = run_spawn_checkpointed_campaign(
        root / RESULT_DIRECTORY / "replay",
        pilot=pilot,
        foundation=foundation,
        e004=e004,
        cases=cases,
        scenarios=replay_scenarios,
        workers=workers,
    )
    replay_path = root / RESULT_DIRECTORY / "replay/pilot-episodes.jsonl"
    original_subset = b"".join(
        canonical_json(row) + b"\n" for row in rows if row["root_seed_id"] in selected
    )
    replay_equivalent = replay_path.read_bytes() == original_subset
    summary = {
        "schema_version": SCHEMA_VERSION,
        "amendment_freeze_id": verification["freeze_id"],
        "amendment_readiness_id": verification["readiness_id"],
        "partition_code": REPLACEMENT_PARTITION_CODE,
        "campaign": campaign,
        "complete_cell_validation": complete_cells,
        "replay": replay,
        "replay_byte_equivalent": replay_equivalent,
        "retries": 0,
        "replacement_roots": 0,
        "scientific_endpoints_evaluated": False,
        "scientific_claims_supported": False,
        "status": "EXECUTION_COMPLETE_PENDING_FROZEN_SCIENTIFIC_GATE_EVALUATION",
    }
    summary_path = root / RESULT_DIRECTORY / "execution-summary.json"
    content = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    if summary_path.exists():
        if summary_path.read_bytes() != content:
            raise RuntimeError("existing execution summary conflicts with frozen campaign")
    else:
        _publish_no_clobber(summary_path, content)
    return {
        "passed": bool(complete_cells["passed"] and replay["passed"] and replay_equivalent),
        "status": summary["status"],
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experiment 005 transfer-pilot replacement execution amendment"
    )
    parser.add_argument(
        "command",
        choices=(
            "fixture-validate",
            "validate",
            "freeze",
            "verify-freeze",
            "execute",
        ),
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "fixture-validate":
        result = run_fixture_validation(root)
        output = args.output or root / FIXTURE_VALIDATION_PATH
        _write_json(output, result, replace=args.output is not None)
    elif args.command == "validate":
        result = validate(root)
    elif args.command == "freeze":
        result = freeze(root)
    elif args.command == "verify-freeze":
        result = verify_freeze(root, require_unmaterialized=True)
    else:
        result = execute(root, args.workers)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if not result.get("passed", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
