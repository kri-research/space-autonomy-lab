from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_005.config import Experiment005Config
from kri_space_autonomy.experiment_005.seeds import BIT_GENERATOR
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    TransferCase,
    TransferPilotConfig,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    SEED_DERIVATION,
    TransferScenario,
    _scenario_for_partition,
    canonical_json,
    sha256_bytes,
)

from . import SCHEMA_VERSION
from .runner import (
    REPLACEMENT_PARTITION_CODE,
    RESERVED_CONFIRMATORY_PARTITION_CODE,
    RETIRED_PARTITION_CODE,
    TEST_FIXTURE_PARTITION_CODE,
)

DESIGN_DIRECTORY = Path("experiments/005-transfer-pilot")
AMENDMENT_DIRECTORY = Path("experiments/005-transfer-pilot-replacement")
SEED_DIRECTORY = AMENDMENT_DIRECTORY / "seeds"
RESULT_DIRECTORY = Path("results/experiment-005-transfer-pilot-replacement")
CONTRACT_PATH = AMENDMENT_DIRECTORY / "seed-contract.json"
MANIFEST_NAME = "pilot.jsonl"
REPLAY_NAME = "replay-subset.json"
INDEX_NAME = "index.json"


def replacement_pilot_config(root: str | Path) -> TransferPilotConfig:
    """Return the frozen pilot configuration with only its retired namespace replaced."""

    project = Path(root)
    original = load_pilot_config(project / DESIGN_DIRECTORY / "config.json", root=project)
    amended = replace(original, pilot_partition_code=REPLACEMENT_PARTITION_CODE)
    changed = [
        field.name
        for field in fields(TransferPilotConfig)
        if getattr(original, field.name) != getattr(amended, field.name)
    ]
    if changed != ["pilot_partition_code"]:
        raise RuntimeError("replacement configuration changed a scientific design field")
    if (
        original.pilot_partition_code != RETIRED_PARTITION_CODE
        or amended.pilot_partition_code != REPLACEMENT_PARTITION_CODE
        or original.future_confirmatory_partition_code
        != RESERVED_CONFIRMATORY_PARTITION_CODE
        or original.test_fixture_partition_code != TEST_FIXTURE_PARTITION_CODE
    ):
        raise RuntimeError("replacement partition identity changed")
    return amended


def _expected_contract(pilot: TransferPilotConfig) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "bit_generator": BIT_GENERATOR,
        "master_seed": 5005,
        "derivation": SEED_DERIVATION,
        "invalid_partition_code": RETIRED_PARTITION_CODE,
        "future_confirmatory_partition_code": RESERVED_CONFIRMATORY_PARTITION_CODE,
        "replacement_partition_code": REPLACEMENT_PARTITION_CODE,
        "test_fixture_partition_code": TEST_FIXTURE_PARTITION_CODE,
        "status_at_freeze": "reserved_not_materialized_or_executed",
        "roots_per_case": pilot.pilot_roots_per_case,
        "case_count": pilot.case_count,
        "expected_root_rows": pilot.pilot_blocks,
        "configurations_per_root": len(pilot.configuration_ids),
        "expected_episode_rows": pilot.pilot_episodes,
        "replay_selection": (
            "replicate 0 in every frozen case; outcome-blind and unchanged"
        ),
        "replay_roots_per_case": pilot.replay_roots_per_case,
        "expected_replay_root_rows": pilot.replay_blocks,
        "expected_replay_episode_rows": pilot.replay_episodes,
        "materialization_outputs": [
            f"{SEED_DIRECTORY.as_posix()}/{MANIFEST_NAME}",
            f"{SEED_DIRECTORY.as_posix()}/{REPLAY_NAME}",
            f"{SEED_DIRECTORY.as_posix()}/{INDEX_NAME}",
        ],
        "generator_available_only_after_verified_amendment_freeze": True,
        "generator_invoked": False,
        "maximum_retries": 0,
        "maximum_replacement_roots": 0,
        "replacement_extension_or_count_drift_allowed": False,
        "outcome_dependent_materialization_allowed": False,
    }


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


