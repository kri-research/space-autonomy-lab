from __future__ import annotations

import errno
import hashlib
import json
import os
import platform
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_004.config import Experiment004Config
from kri_space_autonomy.experiment_004.control import (
    DeterministicHoldController,
    EstimatedGeometryMonitor,
    observation_from_snapshot,
)
from kri_space_autonomy.experiment_004.dynamics import propagate_exact
from kri_space_autonomy.experiment_004.estimator import (
    NavigationSnapshot,
    PlanarNavigationFilter,
)
from kri_space_autonomy.experiment_004.measurements import (
    MeasurementFault,
    navigation_packet,
)
from kri_space_autonomy.experiment_005.config import Experiment005Config
from kri_space_autonomy.experiment_005.dynamics import (
    circular_chief_state,
    pair_from_relative,
    pair_to_relative,
    propagate_fixed,
)
from kri_space_autonomy.experiment_005.geometry import (
    IndependentTruthEvaluator,
    evaluate_truth_hold_segment,
)
from kri_space_autonomy.experiment_005.runner import default_workers

from .config import CONFIGURATIONS, TransferCase, TransferPilotConfig
from .seeds import (
    TransferScenario,
    TransferStreams,
    canonical_json,
    materialize_streams,
    sha256_bytes,
)

SHARD_SCHEMA_VERSION = "experiment-005-transfer-pilot-cell-shard-1.0"
CAMPAIGN_SCHEMA_VERSION = "experiment-005-transfer-pilot-checkpoint-1.0"
FAILURE_SCHEMA_VERSION = "experiment-005-transfer-pilot-terminal-failure-1.0"
LOCK_NAME = ".campaign.lock"


class RealizedTruthSegment:
    """Nonlinear truth arc for commanded acceleration plus additive realized terms.

    The frozen ``0.02 m/s^2`` limit applies to the online commanded vector. Additive
    actuator uncertainty, process acceleration, and the frozen disturbance case are
    recorded separately and may make the realized external acceleration slightly larger.
    """

    def __init__(
        self,
        start_pair_state: np.ndarray,
        realized_acceleration_lvlh_mps2: np.ndarray,
        config: Experiment005Config,
        duration_s: float,
    ) -> None:
        state = np.asarray(start_pair_state, dtype=np.float64)
        acceleration = np.asarray(realized_acceleration_lvlh_mps2, dtype=np.float64)
        if state.shape != (12,) or not np.all(np.isfinite(state)):
            raise ValueError("realized truth segment requires a finite 12-state")
        if acceleration.shape != (3,) or not np.all(np.isfinite(acceleration)):
            raise ValueError("realized truth segment requires a finite LVLH acceleration")
        if (
            not np.isfinite(duration_s)
            or duration_s <= 0.0
            or duration_s > config.event_interval_max_s + 1e-12
        ):
            raise ValueError("realized truth segment duration violates event splitting")
        self.start_pair_state = np.array(state, copy=True)
        self.command_lvlh_mps2 = np.array(acceleration, copy=True)
        self.config = config
        self.duration_s = float(duration_s)

    def state_at(self, elapsed_s: float) -> np.ndarray:
        if not np.isfinite(elapsed_s) or not -1e-12 <= elapsed_s <= self.duration_s + 1e-12:
            raise ValueError("elapsed time lies outside the realized truth segment")
        elapsed = min(self.duration_s, max(0.0, float(elapsed_s)))
        return propagate_fixed(
            self.start_pair_state,
            self.command_lvlh_mps2,
            self.config.gravitational_parameter_m3_s2,
            elapsed,
            self.config.production_max_step_s,
        )

    def relative_state_at(self, elapsed_s: float) -> np.ndarray:
        return pair_to_relative(self.state_at(elapsed_s))


