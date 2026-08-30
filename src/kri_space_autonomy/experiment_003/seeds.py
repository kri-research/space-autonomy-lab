from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import ESTIMATOR_STRATA, STREAM_NAMES, Experiment003Config

BIT_GENERATOR = "PCG64DXSM"
STRATUM_CODES = {name: index + 1 for index, name in enumerate(ESTIMATOR_STRATA)}
STREAM_CODES = {name: index + 101 for index, name in enumerate(STREAM_NAMES)}


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_fixture_rng(
    config: Experiment003Config,
    stratum: str,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    """Return RNG only in the explicitly non-outcome fixture partition."""

    if stratum not in STRATUM_CODES:
        raise ValueError("unknown Experiment 003 stratum")
    if type(replicate) is not int or replicate < 0:
        raise ValueError("replicate must be a non-negative integer")
    if stream not in STREAM_CODES:
        raise ValueError("unknown Experiment 003 stream")
    sequence = np.random.SeedSequence(
        [
            config.master_seed,
            config.test_fixture_partition_code,
            STRATUM_CODES[stratum],
            replicate,
            STREAM_CODES[stream],
        ]
    )
    return np.random.Generator(np.random.PCG64DXSM(sequence))


def validate_seed_contract(
    config: Experiment003Config,
    contract_path: str | Path,
    root: str | Path = ".",
) -> dict[str, Any]:
    contract_file = Path(contract_path)
    contract = json.loads(contract_file.read_text(encoding="utf-8"))
    errors: list[str] = []
    expected = {
        "schema_version": config.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": config.master_seed,
        "derivation": "SeedSequence([master, partition, stratum, replicate, stream])",
        "pilot_partition": {
            "name": "experiment_003_design_validation_pilot_reserved",
            "code": config.pilot_partition_code,
            "status": "reserved_not_materialized_or_executed",
            "roots_per_stratum": config.pilot_roots_per_stratum,
            "expected_root_rows": config.pilot_blocks,
            "expected_episode_rows": config.pilot_episodes,
            "replay_roots_per_stratum": config.pilot_replay_roots_per_stratum,
        },
        "confirmatory_partition": {
            "name": "experiment_003_confirmatory_reserved",
            "code": config.confirmatory_partition_code,
            "status": "reserved_not_materialized_or_executed",
            "candidate_roots_per_stratum": list(
                config.future_candidate_roots_per_stratum
            ),
        },
        "test_fixture_partition": {
            "name": "experiment_003_non_outcome_test_fixtures",
            "code": config.test_fixture_partition_code,
        },
        "stratum_codes": STRATUM_CODES,
        "stream_codes": STREAM_CODES,
        "arms": list(config.arms),
        "replacement_or_extension_allowed": False,
        "generator_available_at_freeze": True,
        "generator_invoked": False,
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            errors.append(key)
    project_root = Path(root)
    seed_directory = project_root / "experiments/003/seeds"
    result_directory = project_root / "results/experiment-003"
    if seed_directory.exists():
        errors.append("outcome_seed_directory_exists")
    if result_directory.exists():
        errors.append("outcome_result_directory_exists")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(contract_file.read_bytes()),
        "pilot_partition_code": config.pilot_partition_code,
        "confirmatory_partition_code": config.confirmatory_partition_code,
        "pilot_expected_roots": config.pilot_blocks,
        "pilot_expected_episodes": config.pilot_episodes,
        "outcome_seed_files_present": seed_directory.exists(),
        "outcome_result_files_present": result_directory.exists(),
        "generator_invoked": False,
    }


@dataclass(frozen=True)
class Experiment003Scenario:
    schema_version: str
    stratum_id: str
    replicate: int
    root_seed_id: str
    initial_range_m: float
    initial_velocity_mps: float
    initial_propellant: float
    fault_channel: str
    fault_onset_s: float | None
    fault_end_s: float | None
    range_bias_m: float | None
    covariance_factor: float
    arm_run_order: tuple[str, ...]
    stream_hashes: dict[str, str]
    scenario_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Experiment003Streams:
    process_acceleration_mps2: np.ndarray
    primary_range_noise_m: np.ndarray
    primary_velocity_noise_mps: np.ndarray
    primary_latency_s: np.ndarray
    monitor_range_noise_m: np.ndarray
    monitor_velocity_noise_mps: np.ndarray
    monitor_latency_s: np.ndarray


def _rng(entropy: list[int]) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence(entropy)))


