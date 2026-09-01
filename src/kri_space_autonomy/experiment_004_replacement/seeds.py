from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_004.seeds import STREAM_CODES
from kri_space_autonomy.experiment_004_pilot.config import (
    PilotCase,
    PilotConfig,
    load_case_matrix,
)
from kri_space_autonomy.experiment_004_pilot.seeds import (
    BIT_GENERATOR,
    SEED_DERIVATION,
    PilotScenario,
    _configuration_order,
    _fault_spec,
    _historical_root_ids,
    _stratified_initial_state,
    canonical_json,
    materialize_streams,
    sha256_bytes,
)

from .config import ConfirmatoryConfig

SEED_DIRECTORY = Path("experiments/004-replacement-confirmatory/seeds")
RESULT_DIRECTORY = Path("results/experiment-004-replacement-confirmatory")
MANIFEST_NAME = "confirmatory.jsonl"
REPLAY_NAME = "replay-subset.json"
INDEX_NAME = "index.json"


def _prior_root_ids(root: Path) -> set[str]:
    identifiers: set[str] = set()
    current = (root / SEED_DIRECTORY / MANIFEST_NAME).resolve()
    for path in root.glob("experiments/*/seeds/*.jsonl"):
        if path.resolve() == current:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line).get("root_seed_id")
            except json.JSONDecodeError:
                continue
            if isinstance(value, str):
                identifiers.add(value)
    return identifiers


def load_confirmatory_cases(
    path: str | Path = "experiments/004-pilot/case-matrix.json",
    *,
    study: ConfirmatoryConfig,
) -> tuple[PilotCase, ...]:
    case_map = {case.id: case for case in load_case_matrix(path)}
    cases = tuple(case_map[name] for name in study.strata)
    if any(case.fixture != "stochastic_bounded_initial_state" for case in cases):
        raise ValueError("confirmatory population may not contain forced physical fixtures")
    return cases


def _expected_contract(study: ConfirmatoryConfig) -> dict[str, Any]:
    return {
        "schema_version": study.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": study.master_seed,
        "partition_code": study.confirmatory_partition_code,
        "status_at_freeze": "reserved_not_materialized_or_executed",
        "derivation": SEED_DERIVATION,
        "strata": [
            {
                "id": stratum,
                "roots": study.roots_by_stratum[stratum],
                "primary_weight": 0.5 if stratum in study.primary_strata else None,
            }
            for stratum in study.strata
        ],
        "stream_codes": STREAM_CODES,
        "configurations": list(study.configurations),
        "expected_root_rows": study.planned_blocks,
        "expected_episode_rows": study.planned_episodes,
        "replay_selection": "replicates 0 through 7 in every stratum; outcome-blind",
        "replay_roots_per_stratum": study.replay_roots_per_stratum,
        "expected_replay_root_rows": study.replay_blocks,
        "expected_replay_episode_rows": study.replay_episodes,
        "materialization_prerequisite": (
            "Exact Experiment 004 confirmatory freeze and readiness self-hashes must verify "
            "before the partition-45 generator is invoked."
        ),
        "materialization_outputs": [
            f"{SEED_DIRECTORY.as_posix()}/{MANIFEST_NAME}",
            f"{SEED_DIRECTORY.as_posix()}/{REPLAY_NAME}",
            f"{SEED_DIRECTORY.as_posix()}/{INDEX_NAME}",
        ],
        "generator_available_after_verified_freeze": True,
        "generator_invoked": False,
        "replacement_extension_or_count_drift_allowed": False,
        "outcome_dependent_materialization_allowed": False,
    }


def validate_seed_contract(
    study: ConfirmatoryConfig,
    path: str | Path,
    *,
    root: str | Path = ".",
) -> dict[str, Any]:
    contract_path = Path(path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = _expected_contract(study)
    errors = [key for key, value in expected.items() if contract.get(key) != value]
    project_root = Path(root)
    seed_directory = project_root / SEED_DIRECTORY
    result_directory = project_root / RESULT_DIRECTORY
    if seed_directory.exists():
        errors.append("partition_45_seed_directory_exists")
    if result_directory.exists():
        errors.append("confirmatory_result_directory_exists")
    historical = _historical_root_ids(project_root)
    overlap = sorted(root_id for root_id in historical if root_id.startswith("experiment004:45:"))
    if overlap:
        errors.append("historical_partition_45_root_overlap")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(contract_path.read_bytes()),
        "partition_code": study.confirmatory_partition_code,
        "expected_root_rows": study.planned_blocks,
        "expected_episode_rows": study.planned_episodes,
        "expected_replay_root_rows": study.replay_blocks,
        "expected_replay_episode_rows": study.replay_episodes,
        "seed_directory_present": seed_directory.exists(),
        "result_directory_present": result_directory.exists(),
        "historical_root_ids_compared": len(historical),
        "historical_partition_45_overlap": len(overlap),
        "state": "reserved_not_materialized_or_executed",
    }


