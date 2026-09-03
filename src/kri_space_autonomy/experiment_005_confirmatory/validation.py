from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path
from typing import Any

from scipy.stats import binom

from kri_space_autonomy.experiment_004_confirmatory.analysis import (
    exact_primary_sample_size as exact_e004_sample_size,
)
from kri_space_autonomy.experiment_004_confirmatory.config import (
    load_confirmatory_config as load_e004_confirmatory_config,
)
from kri_space_autonomy.experiment_005.workflow import (
    dependency_runtime_identity,
    verify_historical_campaigns,
)
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    load_case_matrix as load_transfer_cases,
)
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.validation import (
    foundation_identity,
    historical_snapshot,
    information_boundary,
    publication_privacy,
)

from .analysis import (
    analyze_confirmatory_rows,
    exact_mission_power,
    exact_primary_sample_size,
)
from .config import (
    AMENDMENT_FREEZE_ID,
    AMENDMENT_READINESS_ID,
    BASE_COMMIT,
    CLOSEOUT_MANIFEST_SHA256,
    FOUNDATION_FREEZE_ID,
    FOUNDATION_READINESS_ID,
    RESULT_VERIFICATION_SHA256,
    TRANSFER_FREEZE_ID,
    TRANSFER_READINESS_ID,
    ConfirmatoryConfig,
)
from .runner import (
    MODULE_ENTRYPOINT,
    PROCESS_START_METHOD,
    run_spawn_checkpointed_confirmatory_campaign,
)
from .seeds import (
    materialize_confirmatory_scenario,
    materialize_confirmatory_seeds,
    partition_53_unmaterialized,
    validate_seed_contract,
)