@dataclass(frozen=True)
class TransferEpisode:
    schema_version: str
    study_phase: str
    design_freeze_id: str | None
    case_id: str
    case_code: int
    domain: str
    root_seed_id: str
    replicate: int
    configuration_id: str
    run_order: int
    attempt_status: str
    infrastructure_failure: bool
    physical_collision: bool
    physical_keep_out_entry: bool
    physical_corridor_departure: bool
    minimum_separation_m: float
    maximum_admissible_position_excess_m: float
    maximum_abs_crosstrack_m: float
    hold_acquired: bool
    maximum_contiguous_hold_dwell_s: float
    primary_estimator_fault: bool
    monitor_estimator_fault: bool
    monitor_logic_fault: bool
    shared_cause_fault: bool
    actuation_degradation_scheduled: bool
    disturbance_scheduled: bool
    primary_fault_active_packets: int
    monitor_fault_active_packets: int
    monitor_logic_active_commands: int
    actuation_degradation_active_commands: int
    disturbance_active_substeps: int
    monitor_override_commands: int
    monitor_reason_counts: dict[str, int]
    primary_disposition_counts: dict[str, int]
    monitor_disposition_counts: dict[str, int]
    minimum_covariance_eigenvalue: float
    maximum_covariance_trace: float
    nonlinear_truth_numerical_valid: bool
    model_mismatch_observations: int
    maximum_hcw_position_residual_m: float
    maximum_hcw_velocity_residual_mps: float
    final_truth_relative_state: tuple[float, float, float, float, float, float]
    scenario_hash: str
    stream_hashes: dict[str, str]
    controller_identity: str
    trace_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _active(scenario: TransferScenario, time_s: float) -> bool:
    return bool(
        scenario.fault_onset_s is not None
        and time_s >= scenario.fault_onset_s
        and (scenario.fault_end_s is None or time_s < scenario.fault_end_s)
    )


def _measurement_fault(scenario: TransferScenario) -> MeasurementFault:
    return MeasurementFault(
        kind=scenario.measurement_fault_kind,
        channel=scenario.measurement_fault_channel,
        onset_s=scenario.fault_onset_s,
        end_s=scenario.fault_end_s,
        additive_bias=scenario.additive_bias,
        covariance_factor=scenario.covariance_factor,
    )


def _online_control(
    primary_snapshot: NavigationSnapshot,
    monitor_snapshot: NavigationSnapshot,
    controller: DeterministicHoldController,
    monitor: EstimatedGeometryMonitor,
    configuration_id: str,
) -> tuple[np.ndarray, bool, str | None]:
    """Online path: only HCW navigation snapshots and the proposed command enter."""

    proposal = controller.decide(observation_from_snapshot(primary_snapshot))
    if configuration_id == "primary_reference":
        return proposal.acceleration_mps2, False, None
    if configuration_id != "independent_monitor_gate":
        raise ValueError("unknown transfer-pilot diagnostic configuration")
    decision = monitor.gate(monitor_snapshot, proposal)
    return decision.executed_acceleration_mps2, decision.overridden, decision.reason


def _packet(
    *,
    channel: str,
    sequence_id: int,
    time_s: float,
    latent_planar_state: np.ndarray,
    noise: np.ndarray,
    e004: Experiment004Config,
    fault: MeasurementFault,
    previous_packet: Any,
):
    return navigation_packet(
        sequence_id=sequence_id,
        measured_at_s=time_s,
        received_at_s=time_s,
        latent_state=latent_planar_state,
        measurement_noise=noise,
        quantization=np.asarray(e004.measurement_quantization, dtype=np.float64),
        nominal_covariance=e004.nominal_measurement_covariance,
        channel=channel,
        fault=fault,
        previous_packet=previous_packet,
    )


def _planar(relative: np.ndarray) -> np.ndarray:
    return np.array(
        [relative[0], relative[1], relative[3], relative[4]], dtype=np.float64
    )


def _update_covariance_extremes(
    snapshots: tuple[NavigationSnapshot, NavigationSnapshot],
    minimum: float,
    maximum: float,
) -> tuple[float, float]:
    for snapshot in snapshots:
        minimum = min(minimum, float(np.linalg.eigvalsh(snapshot.covariance)[0]))
        maximum = max(maximum, float(np.trace(snapshot.covariance)))
    return minimum, maximum