def materialize_confirmatory_scenario(
    study: ConfirmatoryConfig,
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
    *,
    freeze_id: str,
) -> PilotScenario:
    """Derive one partition-45 scenario; never call this during design freeze."""

    if case.id not in study.strata:
        raise ValueError("case is outside the frozen confirmatory population")
    if type(replicate) is not int or not 0 <= replicate < study.roots_by_stratum[case.id]:
        raise ValueError("replicate is outside the frozen stratum count")
    partition = study.confirmatory_partition_code
    initial = _stratified_initial_state(pilot, foundation, case, replicate, partition)
    fault = _fault_spec(pilot, foundation, case, replicate, partition)
    order = _configuration_order(foundation, partition, case, replicate)
    _, stochastic_hashes = materialize_streams(
        pilot,
        foundation,
        case,
        replicate,
        partition_code=partition,
    )
    hashes = {
        **stochastic_hashes,
        "initial_state": sha256_bytes(canonical_json(initial)),
        "fault_parameters": sha256_bytes(canonical_json(fault)),
        "configuration_run_order": sha256_bytes(canonical_json(order)),
    }
    root_id = f"experiment004:45:{case.case_code:03d}:{replicate:04d}"
    unsigned = {
        "schema_version": study.schema_version,
        "partition_code": partition,
        "case_id": case.id,
        "geometry_code": case.geometry_code,
        "fault_code": case.fault_code,
        "case_code": case.case_code,
        "replicate": replicate,
        "root_seed_id": root_id,
        "initial_state": initial,
        "horizon_s": study.standard_horizon_s,
        "fixture_command_mps2": None,
        **fault,
        "configuration_run_order": order,
        "stream_hashes": hashes,
        "design_freeze_id": freeze_id,
    }
    deterministic = {
        "initial_state": initial,
        "fault": fault,
        "configuration_run_order": order,
    }
    return PilotScenario(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json({**unsigned, "deterministic": deterministic})),
    )


def validate_materialized_confirmatory_seeds(
    study: ConfirmatoryConfig,
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
    *,
    root: str | Path,
    freeze_id: str,
    readiness_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    directory = Path(root) / SEED_DIRECTORY
    manifest_path = directory / MANIFEST_NAME
    replay_path = directory / REPLAY_NAME
    index_path = directory / INDEX_NAME
    errors: list[str] = []
    try:
        rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"load:{exc}"]}
    case_map = {case.id: case for case in cases}
    expected_keys = {
        (case.id, replicate)
        for case in cases
        for replicate in range(study.roots_by_stratum[case.id])
    }
    observed_keys: set[tuple[str, int]] = set()
    root_ids: set[str] = set()
    rederivation_errors = 0
    for row in rows:
        case = case_map.get(str(row.get("case_id")))
        replicate = row.get("replicate")
        if case is None or type(replicate) is not int:
            errors.append("invalid_case_or_replicate")
            continue
        key = (case.id, replicate)
        if key in observed_keys:
            errors.append("duplicate_case_replicate")
        observed_keys.add(key)
        root_ids.add(str(row.get("root_seed_id")))
        expected = materialize_confirmatory_scenario(
            study,
            pilot,
            foundation,
            case,
            replicate,
            freeze_id=freeze_id,
        )
        rederivation_errors += int(canonical_json(row) != canonical_json(expected.to_dict()))
    if observed_keys != expected_keys:
        errors.append("case_replicate_set")
    if len(rows) != study.planned_blocks or len(root_ids) != study.planned_blocks:
        errors.append("root_count_or_uniqueness")
    if rederivation_errors:
        errors.append("deterministic_rederivation")
    expected_replay = [
        f"experiment004:45:{case.case_code:03d}:{replicate:04d}"
        for case in cases
        for replicate in range(study.replay_roots_per_stratum)
    ]
    if replay.get("root_seed_ids") != expected_replay:
        errors.append("replay_subset")
    expected_index = {
        "design_freeze_id": freeze_id,
        "design_readiness_id": readiness_id,
        "seed_contract_sha256": seed_contract_sha256,
        "partition_code": study.confirmatory_partition_code,
        "root_rows": study.planned_blocks,
        "planned_episode_rows": study.planned_episodes,
        "replay_root_rows": study.replay_blocks,
        "replay_episode_rows": study.replay_episodes,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
        "replacement_extension_or_count_drift_allowed": False,
    }
    errors.extend(
        f"index:{key}" for key, value in expected_index.items() if index.get(key) != value
    )
    historical = _prior_root_ids(Path(root))
    overlap = root_ids & historical
    if overlap:
        errors.append("historical_root_overlap")
    if any(not root_id.startswith("experiment004:45:") for root_id in root_ids):
        errors.append("root_partition_namespace")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "rows": len(rows),
        "unique_root_ids": len(root_ids),
        "deterministic_rederivation_errors": rederivation_errors,
        "historical_root_overlap": len(overlap),
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
        "replacement_extension_or_count_drift_allowed": False,
    }


