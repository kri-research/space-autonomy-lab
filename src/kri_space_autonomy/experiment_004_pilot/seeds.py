from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_004.seeds import STREAM_CODES

from .config import CONFIGURATIONS, PilotCase, PilotConfig

BIT_GENERATOR = "PCG64DXSM"
SEED_DERIVATION = (
    "SeedSequence([master, partition, geometry_case, fault_case, replicate, stream])"
)


def canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rng(entropy: list[int]) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence(entropy)))


def _stream_rng(
    foundation: Experiment004Config,
    partition_code: int,
    case: PilotCase,
    replicate: int,
    stream: str,
) -> np.random.Generator:
    if stream not in STREAM_CODES:
        raise ValueError("unknown Experiment 004 stream")
    if type(replicate) is not int or replicate < 0:
        raise ValueError("replicate must be a non-negative integer")
    return _rng(
        [
            foundation.master_seed,
            partition_code,
            case.geometry_code,
            case.fault_code,
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


@dataclass(frozen=True)
class PilotStreams:
    process_acceleration_mps2: np.ndarray
    primary_measurement_noise: np.ndarray
    monitor_measurement_noise: np.ndarray
    actuator_uncertainty_mps2: np.ndarray


@dataclass(frozen=True)
class PilotScenario:
    schema_version: str
    partition_code: int
    case_id: str
    geometry_code: int
    fault_code: int
    case_code: int
    replicate: int
    root_seed_id: str
    initial_state: tuple[float, float, float, float]
    horizon_s: float
    fixture_command_mps2: tuple[float, float] | None
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
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
    partition_code: int,
) -> tuple[float, float, float, float]:
    names = ("x_radial_m", "y_alongtrack_m", "vx_radial_mps", "vy_alongtrack_mps")
    permutations = (
        (0, 1, 2, 3),
        (2, 0, 3, 1),
        (1, 3, 0, 2),
        (3, 2, 1, 0),
    )
    rng = _stream_rng(foundation, partition_code, case, replicate, "initial_state")
    values = []
    for index, name in enumerate(names):
        lower, upper = pilot.initial_state_bounds[name]
        quartile = permutations[index][replicate % 4]
        fraction = (quartile + float(rng.random())) / 4.0
        values.append(lower + fraction * (upper - lower))
    return tuple(float(value) for value in values)  # type: ignore[return-value]


def _fault_spec(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
    partition_code: int,
) -> dict[str, Any]:
    rng = _stream_rng(foundation, partition_code, case, replicate, "fault_parameters")
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
        "P00_nominal_feasibility",
        "P01_forced_collision",
        "P02_forced_keep_out_only",
        "P03_forced_corridor_departure",
    }:
        return none
    if case.id in {
        "P04_primary_navigation_bias",
        "P05_primary_navigation_dropout",
        "P06_monitor_navigation_bias",
        "P08_shared_navigation_bias",
    }:
        onset = float(rng.uniform(*pilot.fault_onset_range_s))
        duration = (
            pilot.dropout_duration_s
            if case.id == "P05_primary_navigation_dropout"
            else pilot.bias_duration_s
        )
        channel = {
            "P04_primary_navigation_bias": "primary",
            "P05_primary_navigation_dropout": "primary",
            "P06_monitor_navigation_bias": "monitor",
            "P08_shared_navigation_bias": "shared",
        }[case.id]
        kind = "dropout" if case.id == "P05_primary_navigation_dropout" else "bias"
        return {
            **none,
            "measurement_fault_kind": kind,
            "measurement_fault_channel": channel,
            "fault_onset_s": onset,
            "fault_end_s": onset + duration,
            "additive_bias": tuple(pilot.navigation_bias) if kind == "bias" else None,
        }
    onset = float(rng.uniform(*pilot.actuation_onset_range_s))
    if case.id == "P07_monitor_logic_false_trip":
        return {
            **none,
            "fault_onset_s": onset,
            "fault_end_s": onset + pilot.monitor_logic_duration_s,
            "monitor_logic_fault": True,
        }
    if case.id == "P09_actuation_degradation":
        return {
            **none,
            "fault_onset_s": onset,
            "fault_end_s": onset + pilot.actuation_duration_s,
            "actuation_effectiveness": pilot.actuation_effectiveness,
        }
    if case.id == "P10_disturbance_burst":
        return {
            **none,
            "fault_onset_s": onset,
            "fault_end_s": onset + pilot.actuation_duration_s,
            "disturbance_bias_mps2": tuple(pilot.disturbance_bias_mps2),
        }
    raise ValueError(f"unmapped pilot case {case.id}")