def run_episode(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    scenario: TransferScenario,
    streams: TransferStreams,
    configuration_id: str,
    run_order: int,
) -> TransferEpisode:
    if configuration_id not in CONFIGURATIONS:
        raise ValueError("unknown diagnostic configuration")
    if scenario.case_id != case.id or scenario.case_code != case.case_code:
        raise ValueError("scenario does not match the frozen transfer case")
    if scenario.configuration_run_order[run_order - 1] != configuration_id:
        raise ValueError("configuration run order does not match the frozen block")
    controller = DeterministicHoldController(e004)
    monitor = EstimatedGeometryMonitor(
        e004,
        DeterministicHoldController(e004),
        expected_controller_identity=controller.controller_identity,
    )
    primary_filter = PlanarNavigationFilter(e004)
    monitor_filter = PlanarNavigationFilter(e004)
    evaluator = IndependentTruthEvaluator(foundation)
    chief = circular_chief_state(
        foundation.gravitational_parameter_m3_s2, foundation.reference_radius_m
    )
    truth = pair_from_relative(
        chief, np.asarray(scenario.initial_relative_state, dtype=np.float64)
    )
    fault = _measurement_fault(scenario)
    previous_packets: dict[str, Any] = {"primary": None, "monitor": None}
    dispositions = {"primary": Counter(), "monitor": Counter()}
    monitor_reasons: Counter[str] = Counter()
    primary_active = 0
    monitor_active = 0
    logic_active = 0
    actuation_active = 0
    disturbance_active = 0
    monitor_overrides = 0
    minimum_covariance_eigenvalue = np.inf
    maximum_covariance_trace = 0.0
    numerical_valid = True
    mismatch_positions: list[float] = []
    mismatch_velocities: list[float] = []
    dwell_s = 0.0
    maximum_dwell_s = 0.0
    digest = hashlib.sha256()

    initial_relative = pair_to_relative(truth)
    initial_planar = _planar(initial_relative)
    for channel, filter_, raw_noise in (
        ("primary", primary_filter, streams.primary_measurement_noise[0]),
        ("monitor", monitor_filter, streams.monitor_measurement_noise[0]),
    ):
        noise = raw_noise if scenario.navigation_noise_enabled else np.zeros(4)
        packet = _packet(
            channel=channel,
            sequence_id=0,
            time_s=0.0,
            latent_planar_state=initial_planar,
            noise=noise,
            e004=e004,
            fault=fault,
            previous_packet=None,
        )
        if packet is None:
            dispositions[channel]["dropout"] += 1
        else:
            diagnostic = filter_.ingest(packet)
            dispositions[channel][diagnostic.disposition.value] += 1
            previous_packets[channel] = packet
    minimum_covariance_eigenvalue, maximum_covariance_trace = _update_covariance_extremes(
        (primary_filter.snapshot(), monitor_filter.snapshot()),
        minimum_covariance_eigenvalue,
        maximum_covariance_trace,
    )

    command_steps = round(scenario.horizon_s / e004.command_period_s)
    substeps = round(e004.command_period_s / e004.process_acceleration_draw_period_s)
    if command_steps * substeps != len(streams.process_acceleration_mps2):
        raise ValueError("mechanics stream length does not match the scenario horizon")
    for command_index in range(command_steps):
        time_s = command_index * e004.command_period_s
        command, overridden, reason = _online_control(
            primary_filter.snapshot(),
            monitor_filter.snapshot(),
            controller,
            monitor,
            configuration_id,
        )
        active = _active(scenario, time_s)
        if (
            scenario.monitor_logic_fault
            and active
            and configuration_id == "independent_monitor_gate"
        ):
            command = controller.decide(
                observation_from_snapshot(monitor_filter.snapshot())
            ).acceleration_mps2
            overridden = True
            reason = "MONITOR_LOGIC_FORCED_TRIP"
            logic_active += 1
        if overridden:
            monitor_overrides += 1
            monitor_reasons[str(reason)] += 1
        if case.fixture == "open_loop_truth_arc":
            command = np.asarray(scenario.fixture_command_mps2, dtype=np.float64)
        commanded = np.asarray(command, dtype=np.float64)
        if np.linalg.norm(commanded) > foundation.max_acceleration_mps2 + 1e-12:
            raise RuntimeError("online commanded vector exceeds the frozen transfer bound")
        start_relative = pair_to_relative(truth)
        hcw_prediction = propagate_exact(
            _planar(start_relative),
            commanded,
            e004.mean_motion_rad_s,
            e004.command_period_s,
        )
        effectiveness = 1.0
        if scenario.actuation_effectiveness < 1.0 and active:
            effectiveness = scenario.actuation_effectiveness
            actuation_active += 1
        actuator_error = (
            streams.actuator_uncertainty_mps2[command_index]
            if scenario.mechanics_noise_enabled
            else np.zeros(2)
        )
        for substep in range(substeps):
            stream_index = command_index * substeps + substep
            sub_time = time_s + substep * e004.process_acceleration_draw_period_s
            process = (
                streams.process_acceleration_mps2[stream_index]
                if scenario.mechanics_noise_enabled
                else np.zeros(2)
            )
            disturbance = np.zeros(2, dtype=np.float64)
            if any(scenario.disturbance_bias_mps2) and _active(scenario, sub_time):
                disturbance = np.asarray(scenario.disturbance_bias_mps2, dtype=np.float64)
                disturbance_active += 1
            realized = effectiveness * commanded + actuator_error + process + disturbance
            segment = RealizedTruthSegment(
                truth,
                np.array([realized[0], realized[1], 0.0], dtype=np.float64),
                foundation,
                e004.process_acceleration_draw_period_s,
            )
            evaluator.observe(segment)
            hold = evaluate_truth_hold_segment(segment, foundation)
            if hold.entirely_inside:
                dwell_s += e004.process_acceleration_draw_period_s
                maximum_dwell_s = max(maximum_dwell_s, dwell_s)
            else:
                dwell_s = 0.0
            truth = segment.state_at(e004.process_acceleration_draw_period_s)
            digest.update(np.asarray(truth, dtype="<f8").tobytes())
            digest.update(np.asarray(realized, dtype="<f8").tobytes())
        next_relative = pair_to_relative(truth)
        mismatch_positions.append(
            float(np.linalg.norm(next_relative[:2] - hcw_prediction[:2]))
        )
        mismatch_velocities.append(
            float(np.linalg.norm(next_relative[3:5] - hcw_prediction[2:]))
        )
        next_time = float(command_index + 1)
        primary_filter.advance(commanded, next_time)
        monitor_filter.advance(commanded, next_time)
        next_planar = _planar(next_relative)
        for channel, filter_, raw_noise in (
            (
                "primary",
                primary_filter,
                streams.primary_measurement_noise[command_index + 1],
            ),
            (
                "monitor",
                monitor_filter,
                streams.monitor_measurement_noise[command_index + 1],
            ),
        ):
            if fault.active(next_time, channel):
                if channel == "primary":
                    primary_active += 1
                else:
                    monitor_active += 1
            noise = raw_noise if scenario.navigation_noise_enabled else np.zeros(4)
            packet = _packet(
                channel=channel,
                sequence_id=command_index + 1,
                time_s=next_time,
                latent_planar_state=next_planar,
                noise=noise,
                e004=e004,
                fault=fault,
                previous_packet=previous_packets[channel],
            )
            if packet is None:
                dispositions[channel]["dropout"] += 1
            else:
                diagnostic = filter_.ingest(packet)
                dispositions[channel][diagnostic.disposition.value] += 1
                previous_packets[channel] = packet
                digest.update(diagnostic.disposition.value.encode())
        snapshots = (primary_filter.snapshot(), monitor_filter.snapshot())
        minimum_covariance_eigenvalue, maximum_covariance_trace = (
            _update_covariance_extremes(
                snapshots,
                minimum_covariance_eigenvalue,
                maximum_covariance_trace,
            )
        )
        for snapshot in snapshots:
            digest.update(np.asarray(snapshot.mean, dtype="<f8").tobytes())
            digest.update(np.asarray(snapshot.covariance, dtype="<f8").tobytes())
        numerical_valid = bool(
            numerical_valid
            and np.all(np.isfinite(truth))
            and np.all(np.isfinite(next_relative))
            and np.all(np.isfinite(mismatch_positions))
            and np.all(np.isfinite(mismatch_velocities))
            and minimum_covariance_eigenvalue
            >= -e004.covariance_negative_eigenvalue_tolerance
            and maximum_covariance_trace < e004.covariance_trace_limit
        )
    physical = evaluator.finalize()
    final_relative = pair_to_relative(truth)
    return TransferEpisode(
        schema_version=pilot.schema_version,
        study_phase=(
            "design_validation_pilot"
            if scenario.partition_code == pilot.pilot_partition_code
            else "deterministic_validation_fixture"
        ),
        design_freeze_id=scenario.design_freeze_id,
        case_id=case.id,
        case_code=case.case_code,
        domain=case.domain,
        root_seed_id=scenario.root_seed_id,
        replicate=scenario.replicate,
        configuration_id=configuration_id,
        run_order=run_order,
        attempt_status="valid" if numerical_valid else "invalid",
        infrastructure_failure=False,
        physical_collision=physical.collision,
        physical_keep_out_entry=physical.unauthorized_keep_out_entry,
        physical_corridor_departure=physical.corridor_departure,
        minimum_separation_m=physical.minimum_separation_m,
        maximum_admissible_position_excess_m=(
            physical.maximum_admissible_position_excess_m
        ),
        maximum_abs_crosstrack_m=physical.maximum_abs_crosstrack_m,
        hold_acquired=maximum_dwell_s >= foundation.hold_required_dwell_s,
        maximum_contiguous_hold_dwell_s=maximum_dwell_s,
        primary_estimator_fault=scenario.measurement_fault_channel == "primary",
        monitor_estimator_fault=scenario.measurement_fault_channel == "monitor",
        monitor_logic_fault=scenario.monitor_logic_fault,
        shared_cause_fault=scenario.measurement_fault_channel == "shared",
        actuation_degradation_scheduled=scenario.actuation_effectiveness < 1.0,
        disturbance_scheduled=any(scenario.disturbance_bias_mps2),
        primary_fault_active_packets=primary_active,
        monitor_fault_active_packets=monitor_active,
        monitor_logic_active_commands=logic_active,
        actuation_degradation_active_commands=actuation_active,
        disturbance_active_substeps=disturbance_active,
        monitor_override_commands=monitor_overrides,
        monitor_reason_counts=dict(monitor_reasons),
        primary_disposition_counts=dict(dispositions["primary"]),
        monitor_disposition_counts=dict(dispositions["monitor"]),
        minimum_covariance_eigenvalue=minimum_covariance_eigenvalue,
        maximum_covariance_trace=maximum_covariance_trace,
        nonlinear_truth_numerical_valid=numerical_valid,
        model_mismatch_observations=len(mismatch_positions),
        maximum_hcw_position_residual_m=max(mismatch_positions),
        maximum_hcw_velocity_residual_mps=max(mismatch_velocities),
        final_truth_relative_state=tuple(float(value) for value in final_relative),
        scenario_hash=scenario.scenario_hash,
        stream_hashes=scenario.stream_hashes,
        controller_identity=controller.controller_identity,
        trace_digest=digest.hexdigest(),
    )


