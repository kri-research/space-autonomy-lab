from __future__ import annotations

import ast
import inspect
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_005.config import load_config as load_e005_config
from kri_space_autonomy.experiment_005.workflow import (
    dependency_runtime_identity,
    enhanced_publication_and_secret_scan,
    verify_historical_campaigns,
)

from .calibration import verify_calibration
from .config import (
    CASE_IDS,
    FOUNDATION_COMMIT,
    FOUNDATION_FREEZE_ID,
    FOUNDATION_READINESS_ID,
    TransferCase,
    TransferPilotConfig,
)
from .runner import _online_control, run_checkpointed_campaign
from .seeds import (
    materialize_pilot_seeds,
    sha256_bytes,
    test_fixture_scenario,
    validate_seed_contract,
)

FOUNDATION_FREEZE_PATH = Path("experiments/005/freeze-manifest.json")
FOUNDATION_READINESS_PATH = Path("experiments/005/readiness.json")
PILOT_CONTRACT_PATH = Path("experiments/005-transfer-pilot/seed-contract.json")
PILOT_GATES_PATH = Path("experiments/005-transfer-pilot/gates.json")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, text=True, capture_output=True
    ).stdout.strip()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def _self_hashed(path: Path, field: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    identity = value.pop(field)
    if identity != sha256_bytes(_canonical_json(value)):
        raise RuntimeError(f"self-hash mismatch: {path.as_posix()}")
    value[field] = identity
    return value


def foundation_identity(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest = _self_hashed(root / FOUNDATION_FREEZE_PATH, "freeze_id")
        readiness = _self_hashed(root / FOUNDATION_READINESS_PATH, "readiness_id")
    except (OSError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"foundation_load:{exc}"]}
    if manifest.get("freeze_id") != FOUNDATION_FREEZE_ID:
        errors.append("foundation_freeze_id")
    if readiness.get("readiness_id") != FOUNDATION_READINESS_ID:
        errors.append("foundation_readiness_id")
    if readiness.get("freeze_id") != FOUNDATION_FREEZE_ID:
        errors.append("foundation_readiness_binding")
    if readiness.get("status") != "READY_FOR_DESIGN_VALIDATION_PILOT":
        errors.append("foundation_status")
    source_mismatches = []
    for relative, expected in manifest.get("source_file_hashes", {}).items():
        path = root / relative
        observed = sha256_bytes(path.read_bytes()) if path.is_file() else None
        if observed != expected:
            source_mismatches.append(relative)
    if source_mismatches:
        errors.append("frozen_foundation_source_hashes")
    validation = root / "experiments/005/validation-evidence.json"
    if (
        not validation.is_file()
        or sha256_bytes(validation.read_bytes()) != manifest.get("validation_sha256")
    ):
        errors.append("foundation_validation_identity")
    commit_present = subprocess.run(
        ["git", "cat-file", "-e", f"{FOUNDATION_COMMIT}^{{commit}}"],
        cwd=root,
        capture_output=True,
    ).returncode == 0
    ancestor: bool | None = None
    if commit_present:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", FOUNDATION_COMMIT, "HEAD"],
            cwd=root,
            capture_output=True,
        ).returncode == 0
        if not ancestor:
            errors.append("foundation_commit_anchor")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "freeze_id": manifest.get("freeze_id"),
        "readiness_id": readiness.get("readiness_id"),
        "status": readiness.get("status"),
        "source_files_verified": len(manifest.get("source_file_hashes", {})),
        "source_mismatches": source_mismatches,
        "foundation_commit": FOUNDATION_COMMIT,
        "foundation_commit_object_present": commit_present,
        "foundation_commit_ancestor": ancestor,
        "phase_transition": {
            "historical_readiness_is_byte_identity_anchor": True,
            "historical_partition_state_is_not_reasserted_as_current": True,
            "current_partition_51_state_owned_by": (
                "experiments/005-transfer-pilot/calibration-evidence.json"
            ),
            "foundation_files_modified": False,
        },
    }


