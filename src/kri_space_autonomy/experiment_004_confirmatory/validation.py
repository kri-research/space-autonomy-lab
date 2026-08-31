from __future__ import annotations

import ast
import inspect
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.control import (
    DeterministicHoldController,
    EstimatedGeometryMonitor,
    observation_from_snapshot,
)
from kri_space_autonomy.experiment_004.estimator import (
    FilterHealth,
    FilterReason,
    PlanarNavigationFilter,
)
from kri_space_autonomy.experiment_004.seeds import canonical_json, sha256_bytes
from kri_space_autonomy.experiment_004.validation import run_foundation_checks
from kri_space_autonomy.experiment_004_pilot.config import (
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_004_pilot.runner import _nominal_control, run_block
from kri_space_autonomy.experiment_004_pilot.seeds import test_fixture_scenario
from kri_space_autonomy.experiment_004_pilot.validation import (
    historical_integrity,
    information_boundary,
    publication_privacy,
    runtime_identity,
)
from kri_space_autonomy.experiment_004_pilot.workflow import verify_replay

from .analysis import analyze_confirmatory_rows, exact_primary_sample_size
from .config import (
    CONFIGURATIONS,
    EXPECTED_BASE,
    FOUNDATION_FREEZE_ID,
    FOUNDATION_READINESS_ID,
    PILOT_FREEZE_ID,
    PILOT_READINESS_ID,
    ConfirmatoryConfig,
)
from .seeds import validate_seed_contract

FOUNDATION_FREEZE_PATH = Path("experiments/004/freeze-manifest.json")
FOUNDATION_READINESS_PATH = Path("experiments/004/readiness.json")
PILOT_FREEZE_PATH = Path("experiments/004-pilot/freeze-manifest.json")
PILOT_READINESS_PATH = Path("experiments/004-pilot/readiness.json")
PILOT_RESULTS = Path("results/experiment-004-pilot")
PILOT_EPISODES = PILOT_RESULTS / "pilot-episodes.jsonl"
PILOT_RESULT_VERIFICATION = PILOT_RESULTS / "result-verification.json"
PILOT_QC = PILOT_RESULTS / "qc.json"
PILOT_CHECKSUMS = PILOT_RESULTS / "checksums.sha256"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _self_hash(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    if sha256_bytes(canonical_json(value)) != identity:
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def _verify_declared_hashes(root: Path, manifest: dict[str, Any]) -> list[str]:
    mismatches = []
    for relative, expected in manifest["source_file_hashes"].items():
        path = root / relative
        actual = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            mismatches.append(relative)
    return mismatches


def _verify_checksum_file(directory: Path, checksum_path: Path) -> list[str]:
    errors = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        candidate = directory / name
        actual = sha256_bytes(candidate.read_bytes()) if candidate.is_file() else None
        if actual != expected:
            errors.append(name)
    return errors


def verify_completed_chain(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        foundation = _self_hash(root / FOUNDATION_FREEZE_PATH, "freeze_id")
        foundation_ready = _self_hash(root / FOUNDATION_READINESS_PATH, "readiness_id")
        pilot = _self_hash(root / PILOT_FREEZE_PATH, "freeze_id")
        pilot_ready = _self_hash(root / PILOT_READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"identity_load:{exc}"]}
    identities = {
        "foundation_freeze_id": foundation["freeze_id"],
        "foundation_readiness_id": foundation_ready["readiness_id"],
        "pilot_freeze_id": pilot["freeze_id"],
        "pilot_readiness_id": pilot_ready["readiness_id"],
    }
    expected_identities = {
        "foundation_freeze_id": FOUNDATION_FREEZE_ID,
        "foundation_readiness_id": FOUNDATION_READINESS_ID,
        "pilot_freeze_id": PILOT_FREEZE_ID,
        "pilot_readiness_id": PILOT_READINESS_ID,
    }
    if identities != expected_identities:
        errors.append("freeze_or_readiness_identity")
    if (
        foundation_ready.get("freeze_id") != foundation.get("freeze_id")
        or pilot_ready.get("freeze_id") != pilot.get("freeze_id")
    ):
        errors.append("readiness_binding")
    frozen_mismatches = {
        "foundation": _verify_declared_hashes(root, foundation),
        "pilot_design": _verify_declared_hashes(root, pilot),
    }
    if any(frozen_mismatches.values()):
        errors.append("frozen_source_hashes")
    result_checksum_errors = _verify_checksum_file(
        root / PILOT_RESULTS,
        root / PILOT_CHECKSUMS,
    )
    if result_checksum_errors:
        errors.append("pilot_result_checksums")
    rows = [
        json.loads(line)
        for line in (root / PILOT_EPISODES).read_text(encoding="utf-8").splitlines()
    ]
    cells: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        cells.setdefault((row["case_id"], row["root_seed_id"]), set()).add(
            row["configuration_id"]
        )
    cases = {row["case_id"] for row in rows}
    counts_pass = bool(
        len(rows) == 88
        and len(cells) == 44
        and len(cases) == 11
        and all(configurations == set(CONFIGURATIONS) for configurations in cells.values())
        and all(
            sum(row["case_id"] == case for row in rows) == 8
            for case in cases
        )
        and sum(bool(row["infrastructure_failure"]) for row in rows) == 0
    )
    if not counts_pass:
        errors.append("pilot_counts_or_infrastructure")
    replay = verify_replay(root)
    if not (
        replay["passed"]
        and replay["blocks"] == 11
        and replay["episodes"] == 22
        and replay["original_digest"] == replay["replay_digest"]
    ):
        errors.append("pilot_replay")
    verification = json.loads(
        (root / PILOT_RESULT_VERIFICATION).read_text(encoding="utf-8")
    )
    qc = json.loads((root / PILOT_QC).read_text(encoding="utf-8"))
    gates_pass = bool(
        verification.get("passed")
        and verification.get("overall_decision") == "pilot_design_gates_passed"
        and all(verification.get("checks", {}).values())
        and qc.get("overall_passed")
        and all(check.get("passed") for check in qc.get("checks", {}).values())
    )
    if not gates_pass:
        errors.append("pilot_frozen_gates")
    historical = historical_integrity(root)
    if not historical["passed"]:
        errors.append("historical_experiment_001_003_integrity")
    frozen_prefixes = (
        "src/kri_space_autonomy/experiment_001",
        "src/kri_space_autonomy/experiment_002",
        "src/kri_space_autonomy/experiment_003",
        "src/kri_space_autonomy/experiment_004/",
        "src/kri_space_autonomy/experiment_004_pilot/",
        "experiments/001",
        "experiments/002",
        "experiments/003",
        "experiments/004/",
        "experiments/004-pilot/",
        "results/",
        "docs/experiment-001",
        "docs/experiment-002",
        "docs/experiment-003",
        "docs/experiment-004.md",
        "docs/experiment-004-pilot.md",
        "artifacts/experiment-002",
    )
    changed = _git(root, "diff", "--name-only", EXPECTED_BASE, "--", *frozen_prefixes)
    changed_paths = [line for line in changed.splitlines() if line]
    if changed_paths:
        errors.append("historical_foundation_or_pilot_bytes_changed")
    return {
        "passed": not errors,
        "errors_preview": errors[:30],
        "identities": identities,
        "frozen_source_files_verified": {
            "foundation": len(foundation["source_file_hashes"]),
            "pilot_design": len(pilot["source_file_hashes"]),
        },
        "frozen_source_mismatches": frozen_mismatches,
        "pilot_result_checksum_files_verified": len(
            (root / PILOT_CHECKSUMS).read_text(encoding="utf-8").splitlines()
        ),
        "pilot_result_checksum_errors": result_checksum_errors,
        "pilot_counts": {
            "complete_blocks": len(cells),
            "episodes": len(rows),
            "cases": len(cases),
            "infrastructure_failures": sum(
                bool(row["infrastructure_failure"]) for row in rows
            ),
        },
        "pilot_replay": replay,
        "pilot_gate_decision": verification.get("overall_decision"),
        "all_frozen_pilot_gates_passed": gates_pass,
        "historical_integrity": historical,
        "changed_frozen_paths_from_base": changed_paths,
    }


def verify_partition_44_unmaterialized(root: Path) -> dict[str, Any]:
    paths = (
        root / "experiments/004-confirmatory/seeds",
        root / "results/experiment-004-confirmatory",
    )
    present = [path.relative_to(root).as_posix() for path in paths if path.exists()]
    root_rows = []
    for path in root.glob("**/*.jsonl"):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if "experiment004:44:" in line:
                root_rows.append(f"{path.relative_to(root)}:{line_number}")
    return {
        "passed": not present and not root_rows,
        "partition_code": 44,
        "seed_or_result_paths_present": present,
        "materialized_root_rows": root_rows[:20],
        "generator_invoked": False,
        "outcomes_executed": False,
    }


def architecture_capability(root: Path) -> dict[str, Any]:
    foundation = load_config(root / "experiments/004/config.json")
    pilot = load_pilot_config(root / "experiments/004-pilot/config.json")
    cases = load_case_matrix(root / "experiments/004-pilot/case-matrix.json")
    forced_checks: dict[str, bool] = {}
    for case_id in (
        "P01_forced_collision",
        "P02_forced_keep_out_only",
        "P03_forced_corridor_departure",
    ):
        case = next(item for item in cases if item.id == case_id)
        scenario, _ = test_fixture_scenario(pilot, foundation, case, 0)
        first = [row.to_dict() for row in run_block(pilot, foundation, case, scenario)]
        replayed = [row.to_dict() for row in run_block(pilot, foundation, case, scenario)]
        expected = {
            "P01_forced_collision": all(
                row["physical_collision"] and row["physical_keep_out_entry"]
                for row in first
            ),
            "P02_forced_keep_out_only": all(
                not row["physical_collision"] and row["physical_keep_out_entry"]
                for row in first
            ),
            "P03_forced_corridor_departure": all(
                not row["physical_collision"]
                and not row["physical_keep_out_entry"]
                and row["physical_corridor_departure"]
                for row in first
            ),
        }[case_id]
        forced_checks[case_id] = bool(first == replayed and expected)
    base = PlanarNavigationFilter(foundation).snapshot()
    covariance = np.diag([0.01, 0.01, 0.0001, 0.0001])
    valid = replace(
        base,
        covariance=covariance,
        health=FilterHealth.VALID,
        reason=FilterReason.NONE,
        prediction_only_age_s=0.0,
        consecutive_innovation_rejections=0,
    )
    monitor_snapshot = replace(
        valid,
        mean=np.array([9.9999, -100.0, 0.02, 0.12], dtype=np.float64),
    )
    primary_snapshot = replace(
        valid,
        mean=np.array([17.9999, -100.0, 0.02, 0.12], dtype=np.float64),
    )
    controller = DeterministicHoldController(foundation)
    monitor = EstimatedGeometryMonitor(
        foundation,
        DeterministicHoldController(foundation),
        controller.controller_identity,
    )
    proposal = controller.decide(observation_from_snapshot(primary_snapshot))
    decision = monitor.gate(monitor_snapshot, proposal)
    structural_discordance = bool(
        decision.overridden
        and decision.reason == "UNCERTAINTY_AWARE_GEOMETRY"
        and not np.array_equal(
            decision.proposed_acceleration_mps2,
            decision.executed_acceleration_mps2,
        )
    )
    return {
        "passed": all(forced_checks.values()) and structural_discordance,
        "partition_941_event_fixtures": forced_checks,
        "configuration_command_discordance_capable": structural_discordance,
        "synthetic_primary_minus_monitor_radial_bias_m": 8.0,
        "confirmatory_partition_used": False,
        "confirmatory_outcomes_generated": False,
        "interpretation": (
            "mechanical capability only; no configuration effect direction or outcome rate "
            "was estimated"
        ),
    }


def information_boundaries() -> dict[str, Any]:
    pilot_boundary = information_boundary()
    signature = tuple(inspect.signature(_nominal_control).parameters)
    tree = ast.parse(inspect.getsource(_nominal_control))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    prohibited = sorted(
        names
        & {
            "latent_state",
            "truth_state",
            "scenario",
            "fault_label",
            "root_seed_id",
            "evaluator",
        }
    )
    return {
        "passed": bool(
            pilot_boundary["passed"]
            and signature
            == (
                "primary_snapshot",
                "monitor_snapshot",
                "controller",
                "monitor",
                "configuration_id",
            )
            and not prohibited
        ),
        "pilot_boundary": pilot_boundary,
        "online_signature": list(signature),
        "prohibited_online_names": prohibited,
        "truth_evaluator_returns_data_to_online_path": False,
    }


def sample_size_evidence(study: ConfirmatoryConfig) -> dict[str, Any]:
    resolution = exact_primary_sample_size(
        alpha=study.primary_one_sided_alpha,
        target_power=study.primary_target_power,
        planning_net_reduction=study.primary_planning_net_reduction,
    )
    previous_even = exact_primary_sample_size(
        alpha=study.primary_one_sided_alpha,
        target_power=0.899,
        planning_net_reduction=study.primary_planning_net_reduction,
    )
    passed = bool(
        resolution["roots"] == study.primary_roots == 1068
        and study.roots_by_stratum[study.primary_strata[0]]
        == study.roots_by_stratum[study.primary_strata[1]]
        == 534
        and resolution["achieved_power"] >= study.primary_target_power
        and previous_even["roots"] <= resolution["roots"]
    )
    return {
        "passed": passed,
        "resolution": resolution,
        "roots_per_primary_stratum": 534,
        "pilot_outcome_effect_used": False,
        "pilot_configuration_direction_used": False,
        "planning_basis": (
            "exact worst-case all-discordant paired binary calculation at a prospective "
            "10 percentage-point net reduction"
        ),
    }


def synthetic_analysis_sign_checks(study: ConfirmatoryConfig) -> dict[str, Any]:
    seed_rows = [
        {"case_id": stratum, "root_seed_id": f"synthetic:{stratum}:{replicate:04d}"}
        for stratum in study.strata
        for replicate in range(study.roots_by_stratum[stratum])
    ]

    def rows_with(*, reverse: bool = False, mission_harms: int = 0) -> list[dict[str, Any]]:
        rows = []
        primary_index = 0
        for seed in seed_rows:
            is_primary = seed["case_id"] in study.primary_strata
            for configuration in study.configurations:
                beneficial_fixture = is_primary and primary_index < 100
                reference_adverse = beneficial_fixture and not reverse
                gate_adverse = beneficial_fixture and reverse
                gate_mission_harm = (
                    is_primary
                    and primary_index < mission_harms
                    and configuration == "independent_monitor_gate"
                )
                adverse = (
                    reference_adverse
                    if configuration == "primary_reference"
                    else gate_adverse
                )
                rows.append(
                    {
                        **seed,
                        "configuration_id": configuration,
                        "physical_collision": adverse,
                        "physical_keep_out_entry": False,
                        "physical_corridor_departure": False,
                        "hold_acquired": not gate_mission_harm,
                        "infrastructure_failure": False,
                        "numerical_valid": True,
                        "primary_estimator_fault": seed["case_id"]
                        in study.primary_strata,
                        "monitor_estimator_fault": False,
                        "monitor_logic_fault": False,
                        "shared_cause_fault": False,
                        "actuation_degradation_scheduled": False,
                        "disturbance_scheduled": False,
                    }
                )
            if is_primary:
                primary_index += 1
        return rows

    favorable = analyze_confirmatory_rows(rows_with(), seed_rows, study)
    reversed_result = analyze_confirmatory_rows(rows_with(reverse=True), seed_rows, study)
    mission_fail = analyze_confirmatory_rows(
        rows_with(mission_harms=100),
        seed_rows,
        study,
    )
    h1 = favorable["primary_gatekeeping"]["H1_physical_safety"]
    h2_fail = mission_fail["primary_gatekeeping"]["H2_mission"]
    passed = bool(
        favorable["decision"] == "favorable"
        and h1["gate_minus_reference_risk_difference"] < 0.0
        and reversed_result["decision"] == "inconclusive"
        and reversed_result["primary_gatekeeping"]["H1_physical_safety"][
            "gate_minus_reference_risk_difference"
        ]
        > 0.0
        and h2_fail["status"] == "tested"
        and h2_fail["passed"] is False
    )
    return {
        "passed": passed,
        "beneficial_fixture_decision": favorable["decision"],
        "beneficial_fixture_primary_difference": h1[
            "gate_minus_reference_risk_difference"
        ],
        "reversed_fixture_decision": reversed_result["decision"],
        "mission_harm_fixture_passed": h2_fail["passed"],
        "fixtures_are_synthetic_non_outcome_rows": True,
        "partition_44_used": False,
    }


def run_preoutcome_checks(
    root: Path,
    study: ConfirmatoryConfig,
    *,
    seed_contract_path: Path,
) -> dict[str, Any]:
    foundation = run_foundation_checks(load_config(root / "experiments/004/config.json"))
    checks = {
        "completed_chain": verify_completed_chain(root),
        "partition_44_unmaterialized": verify_partition_44_unmaterialized(root),
        "hcw_reference_geometry_observability_covariance": foundation,
        "architecture_and_event_capability": architecture_capability(root),
        "information_boundaries": information_boundaries(),
        "seed_contract": validate_seed_contract(
            study,
            root / seed_contract_path,
            root=root,
        ),
        "sample_size": sample_size_evidence(study),
        "synthetic_analysis_signs": synthetic_analysis_sign_checks(study),
        "dependency_runtime_identity": runtime_identity(root),
        "publication_privacy": publication_privacy(root),
    }
    return {
        "passed": all(bool(check.get("passed")) for check in checks.values()),
        "checks": checks,
        "partition_44_materialized": False,
        "confirmatory_outcomes_executed": False,
        "pilot_outcome_direction_influenced_design": False,
        "learned_policy_claimed": False,
    }
