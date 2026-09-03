from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_005.config import Experiment005Config
from kri_space_autonomy.experiment_005.seeds import BIT_GENERATOR, STREAM_CODES
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    TransferCase,
    TransferPilotConfig,
    load_case_matrix,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    SEED_DERIVATION,
    TransferScenario,
    _configuration_order,
    _fault_spec,
    canonical_json,
    materialize_streams,
    sha256_bytes,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    _stratified_initial_state as _pilot_stratified_initial_state,
)

from .config import ConfirmatoryConfig

DESIGN_DIRECTORY = Path("experiments/005-confirmatory")
SEED_DIRECTORY = DESIGN_DIRECTORY / "seeds"
RESULT_DIRECTORY = Path("results/experiment-005-confirmatory")
CONTRACT_PATH = DESIGN_DIRECTORY / "seed-contract.json"
MANIFEST_NAME = "confirmatory.jsonl"
REPLAY_NAME = "replay-subset.json"
INDEX_NAME = "index.json"


def _root_ids(root: Path, *, exclude: Path | None = None) -> set[str]:
    identifiers: set[str] = set()
    excluded = exclude.resolve() if exclude is not None else None
    for base in (root / "experiments", root / "results"):
        if not base.exists():
            continue
        for path in base.rglob("*.jsonl"):
            if excluded is not None and path.resolve() == excluded:
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    value = json.loads(line).get("root_seed_id")
                except (AttributeError, json.JSONDecodeError):
                    continue
                if isinstance(value, str):
                    identifiers.add(value)
    return identifiers


def load_confirmatory_cases(
    path: str | Path = "experiments/005-transfer-pilot/case-matrix.json",
    *,
    study: ConfirmatoryConfig,
) -> tuple[TransferCase, ...]:
    case_map = {case.id: case for case in load_case_matrix(path)}
    cases = tuple(case_map[name] for name in study.cases)
    if any(case.fixture != "stochastic_bounded_initial_state" for case in cases):
        raise ValueError("confirmatory population may not contain deterministic fixtures")
    if any(case.horizon_kind != "standard" for case in cases):
        raise ValueError("confirmatory population requires the frozen standard horizon")
    return cases


def _expected_contract(study: ConfirmatoryConfig) -> dict[str, Any]:
    return {
        "schema_version": study.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": study.master_seed,
        "partition_code": study.confirmatory_partition_code,
        "status_at_freeze": "reserved_not_materialized_or_executed",
        "derivation": SEED_DERIVATION,
        "cases": [
            {
                "id": case_id,
                "roots": study.roots_by_case[case_id],
                "primary_weight": study.case_weights[case_id],
            }
            for case_id in study.cases
        ],
        "stream_codes": STREAM_CODES,
        "root_identity_namespace": "experiment005:53:<case_code>:<replicate>",
        "configurations": list(study.configurations),
        "configuration_order": (
            "the partition-53 cell_order stream chooses the first configuration at "
            "replicate 0 and order alternates thereafter; each even case count is exactly balanced"
        ),
        "expected_root_rows": study.planned_blocks,
        "expected_episode_rows": study.planned_episodes,
        "replay_selection": "replicates 0 through 7 in each frozen case; outcome-blind",
        "replay_roots_per_case": study.replay_roots_per_case,
        "expected_replay_root_rows": study.replay_blocks,
        "expected_replay_episode_rows": study.replay_episodes,
        "materialization_prerequisite": (
            "exact Experiment 005 confirmatory freeze, readiness, lineage, and seed-contract "
            "identities must verify before the partition-53 generator is invoked"
        ),
        "materialization_outputs": [
            f"{SEED_DIRECTORY.as_posix()}/{MANIFEST_NAME}",
            f"{SEED_DIRECTORY.as_posix()}/{REPLAY_NAME}",
            f"{SEED_DIRECTORY.as_posix()}/{INDEX_NAME}",
        ],
        "execution_outputs": [
            f"{RESULT_DIRECTORY.as_posix()}/campaign/confirmatory-episodes.jsonl",
            f"{RESULT_DIRECTORY.as_posix()}/replay/confirmatory-episodes.jsonl",
        ],
        "generator_available_after_verified_freeze": True,
        "generator_invoked": False,
        "write_once_materialization": True,
        "disjoint_from_partitions": [51, 52, 54, 951],
        "historical_master_domains": [1001, 2002, 3003, 4004],
        "checkpoint_continuation": (
            "after interruption only, validate every completed shard and execute missing "
            "unpublished paired blocks"
        ),
        "completed_valid_blocks_recomputed": False,
        "maximum_retries": 0,
        "maximum_replacement_roots": 0,
        "replacement_extension_or_count_drift_allowed": False,
        "outcome_dependent_materialization_allowed": False,
    }