def historical_snapshot(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / FOUNDATION_FREEZE_PATH).read_text(encoding="utf-8"))
    protected = manifest["historical_protected_blob_ids"]
    mismatches = []
    for relative, object_id in protected.items():
        path = root / relative
        if not path.is_file() or _git(root, "hash-object", "--", relative) != object_id:
            mismatches.append(relative)
    return {
        "passed": not mismatches,
        "protected_files": len(protected),
        "mismatches": len(mismatches),
        "mismatches_preview": mismatches[:30],
        "historical_experiments_001_004_and_results_included": True,
    }


def matrix_and_gates(
    root: Path,
    pilot: TransferPilotConfig,
    cases: tuple[TransferCase, ...],
) -> dict[str, Any]:
    gates = json.loads((root / PILOT_GATES_PATH).read_text(encoding="utf-8"))
    domains = {case.domain for case in cases}
    required_domains = {
        "nominal_transfer",
        "model_mismatch",
        "truth_event_geometry",
        "primary_estimator",
        "monitor_estimator",
        "monitor_logic",
        "shared_cause",
        "actuation",
        "disturbance",
    }
    complete = gates.get("gates", {}).get("complete_cells", {})
    infrastructure = gates.get("gates", {}).get("infrastructure", {})
    analysis = gates.get("gates", {}).get("analysis", {})
    case_codes = {case.case_code for case in cases}
    order_coverage = {}
    foundation = load_e005_config(root / "experiments/005/config.json", root=root)
    e004 = load_e004_config(root / "experiments/004/config.json")
    for case in cases:
        first = [
            test_fixture_scenario(pilot, foundation, e004, case, replicate)[
                0
            ].configuration_run_order[0]
            for replicate in range(pilot.pilot_roots_per_case)
        ]
        order_coverage[case.id] = {
            configuration: first.count(configuration)
            for configuration in pilot.configuration_ids
        }
    passed = bool(
        tuple(case.id for case in cases) == CASE_IDS
        and len(case_codes) == len(cases) == 10
        and required_domains <= domains
        and (pilot.pilot_blocks, pilot.pilot_episodes) == (20, 40)
        and (pilot.replay_blocks, pilot.replay_episodes) == (10, 20)
        and complete
        == {
            "expected_cases": 10,
            "expected_roots_per_case": 2,
            "expected_blocks": 20,
            "expected_configurations_per_block": 2,
            "expected_episodes": 40,
            "duplicates_allowed": 0,
            "missing_allowed": 0,
            "extra_allowed": 0,
        }
        and infrastructure.get("maximum_infrastructure_failures") == 0
        and infrastructure.get("maximum_retries") == 0
        and infrastructure.get("maximum_replacement_roots") == 0
        and all(
            counts == {"primary_reference": 1, "independent_monitor_gate": 1}
            for counts in order_coverage.values()
        )
        and analysis.get("mode") == "descriptive_mechanistic_gate_only"
        and analysis.get("p_values_allowed") is False
        and analysis.get("superiority_or_noninferiority_tests_allowed") is False
        and analysis.get("architecture_effect_claims_allowed") is False
        and analysis.get("hazard_rate_claims_allowed") is False
        and analysis.get("model_mismatch_sign_interpreted_as_favorable_or_unfavorable")
        is False
    )
    return {
        "passed": passed,
        "case_ids": [case.id for case in cases],
        "domains": sorted(domains),
        "configuration_ids": list(pilot.configuration_ids),
        "blocks": pilot.pilot_blocks,
        "episodes": pilot.pilot_episodes,
        "replay_blocks": pilot.replay_blocks,
        "replay_episodes": pilot.replay_episodes,
        "within_case_order_coverage": order_coverage,
        "sample_count_basis": "design-validation coverage, not statistical power",
    }


def information_boundary() -> dict[str, Any]:
    signature = tuple(inspect.signature(_online_control).parameters)
    expected = (
        "primary_snapshot",
        "monitor_snapshot",
        "controller",
        "monitor",
        "configuration_id",
    )
    source = inspect.getsource(_online_control)
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    prohibited = sorted(
        names
        & {
            "truth",
            "truth_state",
            "relative_truth",
            "evaluator",
            "case",
            "scenario",
            "root_seed_id",
            "fault_label",
            "event_state",
        }
    )
    return {
        "passed": signature == expected and not prohibited,
        "control_function_parameters": list(signature),
        "prohibited_names_found": prohibited,
        "controller_inputs": "primary HCW navigation snapshot only",
        "monitor_inputs": "monitor HCW navigation snapshot and proposed command only",
        "physical_truth_or_event_evidence_returned_online": False,
    }