def _configuration_order(
    foundation: Experiment004Config,
    partition_code: int,
    case: PilotCase,
    replicate: int,
) -> tuple[str, str]:
    anchor = _stream_rng(
        foundation,
        partition_code,
        case,
        0,
        "configuration_run_order",
    )
    first = int(anchor.integers(0, 2))
    if replicate % 2:
        first = 1 - first
    return (CONFIGURATIONS[first], CONFIGURATIONS[1 - first])


def materialize_streams(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
    *,
    partition_code: int,
) -> tuple[PilotStreams, dict[str, str]]:
    horizon = (
        pilot.forced_fixture_horizon_s
        if case.fixture == "open_loop_exact_arc"
        else pilot.standard_horizon_s
    )
    process_count = round(horizon / foundation.process_acceleration_draw_period_s)
    measurement_count = round(horizon / foundation.command_period_s) + 1
    process_columns = []
    for stream, sigma in zip(
        ("process_disturbance_radial", "process_disturbance_alongtrack"),
        foundation.process_acceleration_sigma_mps2,
        strict=True,
    ):
        rng = _stream_rng(foundation, partition_code, case, replicate, stream)
        values = rng.normal(0.0, sigma, process_count)
        values = np.clip(
            values,
            -pilot.process_disturbance_clip_sigma * sigma,
            pilot.process_disturbance_clip_sigma * sigma,
        )
        process_columns.append(values.astype(np.float64))
    process = np.column_stack(process_columns)
    measurement_streams = []
    for stream in ("primary_measurement", "monitor_measurement"):
        rng = _stream_rng(foundation, partition_code, case, replicate, stream)
        measurement_streams.append(
            rng.normal(
                0.0,
                np.asarray(foundation.measurement_sigma, dtype=np.float64),
                size=(measurement_count, 4),
            ).astype(np.float64)
        )
    actuator_rng = _stream_rng(
        foundation,
        partition_code,
        case,
        replicate,
        "actuator_uncertainty",
    )
    actuator = actuator_rng.normal(
        0.0,
        pilot.actuator_uncertainty_sigma_mps2,
        size=(measurement_count - 1, 2),
    ).astype(np.float64)
    streams = PilotStreams(process, measurement_streams[0], measurement_streams[1], actuator)
    hashes = {
        "process_disturbance_radial": _array_hash(process[:, 0]),
        "process_disturbance_alongtrack": _array_hash(process[:, 1]),
        "primary_measurement": _array_hash(measurement_streams[0]),
        "monitor_measurement": _array_hash(measurement_streams[1]),
        "actuator_uncertainty": _array_hash(actuator),
    }
    return streams, hashes


def _scenario_for_partition(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
    *,
    partition_code: int,
    design_freeze_id: str | None = None,
) -> tuple[PilotScenario, PilotStreams]:
    if partition_code not in {
        pilot.calibration_partition_code,
        pilot.pilot_partition_code,
        pilot.test_fixture_partition_code,
    }:
        raise ValueError("partition is not available to the pilot design package")
    initial = (
        tuple(case.initial_state)
        if case.initial_state is not None
        else _stratified_initial_state(pilot, foundation, case, replicate, partition_code)
    )
    horizon = (
        pilot.forced_fixture_horizon_s
        if case.fixture == "open_loop_exact_arc"
        else pilot.standard_horizon_s
    )
    fault = _fault_spec(pilot, foundation, case, replicate, partition_code)
    order = _configuration_order(foundation, partition_code, case, replicate)
    streams, stochastic_hashes = materialize_streams(
        pilot,
        foundation,
        case,
        replicate,
        partition_code=partition_code,
    )
    deterministic = {
        "initial_state": initial,
        "fault": fault,
        "configuration_run_order": order,
    }
    hashes = {
        **stochastic_hashes,
        "initial_state": sha256_bytes(canonical_json(initial)),
        "fault_parameters": sha256_bytes(canonical_json(fault)),
        "configuration_run_order": sha256_bytes(canonical_json(order)),
    }
    root_id = f"experiment004:{partition_code}:{case.case_code:03d}:{replicate:04d}"
    unsigned = {
        "schema_version": pilot.schema_version,
        "partition_code": partition_code,
        "case_id": case.id,
        "geometry_code": case.geometry_code,
        "fault_code": case.fault_code,
        "case_code": case.case_code,
        "replicate": replicate,
        "root_seed_id": root_id,
        "initial_state": initial,
        "horizon_s": horizon,
        "fixture_command_mps2": case.fixture_command_mps2,
        **fault,
        "configuration_run_order": order,
        "stream_hashes": hashes,
        "design_freeze_id": design_freeze_id,
    }
    scenario = PilotScenario(
        **unsigned,
        scenario_hash=sha256_bytes(canonical_json({**unsigned, "deterministic": deterministic})),
    )
    return scenario, streams


