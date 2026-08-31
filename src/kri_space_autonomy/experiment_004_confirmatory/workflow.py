from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_004_pilot.config import load_pilot_config
from kri_space_autonomy.experiment_004_pilot.runner import _scenario_from_row
from kri_space_autonomy.experiment_004_pilot.validation import publication_privacy

from .analysis import analyze_confirmatory_rows
from .config import EXPECTED_BASE, ConfirmatoryConfig, load_confirmatory_config
from .runner import load_episode_rows, run_confirmatory_block, run_confirmatory_campaign
from .seeds import (
    MANIFEST_NAME,
    REPLAY_NAME,
    RESULT_DIRECTORY,
    SEED_DIRECTORY,
    load_confirmatory_cases,
    materialize_confirmatory_seeds,
    validate_materialized_confirmatory_seeds,
    validate_seed_contract,
)
from .validation import run_preoutcome_checks, verify_partition_44_unmaterialized

EXPECTED_BRANCH = "experiment-004-confirmatory-design"
CONFIG_PATH = Path("experiments/004-confirmatory/config.json")
STRATA_PATH = Path("experiments/004-confirmatory/strata.json")
SEED_CONTRACT_PATH = Path("experiments/004-confirmatory/seed-contract.json")
PREREGISTRATION_PATH = Path("experiments/004-confirmatory/preregistration.md")
VALIDATION_PATH = Path("experiments/004-confirmatory/validation-evidence.json")
FREEZE_PATH = Path("experiments/004-confirmatory/freeze-manifest.json")
READINESS_PATH = Path("experiments/004-confirmatory/readiness.json")
DOC_PATH = Path("docs/experiment-004-confirmatory.md")
FOUNDATION_CONFIG_PATH = Path("experiments/004/config.json")
PILOT_CONFIG_PATH = Path("experiments/004-pilot/config.json")
PILOT_MATRIX_PATH = Path("experiments/004-pilot/case-matrix.json")
EPISODES_PATH = RESULT_DIRECTORY / "confirmatory-episodes.jsonl"
EXECUTION_PATH = RESULT_DIRECTORY / "execution-summary.json"
ANALYSIS_PATH = RESULT_DIRECTORY / "analysis.json"
REPRODUCIBILITY_PATH = RESULT_DIRECTORY / "reproducibility.json"
CHECKSUMS_PATH = RESULT_DIRECTORY / "checksums.sha256"
SOURCE_GLOBS = (
    "src/kri_space_autonomy/experiment_004_confirmatory/*.py",
    "tests/test_experiment_004_confirmatory_*.py",
    "experiments/004-confirmatory/config.json",
    "experiments/004-confirmatory/strata.json",
    "experiments/004-confirmatory/seed-contract.json",
    "experiments/004-confirmatory/preregistration.md",
    "docs/experiment-004-confirmatory.md",
    ".github/workflows/ci.yml",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
PHASE_INAPPLICABLE_TESTS = (
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
        "tail": lines[-8:],
    }


def _self_hashed(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    if sha256_bytes(canonical_json(value)) != identity:
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def _source_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    paths.add(root / VALIDATION_PATH)
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def _file_hashes(root: Path, paths: list[Path]) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_bytes(path.read_bytes())
        for path in paths
    }


def validate(root: Path) -> dict[str, Any]:
    study = load_confirmatory_config(root / CONFIG_PATH)
    pytest_command = ["uv", "run", "pytest", "-q"]
    for test in PHASE_INAPPLICABLE_TESTS:
        pytest_command.extend(("--deselect", test))
    commands = [
        _run(root, ["uv", "sync", "--frozen", "--extra", "dev"], "dependency_lock"),
        _run(root, ["uv", "run", "ruff", "check", "."], "ruff"),
        _run(root, pytest_command, "phase_appropriate_full_pytest"),
        _run(
            root,
            ["uv", "run", "pytest", "-q", "-k", "experiment_004_confirmatory"],
            "experiment_004_confirmatory_tests",
        ),
        _run(
            root,
            ["uv", "run", "python", "-m", "compileall", "-q", "src", "tests"],
            "compileall",
        ),
        _run(root, ["uv", "run", "kri-space-lab", "verify-gate"], "stable_gate"),
        _run(root, ["git", "diff", "--check"], "git_diff_check"),
    ]
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    science = run_preoutcome_checks(
        root,
        study,
        seed_contract_path=SEED_CONTRACT_PATH,
    )
    checks = [
        *commands,
        {
            "id": "requested_branch_and_merged_main_base",
            "passed": branch == EXPECTED_BRANCH and head == EXPECTED_BASE,
            "observed": {"branch": branch, "head": head},
        },
        {
            "id": "fail_closed_scientific_and_integrity_checks",
            "passed": science["passed"],
            "observed": science,
        },
    ]
    passed = all(bool(check["passed"]) for check in checks)
    result = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_confirmatory_design_validation",
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "passed": passed,
        "status": "READY_TO_FREEZE" if passed else "NOT_READY_FOR_CONFIRMATORY_DESIGN",
        "checks": checks,
        "phase_appropriate_exclusions": {
            "tests": list(PHASE_INAPPLICABLE_TESTS),
            "reason": (
                "historical absence assertions are phase-inapplicable after their frozen "
                "outcome campaigns or after the additive partition-44 design directory exists; "
                "completed result verifiers and explicit partition-44 seed/result absence replace "
                "them"
            ),
        },
        "partition_44_materialized": False,
        "confirmatory_outcomes_executed": False,
        "confirmatory_outcome_rows_created": False,
        "pilot_outcome_direction_influenced_design": False,
        "learned_policy_claimed": False,
    }
    (root / VALIDATION_PATH).write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result