def assert_materialization_targets_absent(root: str | Path) -> None:
    project_root = Path(root)
    if (project_root / SEED_DIRECTORY).exists() or (project_root / RESULT_DIRECTORY).exists():
        raise RuntimeError("refusing pre-existing partition-45 seed or result path")


def materialize_confirmatory_seeds(
    study: ConfirmatoryConfig,
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
    *,
    root: str | Path,
    freeze_id: str,
    readiness_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    """Write the exact partition-45 schedule once after verified design freeze."""

    project_root = Path(root)
    from .workflow import verify_freeze

    verification = verify_freeze(project_root, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError("refusing partition-45 materialization before verified freeze")
    if (
        freeze_id != verification["freeze_id"]
        or readiness_id != verification["readiness_id"]
        or seed_contract_sha256 != verification["seed_contract"]["contract_sha256"]
    ):
        raise RuntimeError("partition-45 materializer received a non-frozen identity")
    assert_materialization_targets_absent(project_root)
    seed_directory = project_root / SEED_DIRECTORY
    staging = seed_directory.parent / f".seeds-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        historical = _historical_root_ids(project_root)
        observed: set[str] = set()
        manifest = staging / MANIFEST_NAME
        with manifest.open("x", encoding="utf-8") as handle:
            for case in cases:
                for replicate in range(study.roots_by_stratum[case.id]):
                    scenario = materialize_confirmatory_scenario(
                        study,
                        pilot,
                        foundation,
                        case,
                        replicate,
                        freeze_id=freeze_id,
                    )
                    if scenario.root_seed_id in observed or scenario.root_seed_id in historical:
                        raise RuntimeError("partition-45 root identity is not unique and disjoint")
                    observed.add(scenario.root_seed_id)
                    handle.write(canonical_json(scenario.to_dict()).decode() + "\n")
        if len(observed) != study.planned_blocks:
            raise RuntimeError("partition-45 root count drift")
        replay_root_ids = [
            f"experiment004:45:{case.case_code:03d}:{replicate:04d}"
            for case in cases
            for replicate in range(study.replay_roots_per_stratum)
        ]
        replay = {
            "schema_version": study.schema_version,
            "selection": "replicates 0 through 7 in every stratum; outcome-blind",
            "root_seed_ids": replay_root_ids,
            "expected_blocks": study.replay_blocks,
            "expected_episodes": study.replay_episodes,
        }
        replay_path = staging / REPLAY_NAME
        replay_path.write_text(
            json.dumps(replay, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        index = {
            "schema_version": study.schema_version,
            "design_freeze_id": freeze_id,
            "design_readiness_id": readiness_id,
            "seed_contract_sha256": seed_contract_sha256,
            "partition_code": study.confirmatory_partition_code,
            "root_rows": len(observed),
            "planned_episode_rows": study.planned_episodes,
            "replay_root_rows": study.replay_blocks,
            "replay_episode_rows": study.replay_episodes,
            "manifest_sha256": sha256_bytes(manifest.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "historical_root_ids_compared": len(historical),
            "materialized_only_after_exact_freeze_and_readiness_verification": True,
            "replacement_extension_or_count_drift_allowed": False,
        }
        (staging / INDEX_NAME).write_text(
            json.dumps(index, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staging.rename(seed_directory)
        return index
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