def calibration_scenario(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
) -> tuple[PilotScenario, PilotStreams]:
    """Create an in-memory partition-41 mechanics scenario, never an outcome row."""

    return _scenario_for_partition(
        pilot,
        foundation,
        case,
        replicate,
        partition_code=pilot.calibration_partition_code,
    )


def test_fixture_scenario(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
) -> tuple[PilotScenario, PilotStreams]:
    return _scenario_for_partition(
        pilot,
        foundation,
        case,
        replicate,
        partition_code=pilot.test_fixture_partition_code,
    )


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
    pilot: PilotConfig,
    contract_path: str | Path,
    *,
    root: str | Path = ".",
) -> dict[str, Any]:
    path = Path(contract_path)
    contract = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    expected_pilot = {
        "code": pilot.pilot_partition_code,
        "status": "reserved_not_materialized_or_executed",
        "roots_per_case": pilot.pilot_roots_per_case,
        "case_count": pilot.case_count,
        "expected_root_rows": pilot.pilot_blocks,
        "configurations_per_root": len(pilot.configuration_ids),
        "expected_episode_rows": pilot.pilot_episodes,
        "replay_roots_per_case": pilot.replay_roots_per_case,
        "generator_available_only_after_verified_design_freeze": True,
        "generator_invoked": False,
    }
    expected_confirmatory = {
        "code": pilot.future_confirmatory_partition_code,
        "status": "reserved_unmaterialized_hypothesis_and_sample_size_not_set",
        "generator_available": False,
    }
    if contract.get("schema_version") != pilot.schema_version:
        errors.append("schema_version")
    if contract.get("bit_generator") != BIT_GENERATOR:
        errors.append("bit_generator")
    if contract.get("master_seed") != 4004 or contract.get("derivation") != SEED_DERIVATION:
        errors.append("derivation")
    partitions = contract.get("partitions", {})
    if partitions.get("design_validation_pilot") != expected_pilot:
        errors.append("pilot_partition")
    if partitions.get("future_confirmatory") != expected_confirmatory:
        errors.append("future_confirmatory_partition")
    if contract.get("stream_codes") != STREAM_CODES:
        errors.append("stream_codes")
    if contract.get("forbidden_overlap_partitions") != [41, 42, 44, 941]:
        errors.append("forbidden_overlap_partitions")
    if contract.get("replacement_extension_or_count_drift_allowed") is not False:
        errors.append("replacement_policy")
    project_root = Path(root)
    forbidden = (
        project_root / "experiments/004-pilot/seeds",
        project_root / "results/experiment-004-pilot",
        project_root / "experiments/004-confirmatory",
        project_root / "results/experiment-004-confirmatory",
    )
    present = [path.relative_to(project_root).as_posix() for path in forbidden if path.exists()]
    if present:
        errors.append("reserved_output_path_present")
    historical = _historical_root_ids(project_root)
    namespace_overlap = sorted(
        value for value in historical if value.startswith("experiment004:43:")
    )
    if namespace_overlap:
        errors.append("historical_partition_43_root_overlap")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "contract_sha256": sha256_bytes(path.read_bytes()),
        "expected_root_rows": pilot.pilot_blocks,
        "expected_episode_rows": pilot.pilot_episodes,
        "forbidden_paths_present": present,
        "historical_root_ids_compared": len(historical),
        "historical_partition_43_overlap": len(namespace_overlap),
        "partition_43_materialized": False,
        "partition_44_materialized": False,
    }