def partition_54_unmaterialized(root: str | Path) -> dict[str, Any]:
    project = Path(root)
    target_paths = (project / SEED_DIRECTORY, project / RESULT_DIRECTORY)
    present = [path.relative_to(project).as_posix() for path in target_paths if path.exists()]
    prefix = f"experiment005:{REPLACEMENT_PARTITION_CODE}:"
    overlap = sorted(value for value in _root_ids(project) if value.startswith(prefix))
    return {
        "passed": not present and not overlap,
        "partition_code": REPLACEMENT_PARTITION_CODE,
        "state": "reserved_not_materialized_or_executed",
        "seed_or_result_paths_present": present,
        "historical_root_overlap": len(overlap),
        "overlap_preview": overlap[:10],
    }


def validate_seed_contract(
    pilot: TransferPilotConfig,
    path: str | Path,
    *,
    root: str | Path,
    require_unmaterialized: bool = True,
) -> dict[str, Any]:
    contract_path = Path(path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = _expected_contract(pilot)
    errors = [key for key, value in expected.items() if contract.get(key) != value]
    partition = (
        partition_54_unmaterialized(root)
        if require_unmaterialized
        else {
            "passed": True,
            "partition_code": REPLACEMENT_PARTITION_CODE,
            "state": "materialization_state_not_required",
        }
    )
    if not partition["passed"]:
        errors.append("partition_54_state")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(contract_path.read_bytes()),
        "partition": partition,
        "expected_root_rows": pilot.pilot_blocks,
        "expected_episode_rows": pilot.pilot_episodes,
        "expected_replay_root_rows": pilot.replay_blocks,
        "expected_replay_episode_rows": pilot.replay_episodes,
    }


def materialize_replacement_scenario(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    replicate: int,
    *,
    amendment_freeze_id: str,
) -> TransferScenario:
    """Derive one partition-54 scenario only after the amendment freeze is verified."""

    if pilot.pilot_partition_code != REPLACEMENT_PARTITION_CODE:
        raise ValueError("replacement pilot configuration is not bound to partition 54")
    if type(replicate) is not int or not 0 <= replicate < pilot.pilot_roots_per_case:
        raise ValueError("replicate is outside the frozen transfer-pilot count")
    scenario, _ = _scenario_for_partition(
        pilot,
        foundation,
        e004,
        case,
        replicate,
        partition_code=REPLACEMENT_PARTITION_CODE,
        design_freeze_id=amendment_freeze_id,
    )
    return scenario


