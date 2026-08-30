from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from kri_space_autonomy.experiment_003.config import ESTIMATOR_STRATA, Experiment003Config
from kri_space_autonomy.experiment_003.seeds import (
    BIT_GENERATOR,
    STRATUM_CODES,
    STREAM_CODES,
    Experiment003Scenario,
    canonical_json,
    materialize_scenario,
    sha256_bytes,
)

from .config import ConfirmatoryConfig

ROOT_PREFIX = "confirmatory003"
PRIOR_SEED_DIRECTORIES = (
    Path("experiments/002/seeds"),
    Path("experiments/002b/seeds"),
    Path("experiments/002c/seeds"),
    Path("experiments/002d/seeds"),
    Path("experiments/002-confirmatory/seeds"),
    Path("experiments/003/seeds"),
)


def validate_seed_contract(
    study: ConfirmatoryConfig,
    path: str | Path,
    root: str | Path = ".",
) -> dict[str, Any]:
    contract_path = Path(path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": study.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": study.master_seed,
        "partition": study.partition_name,
        "partition_code": study.partition_code,
        "status_at_freeze": "reserved_not_materialized_or_executed",
        "derivation": "SeedSequence([master, partition, stratum, replicate, stream])",
        "strata": [
            {
                "id": name,
                "code": STRATUM_CODES[name],
                "roots": study.roots_per_stratum,
                "weight": study.stratum_weight,
            }
            for name in ESTIMATOR_STRATA
        ],
        "streams": STREAM_CODES,
        "arms": list(study.arms),
        "expected_root_rows": study.planned_blocks,
        "expected_episode_rows": study.planned_episodes,
        "replay_roots_per_stratum": study.replay_roots_per_stratum,
        "expected_replay_episode_rows": study.replay_episodes,
        "materialization_prerequisite": (
            "Successful internal verification of the Experiment 003 confirmatory freeze and "
            "readiness identities before any partition-32 generator invocation."
        ),
        "materialization_outputs": [
            "experiments/003-confirmatory/seeds/confirmatory.jsonl",
            "experiments/003-confirmatory/seeds/replay-subset.json",
            "experiments/003-confirmatory/seeds/index.json",
        ],
        "replacement_or_extension_allowed": False,
        "outcome_dependent_materialization_allowed": False,
    }
    errors = [key for key, value in expected.items() if contract.get(key) != value]
    project_root = Path(root)
    seed_directory = project_root / "experiments/003-confirmatory/seeds"
    result_directory = project_root / "results/experiment-003-confirmatory"
    if seed_directory.exists():
        errors.append("confirmatory_seed_directory_exists")
    if result_directory.exists():
        errors.append("confirmatory_result_directory_exists")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(contract_path.read_bytes()),
        "partition_code": study.partition_code,
        "expected_roots": study.planned_blocks,
        "expected_episodes": study.planned_episodes,
        "seed_directory_present": seed_directory.exists(),
        "result_directory_present": result_directory.exists(),
        "state": "reserved_not_materialized_or_executed",
    }


def materialize_confirmatory_scenario(
    study: ConfirmatoryConfig,
    foundation: Experiment003Config,
    production: Any,
    stratum: str,
    replicate: int,
) -> Experiment003Scenario:
    """Derive one partition-32 scenario through the frozen foundation generator."""

    scenario, _ = materialize_scenario(
        foundation,
        production,
        stratum,
        replicate,
        partition_code=study.partition_code,
    )
    unsigned = scenario.to_dict()
    unsigned.pop("scenario_hash")
    unsigned["schema_version"] = study.schema_version
    unsigned["root_seed_id"] = f"{ROOT_PREFIX}:{stratum}:{replicate:04d}"
    return Experiment003Scenario(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json(unsigned)),
    )


def _prior_root_ids(root: Path) -> set[str]:
    identifiers: set[str] = set()
    for relative in PRIOR_SEED_DIRECTORIES:
        directory = root / relative
        if not directory.is_dir():
            continue
        for path in directory.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                value = json.loads(line).get("root_seed_id")
                if isinstance(value, str):
                    identifiers.add(value)
    return identifiers