def run_block(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    scenario: TransferScenario,
) -> list[TransferEpisode]:
    streams, hashes = materialize_streams(
        pilot,
        foundation,
        e004,
        case,
        scenario.replicate,
        partition_code=scenario.partition_code,
    )
    for name, expected in hashes.items():
        if scenario.stream_hashes.get(name) != expected:
            raise RuntimeError(f"stream hash drift for {scenario.root_seed_id}/{name}")
    return [
        run_episode(
            pilot,
            foundation,
            e004,
            case,
            scenario,
            streams,
            configuration,
            order,
        )
        for order, configuration in enumerate(scenario.configuration_run_order, start=1)
    ]


def validate_complete_cells(
    rows: list[dict[str, Any]],
    pilot: TransferPilotConfig,
    cases: tuple[TransferCase, ...],
) -> dict[str, Any]:
    expected = {
        (case.id, replicate, configuration)
        for case in cases
        for replicate in range(pilot.pilot_roots_per_case)
        for configuration in pilot.configuration_ids
    }
    observed = [
        (str(row.get("case_id")), row.get("replicate"), str(row.get("configuration_id")))
        for row in rows
    ]
    observed_set = set(observed)
    duplicates = len(observed) - len(observed_set)
    missing = expected - observed_set
    extra = observed_set - expected
    roots = [str(row.get("root_seed_id")) for row in rows]
    root_pairs = {(row[0], row[1]) for row in observed}
    return {
        "passed": bool(
            len(rows) == pilot.pilot_episodes
            and duplicates == 0
            and not missing
            and not extra
            and len(root_pairs) == pilot.pilot_blocks
            and len(set(roots)) == pilot.pilot_blocks
        ),
        "expected_rows": pilot.pilot_episodes,
        "observed_rows": len(rows),
        "duplicates": duplicates,
        "missing": len(missing),
        "extra": len(extra),
        "unique_roots": len(set(roots)),
    }


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _publish_no_clobber(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise RuntimeError(f"refusing to replace completed file: {path.name}") from exc
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise RuntimeError(f"refusing to replace completed file: {path.name}") from exc
            raise
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _acquire_lock(checkpoint_dir: Path) -> tuple[Path, int]:
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    lock_path = checkpoint_dir / LOCK_NAME
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("checkpoint campaign is locked or requires stale-lock review") from exc
    os.write(
        descriptor,
        canonical_json({"pid": os.getpid(), "schema": CAMPAIGN_SCHEMA_VERSION}) + b"\n",
    )
    os.fsync(descriptor)
    _fsync_directory(checkpoint_dir)
    return lock_path, descriptor


def _release_lock(lock_path: Path, descriptor: int) -> None:
    os.close(descriptor)
    lock_path.unlink(missing_ok=False)
    _fsync_directory(lock_path.parent)


def _task_identity(index: int, scenario: TransferScenario) -> dict[str, Any]:
    unsigned = {
        "cell_index": index,
        "root_seed_id": scenario.root_seed_id,
        "case_id": scenario.case_id,
        "scenario_hash": scenario.scenario_hash,
        "configuration_run_order": list(scenario.configuration_run_order),
    }
    return {**unsigned, "cell_sha256": sha256_bytes(canonical_json(unsigned))}


def _campaign_record(scenarios: tuple[TransferScenario, ...]) -> dict[str, Any]:
    schedule = [_task_identity(index, scenario) for index, scenario in enumerate(scenarios)]
    unsigned = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "partition_code": scenarios[0].partition_code,
        "cell_count": len(scenarios),
        "ordered_schedule_sha256": sha256_bytes(canonical_json(schedule)),
        "canonical_assembly_order": "ascending frozen cell_index and within-cell run order",
        "parallelism": "process pool when workers exceed one",
        "resume_semantics": "validate all shards then execute missing unpublished cells only",
        "failure_semantics": "write immutable terminal failure record; never retry failed cell",
        "corrupt_shard_semantics": "fail closed without automatic recomputation",
        "maximum_retries": 0,
        "maximum_replacement_roots": 0,
    }
    return {**unsigned, "campaign_id": sha256_bytes(canonical_json(unsigned))}


