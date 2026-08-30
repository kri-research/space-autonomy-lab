from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.config import STREAM_CODES, PilotConfig
from kri_space_autonomy.experiment_002.seeds import (
    ExogenousStreams,
    canonical_json,
    sha256_bytes,
)

from .config import (
    CONFIRMATORY_STRATA,
    MIXED_STRATA,
    STRATUM_CODES,
    ConfirmatoryConfig,
)

BIT_GENERATOR = "PCG64DXSM"


@dataclass(frozen=True)
class ConfirmatoryScenarioSpec:
    schema_version: str
    stratum_id: str
    replicate: int
    root_seed_id: str
    initial_range_m: float
    initial_velocity_mps: float
    initial_propellant: float
    fault_subtype: str
    fault_channel: str
    fault_onset_s: float | None
    fault_end_s: float | None
    navigation_subtype: str
    navigation_channel: str
    navigation_onset_s: float | None
    navigation_end_s: float | None
    range_bias_m: float | None
    actuator_onset_s: float | None
    actuator_end_s: float | None
    actuator_effectiveness: float | None
    model_onset_s: float | None
    model_weight_index: int | None
    model_normalized_magnitude: float | None
    arm_run_order: tuple[str, ...]
    stream_hashes: dict[str, str]
    scenario_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rng(entropy: list[int]) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence(entropy)))