def partition_53_unmaterialized(root: str | Path) -> dict[str, Any]:
    project = Path(root)
    targets = (project / SEED_DIRECTORY, project / RESULT_DIRECTORY)
    present = [path.relative_to(project).as_posix() for path in targets if path.exists()]
    overlap = sorted(
        root_id for root_id in _root_ids(project) if root_id.startswith("experiment005:53:")
    )
    return {
        "passed": not present and not overlap,
        "partition_code": 53,
        "state": "reserved_not_materialized_or_executed",
        "seed_or_result_paths_present": present,
        "historical_root_overlap": len(overlap),
        "overlap_preview": overlap[:10],
        "generator_invoked": False,
        "outcomes_executed": False,
    }


def validate_seed_contract(
    study: ConfirmatoryConfig,
    path: str | Path,
    *,
    root: str | Path,
    require_unmaterialized: bool = True,
) -> dict[str, Any]:
    contract_path = Path(path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = _expected_contract(study)
    errors = [key for key, value in expected.items() if contract.get(key) != value]
    partition = (
        partition_53_unmaterialized(root)
        if require_unmaterialized
        else {
            "passed": True,
            "partition_code": 53,
            "state": "materialization_state_not_required",
        }
    )
    if not partition["passed"]:
        errors.append("partition_53_state")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(contract_path.read_bytes()),
        "partition": partition,
        "expected_root_rows": study.planned_blocks,
        "expected_episode_rows": study.planned_episodes,
        "expected_replay_root_rows": study.replay_blocks,
        "expected_replay_episode_rows": study.replay_episodes,
    }


def _stratified_initial_state(
    study: ConfirmatoryConfig,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    case: TransferCase,
    replicate: int,
) -> tuple[float, float, float, float, float, float]:
    return _pilot_stratified_initial_state(
        pilot,
        foundation,
        case,
        replicate,
        study.confirmatory_partition_code,
    )


def materialize_confirmatory_scenario(
    study: ConfirmatoryConfig,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    replicate: int,
    *,
    freeze_id: str,
) -> TransferScenario:
    """Derive one partition-53 scenario; never call this during design freeze."""

    if case.id not in study.cases:
        raise ValueError("case is outside the frozen confirmatory population")
    if type(replicate) is not int or not 0 <= replicate < study.roots_by_case[case.id]:
        raise ValueError("replicate is outside the frozen case count")
    partition = study.confirmatory_partition_code
    initial = _stratified_initial_state(study, pilot, foundation, case, replicate)
    fault = _fault_spec(pilot, foundation, case, replicate, partition)
    order = _configuration_order(foundation, partition, case, replicate)
    _, stochastic_hashes = materialize_streams(
        pilot,
        foundation,
        e004,
        case,
        replicate,
        partition_code=partition,
    )
    hashes = {
        **stochastic_hashes,
        "initial_truth_state": sha256_bytes(canonical_json(initial)),
        "challenge_parameters": sha256_bytes(canonical_json(fault)),
        "cell_order": sha256_bytes(canonical_json(order)),
    }
    root_id = f"experiment005:53:{case.case_code:03d}:{replicate:04d}"
    unsigned = {
        "schema_version": study.schema_version,
        "partition_code": partition,
        "case_id": case.id,
        "geometry_code": case.geometry_code,
        "challenge_code": case.challenge_code,
        "case_code": case.case_code,
        "replicate": replicate,
        "root_seed_id": root_id,
        "initial_relative_state": initial,
        "horizon_s": study.standard_horizon_s,
        "fixture_command_mps2": None,
        "mechanics_noise_enabled": case.mechanics_noise_enabled,
        "navigation_noise_enabled": case.navigation_noise_enabled,
        **fault,
        "configuration_run_order": order,
        "stream_hashes": hashes,
        "design_freeze_id": freeze_id,
    }
    deterministic = {
        "initial_relative_state": initial,
        "fault": fault,
        "configuration_run_order": order,
    }
    return TransferScenario(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json({**unsigned, "deterministic": deterministic})),
    )