def _prepare_checkpoint_directory(directory: Path, campaign: dict[str, Any]) -> None:
    state_path = directory / "campaign.json"
    expected = canonical_json(campaign) + b"\n"
    if state_path.exists():
        if state_path.read_bytes() != expected:
            raise RuntimeError("checkpoint campaign identity mismatch")
        return
    remaining = [path for path in directory.iterdir() if path.name != LOCK_NAME]
    if remaining:
        raise RuntimeError("checkpoint directory lacks its frozen campaign identity")
    _publish_no_clobber(state_path, expected)


def _shard_path(directory: Path, cell_index: int) -> Path:
    return directory / f"cell-{cell_index:06d}.json"


def _failure_path(directory: Path, cell_index: int) -> Path:
    return directory / "failures" / f"cell-{cell_index:06d}.json"


def _build_shard(
    identity: dict[str, Any], rows: list[dict[str, Any]], campaign_id: str
) -> dict[str, Any]:
    if len(rows) != 2 or [row.get("run_order") for row in rows] != [1, 2]:
        raise RuntimeError("transfer cell did not produce one complete ordered block")
    if any(row.get("root_seed_id") != identity["root_seed_id"] for row in rows):
        raise RuntimeError("transfer cell root identity drift")
    unsigned = {
        "schema_version": SHARD_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        **identity,
        "rows": rows,
        "rows_sha256": sha256_bytes(canonical_json(rows)),
    }
    return {**unsigned, "shard_id": sha256_bytes(canonical_json(unsigned))}