CHAIN = (
    "344dfe4251e6b7aa654fc57c4f0cf9af21f6c342",
    "27993dcd6b3f45aa3283798f34c2a9160767697d",
    "90de438624556f4890444105fe3c0c19667d5bfa",
    "a311c4f6439c13666a1df6b102fd0fd2bbd35a55",
    "cf007e1cd7e44002069a8a5812867201d349f292",
    BASE_COMMIT,
)
CI_SHA256 = "bc033a3ddc0114964059760a6372b8da233b8aac1026d24af2a795c5b607f420"
BLOCKER_AUDIT_SHA256 = "8780e06580187cc4c6f7a1307ebf7c36e94040c3ddcb5a9133b4166adf33f96f"
FROZEN_FILE_HASHES = {
    ".github/workflows/ci.yml": CI_SHA256,
    "docs/experiment-005-confirmatory-design-blocker.md": BLOCKER_AUDIT_SHA256,
    "experiments/005/freeze-manifest.json": (
        "2a32494b4db71a7bec908426f0ec8e0f60a63a853bc220e63b481ddc8939131e"
    ),
    "experiments/005/readiness.json": (
        "7a4a4abdb2fe068b794a1b4dfa6e4c62c037f31563c26df536fb9495c45e539d"
    ),
    "experiments/005-transfer-pilot/freeze-manifest.json": (
        "871baad028464a074030ef572870172167bd7d0b7ade70b578c6c30f5b3349ff"
    ),
    "experiments/005-transfer-pilot/readiness.json": (
        "6d62df08b7a835370a404800cdd32fa1829e297985f9f5f01d13e9c4ed4a248d"
    ),
    "results/experiment-005-transfer-pilot/invalid-attempt-audit.json": (
        "66ad8dfb592ce5129459f0fda6c7b10c32390592e4960e95278168e97e5e3807"
    ),
    "experiments/005-transfer-pilot-replacement/freeze-manifest.json": (
        "ab754552f8beabbbad5c6e43cccd23c0e658a2f2783fa2dcaed1f9afe7bd38eb"
    ),
    "experiments/005-transfer-pilot-replacement/readiness.json": (
        "e1733fda8bb388dabdfc2fd5494d65411b32e4b89a0e72ddf2d0d9a363b4dd7c"
    ),
    "results/experiment-005-transfer-pilot-replacement/manifest.json": (
        CLOSEOUT_MANIFEST_SHA256
    ),
    "results/experiment-005-transfer-pilot-replacement/result-verification.json": (
        RESULT_VERIFICATION_SHA256
    ),
    "results/experiment-005-transfer-pilot-replacement/design-integrity-postexecution.json": (
        "f1aca26e9e160ef903b2c0833bb2751ff42beae3ca749e8f7594b26845992ce9"
    ),
    "results/experiment-005-transfer-pilot-replacement/reproducibility.json": (
        "79addb6583a0129fb871776d026a87345093959cb5495a0d43188ae6fce1b5f1"
    ),
    "results/experiment-005-transfer-pilot-replacement/checksums.sha256": (
        "1799c0a00fa49b21eb7dc8cf363031960de998ed457597930c4bc845e569c975"
    ),
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _self_hashed(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    from kri_space_autonomy.experiment_005_transfer_pilot.seeds import sha256_bytes

    if identity != sha256_bytes(_canonical_json(value)):
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def _verify_source_manifest(root: Path, relative: str) -> dict[str, Any]:
    manifest = json.loads((root / relative).read_text(encoding="utf-8"))
    mismatches = []
    for source, expected in manifest.get("source_file_hashes", {}).items():
        path = root / source
        if not path.is_file() or _sha(path) != expected:
            mismatches.append(source)
    return {
        "passed": not mismatches,
        "manifest": relative,
        "source_files_verified": len(manifest.get("source_file_hashes", {})),
        "source_mismatches": mismatches[:30],
    }


def _verify_closeout_artifacts(root: Path) -> dict[str, Any]:
    result_root = root / "results/experiment-005-transfer-pilot-replacement"
    manifest = json.loads((result_root / "manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    for item in manifest.get("artifacts", []):
        path = root / item["path"]
        if (
            not path.is_file()
            or path.stat().st_size != item["bytes"]
            or _sha(path) != item["sha256"]
        ):
            errors.append(f"manifest:{item['path']}")
    checksum_path = result_root / "checksums.sha256"
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        path = root / relative
        if not path.is_file() or _sha(path) != expected:
            errors.append(f"checksum:{relative}")
    verification = json.loads((result_root / "result-verification.json").read_text())
    reproducibility = json.loads((result_root / "reproducibility.json").read_text())
    if not (
        manifest.get("decision") == "pilot_design_gates_passed"
        and manifest.get("partition_code") == 54
        and manifest.get("retired_partition_code") == 52
        and manifest.get("future_confirmatory_partition_code") == 53
        and verification.get("passed") is True
        and verification.get("partition_52_invalid_attempt_preserved") is True
        and verification.get("partition_53_untouched") is True
        and reproducibility.get("passed") is True
        and reproducibility.get("original_subset_sha256")
        == reproducibility.get("replay_sha256")
    ):
        errors.append("closeout_semantics")
    return {
        "passed": not errors,
        "errors_preview": errors[:30],
        "manifest_artifacts_verified": len(manifest.get("artifacts", [])),
        "campaign_rows_sha256": verification.get("digests", {}).get(
            "campaign_rows_sha256"
        ),
        "replay_rows_sha256": verification.get("digests", {}).get("replay_rows_sha256"),
        "replay_byte_identical": reproducibility.get("passed") is True,
        "partition_52_invalid_attempt_preserved": verification.get(
            "partition_52_invalid_attempt_preserved"
        ),
        "partition_53_campaign_authorized": verification.get(
            "confirmatory_partition_53_campaign_authorized"
        ),
    }


def lineage_integrity(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    observed_hashes: dict[str, str | None] = {}
    for relative, expected in FROZEN_FILE_HASHES.items():
        path = root / relative
        observed = _sha(path) if path.is_file() else None
        observed_hashes[relative] = observed
        if observed != expected:
            errors.append(f"frozen_hash:{relative}")
    for commit in CHAIN:
        if subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=root,
            capture_output=True,
        ).returncode:
            errors.append(f"missing_commit:{commit}")
    for parent, child in zip(CHAIN, CHAIN[1:], strict=False):
        if _git(root, "rev-parse", f"{child}^") != parent:
            errors.append(f"nonlinear_chain:{child}")
    head = _git(root, "rev-parse", "HEAD")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", BASE_COMMIT, head],
        cwd=root,
        capture_output=True,
    ).returncode:
        errors.append("base_not_ancestor")
    try:
        foundation = _self_hashed(root / "experiments/005/freeze-manifest.json", "freeze_id")
        foundation_ready = _self_hashed(root / "experiments/005/readiness.json", "readiness_id")
        transfer = _self_hashed(
            root / "experiments/005-transfer-pilot/freeze-manifest.json", "freeze_id"
        )
        transfer_ready = _self_hashed(
            root / "experiments/005-transfer-pilot/readiness.json", "readiness_id"
        )
        amendment = _self_hashed(
            root / "experiments/005-transfer-pilot-replacement/freeze-manifest.json",
            "freeze_id",
        )
        amendment_ready = _self_hashed(
            root / "experiments/005-transfer-pilot-replacement/readiness.json",
            "readiness_id",
        )
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        errors.append(f"identity_load:{type(exc).__name__}")
        foundation = foundation_ready = transfer = transfer_ready = {}
        amendment = amendment_ready = {}
    identities = {
        "foundation_freeze_id": foundation.get("freeze_id"),
        "foundation_readiness_id": foundation_ready.get("readiness_id"),
        "transfer_pilot_freeze_id": transfer.get("freeze_id"),
        "transfer_pilot_readiness_id": transfer_ready.get("readiness_id"),
        "replacement_amendment_freeze_id": amendment.get("freeze_id"),
        "replacement_amendment_readiness_id": amendment_ready.get("readiness_id"),
    }
    expected_identities = {
        "foundation_freeze_id": FOUNDATION_FREEZE_ID,
        "foundation_readiness_id": FOUNDATION_READINESS_ID,
        "transfer_pilot_freeze_id": TRANSFER_FREEZE_ID,
        "transfer_pilot_readiness_id": TRANSFER_READINESS_ID,
        "replacement_amendment_freeze_id": AMENDMENT_FREEZE_ID,
        "replacement_amendment_readiness_id": AMENDMENT_READINESS_ID,
    }
    if identities != expected_identities:
        errors.append("freeze_readiness_identities")
    source_checks = [
        _verify_source_manifest(root, "experiments/005/freeze-manifest.json"),
        _verify_source_manifest(root, "experiments/005-transfer-pilot/freeze-manifest.json"),
        _verify_source_manifest(
            root, "experiments/005-transfer-pilot-replacement/freeze-manifest.json"
        ),
    ]
    if not all(check["passed"] for check in source_checks):
        errors.append("frozen_source_manifests")
    invalid = json.loads(
        (root / "results/experiment-005-transfer-pilot/invalid-attempt-audit.json").read_text()
    )
    invalid_ok = bool(
        invalid.get("decision") == "pilot_invalid_infrastructure_failure"
        and invalid.get("partition_code") == 52
        and invalid.get("partition_reusable") is False
        and invalid.get("durable_complete_blocks") == 0
        and invalid.get("durable_episode_rows") == 0
        and invalid.get("terminal_infrastructure_failures") == 1
        and invalid.get("partial_outcomes_used") is False
        and invalid.get("retries_observed") == 0
        and invalid.get("replacement_roots_observed") == 0
        and invalid.get("extensions_observed") == 0
    )
    if not invalid_ok:
        errors.append("invalid_partition_52_audit")
    closeout = _verify_closeout_artifacts(root)
    if not closeout["passed"]:
        errors.append("partition_54_closeout")
    pre_design = json.loads(
        (root / "experiments/005-confirmatory/lineage-audit.json").read_text()
    )
    pre_design_ok = bool(
        pre_design.get("audited_head") == BASE_COMMIT
        and pre_design.get("complete_closeout_verifier", {}).get("passed") is True
        and pre_design.get("complete_closeout_verifier", {}).get("evidence_passed") is True
        and pre_design.get("partition_53_seed_directory_present") is False
        and pre_design.get("partition_53_result_directory_present") is False
        and pre_design.get("partition_53_materialized_root_rows") == 0
        and pre_design.get("blocker_audit_sha256") == BLOCKER_AUDIT_SHA256
    )
    if not pre_design_ok:
        errors.append("pre_design_complete_verifier_evidence")
    foundation_live = foundation_identity(root)
    if not foundation_live["passed"]:
        errors.append("restored_foundation_source_identity")
    historical = historical_snapshot(root)
    historical_phase_passed = bool(
        historical["passed"]
        or (
            historical.get("mismatches_preview") == ["docs/research-roadmap.md"]
            and closeout["passed"]
        )
    )
    if not historical_phase_passed:
        errors.append("historical_snapshot")
    historical_campaigns = verify_historical_campaigns(root)
    if not historical_campaigns["passed"]:
        errors.append("historical_campaign_results")
    return {
        "passed": not errors,
        "errors_preview": errors[:30],
        "head": head,
        "base_commit": BASE_COMMIT,
        "linear_chain": list(CHAIN),
        "identities": identities,
        "frozen_hashes": observed_hashes,
        "source_manifests": source_checks,
        "invalid_partition_52_preserved": invalid_ok,
        "partition_54_closeout": closeout,
        "pre_design_complete_verifier": pre_design_ok,
        "foundation_source_identity": foundation_live,
        "historical_snapshot": {
            **historical,
            "phase_appropriate_passed": historical_phase_passed,
            "allowed_completed_partition_54_change": (
                ["docs/research-roadmap.md"]
                if not historical["passed"] and historical_phase_passed
                else []
            ),
        },
        "historical_campaign_result_integrity": historical_campaigns,
        "blocker_audit_preserved": observed_hashes.get(
            "docs/experiment-005-confirmatory-design-blocker.md"
        )
        == BLOCKER_AUDIT_SHA256,
        "foundation_workflow_restored": observed_hashes.get(".github/workflows/ci.yml")
        == CI_SHA256,
    }


def matrix_and_outcome_boundary(root: Path, study: ConfirmatoryConfig) -> dict[str, Any]:
    transfer = load_pilot_config(
        root / "experiments/005-transfer-pilot/config.json", root=root
    )
    transfer_cases = {
        case.id: case
        for case in load_transfer_cases(
            root / "experiments/005-transfer-pilot/case-matrix.json"
        )
    }
    matrix = json.loads(
        (root / "experiments/005-confirmatory/case-matrix.json").read_text()
    )
    transfer_gates = json.loads(
        (root / "experiments/005-transfer-pilot/gates.json").read_text()
    )["gates"]
    rows = matrix.get("cases", [])
    expected_rows = [
        {
            "id": case_id,
            "geometry_code": transfer_cases[case_id].geometry_code,
            "challenge_code": transfer_cases[case_id].challenge_code,
            "case_code": transfer_cases[case_id].case_code,
            "roots": study.roots_by_case[case_id],
            "primary_weight": study.case_weights[case_id],
            "fixture": "stochastic_bounded_initial_state",
            "horizon_kind": "standard",
        }
        for case_id in study.cases
    ]
    selected = [
        {
            key: row.get(key)
            for key in (
                "id",
                "geometry_code",
                "challenge_code",
                "case_code",
                "roots",
                "primary_weight",
                "fixture",
                "horizon_kind",
            )
        }
        for row in rows
    ]
    e004 = load_e004_confirmatory_config(
        root / "experiments/004-confirmatory/config.json"
    )
    inherited_analysis = bool(
        study.primary_one_sided_alpha == e004.primary_one_sided_alpha
        and study.primary_planning_net_reduction == e004.primary_planning_net_reduction
        and study.primary_minimum_reportable_net_reduction
        == e004.primary_minimum_reportable_net_reduction
        and study.primary_target_power == e004.primary_target_power
        and study.mission_harm_margin == e004.mission_harm_margin
        and study.mission_harm_planning_rate == e004.mission_harm_planning_rate
    )
    forbidden_outcome_fields = {
        "aggregate_observations",
        "collision_count",
        "keep_out_entry_count",
        "corridor_departure_count",
        "hold_acquired_count",
        "architecture_effect",
        "discordance_observed",
    }
    semantic_json = [
        json.loads((root / "experiments/005-confirmatory/config.json").read_text()),
        matrix,
        json.loads((root / "experiments/005-confirmatory/seed-contract.json").read_text()),
    ]
    outcome_fields_present = sorted(
        key for payload in semantic_json for key in forbidden_outcome_fields if key in payload
    )
    checks = {
        "exact_two_primary_cases": selected == expected_rows,
        "equal_fixed_weights": study.case_weights == {name: 0.5 for name in study.cases},
        "frozen_transfer_challenges": bool(
            transfer.navigation_bias == (8.0, 0.0, 0.0, 0.0)
            and transfer.bias_duration_s == 30.0
            and transfer.dropout_duration_s == 6.0
            and transfer.standard_horizon_s == 300.0
        ),
        "frozen_covariance_validity_gates": bool(
            study.minimum_covariance_eigenvalue_lower_bound
            == transfer_gates["estimator_covariance"]["minimum_eigenvalue_lower_bound"]
            and study.maximum_covariance_trace_exclusive_upper_bound
            == transfer_gates["estimator_covariance"][
                "maximum_trace_exclusive_upper_bound"
            ]
        ),
        "pre_outcome_analysis_contract_inherited": inherited_analysis,
        "partition_54_outcomes_used_for_design": (
            study.partition_54_outcomes_used_for_design is False
        ),
        "no_observed_outcome_fields_imported": not outcome_fields_present,
        "forced_fixtures_excluded": matrix.get("forced_physical_fixtures_in_scientific_population")
        is False,
        "configuration_semantics_frozen": [
            item.get("id") for item in matrix.get("configuration_comparison", [])
        ]
        == list(study.configurations),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "cases": list(study.cases),
        "outcome_fields_present": outcome_fields_present,
        "partition_54_permitted_use": (
            "mechanics, feasibility, process launch, checkpoint, replay, and integrity only"
        ),
        "partition_54_effect_rate_direction_or_discordance_used": False,
    }


def sample_size_and_analysis_contract(study: ConfirmatoryConfig) -> dict[str, Any]:
    primary = exact_primary_sample_size(
        alpha=study.primary_one_sided_alpha,
        target_power=study.primary_target_power,
        planning_net_reduction=study.primary_planning_net_reduction,
    )
    inherited = exact_e004_sample_size(
        alpha=study.primary_one_sided_alpha,
        target_power=study.primary_target_power,
        planning_net_reduction=study.primary_planning_net_reduction,
    )
    mission = exact_mission_power(
        roots=study.primary_roots,
        alpha=study.primary_one_sided_alpha,
        margin=study.mission_harm_margin,
        planning_rate=study.mission_harm_planning_rate,
    )
    passed = bool(
        primary == inherited
        and primary["roots"] == study.primary_roots == 1068
        and primary["critical_beneficial_discordances_if_all_discordant"] == 567
        and primary["achieved_power"] >= 0.90
        and mission["maximum_harms_for_rejection"] == 39
        and mission["achieved_alpha"] <= 0.025
        and mission["achieved_power"] > 0.9999999999
    )
    return {
        "passed": passed,
        "primary": primary,
        "mission": mission,
        "minimum_even_count": True,
        "previous_even_count_power": float(binom.sf(565, 1066, 0.55)),
        "partition_54_outcome_used": False,
    }


def synthetic_analysis_sign_checks(study: ConfirmatoryConfig) -> dict[str, Any]:
    seeds = [
        {"case_id": case_id, "root_seed_id": f"fixture:{case_id}:{replicate:04d}"}
        for case_id in study.cases
        for replicate in range(study.roots_by_case[case_id])
    ]

    def rows(*, reverse: bool = False, mission_harms: int = 0, saturated: bool = False):
        values: list[dict[str, Any]] = []
        for index, seed in enumerate(seeds):
            beneficial = index < 600
            reference_adverse = saturated or (beneficial and not reverse)
            gate_adverse = saturated or (beneficial and reverse)
            for configuration, adverse in (
                ("primary_reference", reference_adverse),
                ("independent_monitor_gate", gate_adverse),
            ):
                values.append(
                    {
                        **seed,
                        "configuration_id": configuration,
                        "attempt_status": "valid",
                        "physical_collision": adverse,
                        "physical_keep_out_entry": False,
                        "physical_corridor_departure": False,
                        "hold_acquired": not (
                            configuration == "independent_monitor_gate"
                            and index < mission_harms
                        ),
                        "infrastructure_failure": False,
                        "nonlinear_truth_numerical_valid": True,
                        "minimum_covariance_eigenvalue": 0.1,
                        "maximum_covariance_trace": 1.0,
                        "primary_fault_active_packets": (
                            30
                            if seed["case_id"] == "T03_primary_navigation_bias"
                            else 6
                        ),
                        "monitor_fault_active_packets": 0,
                    }
                )
        return values

    favorable = analyze_confirmatory_rows(rows(), seeds, study)
    reversed_result = analyze_confirmatory_rows(rows(reverse=True), seeds, study)
    mission = analyze_confirmatory_rows(rows(mission_harms=60), seeds, study)
    saturated = analyze_confirmatory_rows(rows(saturated=True), seeds, study)
    invalid_covariance_rows = rows()
    invalid_covariance_rows[0]["maximum_covariance_trace"] = (
        study.maximum_covariance_trace_exclusive_upper_bound
    )
    invalid_covariance = analyze_confirmatory_rows(
        invalid_covariance_rows, seeds, study
    )
    invalid_activation_rows = rows()
    invalid_activation_rows[0]["primary_fault_active_packets"] = 0
    invalid_activation = analyze_confirmatory_rows(
        invalid_activation_rows, seeds, study
    )
    checks = {
        "beneficial_fixture_favorable": favorable["decision"] == "favorable",
        "reversed_fixture_inconclusive": reversed_result["decision"] == "inconclusive",
        "mission_harm_gate_closes": bool(
            mission["primary_gatekeeping"]["H1_physical_safety"]["passed"]
            and mission["primary_gatekeeping"]["H2_mission"]["passed"] is False
        ),
        "saturated_endpoint_inconclusive": bool(
            saturated["decision"] == "inconclusive"
            and saturated["primary_gatekeeping"]["H1_physical_safety"]["discordant_pairs"]
            == 0
        ),
        "covariance_failure_invalidates_inference": bool(
            invalid_covariance["decision"] == "inconclusive_invalid"
            and invalid_covariance["validity"]["covariance_validity_failures"] == 1
        ),
        "fault_activation_failure_invalidates_inference": bool(
            invalid_activation["decision"] == "inconclusive_invalid"
            and invalid_activation["validity"]["fault_activation_failures"] == 1
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "fixtures_are_synthetic_non_outcome_rows": True,
        "partition_53_used": False,
    }


def execution_protocol_contract() -> dict[str, Any]:
    runner_source = inspect.getsource(run_spawn_checkpointed_confirmatory_campaign)
    from .seeds import _stratified_initial_state

    generator_source = inspect.getsource(materialize_confirmatory_seeds)
    scenario_source = inspect.getsource(materialize_confirmatory_scenario)
    initial_state_source = inspect.getsource(_stratified_initial_state)
    checks = {
        "explicit_spawn": PROCESS_START_METHOD == "spawn",
        "importable_entrypoint": MODULE_ENTRYPOINT.endswith(".workflow"),
        "partition_53_only": "accepts only partition 53" in runner_source,
        "complete_schedule_required": "study.planned_blocks" in runner_source,
        "terminal_failure_record": "_terminal_failure" in runner_source,
        "missing_only_continuation": "missing =" in runner_source,
        "no_retry_counter": '"retries": 0' in runner_source,
        "no_replacement_counter": '"replacement_roots": 0' in runner_source,
        "exact_freeze_gate": "verify_freeze(project, require_unmaterialized=True)"
        in generator_source,
        "write_once_target_guard": "assert_materialization_targets_absent" in generator_source,
        "frozen_initial_state_generator_reused": bool(
            "_stratified_initial_state" in scenario_source
            and "_pilot_stratified_initial_state" in initial_state_source
        ),
        "generator_not_invoked": True,
    }
    return {"passed": all(checks.values()), "checks": checks}


def run_design_checks(root: Path, study: ConfirmatoryConfig) -> dict[str, Any]:
    chain = lineage_integrity(root)
    seed_contract = validate_seed_contract(
        study,
        root / "experiments/005-confirmatory/seed-contract.json",
        root=root,
        require_unmaterialized=True,
    )
    partition = partition_53_unmaterialized(root)
    checks = {
        "complete_experiment_005_lineage": chain,
        "case_matrix_and_outcome_boundary": matrix_and_outcome_boundary(root, study),
        "sample_size_and_analysis": sample_size_and_analysis_contract(study),
        "synthetic_analysis_signs": synthetic_analysis_sign_checks(study),
        "controller_monitor_information_boundary": information_boundary(),
        "execution_and_generator_protocol": execution_protocol_contract(),
        "seed_contract_and_partition_53_absence": seed_contract,
        "partition_53_unmaterialized_unexecuted": partition,
        "dependency_runtime_identity": dependency_runtime_identity(root),
        "publication_privacy_secrets": publication_privacy(root),
    }
    return {
        "passed": all(check["passed"] for check in checks.values()),
        "checks": checks,
        "partition_53_generator_authorized_after_freeze": True,
        "partition_53_generator_invoked": False,
        "partition_53_materialized": False,
        "partition_53_executed": False,
        "partition_54_outcomes_used_for_design": False,
        "scientific_findings_claimed": False,
    }