def validate_materialized_confirmatory_seeds(
    study: ConfirmatoryConfig,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
    *,
    root: str | Path,
    freeze_id: str,
    readiness_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    project = Path(root)
    directory = project / SEED_DIRECTORY
    manifest_path = directory / MANIFEST_NAME
    replay_path = directory / REPLAY_NAME
    index_path = directory / INDEX_NAME
    errors: list[str] = []
    try:
        raw_lines = manifest_path.read_bytes().splitlines()
        rows = [json.loads(line) for line in raw_lines]
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"load:{type(exc).__name__}"]}
    case_map = {case.id: case for case in cases}
    expected_keys = {
        (case.id, replicate)
        for case in cases
        for replicate in range(study.roots_by_case[case.id])
    }
    observed_keys: set[tuple[str, int]] = set()
    root_ids: set[str] = set()
    rederivation_errors = 0
    for raw, row in zip(raw_lines, rows, strict=True):
        if raw != canonical_json(row):
            errors.append("noncanonical_manifest_row")
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
            e004,
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
        f"experiment005:53:{case.case_code:03d}:{replicate:04d}"
        for case in cases
        for replicate in range(study.replay_roots_per_case)
    ]
    if replay.get("root_seed_ids") != expected_replay:
        errors.append("replay_subset")
    expected_index = {
        "design_freeze_id": freeze_id,
        "design_readiness_id": readiness_id,
        "seed_contract_sha256": seed_contract_sha256,
        "partition_code": 53,
        "root_rows": study.planned_blocks,
        "planned_episode_rows": study.planned_episodes,
        "replay_root_rows": study.replay_blocks,
        "replay_episode_rows": study.replay_episodes,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
        "maximum_retries": 0,
        "maximum_replacement_roots": 0,
        "replacement_extension_or_count_drift_allowed": False,
    }
    errors.extend(
        f"index:{key}" for key, value in expected_index.items() if index.get(key) != value
    )
    prior = _root_ids(project, exclude=manifest_path)
    overlap = root_ids & prior
    if overlap:
        errors.append("historical_root_overlap")
    if any(not root_id.startswith("experiment005:53:") for root_id in root_ids):
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
    }


def assert_materialization_targets_absent(root: str | Path) -> None:
    project = Path(root)
    if (project / SEED_DIRECTORY).exists() or (project / RESULT_DIRECTORY).exists():
        raise RuntimeError("refusing pre-existing partition-53 seed or result path")


def materialize_confirmatory_seeds(
    study: ConfirmatoryConfig,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
    *,
    root: str | Path,
    freeze_id: str,
    readiness_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    """Write the exact partition-53 schedule once after verified design freeze."""

    from .workflow import verify_freeze

    project = Path(root)
    verification = verify_freeze(project, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError("refusing partition-53 materialization before verified freeze")
    if (
        freeze_id != verification["freeze_id"]
        or readiness_id != verification["readiness_id"]
        or seed_contract_sha256 != verification["seed_contract"]["contract_sha256"]
    ):
        raise RuntimeError("partition-53 materializer received a non-frozen identity")
    assert_materialization_targets_absent(project)
    seed_directory = project / SEED_DIRECTORY
    staging = seed_directory.parent / f".seeds-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        historical = _root_ids(project)
        observed: set[str] = set()
        manifest_path = staging / MANIFEST_NAME
        with manifest_path.open("x", encoding="utf-8") as handle:
            for case in cases:
                for replicate in range(study.roots_by_case[case.id]):
                    scenario = materialize_confirmatory_scenario(
                        study,
                        pilot,
                        foundation,
                        e004,
                        case,
                        replicate,
                        freeze_id=freeze_id,
                    )
                    if scenario.root_seed_id in observed or scenario.root_seed_id in historical:
                        raise RuntimeError("partition-53 root identity is not unique and disjoint")
                    observed.add(scenario.root_seed_id)
                    handle.write(canonical_json(scenario.to_dict()).decode() + "\n")
        if len(observed) != study.planned_blocks:
            raise RuntimeError("partition-53 root count drift")
        replay_root_ids = [
            f"experiment005:53:{case.case_code:03d}:{replicate:04d}"
            for case in cases
            for replicate in range(study.replay_roots_per_case)
        ]
        replay = {
            "schema_version": study.schema_version,
            "selection": "replicates 0 through 7 in each frozen case; outcome-blind",
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
            "partition_code": 53,
            "root_rows": len(observed),
            "planned_episode_rows": study.planned_episodes,
            "replay_root_rows": study.replay_blocks,
            "replay_episode_rows": study.replay_episodes,
            "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "historical_root_ids_compared": len(historical),
            "materialized_only_after_exact_freeze_and_readiness_verification": True,
            "maximum_retries": 0,
            "maximum_replacement_roots": 0,
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