def validate_materialized_replacement_seeds(
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
        return {"passed": False, "errors_preview": [f"load:{exc}"]}
    expected_keys = {
        (case.id, replicate)
        for case in cases
        for replicate in range(pilot.pilot_roots_per_case)
    }
    case_map = {case.id: case for case in cases}
    observed_keys: set[tuple[str, int]] = set()
    roots: set[str] = set()
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
        roots.add(str(row.get("root_seed_id")))
        expected = materialize_replacement_scenario(
            pilot,
            foundation,
            e004,
            case,
            replicate,
            amendment_freeze_id=freeze_id,
        )
        rederivation_errors += int(canonical_json(row) != canonical_json(expected.to_dict()))
    if observed_keys != expected_keys:
        errors.append("case_replicate_set")
    if len(rows) != pilot.pilot_blocks or len(roots) != pilot.pilot_blocks:
        errors.append("root_count_or_uniqueness")
    if rederivation_errors:
        errors.append("deterministic_rederivation")
    expected_replay = [
        f"experiment005:{REPLACEMENT_PARTITION_CODE}:{case.case_code:03d}:0000"
        for case in cases
    ]
    if replay.get("root_seed_ids") != expected_replay:
        errors.append("replay_subset")
    expected_index = {
        "original_design_freeze_id": (
            "3fa9fd6e9e4d3146af6495c07599ed792cfb52ce16e90d0dca234ed64295be8b"
        ),
        "amendment_freeze_id": freeze_id,
        "amendment_readiness_id": readiness_id,
        "seed_contract_sha256": seed_contract_sha256,
        "partition_code": REPLACEMENT_PARTITION_CODE,
        "root_rows": pilot.pilot_blocks,
        "planned_episode_rows": pilot.pilot_episodes,
        "replay_root_rows": pilot.replay_blocks,
        "replay_episode_rows": pilot.replay_episodes,
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
    overlap = roots & prior
    if overlap:
        errors.append("historical_root_overlap")
    prefix = f"experiment005:{REPLACEMENT_PARTITION_CODE}:"
    if any(not root_id.startswith(prefix) for root_id in roots):
        errors.append("root_partition_namespace")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "rows": len(rows),
        "unique_root_ids": len(roots),
        "deterministic_rederivation_errors": rederivation_errors,
        "historical_root_overlap": len(overlap),
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
    }


def materialize_replacement_seeds(
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
    """Write the partition-54 schedule once after exact amendment verification."""

    from .workflow import verify_freeze

    project = Path(root)
    verification = verify_freeze(project, require_unmaterialized=True)
    if not verification["passed"]:
        raise RuntimeError("refusing partition-54 materialization before verified amendment")
    if (
        freeze_id != verification["freeze_id"]
        or readiness_id != verification["readiness_id"]
        or seed_contract_sha256 != verification["seed_contract"]["contract_sha256"]
    ):
        raise RuntimeError("partition-54 materializer received a non-frozen identity")
    partition = partition_54_unmaterialized(project)
    if not partition["passed"]:
        raise RuntimeError("refusing pre-existing partition-54 seed or result identity")

    seed_directory = project / SEED_DIRECTORY
    staging = seed_directory.parent / f".seeds-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        historical = _root_ids(project)
        observed: set[str] = set()
        manifest_path = staging / MANIFEST_NAME
        with manifest_path.open("x", encoding="utf-8") as handle:
            for case in cases:
                for replicate in range(pilot.pilot_roots_per_case):
                    scenario = materialize_replacement_scenario(
                        pilot,
                        foundation,
                        e004,
                        case,
                        replicate,
                        amendment_freeze_id=freeze_id,
                    )
                    if scenario.root_seed_id in observed or scenario.root_seed_id in historical:
                        raise RuntimeError("partition-54 root identity is not unique and disjoint")
                    observed.add(scenario.root_seed_id)
                    handle.write(canonical_json(scenario.to_dict()).decode() + "\n")
        if len(observed) != pilot.pilot_blocks:
            raise RuntimeError("partition-54 root count drift")
        replay = {
            "schema_version": SCHEMA_VERSION,
            "selection": "replicate 0 in every frozen case; outcome-blind and unchanged",
            "root_seed_ids": [
                f"experiment005:{REPLACEMENT_PARTITION_CODE}:{case.case_code:03d}:0000"
                for case in cases
            ],
            "expected_blocks": pilot.replay_blocks,
            "expected_episodes": pilot.replay_episodes,
        }
        replay_path = staging / REPLAY_NAME
        replay_path.write_text(
            json.dumps(replay, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        index = {
            "schema_version": SCHEMA_VERSION,
            "original_design_freeze_id": (
                "3fa9fd6e9e4d3146af6495c07599ed792cfb52ce16e90d0dca234ed64295be8b"
            ),
            "amendment_freeze_id": freeze_id,
            "amendment_readiness_id": readiness_id,
            "seed_contract_sha256": seed_contract_sha256,
            "partition_code": REPLACEMENT_PARTITION_CODE,
            "root_rows": len(observed),
            "planned_episode_rows": pilot.pilot_episodes,
            "replay_root_rows": pilot.replay_blocks,
            "replay_episode_rows": pilot.replay_episodes,
            "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "historical_root_ids_compared": len(historical),
            "materialized_only_after_exact_amendment_verification": True,
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
