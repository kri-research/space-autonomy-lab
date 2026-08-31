from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
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
from kri_space_autonomy.experiment_004.estimator import NavigationSnapshot, PlanarNavigationFilter
from kri_space_autonomy.experiment_004.evaluation import IndependentPlanarEvaluator, TechnicalStatus
from kri_space_autonomy.experiment_004.geometry import HCWSegment
from kri_space_autonomy.experiment_004.measurements import MeasurementFault, navigation_packet

from .config import CONFIGURATIONS, PilotCase, PilotConfig
from .seeds import PilotScenario, PilotStreams, canonical_json, materialize_streams, sha256_bytes


@dataclass(frozen=True)
class PilotEpisode:
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
    maximum_corridor_excess_m: float
    hold_acquired: bool
    maximum_contiguous_hold_dwell_s: float
    safe_incomplete: bool
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
    numerical_valid: bool
    final_state: tuple[float, float, float, float]
    scenario_hash: str
    stream_hashes: dict[str, str]
    controller_identity: str
    trace_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _active(scenario: PilotScenario, time_s: float) -> bool:
    return bool(
        scenario.fault_onset_s is not None
        and time_s >= scenario.fault_onset_s
        and (scenario.fault_end_s is None or time_s < scenario.fault_end_s)
    )


def _measurement_fault(scenario: PilotScenario) -> MeasurementFault:
    return MeasurementFault(
        kind=scenario.measurement_fault_kind,
        channel=scenario.measurement_fault_channel,
        onset_s=scenario.fault_onset_s,
        end_s=scenario.fault_end_s,
        additive_bias=scenario.additive_bias,
        covariance_factor=scenario.covariance_factor,
    )


def _nominal_control(
    primary_snapshot: NavigationSnapshot,
    monitor_snapshot: NavigationSnapshot,
    controller: DeterministicHoldController,
    monitor: EstimatedGeometryMonitor,
    configuration_id: str,
) -> tuple[np.ndarray, bool, str | None]:
    """Online control path; arguments contain no truth, fault label, or evaluator state."""

    proposal = controller.decide(observation_from_snapshot(primary_snapshot))
    if configuration_id == "primary_reference":
        return proposal.acceleration_mps2, False, None
    if configuration_id != "independent_monitor_gate":
        raise ValueError("unknown pilot diagnostic configuration")
    decision = monitor.gate(monitor_snapshot, proposal)
    return decision.executed_acceleration_mps2, decision.overridden, decision.reason


def _packet(
    *,
    channel: str,
    sequence_id: int,
    time_s: float,
    latent_state: np.ndarray,
    noise: np.ndarray,
    foundation: Experiment004Config,
    fault: MeasurementFault,
    previous_packet,
):
    return navigation_packet(
        sequence_id=sequence_id,
        measured_at_s=time_s,
        received_at_s=time_s,
        latent_state=latent_state,
        measurement_noise=noise,
        quantization=np.asarray(foundation.measurement_quantization, dtype=np.float64),
        nominal_covariance=foundation.nominal_measurement_covariance,
        channel=channel,
        fault=fault,
        previous_packet=previous_packet,
    )


def _update_covariance_extremes(
    snapshots: tuple[NavigationSnapshot, NavigationSnapshot],
    minimum: float,
    maximum: float,
) -> tuple[float, float]:
    for snapshot in snapshots:
        covariance = snapshot.covariance
        minimum = min(minimum, float(np.linalg.eigvalsh(covariance)[0]))
        maximum = max(maximum, float(np.trace(covariance)))
    return minimum, maximum