def _validate_shard(
    path: Path, identity: dict[str, Any], campaign_id: str
) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        shard = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"corrupt checkpoint shard: {path.name}") from exc
    if not isinstance(shard, dict) or raw != canonical_json(shard) + b"\n":
        raise RuntimeError(f"noncanonical checkpoint shard: {path.name}")
    unsigned = dict(shard)
    shard_id = unsigned.pop("shard_id", None)
    if shard_id != sha256_bytes(canonical_json(unsigned)):
        raise RuntimeError(f"checkpoint shard hash mismatch: {path.name}")
    if (
        shard.get("schema_version") != SHARD_SCHEMA_VERSION
        or shard.get("campaign_id") != campaign_id
        or any(shard.get(key) != value for key, value in identity.items())
    ):
        raise RuntimeError(f"checkpoint shard identity mismatch: {path.name}")
    rows = shard.get("rows")
    if not isinstance(rows, list) or shard.get("rows_sha256") != sha256_bytes(
        canonical_json(rows)
    ):
        raise RuntimeError(f"checkpoint shard row hash mismatch: {path.name}")
    _build_shard(identity, rows, campaign_id)
    return shard


def _scan_shards(
    directory: Path,
    scenarios: tuple[TransferScenario, ...],
    campaign_id: str,
) -> dict[int, dict[str, Any]]:
    failure_directory = directory / "failures"
    failures = (
        sorted(failure_directory.glob("*.json"))
        if failure_directory.exists()
        else []
    )
    if failures:
        raise RuntimeError(f"terminal failed cell requires review: {failures[0].name}")
    expected = {_shard_path(directory, index).name for index in range(len(scenarios))}
    ignored = {"campaign.json", LOCK_NAME, "failures"}
    actual = {path.name for path in directory.iterdir() if path.name not in ignored}
    unexpected = sorted(actual - expected)
    if unexpected:
        raise RuntimeError(f"unexpected or duplicate checkpoint evidence: {unexpected[0]}")
    completed: dict[int, dict[str, Any]] = {}
    roots: set[str] = set()
    for index, scenario in enumerate(scenarios):
        path = _shard_path(directory, index)
        if not path.exists():
            continue
        identity = _task_identity(index, scenario)
        shard = _validate_shard(path, identity, campaign_id)
        root_id = str(shard["root_seed_id"])
        if root_id in roots:
            raise RuntimeError("duplicate root identity across checkpoint shards")
        roots.add(root_id)
        completed[index] = shard
    return completed


