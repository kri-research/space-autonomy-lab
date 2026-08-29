from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from .config import (
    ARMS,
    MIXED_STRATA,
    PARTITION_CODES,
    PILOT_STRATA,
    STRATUM_CODES,
    STREAM_CODES,
    PilotConfig,
)

BIT_GENERATOR = "PCG64DXSM"
PARTITION_SIZES = {
    "train_fit": 2000,
    "train_stop": 500,
    "validation": 500,
    "metric_calibration": 500,
}


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rng(entropy: list[int]) -> np.random.Generator:
    sequence = np.random.SeedSequence(entropy)
    return np.random.Generator(np.random.PCG64DXSM(sequence))


def partition_rng(
    config: PilotConfig, partition: str, index: int, stream: str
) -> np.random.Generator:
    return _rng(
        [
            config.master_seed,
            PARTITION_CODES[partition],
            0,
            index,
            STREAM_CODES[stream],
        ]
    )


def pilot_rng(
    config: PilotConfig, stratum: str, replicate: int, stream: str
) -> np.random.Generator:
    return _rng(
        [
            config.master_seed,
            PARTITION_CODES["pilot"],
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
def _balanced_subtype_order(master_seed: int, stratum: str, n: int) -> tuple[str, ...]:
    if n != 400:
        raise ValueError("mixed pilot strata are frozen at 400 blocks")
    rng = _rng(
        [
            master_seed,
            PARTITION_CODES["pilot"],
            STRATUM_CODES[stratum],
            0,
            STREAM_CODES["fault_parameters"],
            50_50,
        ]
    )
    labels = np.array(["range_bias"] * 200 + ["dropout"] * 200, dtype="U10")
    return tuple(str(value) for value in labels[rng.permutation(n)])


@dataclass(frozen=True)
class ScenarioSpec:
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
    range_bias_m: float | None
    actuator_effectiveness: float | None
    model_weight_index: int | None
    model_normalized_magnitude: float | None
    arm_run_order: tuple[str, ...]
    stream_hashes: dict[str, str]
    scenario_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExogenousStreams:
    process_acceleration_mps2: np.ndarray
    primary_range_noise_m: np.ndarray
    primary_velocity_noise_mps: np.ndarray
    primary_latency_s: np.ndarray
    monitor_range_noise_m: np.ndarray
    monitor_velocity_noise_mps: np.ndarray
    monitor_latency_s: np.ndarray


def _array_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(str(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


def materialize_exogenous(
    config: PilotConfig, stratum: str, replicate: int
) -> tuple[ExogenousStreams, dict[str, str]]:
    n = config.n_exogenous_steps
    process_rng = pilot_rng(config, stratum, replicate, "process_disturbance")
    process = np.clip(
        process_rng.normal(0.0, config.process_accel_sigma_mps2, n),
        -config.process_accel_clip_mps2,
        config.process_accel_clip_mps2,
    ).astype(np.float64)

    def sensor(channel: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = pilot_rng(config, stratum, replicate, channel)
        range_noise = rng.normal(0.0, config.range_noise_sigma_m, n + 1).astype(np.float64)
        velocity_noise = rng.normal(0.0, config.velocity_noise_sigma_mps, n + 1).astype(np.float64)
        latency = np.where(
            rng.random(n + 1) < config.sensor_latency_one_second_probability,
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


def materialize_partition_case(
    config: PilotConfig, partition: str, index: int
) -> tuple[ScenarioSpec, ExogenousStreams]:
    if partition not in {"metric_calibration", "train_fit", "train_stop", "validation"}:
        raise ValueError("unsupported non-pilot partition")
    initial_rng = partition_rng(config, partition, index, "initial_state")
    initial = {
        "initial_range_m": float(initial_rng.uniform(80.0, 120.0)),
        "initial_velocity_mps": _truncated_normal(initial_rng, -0.15, 0.05, -0.30, 0.0),
        "initial_propellant": float(initial_rng.uniform(0.85, 1.0)),
    }
    n = config.n_exogenous_steps
    process_rng = partition_rng(config, partition, index, "process_disturbance")
    process = np.clip(
        process_rng.normal(0.0, config.process_accel_sigma_mps2, n),
        -config.process_accel_clip_mps2,
        config.process_accel_clip_mps2,
    ).astype(np.float64)

    def sensor(channel: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = partition_rng(config, partition, index, channel)
        return (
            rng.normal(0.0, config.range_noise_sigma_m, n + 1).astype(np.float64),
            rng.normal(0.0, config.velocity_noise_sigma_mps, n + 1).astype(np.float64),
            np.where(
                rng.random(n + 1) < config.sensor_latency_one_second_probability,
                1.0,
                0.0,
            ).astype(np.float64),
        )

    primary = sensor("primary_sensor")
    monitor = sensor("monitor_sensor")
    streams = ExogenousStreams(process, *primary, *monitor)
    order_rng = partition_rng(config, partition, index, "arm_run_order")
    arm_order = tuple(str(value) for value in np.asarray(ARMS)[order_rng.permutation(len(ARMS))])
    stream_hashes = {
        "initial_state": sha256_bytes(canonical_json(initial)),
        "process_disturbance": _array_hash(process),
        "primary_sensor": _array_hash(*primary),
        "monitor_sensor": _array_hash(*monitor),
        "fault_parameters": sha256_bytes(canonical_json({"fault_subtype": "none"})),
        "arm_run_order": sha256_bytes(canonical_json(arm_order)),
    }
    unsigned = {
        "schema_version": config.schema_version,
        "stratum_id": f"{partition}_nominal",
        "replicate": index,
        "root_seed_id": f"{partition}:{index:05d}",
        **initial,
        "fault_subtype": "none",
        "fault_channel": "none",
        "fault_onset_s": None,
        "fault_end_s": None,
        "range_bias_m": None,
        "actuator_effectiveness": None,
        "model_weight_index": None,
        "model_normalized_magnitude": None,
        "arm_run_order": arm_order,
        "stream_hashes": stream_hashes,
    }
    return ScenarioSpec(**unsigned, scenario_hash=sha256_bytes(canonical_json(unsigned))), streams


def _sample_fault(config: PilotConfig, stratum: str, replicate: int) -> dict[str, Any]:
    rng = pilot_rng(config, stratum, replicate, "fault_parameters")
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
        subtype = _balanced_subtype_order(config.master_seed, stratum, 400)[replicate]
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


def materialize_scenario(config: PilotConfig, stratum: str, replicate: int) -> ScenarioSpec:
    if stratum not in PILOT_STRATA:
        raise ValueError(f"unknown stratum: {stratum}")
    if not 0 <= replicate < config.seeds_per_stratum:
        raise ValueError("replicate is outside the frozen pilot manifest")
    initial_rng = pilot_rng(config, stratum, replicate, "initial_state")
    initial = {
        "initial_range_m": float(initial_rng.uniform(80.0, 120.0)),
        "initial_velocity_mps": _truncated_normal(initial_rng, -0.15, 0.05, -0.30, 0.0),
        "initial_propellant": float(initial_rng.uniform(0.85, 1.0)),
    }
    fault = _sample_fault(config, stratum, replicate)
    order_rng = pilot_rng(config, stratum, replicate, "arm_run_order")
    arm_order = tuple(str(value) for value in np.asarray(ARMS)[order_rng.permutation(len(ARMS))])
    _, stochastic_hashes = materialize_exogenous(config, stratum, replicate)
    stream_hashes = {
        "initial_state": sha256_bytes(canonical_json(initial)),
        **stochastic_hashes,
        "fault_parameters": sha256_bytes(canonical_json(fault)),
        "arm_run_order": sha256_bytes(canonical_json(arm_order)),
    }
    root_seed_id = f"pilot:{stratum}:{replicate:04d}"
    unsigned = {
        "schema_version": config.schema_version,
        "stratum_id": stratum,
        "replicate": replicate,
        "root_seed_id": root_seed_id,
        **initial,
        **fault,
        "arm_run_order": arm_order,
        "stream_hashes": stream_hashes,
    }
    return ScenarioSpec(**unsigned, scenario_hash=sha256_bytes(canonical_json(unsigned)))


def write_seed_manifests(config: PilotConfig, output_dir: str | Path) -> dict[str, str]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str] = {}
    for partition, size in PARTITION_SIZES.items():
        path = directory / f"{partition}.jsonl"
        lines = []
        for index in range(size):
            row = {
                "schema_version": config.schema_version,
                "partition": partition,
                "partition_code": PARTITION_CODES[partition],
                "index": index,
                "root_seed_id": f"{partition}:{index:05d}",
                "seed_key": [config.master_seed, PARTITION_CODES[partition], 0, index],
            }
            lines.append(canonical_json(row).decode())
        payload = ("\n".join(lines) + "\n").encode()
        path.write_bytes(payload)
        hashes[path.name] = sha256_bytes(payload)

    pilot_path = directory / "pilot.jsonl"
    with pilot_path.open("w", encoding="utf-8") as handle:
        for stratum in PILOT_STRATA:
            for replicate in range(config.seeds_per_stratum):
                handle.write(
                    canonical_json(
                        materialize_scenario(config, stratum, replicate).to_dict()
                    ).decode()
                )
                handle.write("\n")
    pilot_payload = pilot_path.read_bytes()
    hashes[pilot_path.name] = sha256_bytes(pilot_payload)

    reserved = {
        "schema_version": config.schema_version,
        "partition": "future_confirmatory_reserved",
        "partition_code": PARTITION_CODES["future_confirmatory_reserved"],
        "status": "reserved_not_materialized_or_executed",
        "scope_note": "The 32,000-episode confirmatory campaign is outside this pilot.",
    }
    reserved_path = directory / "future_confirmatory_reserved.json"
    reserved_path.write_bytes(canonical_json(reserved) + b"\n")
    hashes[reserved_path.name] = sha256_bytes(reserved_path.read_bytes())

    index = {
        "schema_version": config.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": config.master_seed,
        "derivation": "SeedSequence([master, partition, stratum, replicate, stream])",
        "manifest_hashes": hashes,
    }
    index_path = directory / "index.json"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return hashes


def validate_pilot_manifest(config: PilotConfig, path: str | Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    ids = {row["root_seed_id"] for row in rows}
    counts = {stratum: 0 for stratum in PILOT_STRATA}
    subtype_counts = {stratum: {"range_bias": 0, "dropout": 0} for stratum in MIXED_STRATA}
    hash_errors = 0
    for row in rows:
        counts[row["stratum_id"]] += 1
        if row["stratum_id"] in MIXED_STRATA:
            subtype_counts[row["stratum_id"]][row["fault_subtype"]] += 1
        expected = materialize_scenario(config, row["stratum_id"], int(row["replicate"]))
        hash_errors += int(expected.scenario_hash != row["scenario_hash"])
    valid = (
        len(rows) == config.planned_blocks
        and len(ids) == config.planned_blocks
        and all(count == 400 for count in counts.values())
        and all(values == {"range_bias": 200, "dropout": 200} for values in subtype_counts.values())
        and hash_errors == 0
    )
    return {
        "valid": valid,
        "rows": len(rows),
        "unique_root_seed_ids": len(ids),
        "stratum_counts": counts,
        "subtype_counts": subtype_counts,
        "scenario_hash_errors": hash_errors,
    }