def _stream_rng(
    config: Experiment003Config,
    partition_code: int,
    stratum: str,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    return _rng(
        [
            config.master_seed,
            partition_code,
            STRATUM_CODES[stratum],
            replicate,
            STREAM_CODES[stream],
        ]
    )


def _array_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(str(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _truncated_velocity(rng: np.random.Generator) -> float:
    for _ in range(1_000):
        value = float(rng.normal(-0.15, 0.05))
        if -0.30 <= value <= 0.0:
            return value
    raise RuntimeError("truncated velocity sampler exceeded 1,000 draws")


def materialize_exogenous(
    config: Experiment003Config,
    production,
    stratum: str,
    replicate: int,
    *,
    partition_code: int,
) -> tuple[Experiment003Streams, dict[str, str]]:
    if stratum not in ESTIMATOR_STRATA:
        raise ValueError("unknown Experiment 003 stratum")
    process_rng = _stream_rng(
        config, partition_code, stratum, replicate, "process_disturbance"
    )
    process = np.clip(
        process_rng.normal(
            0.0,
            production.process_accel_sigma_mps2,
            production.n_exogenous_steps,
        ),
        -production.process_accel_clip_mps2,
        production.process_accel_clip_mps2,
    ).astype(np.float64)
    measurement_count = production.n_command_steps + 1

    def channel(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = _stream_rng(config, partition_code, stratum, replicate, name)
        range_noise = rng.normal(
            0.0, production.range_noise_sigma_m, measurement_count
        ).astype(np.float64)
        velocity_noise = rng.normal(
            0.0, production.velocity_noise_sigma_mps, measurement_count
        ).astype(np.float64)
        latency = np.where(
            rng.random(measurement_count)
            < production.sensor_latency_one_second_probability,
            1.0,
            0.0,
        ).astype(np.float64)
        latency[0] = 0.0
        return range_noise, velocity_noise, latency

    primary = channel("primary_measurement")
    monitor = channel("monitor_measurement")
    streams = Experiment003Streams(process, *primary, *monitor)
    return streams, {
        "process_disturbance": _array_hash(process),
        "primary_measurement": _array_hash(*primary),
        "monitor_measurement": _array_hash(*monitor),
    }


def _fault_parameters(
    config: Experiment003Config,
    stratum: str,
    rng: np.random.Generator,
) -> dict[str, Any]:
    if stratum == "E0_nominal":
        return {
            "fault_channel": "none",
            "fault_onset_s": None,
            "fault_end_s": None,
            "range_bias_m": None,
            "covariance_factor": 1.0,
        }
    onset = float(rng.uniform(config.fault_onset_min_s, config.fault_onset_max_s))
    channel = {
        "E1_primary_range_bias": "primary",
        "E2_primary_dropout": "primary",
        "E3_primary_stale": "primary",
        "E4_primary_covariance_underreporting": "primary",
        "E5_monitor_range_bias": "monitor",
        "E6_shared_range_bias": "shared",
    }[stratum]
    if stratum in {"E2_primary_dropout", "E3_primary_stale"}:
        duration = float(
            rng.uniform(config.dropout_duration_min_s, config.dropout_duration_max_s)
        )
        bias = None
        covariance_factor = 1.0
    else:
        duration = float(rng.uniform(config.bias_duration_min_s, config.bias_duration_max_s))
        if stratum == "E4_primary_covariance_underreporting":
            bias = None
            covariance_factor = config.covariance_underreporting_factor
        else:
            upper = (
                config.shared_bias_max_m
                if stratum == "E6_shared_range_bias"
                else config.bias_max_m
            )
            magnitude = float(rng.uniform(config.bias_min_m, upper))
            bias = magnitude if int(rng.integers(0, 2)) else -magnitude
            covariance_factor = 1.0
    return {
        "fault_channel": channel,
        "fault_onset_s": onset,
        "fault_end_s": onset + duration,
        "range_bias_m": bias,
        "covariance_factor": covariance_factor,
    }


def materialize_scenario(
    config: Experiment003Config,
    production,
    stratum: str,
    replicate: int,
    *,
    partition_code: int,
) -> tuple[Experiment003Scenario, Experiment003Streams]:
    if stratum not in ESTIMATOR_STRATA:
        raise ValueError("unknown Experiment 003 stratum")
    if type(replicate) is not int or replicate < 0:
        raise ValueError("replicate must be a non-negative integer")
    initial_rng = _stream_rng(config, partition_code, stratum, replicate, "initial_state")
    initial = {
        "initial_range_m": float(initial_rng.uniform(80.0, 120.0)),
        "initial_velocity_mps": _truncated_velocity(initial_rng),
        "initial_propellant": float(initial_rng.uniform(0.85, 1.0)),
    }
    fault_rng = _stream_rng(config, partition_code, stratum, replicate, "fault_parameters")
    fault = _fault_parameters(config, stratum, fault_rng)
    order_rng = _stream_rng(config, partition_code, stratum, replicate, "arm_run_order")
    arm_order = tuple(
        str(value)
        for value in np.asarray(config.arms)[order_rng.permutation(len(config.arms))]
    )
    streams, stochastic_hashes = materialize_exogenous(
        config,
        production,
        stratum,
        replicate,
        partition_code=partition_code,
    )
    stream_hashes = {
        "initial_state": sha256_bytes(canonical_json(initial)),
        **stochastic_hashes,
        "fault_parameters": sha256_bytes(canonical_json(fault)),
        "arm_run_order": sha256_bytes(canonical_json(arm_order)),
    }
    prefix = "pilot003" if partition_code == config.pilot_partition_code else "fixture003"
    unsigned = {
        "schema_version": config.schema_version,
        "stratum_id": stratum,
        "replicate": replicate,
        "root_seed_id": f"{prefix}:{stratum}:{replicate:04d}",
        **initial,
        **fault,
        "arm_run_order": arm_order,
        "stream_hashes": stream_hashes,
    }
    scenario = Experiment003Scenario(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json(unsigned)),
    )
    return scenario, streams


def materialize_test_scenario(
    config: Experiment003Config,
    production,
    stratum: str,
    replicate: int,
) -> tuple[Experiment003Scenario, Experiment003Streams]:
    return materialize_scenario(
        config,
        production,
        stratum,
        replicate,
        partition_code=config.test_fixture_partition_code,
    )


def _historical_root_ids(root: Path) -> set[str]:
    identifiers: set[str] = set()
    for directory in (
        root / "experiments/002/seeds",
        root / "experiments/002b/seeds",
        root / "experiments/002c/seeds",
        root / "experiments/002d/seeds",
        root / "experiments/002-confirmatory/seeds",
    ):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                value = json.loads(line).get("root_seed_id")
                if isinstance(value, str):
                    identifiers.add(value)
    return identifiers


def materialize_pilot_seeds(
    config: Experiment003Config,
    production,
    *,
    root: str | Path,
    freeze_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    project_root = Path(root)
    directory = project_root / "experiments/003/seeds"
    results = project_root / "results/experiment-003"
    if directory.exists() or results.exists():
        raise RuntimeError("refusing pre-existing Experiment 003 seed or result path")
    staging = directory.parent / f".seeds-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        historical_ids = _historical_root_ids(project_root)
        observed_ids: set[str] = set()
        manifest_path = staging / "pilot.jsonl"
        with manifest_path.open("w", encoding="utf-8") as handle:
            for stratum in ESTIMATOR_STRATA:
                for replicate in range(config.pilot_roots_per_stratum):
                    scenario, _ = materialize_scenario(
                        config,
                        production,
                        stratum,
                        replicate,
                        partition_code=config.pilot_partition_code,
                    )
                    if (
                        scenario.root_seed_id in observed_ids
                        or scenario.root_seed_id in historical_ids
                    ):
                        raise RuntimeError("Experiment 003 root identity is not disjoint")
                    observed_ids.add(scenario.root_seed_id)
                    handle.write(canonical_json(scenario.to_dict()).decode() + "\n")
        replay = {
            "schema_version": config.schema_version,
            "selection": "first eight replicate indices in every stratum; outcome-blind",
            "replicates_by_stratum": {
                stratum: list(range(config.pilot_replay_roots_per_stratum))
                for stratum in ESTIMATOR_STRATA
            },
        }
        replay_path = staging / "replay-subset.json"
        replay_path.write_text(
            json.dumps(replay, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index = {
            "schema_version": config.schema_version,
            "freeze_id": freeze_id,
            "seed_contract_sha256": seed_contract_sha256,
            "partition_code": config.pilot_partition_code,
            "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "root_rows": len(observed_ids),
            "planned_episode_rows": config.pilot_episodes,
            "historical_root_ids_compared": len(historical_ids),
            "materialized_only_after_freeze_verification": True,
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


def validate_materialized_pilot(
    config: Experiment003Config,
    production,
    *,
    root: str | Path,
    freeze_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    directory = Path(root) / "experiments/003/seeds"
    manifest_path = directory / "pilot.jsonl"
    replay_path = directory / "replay-subset.json"
    index_path = directory / "index.json"
    errors: list[str] = []
    try:
        rows = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
        index = json.loads(index_path.read_text(encoding="utf-8"))
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors_preview": [f"load:{exc}"]}
    counts = {stratum: 0 for stratum in ESTIMATOR_STRATA}
    root_ids: set[str] = set()
    scenario_hash_errors = 0
    for row in rows:
        stratum = row.get("stratum_id")
        replicate = row.get("replicate")
        if stratum not in counts or type(replicate) is not int:
            errors.append("invalid_scenario_key")
            continue
        counts[stratum] += 1
        root_ids.add(str(row.get("root_seed_id")))
        expected, _ = materialize_scenario(
            config,
            production,
            stratum,
            replicate,
            partition_code=config.pilot_partition_code,
        )
        scenario_hash_errors += int(row.get("scenario_hash") != expected.scenario_hash)
    if len(rows) != config.pilot_blocks or len(root_ids) != config.pilot_blocks:
        errors.append("root_count_or_uniqueness")
    if any(value != config.pilot_roots_per_stratum for value in counts.values()):
        errors.append("stratum_counts")
    if scenario_hash_errors:
        errors.append("scenario_hashes")
    expected_replay = {
        stratum: list(range(config.pilot_replay_roots_per_stratum))
        for stratum in ESTIMATOR_STRATA
    }
    if replay.get("replicates_by_stratum") != expected_replay:
        errors.append("replay_subset")
    if index.get("freeze_id") != freeze_id:
        errors.append("freeze_id")
    if index.get("seed_contract_sha256") != seed_contract_sha256:
        errors.append("seed_contract_sha256")
    if index.get("manifest_sha256") != sha256_bytes(manifest_path.read_bytes()):
        errors.append("manifest_sha256")
    if index.get("replay_subset_sha256") != sha256_bytes(replay_path.read_bytes()):
        errors.append("replay_subset_sha256")
    if root_ids & _historical_root_ids(Path(root)):
        errors.append("historical_root_overlap")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "rows": len(rows),
        "unique_root_ids": len(root_ids),
        "stratum_counts": counts,
        "scenario_hash_errors": scenario_hash_errors,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
    }