def freeze(root: Path) -> dict[str, Any]:
    if (root / FREEZE_PATH).exists() or (root / READINESS_PATH).exists():
        raise RuntimeError("refusing to overwrite confirmatory freeze/readiness")
    branch = _git(root, "branch", "--show-current")
    head = _git(root, "rev-parse", "HEAD")
    if branch != EXPECTED_BRANCH or head != EXPECTED_BASE:
        raise RuntimeError("confirmatory freeze requires the requested branch and base")
    validation = validate(root)
    if not validation["passed"]:
        raise RuntimeError("Experiment 004 is NOT_READY_FOR_CONFIRMATORY_DESIGN")
    study = load_confirmatory_config(root / CONFIG_PATH)
    science = next(
        check["observed"]
        for check in validation["checks"]
        if check["id"] == "fail_closed_scientific_and_integrity_checks"
    )
    source_hashes = _file_hashes(root, _source_files(root))
    unsigned = {
        "schema_version": study.schema_version,
        "phase": "pre_outcome_confirmatory_design_freeze",
        "status": "READY_FOR_CONFIRMATORY_EXECUTION",
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "scope": "deterministic planar HCW independent-monitor assurance comparison",
        "source_identity": {
            "branch": branch,
            "base_commit": head,
            "working_tree_dirty": bool(_git(root, "status", "--short")),
            "commit_created": False,
            "paths": "project-relative only",
        },
        "source_file_hashes": source_hashes,
        "source_tree_sha256": sha256_bytes(canonical_json(source_hashes)),
        "validation_sha256": sha256_bytes((root / VALIDATION_PATH).read_bytes()),
        "evidence_chain": science["checks"]["completed_chain"],
        "scientific_readiness": {
            "question": (
                "Does the independent-monitor gate reduce physical adverse events in the "
                "equal-weight primary-bias/dropout challenge population without exceeding a "
                "5% gate-induced hold-loss probability?"
            ),
            "claim_boundary": (
                "deterministic planar HCW assurance; no AI-policy, prevalence, flight-safety, "
                "6-DoF, or HIL claim"
            ),
            "architecture_discordance_capable": science["checks"]
            ["architecture_and_event_capability"]["configuration_command_discordance_capable"],
            "forced_physical_fixtures_in_scientific_population": False,
        },
        "design": {
            "configurations": list(study.configurations),
            "strata": list(study.strata),
            "primary_strata": list(study.primary_strata),
            "roots_by_stratum": study.roots_by_stratum,
            "paired_blocks": study.planned_blocks,
            "episodes": study.planned_episodes,
            "replay_blocks": study.replay_blocks,
            "replay_episodes": study.replay_episodes,
        },
        "analysis_contract": {
            "primary_estimand": (
                "equal-weight P04/P05 gate-minus-reference risk difference for collision OR "
                "unauthorized keep-out entry OR corridor departure"
            ),
            "H1": (
                "exact one-sided paired discordance superiority at alpha 0.025 plus observed "
                "risk difference <= -0.05"
            ),
            "H2": (
                "gatekept exact one-sided gate-induced hold-loss risk below 0.05 at alpha 0.025"
            ),
            "secondary_inferential_family": None,
            "missing_or_infrastructure_failure": (
                "any occurrence invalidates inference; no retry, replacement, extension, or "
                "imputation"
            ),
        },
        "sample_size": science["checks"]["sample_size"],
        "seed_reservation": {
            **science["checks"]["seed_contract"],
            "state_at_freeze": "reserved_not_materialized_or_executed",
            "generator_available": True,
            "generator_invoked": False,
            "materialization_requires_exact_freeze_and_readiness": True,
        },
        "partition_44": science["checks"]["partition_44_unmaterialized"],
        "dependency_runtime_identity": science["checks"]["dependency_runtime_identity"],
        "publication_privacy_scan": science["checks"]["publication_privacy"],
        "partition_43_effect_estimate_used": False,
        "partition_44_materialized": False,
        "confirmatory_outcomes_executed": False,
        "confirmatory_outcome_rows_created": False,
        "learned_policy_trained_or_claimed": False,
        "readiness_policy": "fail closed; no critical-check waiver",
    }
    unsigned["freeze_id"] = sha256_bytes(canonical_json(unsigned))
    (root / FREEZE_PATH).write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    readiness = {
        "schema_version": study.schema_version,
        "freeze_id": unsigned["freeze_id"],
        "status": "READY_FOR_CONFIRMATORY_EXECUTION",
        "scope": "one-time 2,904-episode Experiment 004 confirmatory assurance campaign",
        "partition_code": study.confirmatory_partition_code,
        "partition_state": "reserved_not_materialized_or_executed",
        "paired_blocks": study.planned_blocks,
        "episodes": study.planned_episodes,
        "replay_blocks": study.replay_blocks,
        "replay_episodes": study.replay_episodes,
        "confirmatory_seeds_materialized": False,
        "confirmatory_outcomes_executed": False,
        "next_task": "one-time Experiment 004 confirmatory execution",
        "next_command": (
            "uv run python -m kri_space_autonomy.experiment_004_confirmatory.workflow "
            "execute-confirmatory-once"
        ),
    }
    readiness["readiness_id"] = sha256_bytes(canonical_json(readiness))
    (root / READINESS_PATH).write_text(
        json.dumps(readiness, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    verification = verify_freeze(root, require_unmaterialized=True, recompute_science=False)
    if not verification["passed"]:
        raise RuntimeError("confirmatory freeze failed internal verification")
    return {**unsigned, "readiness": readiness, "verification": verification}


def verify_freeze(
    root: Path,
    *,
    require_unmaterialized: bool = True,
    recompute_science: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = _self_hashed(root / FREEZE_PATH, "freeze_id")
        readiness = _self_hashed(root / READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"freeze_load:{exc}"]}
    for relative, expected in manifest.get("source_file_hashes", {}).items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(relative)
    validation = root / VALIDATION_PATH
    if (
        not validation.is_file()
        or sha256_bytes(validation.read_bytes()) != manifest.get("validation_sha256")
    ):
        errors.append("validation_identity")
    if not (
        readiness.get("freeze_id") == manifest.get("freeze_id")
        and readiness.get("status") == "READY_FOR_CONFIRMATORY_EXECUTION"
        and readiness.get("partition_code") == 44
        and readiness.get("episodes") == 2904
    ):
        errors.append("readiness_identity")
    study = load_confirmatory_config(root / CONFIG_PATH)
    if require_unmaterialized:
        seed_contract = validate_seed_contract(
            study,
            root / SEED_CONTRACT_PATH,
            root=root,
        )
        partition = verify_partition_44_unmaterialized(root)
        if not seed_contract["passed"]:
            errors.append("seed_contract")
        if not partition["passed"]:
            errors.append("partition_44_state")
    else:
        seed_contract = {
            "passed": True,
            "contract_sha256": sha256_bytes((root / SEED_CONTRACT_PATH).read_bytes()),
            "state": "materialized_only_after_verified_freeze",
        }
        partition = {"passed": True, "state": "materialized_execution_phase"}
    if recompute_science and require_unmaterialized:
        science = run_preoutcome_checks(
            root,
            study,
            seed_contract_path=SEED_CONTRACT_PATH,
        )
        if not science["passed"]:
            errors.append("fail_closed_science_or_integrity")
    else:
        saved = json.loads(validation.read_text(encoding="utf-8"))
        saved_science = next(
            check
            for check in saved["checks"]
            if check["id"] == "fail_closed_scientific_and_integrity_checks"
        )
        science = saved_science["observed"]
        if not saved_science["passed"]:
            errors.append("saved_fail_closed_science_or_integrity")
    publication = publication_privacy(root)
    if not publication["passed"]:
        errors.append("publication_privacy")
    return {
        "schema_version": study.schema_version,
        "verified_at_utc": datetime.now(UTC).isoformat(),
        "passed": not errors,
        "status": "READY_FOR_CONFIRMATORY_EXECUTION" if not errors else "NOT_READY",
        "errors_preview": errors[:30],
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "source_files_verified": len(manifest.get("source_file_hashes", {})),
        "seed_contract": seed_contract,
        "partition_44": partition,
        "science_and_integrity": science,
        "publication_privacy": publication,
        "require_unmaterialized": require_unmaterialized,
    }


def _replay_after_execution(
    root: Path,
    study: ConfirmatoryConfig,
    pilot: Any,
    foundation: Any,
    cases: tuple[Any, ...],
    freeze_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    replay = json.loads((root / SEED_DIRECTORY / REPLAY_NAME).read_text(encoding="utf-8"))
    selected = set(replay["root_seed_ids"])
    scenarios = [
        _scenario_from_row(json.loads(line))
        for line in (root / SEED_DIRECTORY / MANIFEST_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
        if json.loads(line)["root_seed_id"] in selected
    ]
    original = [row for row in rows if row["root_seed_id"] in selected]
    case_map = {case.id: case for case in cases}
    replayed = []
    for scenario in scenarios:
        replayed.extend(
            run_confirmatory_block(
                study,
                pilot,
                foundation,
                case_map[scenario.case_id],
                scenario,
                freeze_id=freeze_id,
            )
        )
    first = sha256_bytes(canonical_json(original))
    second = sha256_bytes(canonical_json(replayed))
    return {
        "passed": bool(
            len(scenarios) == study.replay_blocks
            and len(original) == len(replayed) == study.replay_episodes
            and first == second
        ),
        "blocks": len(scenarios),
        "episodes": len(replayed),
        "original_digest": first,
        "replay_digest": second,
    }


def execute_once(root: Path) -> dict[str, Any]:
    verification = verify_freeze(root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError("confirmatory freeze verification failed before one-time execution")
    study = load_confirmatory_config(root / CONFIG_PATH)
    pilot = load_pilot_config(root / PILOT_CONFIG_PATH)
    foundation = load_config(root / FOUNDATION_CONFIG_PATH)
    cases = load_confirmatory_cases(root / PILOT_MATRIX_PATH, study=study)
    index = materialize_confirmatory_seeds(
        study,
        pilot,
        foundation,
        cases,
        root=root,
        freeze_id=verification["freeze_id"],
        readiness_id=verification["readiness_id"],
        seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
    )
    seeds = validate_materialized_confirmatory_seeds(
        study,
        pilot,
        foundation,
        cases,
        root=root,
        freeze_id=verification["freeze_id"],
        readiness_id=verification["readiness_id"],
        seed_contract_sha256=verification["seed_contract"]["contract_sha256"],
    )
    if not seeds["passed"]:
        raise RuntimeError("materialized partition-44 schedule failed exact validation")
    execution = run_confirmatory_campaign(
        study,
        pilot,
        foundation,
        cases,
        seed_manifest_path=root / SEED_DIRECTORY / MANIFEST_NAME,
        output_path=root / EPISODES_PATH,
        freeze_id=verification["freeze_id"],
    )
    execution = {
        **execution,
        "schema_version": study.schema_version,
        "freeze_id": verification["freeze_id"],
        "readiness_id": verification["readiness_id"],
        "seed_index": index,
    }
    (root / EXECUTION_PATH).write_text(
        json.dumps(execution, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    rows = load_episode_rows(root / EPISODES_PATH)
    seed_rows = [
        json.loads(line)
        for line in (root / SEED_DIRECTORY / MANIFEST_NAME)
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    analysis = analyze_confirmatory_rows(rows, seed_rows, study)
    (root / ANALYSIS_PATH).write_text(
        json.dumps(analysis, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    replay = _replay_after_execution(
        root,
        study,
        pilot,
        foundation,
        cases,
        verification["freeze_id"],
        rows,
    )
    reproducibility = {
        "schema_version": study.schema_version,
        "freeze_id": verification["freeze_id"],
        "passed": replay["passed"] and seeds["passed"],
        "seed_validation": seeds,
        "outcome_blind_replay": replay,
    }
    (root / REPRODUCIBILITY_PATH).write_text(
        json.dumps(reproducibility, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    outputs = (EPISODES_PATH, EXECUTION_PATH, ANALYSIS_PATH, REPRODUCIBILITY_PATH)
    (root / CHECKSUMS_PATH).write_text(
        "\n".join(
            f"{sha256_bytes((root / path).read_bytes())}  {path.name}" for path in outputs
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "passed": bool(reproducibility["passed"] and analysis["validity"]["passed"]),
        "decision": analysis["decision"],
        "blocks": execution["blocks"],
        "episodes": execution["episodes"],
        "replay": replay,
        "one_time_execution": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment 004 confirmatory assurance workflow")
    parser.add_argument(
        "command",
        choices=(
            "validate",
            "freeze",
            "verify-freeze",
            "execute-confirmatory-once",
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
    elif args.command == "execute-confirmatory-once":
        result = execute_once(root)
    else:
        result = publication_privacy(root)
    if not result.get("passed", True):
        raise SystemExit(1)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