def run_episode(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    scenario: PilotScenario,
    streams: PilotStreams,
    configuration_id: str,
    run_order: int,
) -> PilotEpisode:
    if configuration_id not in CONFIGURATIONS:
        raise ValueError("unknown diagnostic configuration")
    if scenario.case_id != case.id or scenario.case_code != case.case_code:
        raise ValueError("scenario does not match the frozen case")
    if scenario.configuration_run_order[run_order - 1] != configuration_id:
        raise ValueError("configuration run order does not match the frozen block")

    controller = DeterministicHoldController(foundation)
    monitor = EstimatedGeometryMonitor(
        foundation,
        DeterministicHoldController(foundation),
        controller.controller_identity,
    )
    primary_filter = PlanarNavigationFilter(foundation)
    monitor_filter = PlanarNavigationFilter(foundation)
    evaluator = IndependentPlanarEvaluator(foundation)
    state = np.asarray(scenario.initial_state, dtype=np.float64)
    fault = _measurement_fault(scenario)
    previous_packet: dict[str, Any] = {"primary": None, "monitor": None}
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
    digest = hashlib.sha256()

    for channel, filter_, noise in (
        ("primary", primary_filter, streams.primary_measurement_noise[0]),
        ("monitor", monitor_filter, streams.monitor_measurement_noise[0]),
    ):
        packet = _packet(
            channel=channel,
            sequence_id=0,
            time_s=0.0,
            latent_state=state,
            noise=noise,
            foundation=foundation,
            fault=fault,
            previous_packet=None,
        )
        if packet is not None:
            diagnostic = filter_.ingest(packet)
            dispositions[channel][diagnostic.disposition.value] += 1
            previous_packet[channel] = packet
        else:
            dispositions[channel]["dropout"] += 1
    minimum_covariance_eigenvalue, maximum_covariance_trace = _update_covariance_extremes(
        (primary_filter.snapshot(), monitor_filter.snapshot()),
        minimum_covariance_eigenvalue,
        maximum_covariance_trace,
    )

    command_steps = round(scenario.horizon_s / foundation.command_period_s)
    substeps = round(
        foundation.command_period_s / foundation.process_acceleration_draw_period_s
    )
    if command_steps * substeps != len(streams.process_acceleration_mps2):
        raise ValueError("process stream length does not match the scenario horizon")

    for command_index in range(command_steps):
        time_s = command_index * foundation.command_period_s
        primary_snapshot = primary_filter.snapshot()
        monitor_snapshot = monitor_filter.snapshot()
        command, overridden, reason = _nominal_control(
            primary_snapshot,
            monitor_snapshot,
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
                observation_from_snapshot(monitor_snapshot)
            ).acceleration_mps2
            overridden = True
            reason = "MONITOR_LOGIC_FORCED_TRIP"
            logic_active += 1
        if overridden:
            monitor_overrides += 1
            monitor_reasons[str(reason)] += 1
        if case.fixture == "open_loop_exact_arc":
            command = np.asarray(scenario.fixture_command_mps2, dtype=np.float64)
        commanded = np.asarray(command, dtype=np.float64)
        effectiveness = 1.0
        if scenario.actuation_effectiveness < 1.0 and active:
            effectiveness = scenario.actuation_effectiveness
            actuation_active += 1
        actuator_error = streams.actuator_uncertainty_mps2[command_index]

        for substep in range(substeps):
            stream_index = command_index * substeps + substep
            sub_time = time_s + substep * foundation.process_acceleration_draw_period_s
            disturbance = np.zeros(2, dtype=np.float64)
            if any(scenario.disturbance_bias_mps2) and _active(scenario, sub_time):
                disturbance = np.asarray(scenario.disturbance_bias_mps2, dtype=np.float64)
                disturbance_active += 1
            realized = (
                effectiveness * commanded
                + actuator_error
                + streams.process_acceleration_mps2[stream_index]
                + disturbance
            )
            segment = HCWSegment(
                state,
                realized,
                foundation.mean_motion_rad_s,
                foundation.process_acceleration_draw_period_s,
                maximum_duration_s=foundation.event_interval_max_s,
            )
            evaluator.observe(segment)
            state = segment.state_at(foundation.process_acceleration_draw_period_s)
            digest.update(np.asarray(state, dtype="<f8").tobytes())
            digest.update(np.asarray(realized, dtype="<f8").tobytes())

        next_time = float(command_index + 1)
        primary_filter.advance(commanded, next_time)
        monitor_filter.advance(commanded, next_time)
        for channel, filter_, noise in (
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
            packet = _packet(
                channel=channel,
                sequence_id=command_index + 1,
                time_s=next_time,
                latent_state=state,
                noise=noise,
                foundation=foundation,
                fault=fault,
                previous_packet=previous_packet[channel],
            )
            if packet is None:
                dispositions[channel]["dropout"] += 1
            else:
                diagnostic = filter_.ingest(packet)
                dispositions[channel][diagnostic.disposition.value] += 1
                previous_packet[channel] = packet
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
            and np.all(np.isfinite(state))
            and minimum_covariance_eigenvalue
            >= -foundation.covariance_negative_eigenvalue_tolerance
            and maximum_covariance_trace < foundation.covariance_trace_limit
        )

    technical = TechnicalStatus(
        primary_estimator_fault=scenario.measurement_fault_channel == "primary",
        monitor_estimator_fault=scenario.measurement_fault_channel == "monitor",
        monitor_logic_fault=scenario.monitor_logic_fault,
        shared_cause_fault=scenario.measurement_fault_channel == "shared",
        numerical_failure=not numerical_valid,
    )
    summary = evaluator.finalize(technical)
    return PilotEpisode(
        schema_version=pilot.schema_version,
        study_phase="design_validation_pilot",
        design_freeze_id=scenario.design_freeze_id,
        case_id=case.id,
        case_code=case.case_code,
        domain=case.domain,
        root_seed_id=scenario.root_seed_id,
        replicate=scenario.replicate,
        configuration_id=configuration_id,
        run_order=run_order,
        attempt_status="valid" if numerical_valid else "adverse_valid",
        infrastructure_failure=False,
        physical_collision=summary.physical.collision,
        physical_keep_out_entry=summary.physical.unauthorized_keep_out_entry,
        physical_corridor_departure=summary.physical.corridor_departure,
        minimum_separation_m=summary.physical.minimum_separation_m,
        maximum_corridor_excess_m=summary.physical.maximum_corridor_excess_m,
        hold_acquired=summary.mission.hold_acquired,
        maximum_contiguous_hold_dwell_s=summary.mission.maximum_contiguous_hold_dwell_s,
        safe_incomplete=summary.mission.safe_incomplete,
        primary_estimator_fault=technical.primary_estimator_fault,
        monitor_estimator_fault=technical.monitor_estimator_fault,
        monitor_logic_fault=technical.monitor_logic_fault,
        shared_cause_fault=technical.shared_cause_fault,
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
        numerical_valid=numerical_valid,
        final_state=tuple(float(value) for value in state),
        scenario_hash=scenario.scenario_hash,
        stream_hashes=scenario.stream_hashes,
        controller_identity=controller.controller_identity,
        trace_digest=digest.hexdigest(),
    )