def _terminal_failure(
    identity: dict[str, Any], campaign_id: str, exc: BaseException
) -> dict[str, Any]:
    message = f"{type(exc).__name__}:{exc}"
    unsigned = {
        "schema_version": FAILURE_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        **identity,
        "attempt_number": 1,
        "execution_began": True,
        "terminal_state": "failed_no_retry_or_replacement",
        "exception_class": type(exc).__name__,
        "exception_message_sha256": sha256_bytes(message.encode()),
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
    }
    return {**unsigned, "failure_id": sha256_bytes(canonical_json(unsigned))}


def _execute_cell(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    scenario: TransferScenario,
    fail_case_id_for_test: str | None,
) -> list[dict[str, Any]]:
    if fail_case_id_for_test is not None and scenario.case_id == fail_case_id_for_test:
        if scenario.partition_code != pilot.test_fixture_partition_code:
            raise RuntimeError("failure injection is restricted to partition 951")
        raise RuntimeError("deterministic partition-951 worker failure fixture")
    return [
        episode.to_dict()
        for episode in run_block(pilot, foundation, e004, case, scenario)
    ]


def _assemble(
    output_path: Path,
    directory: Path,
    scenarios: tuple[TransferScenario, ...],
    campaign_id: str,
) -> tuple[int, str]:
    shards = _scan_shards(directory, scenarios, campaign_id)
    if len(shards) != len(scenarios):
        raise RuntimeError("cannot assemble an incomplete frozen campaign")
    content = b"".join(
        canonical_json(row) + b"\n"
        for index in range(len(scenarios))
        for row in shards[index]["rows"]
    )
    if output_path.exists():
        if output_path.read_bytes() != content:
            raise RuntimeError("existing output conflicts with canonical shard assembly")
    else:
        _publish_no_clobber(output_path, content)
    return len(scenarios) * 2, sha256_bytes(content)


