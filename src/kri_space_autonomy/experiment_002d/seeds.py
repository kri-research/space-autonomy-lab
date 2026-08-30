from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.config import STREAM_CODES, PilotConfig
from kri_space_autonomy.experiment_002.seeds import (
    ExogenousStreams,
    canonical_json,
    sha256_bytes,
)

from .config import COMBINED_STRATUM, CombinedInformationConfig

BIT_GENERATOR = "PCG64DXSM"
PARTITION_NAME = "combined_information"


@dataclass(frozen=True)
class CombinedScenarioSpec:
    schema_version: str
    stratum_id: str
    replicate: int
    root_seed_id: str
    initial_range_m: float
    initial_velocity_mps: float
    initial_propellant: float
    fault_subtype: str
    fault_channel: str
    dropout_onset_s: float
    dropout_end_s: float
    actuator_onset_gap_s: float
    actuator_onset_s: float
    actuator_end_s: float
    actuator_effectiveness: float
    arm_run_order: tuple[str, ...]
    stream_hashes: dict[str, str]
    scenario_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rng(entropy: list[int]) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence(entropy)))


def information_rng(
    study: CombinedInformationConfig,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    return _rng(
        [
            study.master_seed,
            study.information_partition_code,
            study.combined_stratum_code,
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


def materialize_exogenous_002d(
    study: CombinedInformationConfig,
    production: PilotConfig,
    replicate: int,
) -> tuple[ExogenousStreams, dict[str, str]]:
    n = production.n_exogenous_steps
    process_rng = information_rng(study, replicate, "process_disturbance")
    process = np.clip(
        process_rng.normal(0.0, production.process_accel_sigma_mps2, n),
        -production.process_accel_clip_mps2,
        production.process_accel_clip_mps2,
    ).astype(np.float64)

    def sensor(stream: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rng = information_rng(study, replicate, stream)
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


def _sample_combined_fault(
    study: CombinedInformationConfig,
    replicate: int,
) -> dict[str, Any]:
    rng = information_rng(study, replicate, "fault_parameters")
    dropout_onset = float(
        rng.uniform(study.dropout_onset_min_s, study.dropout_onset_max_s)
    )
    dropout_duration = float(
        rng.uniform(study.dropout_duration_min_s, study.dropout_duration_max_s)
    )
    actuator_gap = float(
        rng.uniform(study.actuator_onset_gap_min_s, study.actuator_onset_gap_max_s)
    )
    actuator_onset = dropout_onset + actuator_gap
    actuator_duration = float(
        rng.uniform(study.actuator_duration_min_s, study.actuator_duration_max_s)
    )
    effectiveness = float(
        rng.uniform(
            study.actuator_effectiveness_min,
            study.actuator_effectiveness_max,
        )
    )
    return {
        "fault_subtype": "primary_dropout_plus_actuator_degradation",
        "fault_channel": "primary_and_actuator",
        "dropout_onset_s": dropout_onset,
        "dropout_end_s": dropout_onset + dropout_duration,
        "actuator_onset_gap_s": actuator_gap,
        "actuator_onset_s": actuator_onset,
        "actuator_end_s": actuator_onset + actuator_duration,
        "actuator_effectiveness": effectiveness,
    }


def materialize_scenario_002d(
    study: CombinedInformationConfig,
    production: PilotConfig,
    replicate: int,
) -> CombinedScenarioSpec:
    if not 0 <= replicate < study.information_seeds:
        raise ValueError("replicate is outside the frozen 002d information partition")
    initial_rng = information_rng(study, replicate, "initial_state")
    initial = {
        "initial_range_m": float(initial_rng.uniform(80.0, 120.0)),
        "initial_velocity_mps": _truncated_normal(
            initial_rng, -0.15, 0.05, -0.30, 0.0
        ),
        "initial_propellant": float(initial_rng.uniform(0.85, 1.0)),
    }
    fault = _sample_combined_fault(study, replicate)
    order_rng = information_rng(study, replicate, "arm_run_order")
    arm_order = tuple(
        str(value)
        for value in np.asarray(study.arms)[order_rng.permutation(len(study.arms))]
    )
    _, stochastic_hashes = materialize_exogenous_002d(study, production, replicate)
    stream_hashes = {
        "initial_state": sha256_bytes(canonical_json(initial)),
        **stochastic_hashes,
        "fault_parameters": sha256_bytes(canonical_json(fault)),
        "arm_run_order": sha256_bytes(canonical_json(arm_order)),
    }
    root_seed_id = f"experiment-002d:{PARTITION_NAME}:{COMBINED_STRATUM}:{replicate:04d}"
    unsigned = {
        "schema_version": study.schema_version,
        "stratum_id": COMBINED_STRATUM,
        "replicate": replicate,
        "root_seed_id": root_seed_id,
        **initial,
        **fault,
        "arm_run_order": arm_order,
        "stream_hashes": stream_hashes,
    }
    return CombinedScenarioSpec(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json(unsigned)),
    )


def _historical_root_ids(directories: tuple[Path, ...]) -> set[str]:
    root_ids: set[str] = set()
    for directory in directories:
        for path in directory.glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                root_seed_id = json.loads(line).get("root_seed_id")
                if root_seed_id is not None:
                    root_ids.add(str(root_seed_id))
    return root_ids


def _replay_replicates(study: CombinedInformationConfig) -> list[int]:
    rng = _rng(
        [
            study.master_seed,
            study.information_partition_code,
            study.combined_stratum_code,
            0,
            909,
        ]
    )
    return sorted(
        int(value)
        for value in rng.choice(
            study.information_seeds,
            size=study.replay_blocks,
            replace=False,
        )
    )


def write_seed_manifest_002d(
    study: CombinedInformationConfig,
    production: PilotConfig,
    output_dir: str | Path,
    historical_seed_dirs: tuple[Path, ...],
) -> dict[str, Any]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    historical_ids = _historical_root_ids(historical_seed_dirs)
    path = directory / "combined_information.jsonl"
    generated_ids: set[str] = set()
    with path.open("w", encoding="utf-8") as handle:
        for replicate in range(study.information_seeds):
            scenario = materialize_scenario_002d(study, production, replicate)
            if scenario.root_seed_id in historical_ids or scenario.root_seed_id in generated_ids:
                raise RuntimeError("002d root seed id is not disjoint")
            generated_ids.add(scenario.root_seed_id)
            row = scenario.to_dict()
            row["partition"] = PARTITION_NAME
            row["partition_code"] = study.information_partition_code
            row["seed_key_prefix"] = [
                study.master_seed,
                study.information_partition_code,
                study.combined_stratum_code,
                replicate,
            ]
            handle.write(canonical_json(row).decode() + "\n")
    replay_path = directory / "replay_subset.json"
    replay_payload = {
        "schema_version": study.schema_version,
        "selection": "fixed outcome-blind subset of combined-information roots",
        "replicates": _replay_replicates(study),
    }
    replay_path.write_text(
        json.dumps(replay_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    index = {
        "schema_version": study.schema_version,
        "bit_generator": BIT_GENERATOR,
        "master_seed": study.master_seed,
        "derivation": "SeedSequence([master, 002d_partition, F7, replicate, stream])",
        "historical_partition_codes_max": 24,
        "reserved_confirmatory_partition_code": 16,
        "partition_code": study.information_partition_code,
        "stratum_code": study.combined_stratum_code,
        "partition_rows": len(generated_ids),
        "planned_episodes": study.planned_episodes,
        "root_seed_ids_disjoint_from_experiments_002_002b_002c": True,
        "manifest_sha256": sha256_bytes(path.read_bytes()),
        "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
    }
    (directory / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index


def validate_seed_manifest_002d(
    study: CombinedInformationConfig,
    production: PilotConfig,
    directory: str | Path,
    historical_seed_dirs: tuple[Path, ...],
) -> dict[str, Any]:
    root = Path(directory)
    path = root / "combined_information.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    historical_ids = _historical_root_ids(historical_seed_dirs)
    observed_ids: set[str] = set()
    errors: list[str] = []
    for row in rows:
        root_id = str(row["root_seed_id"])
        if root_id in historical_ids or root_id in observed_ids:
            errors.append(f"duplicate:{root_id}")
        observed_ids.add(root_id)
        replicate = int(row["replicate"])
        expected = materialize_scenario_002d(study, production, replicate)
        if expected.scenario_hash != row["scenario_hash"]:
            errors.append(f"scenario_hash:{root_id}")
        if int(row["partition_code"]) != study.information_partition_code:
            errors.append(f"partition:{root_id}")
        if int(row["seed_key_prefix"][2]) != study.combined_stratum_code:
            errors.append(f"stratum_code:{root_id}")
    replay = json.loads((root / "replay_subset.json").read_text(encoding="utf-8"))
    if replay["replicates"] != _replay_replicates(study):
        errors.append("replay_subset")
    if len(rows) != study.information_seeds:
        errors.append("row_count")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "rows": len(rows),
        "unique_root_seed_ids": len(observed_ids),
        "historical_root_seed_ids_compared": len(historical_ids),
        "partition_code_disjoint": study.information_partition_code > 24,
        "confirmatory_partition_untouched": study.information_partition_code != 16,
        "manifest_sha256": sha256_bytes(path.read_bytes()),
        "replay_replicates": replay["replicates"],
    }