def runner_architecture_fixture(
    root: Path,
    pilot: TransferPilotConfig,
    cases: tuple[TransferCase, ...],
) -> dict[str, Any]:
    foundation = load_e005_config(root / "experiments/005/config.json", root=root)
    e004 = load_e004_config(root / "experiments/004/config.json")
    case = next(item for item in cases if item.id == "T02_truth_keep_out_crossing_fixture")
    scenarios = tuple(
        test_fixture_scenario(pilot, foundation, e004, case, replicate)[0]
        for replicate in range(2)
    )
    with tempfile.TemporaryDirectory(prefix="experiment-005-transfer-runner-") as temporary:
        directory = Path(temporary)
        serial = run_checkpointed_campaign(
            directory / "serial",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=1,
        )
        parallel = run_checkpointed_campaign(
            directory / "parallel",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=2,
        )
        interrupted = run_checkpointed_campaign(
            directory / "resume",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=1,
            stop_after_for_test=1,
        )
        resumed = run_checkpointed_campaign(
            directory / "resume",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=2,
        )
        corrupt = run_checkpointed_campaign(
            directory / "corrupt",
            pilot=pilot,
            foundation=foundation,
            e004=e004,
            cases=cases,
            scenarios=scenarios,
            workers=1,
            stop_after_for_test=1,
        )
        (directory / "corrupt/shards/cell-000000.json").write_text(
            "{}\n", encoding="utf-8"
        )
        corrupt_failed_closed = False
        try:
            run_checkpointed_campaign(
                directory / "corrupt",
                pilot=pilot,
                foundation=foundation,
                e004=e004,
                cases=cases,
                scenarios=scenarios,
                workers=1,
            )
        except RuntimeError as exc:
            corrupt_failed_closed = "checkpoint shard" in str(exc)
        worker_failure_preserved = False
        try:
            run_checkpointed_campaign(
                directory / "failure",
                pilot=pilot,
                foundation=foundation,
                e004=e004,
                cases=cases,
                scenarios=scenarios,
                workers=1,
                fail_case_id_for_test=case.id,
            )
        except RuntimeError:
            failure_files = list((directory / "failure/shards/failures").glob("*.json"))
            if len(failure_files) == 1:
                try:
                    run_checkpointed_campaign(
                        directory / "failure",
                        pilot=pilot,
                        foundation=foundation,
                        e004=e004,
                        cases=cases,
                        scenarios=scenarios,
                        workers=1,
                    )
                except RuntimeError as exc:
                    worker_failure_preserved = "terminal failed cell" in str(exc)
        serial_bytes = (directory / "serial/pilot-episodes.jsonl").read_bytes()
        parallel_bytes = (directory / "parallel/pilot-episodes.jsonl").read_bytes()
        resumed_bytes = (directory / "resume/pilot-episodes.jsonl").read_bytes()
        rows = [json.loads(line) for line in serial_bytes.splitlines()]
    event_correct = all(
        row["physical_keep_out_entry"] and not row["physical_collision"] for row in rows
    )
    checks = {
        "serial_complete": serial["passed"],
        "parallel_complete": parallel["passed"],
        "serial_parallel_byte_equivalent": serial_bytes == parallel_bytes,
        "interruption_left_one_unpublished_cell": bool(
            not interrupted["complete"] and interrupted["cells"] == 1
        ),
        "resume_missing_cells_only": bool(
            resumed["passed"]
            and resumed["completed_shards_reused"] == 1
            and resumed["new_shards_written"] == 1
        ),
        "resume_matches_fresh": resumed_bytes == serial_bytes,
        "corrupt_shard_fails_closed": corrupt_failed_closed,
        "corrupt_fixture_was_incomplete": not corrupt["complete"],
        "worker_failure_is_terminal_and_preserved": worker_failure_preserved,
        "truth_event_classification_correct": event_correct,
        "strict_zero_retry_replacement_counts": all(
            item["retries"] == 0
            and item["replacement_roots"] == 0
            and item["infrastructure_failures"] == 0
            for item in (serial, parallel, resumed)
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "partition_code": 951,
        "serial_sha256": serial["output_sha256"],
        "parallel_sha256": parallel["output_sha256"],
        "resumed_sha256": resumed["output_sha256"],
        "partition_52_accessed": False,
        "partition_53_accessed": False,
    }


def partition_53_inert(root: Path, pilot: TransferPilotConfig) -> dict[str, Any]:
    contract = json.loads((root / PILOT_CONTRACT_PATH).read_text(encoding="utf-8"))
    state = contract["partitions"]["future_confirmatory"]
    function_names: set[str] = set()
    source_directory = root / "src/kri_space_autonomy/experiment_005_transfer_pilot"
    for path in source_directory.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function_names.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
    forbidden_symbols = {"materialize_confirmatory", "run_confirmatory"}
    found = sorted(function_names & forbidden_symbols)
    paths = (
        root / "experiments/005-confirmatory",
        root / "results/experiment-005-confirmatory",
    )
    root_rows = []
    for path in root.glob("**/*.jsonl"):
        if any(part in {".git", ".venv"} for part in path.parts):
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if "experiment005:53:" in line:
                root_rows.append(f"{path.relative_to(root)}:{line_number}")
    expected = {
        "code": pilot.future_confirmatory_partition_code,
        "status": (
            "reserved_untouched_unmaterialized_hypothesis_sample_size_and_design_not_set"
        ),
        "generator_available": False,
    }
    return {
        "passed": bool(
            state == expected
            and not found
            and not root_rows
            and not any(path.exists() for path in paths)
        ),
        "state": state,
        "forbidden_symbols_found": found,
        "root_rows": root_rows,
        "paths_present": [
            path.relative_to(root).as_posix() for path in paths if path.exists()
        ],
    }


def partition_52_authorization(
    root: Path, pilot: TransferPilotConfig
) -> dict[str, Any]:
    source = inspect.getsource(materialize_pilot_seeds)
    targets = (
        root / "experiments/005-transfer-pilot/seeds",
        root / "results/experiment-005-transfer-pilot",
    )
    return {
        "passed": bool(
            "verify_freeze" in source
            and "READY_FOR_PARTITION_52_EXECUTION" in source
            and not any(path.exists() for path in targets)
        ),
        "generator_available_only_after_verified_design_freeze": True,
        "generator_invoked": False,
        "seed_or_result_paths_present": [
            path.relative_to(root).as_posix() for path in targets if path.exists()
        ],
    }


def publication_privacy(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / FOUNDATION_FREEZE_PATH).read_text(encoding="utf-8"))
    protected = set(manifest["historical_protected_blob_ids"])
    protected.update(manifest["source_file_hashes"])
    return enhanced_publication_and_secret_scan(root, base_paths=protected)