def _scenario_from_row(row: dict[str, Any]) -> PilotScenario:
    value = dict(row)
    for key in (
        "initial_state",
        "fixture_command_mps2",
        "additive_bias",
        "disturbance_bias_mps2",
        "configuration_run_order",
    ):
        if value.get(key) is not None:
            value[key] = tuple(value[key])
    return PilotScenario(**value)


def run_block(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    scenario: PilotScenario,
) -> list[PilotEpisode]:
    streams, hashes = materialize_streams(
        pilot,
        foundation,
        case,
        scenario.replicate,
        partition_code=scenario.partition_code,
    )
    for name, expected in hashes.items():
        if scenario.stream_hashes.get(name) != expected:
            raise RuntimeError(f"stream hash drift for {scenario.root_seed_id}/{name}")
    return [
        run_episode(pilot, foundation, case, scenario, streams, configuration, order)
        for order, configuration in enumerate(scenario.configuration_run_order, start=1)
    ]


def run_pilot(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
    *,
    seed_manifest_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Future write-once partition-43 runner. This function is not used during design freeze."""

    output = Path(output_path)
    if output.exists() or output.parent.exists():
        raise RuntimeError("refusing pre-existing Experiment 004 pilot result path")
    scenarios = [
        _scenario_from_row(json.loads(line))
        for line in Path(seed_manifest_path).read_text(encoding="utf-8").splitlines()
    ]
    if len(scenarios) != pilot.pilot_blocks:
        raise RuntimeError("pilot manifest root count drift")
    if any(scenario.partition_code != pilot.pilot_partition_code for scenario in scenarios):
        raise RuntimeError("pilot runner received a non-partition-43 scenario")
    case_map = {case.id: case for case in cases}
    output.parent.mkdir(parents=True, exist_ok=False)
    started = time.time()
    episodes = 0
    with output.open("x", encoding="utf-8") as handle:
        for scenario in scenarios:
            case = case_map.get(scenario.case_id)
            if case is None:
                raise RuntimeError("pilot manifest contains an unknown case")
            for episode in run_block(pilot, foundation, case, scenario):
                handle.write(canonical_json(episode.to_dict()).decode() + "\n")
                episodes += 1
            handle.flush()
    if episodes != pilot.pilot_episodes:
        raise RuntimeError("pilot episode count drift")
    return {
        "blocks": len(scenarios),
        "episodes": episodes,
        "elapsed_wall_s": time.time() - started,
        "episodes_sha256": sha256_bytes(output.read_bytes()),
    }