def validate_materialized_pilot(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
    *,
    root: str | Path,
    freeze_id: str,
    readiness_id: str,
) -> dict[str, Any]:
    directory = Path(root) / "experiments/004-pilot/seeds"
    manifest_path = directory / "pilot.jsonl"
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
    case_map = {case.id: case for case in cases}
    expected_keys = {
        (case.id, replicate)
        for case in cases
        for replicate in range(pilot.pilot_roots_per_case)
    }
    observed_keys: set[tuple[str, int]] = set()
    root_ids: set[str] = set()
    scenario_mismatches = 0
    for row in rows:
        case = case_map.get(str(row.get("case_id")))
        replicate = row.get("replicate")
        if case is None or type(replicate) is not int:
            errors.append("invalid_case_or_replicate")
            continue
        observed_keys.add((case.id, replicate))
        root_ids.add(str(row.get("root_seed_id")))
        expected, _ = _scenario_for_partition(
            pilot,
            foundation,
            case,
            replicate,
            partition_code=pilot.pilot_partition_code,
            design_freeze_id=freeze_id,
        )
        scenario_mismatches += int(canonical_json(row) != canonical_json(expected.to_dict()))
    if (
        len(rows) != pilot.pilot_blocks
        or len(root_ids) != pilot.pilot_blocks
        or observed_keys != expected_keys
    ):
        errors.append("root_count_uniqueness_or_cell_drift")
    if scenario_mismatches:
        errors.append("scenario_content_drift")
    expected_replay = [
        f"experiment004:43:{case.case_code:03d}:0000" for case in cases
    ]
    if replay.get("root_seed_ids") != expected_replay:
        errors.append("replay_subset_drift")
    if (
        index.get("design_freeze_id") != freeze_id
        or index.get("design_readiness_id") != readiness_id
        or index.get("partition_code") != pilot.pilot_partition_code
        or index.get("root_rows") != pilot.pilot_blocks
        or index.get("planned_episode_rows") != pilot.pilot_episodes
    ):
        errors.append("index_identity_or_count_drift")
    if index.get("manifest_sha256") != sha256_bytes(manifest_path.read_bytes()):
        errors.append("manifest_hash_drift")
    if index.get("replay_subset_sha256") != sha256_bytes(replay_path.read_bytes()):
        errors.append("replay_hash_drift")
    historical = _historical_root_ids(Path(root))
    historical_without_current = historical - root_ids
    if root_ids & historical_without_current:
        errors.append("historical_root_overlap")
    if any(not root.startswith("experiment004:43:") for root in root_ids):
        errors.append("root_partition_namespace")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "rows": len(rows),
        "unique_root_ids": len(root_ids),
        "scenario_mismatches": scenario_mismatches,
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
        "historical_root_ids_compared": len(historical_without_current),
        "disjoint_from_partitions": [41, 42, 44, 941],
        "replacement_extension_or_count_drift_allowed": False,
    }


def assert_materialization_targets_absent(root: str | Path) -> None:
    project_root = Path(root)
    seed_directory = project_root / "experiments/004-pilot/seeds"
    result_directory = project_root / "results/experiment-004-pilot"
    if seed_directory.exists() or result_directory.exists():
        raise RuntimeError("refusing pre-existing Experiment 004 pilot seed or result path")


def materialize_pilot_seeds(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
    *,
    root: str | Path,
) -> dict[str, Any]:
    """Write partition-43 roots once, only after independent design-freeze verification."""

    from .workflow import verify_freeze

    project_root = Path(root)
    verification = verify_freeze(project_root)
    if not verification["passed"] or verification["status"] != "READY_FOR_PILOT_EXECUTION":
        raise RuntimeError(
            "refusing partition-43 materialization before verified pilot design freeze"
        )
    freeze_id = str(verification["freeze_id"])
    assert_materialization_targets_absent(project_root)
    seed_directory = project_root / "experiments/004-pilot/seeds"
    staging = seed_directory.parent / f".seeds-materializing-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        historical = _historical_root_ids(project_root)
        observed: set[str] = set()
        manifest = staging / "pilot.jsonl"
        with manifest.open("x", encoding="utf-8") as handle:
            for case in cases:
                for replicate in range(pilot.pilot_roots_per_case):
                    scenario, _ = _scenario_for_partition(
                        pilot,
                        foundation,
                        case,
                        replicate,
                        partition_code=pilot.pilot_partition_code,
                        design_freeze_id=freeze_id,
                    )
                    if scenario.root_seed_id in observed or scenario.root_seed_id in historical:
                        raise RuntimeError("partition-43 root identity is not disjoint")
                    observed.add(scenario.root_seed_id)
                    handle.write(canonical_json(scenario.to_dict()).decode() + "\n")
        if len(observed) != pilot.pilot_blocks:
            raise RuntimeError("partition-43 root count drift")
        replay = {
            "schema_version": pilot.schema_version,
            "selection": "replicate 0 in every case; outcome-blind",
            "root_seed_ids": [
                f"experiment004:43:{case.case_code:03d}:0000" for case in cases
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
            "partition_code": pilot.pilot_partition_code,
            "root_rows": len(observed),
            "planned_episode_rows": pilot.pilot_episodes,
            "manifest_sha256": sha256_bytes(manifest.read_bytes()),
            "replay_subset_sha256": sha256_bytes(replay_path.read_bytes()),
            "historical_root_ids_compared": len(historical),
            "disjoint_from_partitions": [41, 42, 44, 941],
            "materialized_only_after_design_freeze_verification": True,
            "replacement_extension_or_count_drift_allowed": False,
        }
        (staging / "index.json").write_text(
            json.dumps(index, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staging.rename(seed_directory)
        return index
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