def run_design_checks(
    root: Path,
    pilot: TransferPilotConfig,
    cases: tuple[TransferCase, ...],
    *,
    recompute_calibration: bool,
) -> dict[str, Any]:
    checks = {
        "frozen_foundation_identity_and_phase_transition": foundation_identity(root),
        "partition_51_calibration_and_attempt_provenance": verify_calibration(
            root, recompute=recompute_calibration
        ),
        "sample_count_matrix_and_frozen_gates": matrix_and_gates(root, pilot, cases),
        "controller_monitor_information_boundary": information_boundary(),
        "checkpoint_process_pool_and_truth_event_fixture": runner_architecture_fixture(
            root, pilot, cases
        ),
        "seed_domain_and_partition_52_absence": validate_seed_contract(
            pilot, root / PILOT_CONTRACT_PATH, root=root
        ),
        "partition_52_postfreeze_authorization": partition_52_authorization(root, pilot),
        "partition_53_reserved_untouched": partition_53_inert(root, pilot),
        "historical_experiment_001_005_bytes": historical_snapshot(root),
        "historical_campaign_result_integrity": verify_historical_campaigns(root),
        "dependency_runtime_identity": dependency_runtime_identity(root),
        "publication_privacy_secrets": publication_privacy(root),
    }
    return {
        "passed": all(check["passed"] for check in checks.values()),
        "checks": checks,
        "partition_51_calibration_complete": True,
        "partition_52_materialized": False,
        "partition_52_executed": False,
        "partition_53_touched": False,
        "confirmatory_inference_enabled": False,
        "scientific_findings_claimed": False,
    }
