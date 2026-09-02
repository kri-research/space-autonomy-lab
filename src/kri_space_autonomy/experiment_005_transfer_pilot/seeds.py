from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_005.config import Experiment005Config
from kri_space_autonomy.experiment_005.seeds import BIT_GENERATOR, STREAM_CODES

from .config import CONFIGURATIONS, TransferCase, TransferPilotConfig

SEED_DERIVATION = (
    "SeedSequence([master, partition, geometry_case, challenge_case, replicate, stream])"
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _array_hash(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(str(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()


def _stream_rng(
    foundation: Experiment005Config,
    partition_code: int,
    case: TransferCase,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    if stream not in STREAM_CODES:
        raise ValueError("unknown Experiment 005 transfer stream")
    if type(replicate) is not int or replicate < 0:
        raise ValueError("replicate must be a non-negative integer")
    sequence = np.random.SeedSequence(
        [
            foundation.master_seed,
            partition_code,
            case.geometry_code,
            case.challenge_code,
            replicate,
            STREAM_CODES[stream],
        ]
    )
    return np.random.Generator(np.random.PCG64DXSM(sequence))


@dataclass(frozen=True)
class TransferStreams:
    process_acceleration_mps2: np.ndarray
    primary_measurement_noise: np.ndarray
    monitor_measurement_noise: np.ndarray
    actuator_uncertainty_mps2: np.ndarray


@dataclass(frozen=True)
class TransferScenario:
    schema_version: str
    partition_code: int
    case_id: str
    geometry_code: int
    challenge_code: int
    case_code: int
    replicate: int
    root_seed_id: str
    initial_relative_state: tuple[float, float, float, float, float, float]
    horizon_s: float
    fixture_command_mps2: tuple[float, float] | None
    mechanics_noise_enabled: bool
    navigation_noise_enabled: bool
    measurement_fault_kind: str
    measurement_fault_channel: str
    fault_onset_s: float | None
    fault_end_s: float | None
    additive_bias: tuple[float, float, float, float] | None
    covariance_factor: float
    monitor_logic_fault: bool
    actuation_effectiveness: float
    disturbance_bias_mps2: tuple[float, float]
    configuration_run_order: tuple[str, str]
    stream_hashes: dict[str, str]
    scenario_hash: str
    design_freeze_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stratified_initial_state(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    case: TransferCase,
    replicate: int,
    partition_code: int,
) -> tuple[float, float, float, float, float, float]:
    names = ("x_radial_m", "y_alongtrack_m", "vx_radial_mps", "vy_alongtrack_mps")
    rng = _stream_rng(foundation, partition_code, case, replicate, "initial_truth_state")
    values: list[float] = []
    for index, name in enumerate(names):
        lower, upper = pilot.initial_state_bounds[name]
        stratum = (replicate + index) % pilot.pilot_roots_per_case
        fraction = (stratum + float(rng.random())) / pilot.pilot_roots_per_case
        values.append(lower + fraction * (upper - lower))
    return (values[0], values[1], 0.0, values[2], values[3], 0.0)


def _fault_spec(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    case: TransferCase,
    replicate: int,
    partition_code: int,
) -> dict[str, Any]:
    rng = _stream_rng(foundation, partition_code, case, replicate, "challenge_parameters")
    none = {
        "measurement_fault_kind": "none",
        "measurement_fault_channel": "none",
        "fault_onset_s": None,
        "fault_end_s": None,
        "additive_bias": None,
        "covariance_factor": 1.0,
        "monitor_logic_fault": False,
        "actuation_effectiveness": 1.0,
        "disturbance_bias_mps2": (0.0, 0.0),
    }
    if case.id in {
        "T00_nominal_transfer",
        "T01_truth_model_mismatch_stress",
        "T02_truth_keep_out_crossing_fixture",
    }:
        return none
    if case.id in {
        "T03_primary_navigation_bias",
        "T04_primary_navigation_dropout",
        "T05_monitor_navigation_bias",
        "T07_shared_navigation_bias",
    }:
        onset = float(rng.uniform(*pilot.fault_onset_range_s))
        duration = (
            pilot.dropout_duration_s
            if case.id == "T04_primary_navigation_dropout"
            else pilot.bias_duration_s
        )
        channel = {
            "T03_primary_navigation_bias": "primary",
            "T04_primary_navigation_dropout": "primary",
            "T05_monitor_navigation_bias": "monitor",
            "T07_shared_navigation_bias": "shared",
        }[case.id]
        kind = "dropout" if case.id == "T04_primary_navigation_dropout" else "bias"
        return {
            **none,
            "measurement_fault_kind": kind,
            "measurement_fault_channel": channel,
            "fault_onset_s": onset,
            "fault_end_s": onset + duration,
            "additive_bias": tuple(pilot.navigation_bias) if kind == "bias" else None,
        }
    onset = float(rng.uniform(*pilot.actuation_onset_range_s))
    if case.id == "T06_monitor_logic_false_trip":
        return {
            **none,
            "fault_onset_s": onset,
            "fault_end_s": onset + pilot.monitor_logic_duration_s,
            "monitor_logic_fault": True,
        }
    if case.id == "T08_actuation_degradation":
        return {
            **none,
            "fault_onset_s": onset,
            "fault_end_s": onset + pilot.actuation_duration_s,
            "actuation_effectiveness": pilot.actuation_effectiveness,
        }
    if case.id == "T09_disturbance_burst":
        return {
            **none,
            "fault_onset_s": onset,
            "fault_end_s": onset + pilot.actuation_duration_s,
            "disturbance_bias_mps2": tuple(pilot.disturbance_bias_mps2),
        }
    raise ValueError(f"unmapped transfer-pilot case: {case.id}")


def _configuration_order(
    foundation: Experiment005Config,
    partition_code: int,
    case: TransferCase,
    replicate: int,
) -> tuple[str, str]:
    anchor = _stream_rng(foundation, partition_code, case, 0, "cell_order")
    first = int(anchor.integers(0, 2))
    if replicate % 2:
        first = 1 - first
    return (CONFIGURATIONS[first], CONFIGURATIONS[1 - first])


def materialize_streams(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    replicate: int,
    *,
    partition_code: int,
) -> tuple[TransferStreams, dict[str, str]]:
    horizon = pilot.horizon_for(case)
    process_count = round(horizon / e004.process_acceleration_draw_period_s)
    measurement_count = round(horizon / e004.command_period_s) + 1
    mechanics_rng = _stream_rng(
        foundation, partition_code, case, replicate, "mechanics_perturbation"
    )
    process = mechanics_rng.normal(
        0.0,
        np.asarray(e004.process_acceleration_sigma_mps2, dtype=np.float64),
        size=(process_count, 2),
    ).astype(np.float64)
    sigma = np.asarray(e004.process_acceleration_sigma_mps2, dtype=np.float64)
    process = np.clip(
        process,
        -pilot.process_disturbance_clip_sigma * sigma,
        pilot.process_disturbance_clip_sigma * sigma,
    )
    measurement_streams = []
    for stream in ("primary_navigation", "monitor_navigation"):
        rng = _stream_rng(foundation, partition_code, case, replicate, stream)
        measurement_streams.append(
            rng.normal(
                0.0,
                np.asarray(e004.measurement_sigma, dtype=np.float64),
                size=(measurement_count, 4),
            ).astype(np.float64)
        )
    actuator_rng = _stream_rng(foundation, partition_code, case, replicate, "actuation")
    actuator = actuator_rng.normal(
        0.0,
        pilot.actuator_uncertainty_sigma_mps2,
        size=(measurement_count - 1, 2),
    ).astype(np.float64)
    streams = TransferStreams(
        process,
        measurement_streams[0],
        measurement_streams[1],
        actuator,
    )
    hashes = {
        "mechanics_perturbation": _array_hash(process),
        "primary_navigation": _array_hash(measurement_streams[0]),
        "monitor_navigation": _array_hash(measurement_streams[1]),
        "actuation": _array_hash(actuator),
    }
    return streams, hashes


def _scenario_for_partition(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    replicate: int,
    *,
    partition_code: int,
    design_freeze_id: str | None = None,
) -> tuple[TransferScenario, TransferStreams]:
    if partition_code not in {
        pilot.calibration_partition_code,
        pilot.pilot_partition_code,
        pilot.test_fixture_partition_code,
    }:
        raise ValueError("partition is unavailable to the transfer-pilot package")
    initial = (
        tuple(case.initial_relative_state)
        if case.initial_relative_state is not None
        else _stratified_initial_state(pilot, foundation, case, replicate, partition_code)
    )
    fault = _fault_spec(pilot, foundation, case, replicate, partition_code)
    order = _configuration_order(foundation, partition_code, case, replicate)
    streams, stochastic_hashes = materialize_streams(
        pilot,
        foundation,
        e004,
        case,
        replicate,
        partition_code=partition_code,
    )
    deterministic = {
        "initial_relative_state": initial,
        "fault": fault,
        "configuration_run_order": order,
    }
    hashes = {
        **stochastic_hashes,
        "initial_truth_state": sha256_bytes(canonical_json(initial)),
        "challenge_parameters": sha256_bytes(canonical_json(fault)),
        "cell_order": sha256_bytes(canonical_json(order)),
    }
    root_id = f"experiment005:{partition_code}:{case.case_code:03d}:{replicate:04d}"
    unsigned = {
        "schema_version": pilot.schema_version,
        "partition_code": partition_code,
        "case_id": case.id,
        "geometry_code": case.geometry_code,
        "challenge_code": case.challenge_code,
        "case_code": case.case_code,
        "replicate": replicate,
        "root_seed_id": root_id,
        "initial_relative_state": initial,
        "horizon_s": pilot.horizon_for(case),
        "fixture_command_mps2": case.fixture_command_mps2,
        "mechanics_noise_enabled": case.mechanics_noise_enabled,
        "navigation_noise_enabled": case.navigation_noise_enabled,
        **fault,
        "configuration_run_order": order,
        "stream_hashes": hashes,
        "design_freeze_id": design_freeze_id,
    }
    scenario = TransferScenario(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json({**unsigned, "deterministic": deterministic})),
    )
    return scenario, streams


def calibration_scenario(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    replicate: int,
) -> tuple[TransferScenario, TransferStreams]:
    """Create an in-memory partition-51 mechanics scenario, never a pilot outcome row."""

    return _scenario_for_partition(
        pilot,
        foundation,
        e004,
        case,
        replicate,
        partition_code=pilot.calibration_partition_code,
    )


def test_fixture_scenario(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    replicate: int,
) -> tuple[TransferScenario, TransferStreams]:
    return _scenario_for_partition(
        pilot,
        foundation,
        e004,
        case,
        replicate,
        partition_code=pilot.test_fixture_partition_code,
    )


def scenario_from_row(row: dict[str, Any]) -> TransferScenario:
    value = dict(row)
    for key in (
        "initial_relative_state",
        "fixture_command_mps2",
        "additive_bias",
        "disturbance_bias_mps2",
        "configuration_run_order",
    ):
        if value.get(key) is not None:
            value[key] = tuple(value[key])
    return TransferScenario(**value)


def _historical_root_ids(root: Path) -> set[str]:
    identifiers: set[str] = set()
    for path in root.glob("experiments/*/seeds/*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line).get("root_seed_id")
            except json.JSONDecodeError:
                continue
            if isinstance(value, str):
                identifiers.add(value)
    return identifiers


def validate_seed_contract(
    pilot: TransferPilotConfig,
    contract_path: str | Path,
    *,
    root: str | Path = ".",
) -> dict[str, Any]:
    contract_path = Path(contract_path)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    expected_pilot = {
        "code": 52,
        "status": "reserved_not_materialized_or_executed",
        "roots_per_case": 2,
        "case_count": 10,
        "expected_root_rows": 20,
        "configurations_per_root": 2,
        "expected_episode_rows": 40,
        "replay_roots_per_case": 1,
        "generator_authorized_only_after_verified_design_freeze": True,
        "generator_invoked": False,
    }
    expected_confirmatory = {
        "code": 53,
        "status": "reserved_untouched_unmaterialized_hypothesis_sample_size_and_design_not_set",
        "generator_available": False,
    }
    if contract.get("schema_version") != pilot.schema_version:
        errors.append("schema_version")
    if contract.get("bit_generator") != BIT_GENERATOR:
        errors.append("bit_generator")
    if contract.get("master_seed") != 5005 or contract.get("derivation") != SEED_DERIVATION:
        errors.append("seed_derivation")
    partitions = contract.get("partitions", {})
    if partitions.get("design_validation_pilot") != expected_pilot:
        errors.append("partition_52_contract")
    if partitions.get("future_confirmatory") != expected_confirmatory:
        errors.append("partition_53_contract")
    if contract.get("stream_codes") != STREAM_CODES:
        errors.append("stream_codes")
    if contract.get("forbidden_overlap_partitions") != [51, 53, 951]:
        errors.append("forbidden_overlap_partitions")
    if contract.get("replacement_extension_or_count_drift_allowed") is not False:
        errors.append("replacement_policy")
    project = Path(root)
    reserved_paths = (
        project / "experiments/005-transfer-pilot/seeds",
        project / "results/experiment-005-transfer-pilot",
        project / "experiments/005-confirmatory",
        project / "results/experiment-005-confirmatory",
    )
    present = [path.relative_to(project).as_posix() for path in reserved_paths if path.exists()]
    if present:
        errors.append("partition_52_or_53_path_present")
    historical = _historical_root_ids(project)
    p52 = sorted(value for value in historical if value.startswith("experiment005:52:"))
    p53 = sorted(value for value in historical if value.startswith("experiment005:53:"))
    if p52:
        errors.append("partition_52_root_materialized")
    if p53:
        errors.append("partition_53_root_materialized")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(contract_path.read_bytes()),
        "expected_root_rows": pilot.pilot_blocks,
        "expected_episode_rows": pilot.pilot_episodes,
        "forbidden_paths_present": present,
        "historical_root_ids_compared": len(historical),
        "partition_52_overlap": len(p52),
        "partition_53_overlap": len(p53),
        "partition_52_materialized": False,
        "partition_53_materialized": False,
    }


def assert_materialization_targets_absent(root: str | Path) -> None:
    project = Path(root)
    targets = (
        project / "experiments/005-transfer-pilot/seeds",
        project / "results/experiment-005-transfer-pilot",
    )
    if any(path.exists() for path in targets):
        raise RuntimeError("refusing pre-existing Experiment 005 transfer-pilot seed/result path")
    confirmatory = (
        project / "experiments/005-confirmatory",
        project / "results/experiment-005-confirmatory",
    )
    if any(path.exists() for path in confirmatory):
        raise RuntimeError("partition 53 must remain untouched")


def materialize_pilot_seeds(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
    *,
    root: str | Path,
) -> dict[str, Any]:
    """Future write-once partition-52 materializer; never called by design/calibration."""

    from .workflow import verify_freeze

    project = Path(root)
    verification = verify_freeze(project)
    if not verification["passed"] or verification["status"] != "READY_FOR_PARTITION_52_EXECUTION":
        raise RuntimeError("refusing partition-52 materialization before verified design freeze")
    freeze_id = str(verification["freeze_id"])
    assert_materialization_targets_absent(project)
    seed_directory = project / "experiments/005-transfer-pilot/seeds"
    staging = seed_directory.parent / f".seeds-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        historical = _historical_root_ids(project)
        observed: set[str] = set()
        manifest = staging / "pilot.jsonl"
        with manifest.open("x", encoding="utf-8") as handle:
            for case in cases:
                for replicate in range(pilot.pilot_roots_per_case):
                    scenario, _ = _scenario_for_partition(
                        pilot,
                        foundation,
                        e004,
                        case,
                        replicate,
                        partition_code=pilot.pilot_partition_code,
                        design_freeze_id=freeze_id,
                    )
                    if scenario.root_seed_id in observed or scenario.root_seed_id in historical:
                        raise RuntimeError("partition-52 root identity is not disjoint")
                    observed.add(scenario.root_seed_id)
                    handle.write(canonical_json(scenario.to_dict()).decode() + "\n")
        replay = {
            "schema_version": pilot.schema_version,
            "selection": "replicate 0 in every case; outcome-blind",
            "root_seed_ids": [
                f"experiment005:52:{case.case_code:03d}:0000" for case in cases
            ],
            "expected_blocks": pilot.replay_blocks,
            "expected_episodes": pilot.replay_episodes,
        }
        replay_path = staging / "replay-subset.json"
        replay_path.write_text(
            json.dumps(replay, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        index = {
            "schema_version": pilot.schema_version,
            "design_freeze_id": freeze_id,
            "design_readiness_id": verification["readiness_id"],
            "partition_code": 52,
            "root_rows": len(observed),
            "planned_episode_rows": pilot.pilot_episodes,
            "manifest_sha256": sha256_bytes(manifest.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "historical_root_ids_compared": len(historical),
            "disjoint_from_partitions": [51, 53, 951],
            "materialized_only_after_design_freeze_verification": True,
            "generator_invocations": 1,
            "replacement_extension_or_count_drift_allowed": False,
        }
        (staging / "index.json").write_text(
            json.dumps(index, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staging.rename(seed_directory)
        return index
    except BaseException:
        quarantine = staging.parent / f".failed-seed-materialization-{uuid.uuid4().hex}"
        if staging.exists():
            staging.rename(quarantine)
        raise
