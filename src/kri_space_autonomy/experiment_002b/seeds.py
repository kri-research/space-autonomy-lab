from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.config import (
    MIXED_STRATA,
    PILOT_STRATA,
    STRATUM_CODES,
    STREAM_CODES,
    PilotConfig,
)
from kri_space_autonomy.experiment_002.seeds import (
    ExogenousStreams,
    ScenarioSpec,
    canonical_json,
    sha256_bytes,
)

from .config import AmendmentConfig

BIT_GENERATOR = "PCG64DXSM"
PARTITION_NAMES = ("operational", "rate_decomposition", "fixed_replay")


def _partition_code(config: AmendmentConfig, partition: str) -> int:
    return {
        "operational": config.operational_partition_code,
        "rate_decomposition": config.rate_partition_code,
        "fixed_replay": config.replay_partition_code,
    }[partition]


def _partition_size(config: AmendmentConfig, partition: str) -> int:
    return {
        "operational": config.operational_seeds_per_stratum,
        "rate_decomposition": config.rate_seeds_per_stratum,
        "fixed_replay": config.replay_seeds_per_stratum,
    }[partition]


def _rng(entropy: list[int]) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence(entropy)))


def amendment_rng(
    amendment: AmendmentConfig,
    partition: str,
    stratum: str,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    return _rng(
        [
            amendment.master_seed,
            _partition_code(amendment, partition),
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


@cache
def _balanced_subtypes(
    master_seed: int,
    partition_code: int,
    stratum: str,
    size: int,
) -> tuple[str, ...]:
    if size == 1:
        return ("range_bias",)
    if size % 2:
        raise ValueError("mixed-stratum size must be even")
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
    labels = np.array(["range_bias"] * (size // 2) + ["dropout"] * (size // 2))
    return tuple(str(value) for value in labels[rng.permutation(size)])


def _array_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(str(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


def materialize_exogenous_002b(
    amendment: AmendmentConfig,
    production: PilotConfig,
    partition: str,
    stratum: str,
    replicate: int,
) -> tuple[ExogenousStreams, dict[str, str]]:
    n = production.n_exogenous_steps
    process_rng = amendment_rng(
        amendment, partition, stratum, replicate, "process_disturbance"
    )
    process = np.clip(
        process_rng.normal(0.0, production.process_accel_sigma_mps2, n),
        -production.process_accel_clip_mps2,
        production.process_accel_clip_mps2,
    ).astype(np.float64)

    def sensor(stream: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = amendment_rng(amendment, partition, stratum, replicate, stream)
        range_noise = rng.normal(0.0, production.range_noise_sigma_m, n + 1).astype(
            np.float64
        )
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


def _sample_fault(
    amendment: AmendmentConfig,
    partition: str,
    stratum: str,
    replicate: int,
) -> dict[str, Any]:
    rng = amendment_rng(amendment, partition, stratum, replicate, "fault_parameters")
    if stratum == "P0_nominal":
        return {
            "fault_subtype": "none",
            "fault_channel": "none",
            "fault_onset_s": None,
            "fault_end_s": None,
            "range_bias_m": None,
            "actuator_effectiveness": None,
            "model_weight_index": None,
            "model_normalized_magnitude": None,
        }
    if stratum in MIXED_STRATA:
        size = _partition_size(amendment, partition)
        subtype = _balanced_subtypes(
            amendment.master_seed,
            _partition_code(amendment, partition),
            stratum,
            size,
        )[replicate]
        channel = {
            "P1_primary_navigation": "primary",
            "P2_monitor_only": "monitor",
            "P3_shared_cause_navigation": "shared",
        }[stratum]
        onset = float(rng.uniform(120.0, 300.0))
        if subtype == "range_bias":
            duration = float(rng.uniform(30.0, 120.0))
            upper = 20.0 if channel == "shared" else 30.0
            magnitude = float(rng.uniform(5.0, upper))
            signed = magnitude if int(rng.integers(0, 2)) else -magnitude
        else:
            max_duration = 15.0 if channel == "shared" else 30.0
            duration = float(rng.uniform(5.0, max_duration))
            signed = None
        return {
            "fault_subtype": subtype,
            "fault_channel": channel,
            "fault_onset_s": onset,
            "fault_end_s": onset + duration,
            "range_bias_m": signed,
            "actuator_effectiveness": None,
            "model_weight_index": None,
            "model_normalized_magnitude": None,
        }
    onset = float(rng.uniform(120.0, 300.0))
    if stratum == "P4_model_upset":
        magnitude = float(rng.uniform(2.0, 6.0))
        signed = magnitude if int(rng.integers(0, 2)) else -magnitude
        return {
            "fault_subtype": "persistent_model_upset",
            "fault_channel": "learned_model",
            "fault_onset_s": onset,
            "fault_end_s": None,
            "range_bias_m": None,
            "actuator_effectiveness": None,
            "model_weight_index": int(rng.integers(0, 6)),
            "model_normalized_magnitude": signed,
        }
    if stratum == "P5_actuator_degradation":
        return {
            "fault_subtype": "actuator_degradation",
            "fault_channel": "actuator",
            "fault_onset_s": onset,
            "fault_end_s": onset + float(rng.uniform(30.0, 150.0)),
            "range_bias_m": None,
            "actuator_effectiveness": float(rng.uniform(0.25, 0.75)),
            "model_weight_index": None,
            "model_normalized_magnitude": None,
        }
    raise ValueError(f"unknown stratum: {stratum}")


def materialize_scenario_002b(
    amendment: AmendmentConfig,
    production: PilotConfig,
    partition: str,
    stratum: str,
    replicate: int,
) -> ScenarioSpec:
    if partition not in PARTITION_NAMES:
        raise ValueError(f"unknown 002b partition: {partition}")
    if stratum not in PILOT_STRATA:
        raise ValueError(f"unknown stratum: {stratum}")
    if not 0 <= replicate < _partition_size(amendment, partition):
        raise ValueError("replicate is outside the frozen 002b partition")
    initial_rng = amendment_rng(amendment, partition, stratum, replicate, "initial_state")
    initial = {
        "initial_range_m": float(initial_rng.uniform(80.0, 120.0)),
        "initial_velocity_mps": _truncated_normal(
            initial_rng, -0.15, 0.05, -0.30, 0.0
        ),
        "initial_propellant": float(initial_rng.uniform(0.85, 1.0)),
    }
    fault = _sample_fault(amendment, partition, stratum, replicate)
    _, stochastic_hashes = materialize_exogenous_002b(
        amendment, production, partition, stratum, replicate
    )
    stream_hashes = {
        "initial_state": sha256_bytes(canonical_json(initial)),
        **stochastic_hashes,
        "fault_parameters": sha256_bytes(canonical_json(fault)),
        "arm_run_order": sha256_bytes(canonical_json(("PD",))),
    }
    root_seed_id = f"experiment-002b:{partition}:{stratum}:{replicate:04d}"
    unsigned = {
        "schema_version": amendment.schema_version,
        "stratum_id": stratum,
        "replicate": replicate,
        "root_seed_id": root_seed_id,
        **initial,
        **fault,
        "arm_run_order": ("PD",),
        "stream_hashes": stream_hashes,
    }
    return ScenarioSpec(**unsigned, scenario_hash=sha256_bytes(canonical_json(unsigned)))


def _historical_root_ids(directory: Path) -> set[str]:
    root_ids: set[str] = set()
    for path in directory.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            root_seed_id = row.get("root_seed_id")
            if root_seed_id is not None:
                root_ids.add(str(root_seed_id))
    return root_ids


def write_seed_manifests_002b(
    amendment: AmendmentConfig,
    production: PilotConfig,
    output_dir: str | Path,
    historical_seed_dir: str | Path,
) -> dict[str, Any]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    historical_ids = _historical_root_ids(Path(historical_seed_dir))
    manifest_hashes: dict[str, str] = {}
    generated_ids: set[str] = set()
    partition_rows: dict[str, int] = {}
    for partition in PARTITION_NAMES:
        path = directory / f"{partition}.jsonl"
        row_count = 0
        with path.open("w", encoding="utf-8") as handle:
            for stratum in PILOT_STRATA:
                for replicate in range(_partition_size(amendment, partition)):
                    scenario = materialize_scenario_002b(
                        amendment, production, partition, stratum, replicate
                    )
                    duplicate = (
                        scenario.root_seed_id in historical_ids
                        or scenario.root_seed_id in generated_ids
                    )
                    if duplicate:
                        raise RuntimeError("002b root seed id is not disjoint")
                    generated_ids.add(scenario.root_seed_id)
                    row = scenario.to_dict()
                    row["partition"] = partition
                    row["partition_code"] = _partition_code(amendment, partition)
                    row["seed_key_prefix"] = [
                        amendment.master_seed,
                        _partition_code(amendment, partition),
                        STRATUM_CODES[stratum],
                        replicate,
                    ]
                    handle.write(canonical_json(row).decode() + "\n")
                    row_count += 1
        partition_rows[partition] = row_count
        manifest_hashes[path.name] = sha256_bytes(path.read_bytes())
    index = {
        "schema_version": amendment.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": amendment.master_seed,
        "derivation": "SeedSequence([master, 002b_partition, stratum, replicate, stream])",
        "historical_partition_codes_max": 19,
        "partition_codes": {
            partition: _partition_code(amendment, partition) for partition in PARTITION_NAMES
        },
        "partition_rows": partition_rows,
        "root_seed_ids_disjoint_from_experiment_002": True,
        "manifest_hashes": manifest_hashes,
    }
    index_path = directory / "index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index


def validate_seed_manifests_002b(
    amendment: AmendmentConfig,
    production: PilotConfig,
    directory: str | Path,
    historical_seed_dir: str | Path,
) -> dict[str, Any]:
    root = Path(directory)
    historical_ids = _historical_root_ids(Path(historical_seed_dir))
    all_ids: set[str] = set()
    partitions: dict[str, Any] = {}
    errors: list[str] = []
    for partition in PARTITION_NAMES:
        rows = [
            json.loads(line)
            for line in (root / f"{partition}.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        counts = {stratum: 0 for stratum in PILOT_STRATA}
        subtype_counts = {
            stratum: {"range_bias": 0, "dropout": 0} for stratum in MIXED_STRATA
        }
        for row in rows:
            root_id = row["root_seed_id"]
            if root_id in historical_ids or root_id in all_ids:
                errors.append(f"duplicate:{root_id}")
            all_ids.add(root_id)
            stratum = row["stratum_id"]
            counts[stratum] += 1
            if stratum in MIXED_STRATA:
                subtype_counts[stratum][row["fault_subtype"]] += 1
            expected = materialize_scenario_002b(
                amendment, production, partition, stratum, int(row["replicate"])
            )
            if expected.scenario_hash != row["scenario_hash"]:
                errors.append(f"scenario_hash:{root_id}")
        expected_size = _partition_size(amendment, partition)
        if any(count != expected_size for count in counts.values()):
            errors.append(f"counts:{partition}")
        if expected_size > 1:
            expected_mix = {"range_bias": expected_size // 2, "dropout": expected_size // 2}
            if any(value != expected_mix for value in subtype_counts.values()):
                errors.append(f"subtypes:{partition}")
        partitions[partition] = {
            "rows": len(rows),
            "stratum_counts": counts,
            "subtype_counts": subtype_counts,
        }
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "unique_002b_root_seed_ids": len(all_ids),
        "historical_root_seed_ids_compared": len(historical_ids),
        "partition_codes_disjoint": min(
            amendment.operational_partition_code,
            amendment.rate_partition_code,
            amendment.replay_partition_code,
        )
        > 19,
        "partitions": partitions,
    }