def materialize_confirmatory_seed_manifest(
    study: ConfirmatoryConfig,
    foundation: Experiment003Config,
    production: Any,
    *,
    root: str | Path,
    freeze_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    project_root = Path(root)
    directory = project_root / "experiments/003-confirmatory/seeds"
    results = project_root / "results/experiment-003-confirmatory"
    if directory.exists() or results.exists():
        raise RuntimeError("refusing pre-existing confirmatory seed or result path")
    staging = directory.parent / f".seeds-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        prior_ids = _prior_root_ids(project_root)
        observed_ids: set[str] = set()
        manifest_path = staging / "confirmatory.jsonl"
        with manifest_path.open("x", encoding="utf-8") as handle:
            for stratum in ESTIMATOR_STRATA:
                for replicate in range(study.roots_per_stratum):
                    scenario = materialize_confirmatory_scenario(
                        study,
                        foundation,
                        production,
                        stratum,
                        replicate,
                    )
                    if scenario.root_seed_id in prior_ids or scenario.root_seed_id in observed_ids:
                        raise RuntimeError("confirmatory root identity is not unique and disjoint")
                    observed_ids.add(scenario.root_seed_id)
                    handle.write(canonical_json(scenario.to_dict()).decode() + "\n")
        if len(observed_ids) != study.planned_blocks:
            raise RuntimeError("confirmatory root count drifted during materialization")
        replay = {
            "schema_version": study.schema_version,
            "selection": "first 30 replicate indices in every stratum; outcome-blind",
            "replicates_by_stratum": {
                stratum: list(range(study.replay_roots_per_stratum))
                for stratum in ESTIMATOR_STRATA
            },
            "root_rows": study.stratum_count * study.replay_roots_per_stratum,
            "episode_rows": study.replay_episodes,
        }
        replay_path = staging / "replay-subset.json"
        replay_path.write_text(
            json.dumps(replay, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index = {
            "schema_version": study.schema_version,
            "confirmatory_freeze_id": freeze_id,
            "seed_contract_sha256": seed_contract_sha256,
            "partition_code": study.partition_code,
            "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "root_rows": len(observed_ids),
            "planned_episode_rows": study.planned_episodes,
            "replay_root_rows": study.stratum_count * study.replay_roots_per_stratum,
            "replay_episode_rows": study.replay_episodes,
            "prior_root_ids_compared": len(prior_ids),
            "materialized_only_after_confirmatory_freeze_verification": True,
            "replacement_or_extension_allowed": False,
        }
        (staging / "index.json").write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(directory)
        return index
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_materialized_confirmatory_seeds(
    study: ConfirmatoryConfig,
    foundation: Experiment003Config,
    production: Any,
    *,
    root: str | Path,
    freeze_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    directory = Path(root) / "experiments/003-confirmatory/seeds"
    manifest_path = directory / "confirmatory.jsonl"
    replay_path = directory / "replay-subset.json"
    index_path = directory / "index.json"
    errors: list[str] = []
    try:
        rows = [
            json.loads(line)
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
        ]
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"load:{exc}"]}

    expected_keys = {
        (stratum, replicate)
        for stratum in ESTIMATOR_STRATA
        for replicate in range(study.roots_per_stratum)
    }
    observed_keys: set[tuple[str, int]] = set()
    root_ids: set[str] = set()
    rederivation_errors = 0
    for row in rows:
        stratum = row.get("stratum_id")
        replicate = row.get("replicate")
        if stratum not in ESTIMATOR_STRATA or type(replicate) is not int:
            errors.append("invalid_scenario_key")
            continue
        key = (str(stratum), replicate)
        if key in observed_keys:
            errors.append("duplicate_scenario_key")
        observed_keys.add(key)
        root_ids.add(str(row.get("root_seed_id")))
        expected = materialize_confirmatory_scenario(
            study,
            foundation,
            production,
            str(stratum),
            replicate,
        )
        rederivation_errors += int(canonical_json(row) != canonical_json(expected.to_dict()))
    if observed_keys != expected_keys:
        errors.append("scenario_key_set")
    if len(rows) != study.planned_blocks or len(root_ids) != study.planned_blocks:
        errors.append("root_count_or_uniqueness")
    if rederivation_errors:
        errors.append("deterministic_rederivation")

    expected_replay = {
        stratum: list(range(study.replay_roots_per_stratum))
        for stratum in ESTIMATOR_STRATA
    }
    if replay.get("replicates_by_stratum") != expected_replay:
        errors.append("replay_subset")
    expected_index = {
        "confirmatory_freeze_id": freeze_id,
        "seed_contract_sha256": seed_contract_sha256,
        "partition_code": study.partition_code,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
        "root_rows": study.planned_blocks,
        "planned_episode_rows": study.planned_episodes,
        "replay_root_rows": study.stratum_count * study.replay_roots_per_stratum,
        "replay_episode_rows": study.replay_episodes,
        "replacement_or_extension_allowed": False,
    }
    errors.extend(
        f"index:{key}" for key, value in expected_index.items() if index.get(key) != value
    )
    overlap = root_ids & _prior_root_ids(Path(root))
    if overlap:
        errors.append("prior_root_overlap")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "rows": len(rows),
        "unique_root_ids": len(root_ids),
        "deterministic_rederivation_errors": rederivation_errors,
        "prior_root_overlap": len(overlap),
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_root_rows": study.stratum_count * study.replay_roots_per_stratum,
        "replay_episode_rows": study.replay_episodes,
    }