def run_checkpointed_campaign(
    directory: str | Path,
    *,
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
    scenarios: tuple[TransferScenario, ...],
    workers: int | None = None,
    stop_after_for_test: int | None = None,
    fail_case_id_for_test: str | None = None,
) -> dict[str, Any]:
    if not scenarios:
        raise ValueError("checkpoint campaign requires frozen scenarios")
    partition_codes = {scenario.partition_code for scenario in scenarios}
    if len(partition_codes) != 1 or partition_codes.pop() not in {
        pilot.pilot_partition_code,
        pilot.test_fixture_partition_code,
    }:
        raise ValueError("checkpoint campaign accepts only partition 52 or 951")
    if len({scenario.root_seed_id for scenario in scenarios}) != len(scenarios):
        raise ValueError("checkpoint campaign contains duplicate roots")
    if stop_after_for_test is not None or fail_case_id_for_test is not None:
        if scenarios[0].partition_code != pilot.test_fixture_partition_code:
            raise ValueError("test controls are restricted to partition 951")
    worker_count = default_workers() if workers is None else workers
    if type(worker_count) is not int or worker_count < 1:
        raise ValueError("workers must be a positive integer")
    case_map = {case.id: case for case in cases}
    if any(scenario.case_id not in case_map for scenario in scenarios):
        raise ValueError("checkpoint schedule contains an unknown case")
    root = Path(directory)
    checkpoint_dir = root / "shards"
    output_path = root / "pilot-episodes.jsonl"
    campaign = _campaign_record(scenarios)
    lock_path, lock_descriptor = _acquire_lock(checkpoint_dir)
    try:
        _prepare_checkpoint_directory(checkpoint_dir, campaign)
        completed = _scan_shards(checkpoint_dir, scenarios, campaign["campaign_id"])
        reused = len(completed)
        missing = [index for index in range(len(scenarios)) if index not in completed]
        if stop_after_for_test is not None:
            missing = missing[:stop_after_for_test]

        def persist(index: int, rows: list[dict[str, Any]]) -> None:
            identity = _task_identity(index, scenarios[index])
            shard = _build_shard(identity, rows, campaign["campaign_id"])
            _publish_no_clobber(
                _shard_path(checkpoint_dir, index), canonical_json(shard) + b"\n"
            )

        if worker_count == 1:
            for index in missing:
                try:
                    rows = _execute_cell(
                        pilot,
                        foundation,
                        e004,
                        case_map[scenarios[index].case_id],
                        scenarios[index],
                        fail_case_id_for_test,
                    )
                except BaseException as exc:
                    failure = _terminal_failure(
                        _task_identity(index, scenarios[index]),
                        campaign["campaign_id"],
                        exc,
                    )
                    _publish_no_clobber(
                        _failure_path(checkpoint_dir, index),
                        canonical_json(failure) + b"\n",
                    )
                    raise
                persist(index, rows)
        else:
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(
                        _execute_cell,
                        pilot,
                        foundation,
                        e004,
                        case_map[scenarios[index].case_id],
                        scenarios[index],
                        fail_case_id_for_test,
                    ): index
                    for index in missing
                }
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        rows = future.result()
                    except BaseException as exc:
                        failure = _terminal_failure(
                            _task_identity(index, scenarios[index]),
                            campaign["campaign_id"],
                            exc,
                        )
                        _publish_no_clobber(
                            _failure_path(checkpoint_dir, index),
                            canonical_json(failure) + b"\n",
                        )
                        for pending in futures:
                            pending.cancel()
                        raise
                    persist(index, rows)
        completed = _scan_shards(checkpoint_dir, scenarios, campaign["campaign_id"])
        complete = len(completed) == len(scenarios)
        rows = None
        digest = None
        if complete:
            rows, digest = _assemble(
                output_path, checkpoint_dir, scenarios, campaign["campaign_id"]
            )
        return {
            "passed": complete,
            "complete": complete,
            "campaign_id": campaign["campaign_id"],
            "partition_code": scenarios[0].partition_code,
            "cells": len(completed),
            "planned_cells": len(scenarios),
            "rows": rows,
            "output_sha256": digest,
            "workers": worker_count,
            "completed_shards_reused": reused,
            "new_shards_written": len(missing),
            "remaining_cells": len(scenarios) - len(completed),
            "infrastructure_failures": 0,
            "retries": 0,
            "replacement_roots": 0,
            "canonical_assembly": True,
        }
    finally:
        _release_lock(lock_path, lock_descriptor)