def _stream_rng(
    study: ConfirmatoryConfig,
    partition_code: int,
    stratum: str,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    return _rng(
        [
            study.master_seed,
            partition_code,
            STRATUM_CODES[stratum],
            replicate,
            STREAM_CODES[stream],
        ]
    )


def _truncated_normal(
    rng: np.random.Generator,
    mean: float,
    sd: float,
    lower: float,
    upper: float,
) -> float:
    for _ in range(1000):
        value = float(rng.normal(mean, sd))
        if lower <= value <= upper:
            return value
    raise RuntimeError("truncated-normal rejection sampler exceeded 1,000 draws")


def _array_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(str(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


@cache
def _balanced_subtype_order(
    master_seed: int,
    partition_code: int,
    stratum: str,
    n: int,
) -> tuple[str, ...]:
    if stratum not in MIXED_STRATA or n != 1000:
        raise ValueError("F3/F4 subtype schedules are frozen at 1,000 roots")
    rng = _rng(
        [
            master_seed,
            partition_code,
            STRATUM_CODES[stratum],
            0,
            STREAM_CODES["fault_parameters"],
            50_50,
        ]
    )
    labels = np.array(["range_bias"] * 500 + ["dropout"] * 500, dtype="U10")
    return tuple(str(value) for value in labels[rng.permutation(n)])


def _materialize_exogenous(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    stratum: str,
    replicate: int,
    partition_code: int,
) -> tuple[ExogenousStreams, dict[str, str]]:
    n = production.n_exogenous_steps
    process_rng = _stream_rng(
        study, partition_code, stratum, replicate, "process_disturbance"
    )
    process = np.clip(
        process_rng.normal(0.0, production.process_accel_sigma_mps2, n),
        -production.process_accel_clip_mps2,
        production.process_accel_clip_mps2,
    ).astype(np.float64)

    def sensor(stream: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = _stream_rng(study, partition_code, stratum, replicate, stream)
        range_noise = rng.normal(
            0.0, production.range_noise_sigma_m, n + 1
        ).astype(np.float64)
        velocity_noise = rng.normal(
            0.0, production.velocity_noise_sigma_mps, n + 1
        ).astype(np.float64)
        latency = np.where(
            rng.random(n + 1) < production.sensor_latency_one_second_probability,
            1.0,
            0.0,
        ).astype(np.float64)
        return range_noise, velocity_noise, latency

    primary = sensor("primary_sensor")
    monitor = sensor("monitor_sensor")
    streams = ExogenousStreams(process, *primary, *monitor)
    hashes = {
        "process_disturbance": _array_hash(process),
        "primary_sensor": _array_hash(*primary),
        "monitor_sensor": _array_hash(*monitor),
    }
    return streams, hashes


def materialize_exogenous(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    stratum: str,
    replicate: int,
) -> tuple[ExogenousStreams, dict[str, str]]:
    return _materialize_exogenous(
        study, production, stratum, replicate, study.partition_code
    )


def _sample_fault(
    study: ConfirmatoryConfig,
    stratum: str,
    replicate: int,
    partition_code: int,
) -> dict[str, Any]:
    rng = _stream_rng(study, partition_code, stratum, replicate, "fault_parameters")
    empty = {
        "navigation_subtype": "none",
        "navigation_channel": "none",
        "navigation_onset_s": None,
        "navigation_end_s": None,
        "range_bias_m": None,
        "actuator_onset_s": None,
        "actuator_end_s": None,
        "actuator_effectiveness": None,
        "model_onset_s": None,
        "model_weight_index": None,
        "model_normalized_magnitude": None,
    }
    if stratum == "F0_nominal":
        return {
            "fault_subtype": "none",
            "fault_channel": "none",
            "fault_onset_s": None,
            "fault_end_s": None,
            **empty,
        }

    if stratum in {
        "F1_primary_range_bias",
        "F2_primary_dropout",
        "F3_monitor_channel_fault",
        "F4_shared_cause_navigation",
    }:
        if stratum == "F1_primary_range_bias":
            subtype = "range_bias"
            channel = "primary"
        elif stratum == "F2_primary_dropout":
            subtype = "dropout"
            channel = "primary"
        else:
            subtype = _balanced_subtype_order(
                study.master_seed,
                partition_code,
                stratum,
                study.seeds_per_stratum,
            )[replicate]
            channel = (
                "monitor"
                if stratum == "F3_monitor_channel_fault"
                else "shared"
            )
        onset = float(rng.uniform(120.0, 300.0))
        if subtype == "range_bias":
            duration = float(rng.uniform(30.0, 120.0))
            upper = 20.0 if channel == "shared" else 30.0
            magnitude = float(rng.uniform(5.0, upper))
            signed = magnitude if int(rng.integers(0, 2)) else -magnitude
        else:
            duration = float(rng.uniform(5.0, 15.0 if channel == "shared" else 30.0))
            signed = None
        return {
            "fault_subtype": subtype,
            "fault_channel": channel,
            "fault_onset_s": onset,
            "fault_end_s": onset + duration,
            **{
                **empty,
                "navigation_subtype": subtype,
                "navigation_channel": channel,
                "navigation_onset_s": onset,
                "navigation_end_s": onset + duration,
                "range_bias_m": signed,
            },
        }

    onset = float(rng.uniform(120.0, 300.0))
    if stratum == "F5_persistent_model_upset":
        magnitude = float(rng.uniform(2.0, 6.0))
        signed = magnitude if int(rng.integers(0, 2)) else -magnitude
        return {
            "fault_subtype": "persistent_model_upset",
            "fault_channel": "learned_model",
            "fault_onset_s": onset,
            "fault_end_s": None,
            **{
                **empty,
                "model_onset_s": onset,
                "model_weight_index": int(rng.integers(0, 6)),
                "model_normalized_magnitude": signed,
            },
        }
    if stratum == "F6_actuator_degradation":
        end = onset + float(rng.uniform(30.0, 150.0))
        return {
            "fault_subtype": "actuator_degradation",
            "fault_channel": "actuator",
            "fault_onset_s": onset,
            "fault_end_s": end,
            **{
                **empty,
                "actuator_onset_s": onset,
                "actuator_end_s": end,
                "actuator_effectiveness": float(rng.uniform(0.25, 0.75)),
            },
        }
    if stratum == "F7_combined_primary_dropout_actuator_degradation":
        dropout_onset = onset
        dropout_duration = float(rng.uniform(5.0, 30.0))
        actuator_gap = float(rng.uniform(-30.0, 30.0))
        actuator_onset = dropout_onset + actuator_gap
        actuator_duration = float(rng.uniform(30.0, 150.0))
        actuator_end = actuator_onset + actuator_duration
        recovery_onset = min(dropout_onset, actuator_onset)
        recovery_end = max(dropout_onset + dropout_duration, actuator_end)
        return {
            "fault_subtype": "primary_dropout_plus_actuator_degradation",
            "fault_channel": "primary_and_actuator",
            "fault_onset_s": recovery_onset,
            "fault_end_s": recovery_end,
            **{
                **empty,
                "navigation_subtype": "dropout",
                "navigation_channel": "primary",
                "navigation_onset_s": dropout_onset,
                "navigation_end_s": dropout_onset + dropout_duration,
                "actuator_onset_s": actuator_onset,
                "actuator_end_s": actuator_end,
                "actuator_effectiveness": float(rng.uniform(0.25, 0.75)),
            },
        }
    raise ValueError(f"unknown confirmatory stratum: {stratum}")


def _materialize_scenario(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    stratum: str,
    replicate: int,
    partition_code: int,
) -> ConfirmatoryScenarioSpec:
    if stratum not in CONFIRMATORY_STRATA:
        raise ValueError(f"unknown confirmatory stratum: {stratum}")
    if not 0 <= replicate < study.seeds_per_stratum:
        raise ValueError("replicate is outside the frozen confirmatory partition")
    initial_rng = _stream_rng(study, partition_code, stratum, replicate, "initial_state")
    initial = {
        "initial_range_m": float(initial_rng.uniform(80.0, 120.0)),
        "initial_velocity_mps": _truncated_normal(
            initial_rng, -0.15, 0.05, -0.30, 0.0
        ),
        "initial_propellant": float(initial_rng.uniform(0.85, 1.0)),
    }
    fault = _sample_fault(study, stratum, replicate, partition_code)
    order_rng = _stream_rng(study, partition_code, stratum, replicate, "arm_run_order")
    arm_order = tuple(
        str(value)
        for value in np.asarray(study.arms)[order_rng.permutation(len(study.arms))]
    )
    _, stochastic_hashes = _materialize_exogenous(
        study, production, stratum, replicate, partition_code
    )
    stream_hashes = {
        "initial_state": sha256_bytes(canonical_json(initial)),
        **stochastic_hashes,
        "fault_parameters": sha256_bytes(canonical_json(fault)),
        "arm_run_order": sha256_bytes(canonical_json(arm_order)),
    }
    root_seed_id = (
        f"experiment-002-confirmatory:{study.partition_name}:{stratum}:{replicate:04d}"
    )
    unsigned = {
        "schema_version": study.schema_version,
        "stratum_id": stratum,
        "replicate": replicate,
        "root_seed_id": root_seed_id,
        **initial,
        **fault,
        "arm_run_order": arm_order,
        "stream_hashes": stream_hashes,
    }
    return ConfirmatoryScenarioSpec(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json(unsigned)),
    )


def materialize_scenario(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    stratum: str,
    replicate: int,
) -> ConfirmatoryScenarioSpec:
    return _materialize_scenario(
        study, production, stratum, replicate, study.partition_code
    )


def materialize_nonreserved_test_scenario(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    stratum: str,
    replicate: int,
    partition_code: int,
) -> ConfirmatoryScenarioSpec:
    if partition_code <= 25:
        raise ValueError("test scenarios require a nonhistorical, nonreserved partition code")
    return _materialize_scenario(
        study, production, stratum, replicate, partition_code
    )


def validate_seed_contract(study: ConfirmatoryConfig, path: str | Path) -> dict[str, Any]:
    contract = json.loads(Path(path).read_text(encoding="utf-8"))
    errors: list[str] = []
    if contract.get("partition_code") != study.partition_code:
        errors.append("partition_code")
    if contract.get("status_at_freeze") != "reserved_not_materialized_or_executed":
        errors.append("status_at_freeze")
    if contract.get("expected_root_rows") != study.planned_blocks:
        errors.append("expected_root_rows")
    if contract.get("expected_episode_rows") != study.planned_episodes:
        errors.append("expected_episode_rows")
    observed = {
        item.get("id"): (item.get("code"), item.get("roots"), item.get("weight"))
        for item in contract.get("strata", [])
    }
    expected = {
        name: (STRATUM_CODES[name], study.seeds_per_stratum, study.stratum_weight)
        for name in CONFIRMATORY_STRATA
    }
    if observed != expected:
        errors.append("strata")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "partition_code": contract.get("partition_code"),
        "status_at_freeze": contract.get("status_at_freeze"),
        "expected_root_rows": contract.get("expected_root_rows"),
        "expected_episode_rows": contract.get("expected_episode_rows"),
        "contract_sha256": sha256_bytes(Path(path).read_bytes()),
    }


def _historical_root_ids(directories: tuple[Path, ...]) -> set[str]:
    root_ids: set[str] = set()
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in directory.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                root_seed_id = json.loads(line).get("root_seed_id")
                if root_seed_id is not None:
                    root_ids.add(str(root_seed_id))
    return root_ids


def _replay_replicates(study: ConfirmatoryConfig, stratum: str) -> list[int]:
    rng = _rng(
        [
            study.master_seed,
            study.partition_code,
            STRATUM_CODES[stratum],
            0,
            909,
        ]
    )
    return sorted(
        int(value)
        for value in rng.choice(
            study.seeds_per_stratum,
            size=study.replay_blocks_per_stratum,
            replace=False,
        )
    )


def write_confirmatory_seed_manifest(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    output_dir: str | Path,
    historical_seed_dirs: tuple[Path, ...],
    freeze_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    directory = Path(output_dir)
    if directory.exists():
        raise RuntimeError("refusing pre-existing confirmatory seed directory")
    staging = directory.parent / f".{directory.name}-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        historical_ids = _historical_root_ids(historical_seed_dirs)
        generated_ids: set[str] = set()
        manifest_path = staging / "confirmatory.jsonl"
        with manifest_path.open("w", encoding="utf-8") as handle:
            for stratum in CONFIRMATORY_STRATA:
                for replicate in range(study.seeds_per_stratum):
                    scenario = materialize_scenario(
                        study, production, stratum, replicate
                    )
                    if (
                        scenario.root_seed_id in historical_ids
                        or scenario.root_seed_id in generated_ids
                    ):
                        raise RuntimeError("confirmatory root seed id is not disjoint")
                    generated_ids.add(scenario.root_seed_id)
                    row = scenario.to_dict()
                    row["partition"] = study.partition_name
                    row["partition_code"] = study.partition_code
                    row["stratum_code"] = STRATUM_CODES[stratum]
                    row["seed_key_prefix"] = [
                        study.master_seed,
                        study.partition_code,
                        STRATUM_CODES[stratum],
                        replicate,
                    ]
                    handle.write(canonical_json(row).decode() + "\n")
        replay_path = staging / "replay-subset.json"
        replay = {
            "schema_version": study.schema_version,
            "selection": "fixed outcome-blind same-platform replay subset",
            "replicates_by_stratum": {
                stratum: _replay_replicates(study, stratum)
                for stratum in CONFIRMATORY_STRATA
            },
        }
        replay_path.write_text(
            json.dumps(replay, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index = {
            "schema_version": study.schema_version,
            "freeze_id": freeze_id,
            "seed_contract_sha256": seed_contract_sha256,
            "bit_generator": BIT_GENERATOR,
            "master_seed": study.master_seed,
            "partition": study.partition_name,
            "partition_code": study.partition_code,
            "stratum_codes": STRATUM_CODES,
            "partition_rows": len(generated_ids),
            "planned_episodes": study.planned_episodes,
            "historical_root_seed_ids_compared": len(historical_ids),
            "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "materialized_only_after_freeze_verification": True,
        }
        (staging / "index.json").write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(staging, directory)
        return index
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def validate_confirmatory_seed_manifest(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    directory: str | Path,
    historical_seed_dirs: tuple[Path, ...],
    freeze_id: str,
    seed_contract_sha256: str,
) -> dict[str, Any]:
    root = Path(directory)
    manifest_path = root / "confirmatory.jsonl"
    replay_path = root / "replay-subset.json"
    index_path = root / "index.json"
    rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    historical_ids = _historical_root_ids(historical_seed_dirs)
    observed_ids: set[str] = set()
    counts = {stratum: 0 for stratum in CONFIRMATORY_STRATA}
    subtype_counts = {
        stratum: {"range_bias": 0, "dropout": 0} for stratum in MIXED_STRATA
    }
    errors: list[str] = []
    for row in rows:
        root_id = str(row["root_seed_id"])
        stratum = str(row["stratum_id"])
        replicate = int(row["replicate"])
        if root_id in historical_ids or root_id in observed_ids:
            errors.append(f"duplicate:{root_id}")
        observed_ids.add(root_id)
        if stratum not in counts:
            errors.append(f"stratum:{root_id}")
            continue
        counts[stratum] += 1
        if stratum in subtype_counts:
            subtype = str(row["navigation_subtype"])
            if subtype not in subtype_counts[stratum]:
                errors.append(f"subtype:{root_id}")
            else:
                subtype_counts[stratum][subtype] += 1
        expected = materialize_scenario(study, production, stratum, replicate)
        if expected.scenario_hash != row.get("scenario_hash"):
            errors.append(f"scenario_hash:{root_id}")
        if row.get("partition_code") != study.partition_code:
            errors.append(f"partition:{root_id}")
        if row.get("stratum_code") != STRATUM_CODES[stratum]:
            errors.append(f"stratum_code:{root_id}")
        if set(row.get("arm_run_order", [])) != set(study.arms):
            errors.append(f"arm_order:{root_id}")
    expected_replay = {
        stratum: _replay_replicates(study, stratum)
        for stratum in CONFIRMATORY_STRATA
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
    if len(rows) != study.planned_blocks:
        errors.append("row_count")
    if any(value != study.seeds_per_stratum for value in counts.values()):
        errors.append("stratum_counts")
    if any(
        value != {"range_bias": 500, "dropout": 500}
        for value in subtype_counts.values()
    ):
        errors.append("subtype_counts")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "rows": len(rows),
        "unique_root_seed_ids": len(observed_ids),
        "stratum_counts": counts,
        "subtype_counts": subtype_counts,
        "historical_root_seed_ids_compared": len(historical_ids),
        "partition_code": study.partition_code,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_replicates_by_stratum": expected_replay,
    }
