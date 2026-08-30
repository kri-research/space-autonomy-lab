from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.dynamics import TruthState, propagate_exact
from kri_space_autonomy.experiment_002.evaluator import IndependentEvaluator
from kri_space_autonomy.experiment_002.policy import FrozenPolicy, ReferenceController

from .config import ARMS, Experiment003Config
from .estimator import FilterHealth, NavigationFilter
from .evaluation import (
    OfflineEstimatorSample,
    classify_estimator_recovery,
    offline_sample,
)
from .interfaces import EstimatedRuntimeGate, policy_observation
from .measurements import MeasurementFault, navigation_packet
from .seeds import (
    Experiment003Scenario,
    Experiment003Streams,
    canonical_json,
    materialize_exogenous,
    sha256_bytes,
)


@dataclass(frozen=True)
class Experiment003Episode:
    schema_version: str
    study_phase: str
    stratum_id: str
    root_seed_id: str
    replicate: int
    arm: str
    run_order: int
    attempt_status: str
    failure_class: str | None
    elapsed_time_s: float
    physical_hazard_observed: bool
    analysis_hazard: bool
    collision: bool
    sustained_success: bool
    propellant_depleted: bool
    braking_unreachable: bool
    minimum_braking_margin_m: float | None
    minimum_range_m: float
    maximum_contiguous_negative_margin_s: float
    recovery_state: str
    recovery_favorable_180: bool | None
    restricted_time_unrecovered_s_180: float | None
    estimator_first_affected_s: float | None
    qualifying_recovery_start_s: float | None
    primary_estimator_diverged: bool
    monitor_estimator_diverged: bool
    primary_accepted_updates: int
    monitor_accepted_updates: int
    primary_innovation_rejections: int
    monitor_innovation_rejections: int
    primary_invalid_packets: int
    monitor_invalid_packets: int
    primary_max_abs_range_error_m: float
    monitor_max_abs_range_error_m: float
    primary_max_abs_velocity_error_mps: float
    monitor_max_abs_velocity_error_mps: float
    primary_nees_available_fraction: float
    monitor_nees_available_fraction: float
    handover_entries: int
    fallback_duty_cycle: float
    propellant_used_fraction: float
    goal_dwell_final60_fraction: float
    fault_onset_s: float | None
    fault_end_s: float | None
    scenario_hash: str
    exogenous_hashes: dict[str, str]
    config_hash: str
    policy_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _scenario_from_dict(row: dict[str, Any]) -> Experiment003Scenario:
    value = dict(row)
    value["arm_run_order"] = tuple(value["arm_run_order"])
    return Experiment003Scenario(**value)


def _fault(spec: Experiment003Scenario) -> MeasurementFault:
    return MeasurementFault(
        spec.stratum_id,
        spec.fault_channel,
        spec.fault_onset_s,
        spec.fault_end_s,
        spec.range_bias_m,
        spec.covariance_factor,
    )


def _packet_for_channel(
    *,
    channel: str,
    command_index: int,
    time_s: float,
    history: list[TruthState],
    streams: Experiment003Streams,
    spec: Experiment003Scenario,
    filter_: NavigationFilter,
    previous_packet,
    production,
):
    if channel == "primary":
        range_noise = streams.primary_range_noise_m[command_index]
        velocity_noise = streams.primary_velocity_noise_mps[command_index]
        latency_s = streams.primary_latency_s[command_index]
    elif channel == "monitor":
        range_noise = streams.monitor_range_noise_m[command_index]
        velocity_noise = streams.monitor_velocity_noise_mps[command_index]
        latency_s = streams.monitor_latency_s[command_index]
    else:
        raise ValueError("channel must be primary or monitor")
    measured_at_s = max(0.0, time_s - float(latency_s))
    history_index = round(measured_at_s / production.exogenous_period_s)
    latent = history[history_index]
    return navigation_packet(
        sequence_id=command_index,
        measured_at_s=measured_at_s,
        received_at_s=time_s,
        range_value_m=latent.range_m,
        velocity_value_mps=latent.relative_velocity_mps,
        range_noise_m=float(range_noise),
        velocity_noise_mps=float(velocity_noise),
        range_quantization_m=production.range_quantization_m,
        velocity_quantization_mps=production.velocity_quantization_mps,
        nominal_covariance=filter_.nominal_measurement_covariance,
        channel=channel,
        fault=_fault(spec),
        previous_packet=previous_packet,
    )


def _combined_sample(
    primary: OfflineEstimatorSample,
    monitor: OfflineEstimatorSample,
) -> OfflineEstimatorSample:
    nees_values = [value for value in (primary.nees, monitor.nees) if value is not None]
    nees = max(nees_values) if len(nees_values) == 2 else None
    health = (
        FilterHealth.DIVERGED
        if FilterHealth.DIVERGED in {primary.runtime_health, monitor.runtime_health}
        else (
            FilterHealth.DEGRADED
            if FilterHealth.DEGRADED in {primary.runtime_health, monitor.runtime_health}
            else FilterHealth.VALID
        )
    )
    return OfflineEstimatorSample(
        primary.time_s,
        max((primary.range_error_m, monitor.range_error_m), key=abs),
        max((primary.velocity_error_mps, monitor.velocity_error_mps), key=abs),
        max((primary.acceleration_error_mps2, monitor.acceleration_error_mps2), key=abs),
        nees,
        health,
    )


def _error_summary(samples: list[OfflineEstimatorSample]) -> tuple[float, float, float]:
    if not samples:
        return 0.0, 0.0, 0.0
    nees_count = sum(sample.nees is not None for sample in samples)
    return (
        max(abs(sample.range_error_m) for sample in samples),
        max(abs(sample.velocity_error_mps) for sample in samples),
        nees_count / len(samples),
    )


def run_arm(
    study: Experiment003Config,
    production,
    spec: Experiment003Scenario,
    streams: Experiment003Streams,
    arm: str,
    run_order: int,
    policy: FrozenPolicy,
    config_hash: str,
    *,
    collect_trace: bool = False,
) -> tuple[Experiment003Episode, list[dict[str, Any]] | None]:
    if arm not in ARMS:
        raise ValueError("unknown Experiment 003 arm")
    reference = ReferenceController(production)
    expected_identity = policy.model_identity
    gate = EstimatedRuntimeGate(study, production, reference, expected_identity)
    primary_filter = NavigationFilter(study, production)
    monitor_filter = NavigationFilter(study, production)
    state = TruthState(
        0.0,
        spec.initial_range_m,
        spec.initial_velocity_mps,
        spec.initial_propellant,
        0.0,
    )
    history = [state]
    evaluator = IndependentEvaluator(production, state, 1.0)
    command = 0.0
    previous_packet = {"primary": None, "monitor": None}
    primary_samples: list[OfflineEstimatorSample] = []
    monitor_samples: list[OfflineEstimatorSample] = []
    recovery_samples: list[OfflineEstimatorSample] = []
    trace: list[dict[str, Any]] | None = [] if collect_trace else None
    previous_overridden = False
    overridden = False
    handover_entries = 0
    fallback_time_s = 0.0
    invalid_action = False
    numerical_failure = False
    command_stride = round(production.command_period_s / production.exogenous_period_s)

    for tick in range(production.n_exogenous_steps):
        time_s = tick * production.exogenous_period_s
        if tick % command_stride == 0:
            command_index = tick // command_stride
            if time_s > 0.0:
                primary_filter.advance(command, time_s)
                monitor_filter.advance(command, time_s)
            for channel, filter_ in (
                ("primary", primary_filter),
                ("monitor", monitor_filter),
            ):
                packet = _packet_for_channel(
                    channel=channel,
                    command_index=command_index,
                    time_s=time_s,
                    history=history,
                    streams=streams,
                    spec=spec,
                    filter_=filter_,
                    previous_packet=previous_packet[channel],
                    production=production,
                )
                if packet is not None:
                    filter_.ingest(packet)
                    previous_packet[channel] = packet
            primary_estimate = primary_filter.snapshot()
            monitor_estimate = monitor_filter.snapshot()
            primary_observation = policy_observation(
                primary_estimate, state.propellant, time_s
            )
            if arm == "R":
                decision = reference.decide(primary_observation)
                command = decision.commanded_acceleration_mps2
                overridden = False
                gate_reason = None
            else:
                decision = policy.decide(primary_observation)
                if arm == "D":
                    command = decision.commanded_acceleration_mps2
                    overridden = False
                    gate_reason = None
                else:
                    gate_estimate = primary_estimate if arm == "PS" else monitor_estimate
                    gated = gate.gate(gate_estimate, state.propellant, decision)
                    command = gated.executed_acceleration_mps2
                    overridden = gated.overridden
                    gate_reason = gated.reason
            if not math.isfinite(command):
                invalid_action = True
                command = 0.0
            if overridden and not previous_overridden:
                handover_entries += 1
            previous_overridden = overridden
            truth_vector = np.array(
                [
                    state.range_m,
                    state.relative_velocity_mps,
                    state.achieved_acceleration_mps2,
                ],
                dtype=np.float64,
            )
            primary_offline = offline_sample(truth_vector, primary_estimate)
            monitor_offline = offline_sample(truth_vector, monitor_estimate)
            primary_samples.append(primary_offline)
            monitor_samples.append(monitor_offline)
            recovery_samples.append(
                _combined_sample(primary_offline, monitor_offline)
                if arm == "PD"
                else primary_offline
            )
            if trace is not None:
                trace.append(
                    {
                        "time_s": time_s,
                        "command_mps2": command,
                        "overridden": overridden,
                        "gate_reason": gate_reason,
                        "primary_mean": primary_estimate.mean.tolist(),
                        "primary_covariance": primary_estimate.covariance.tolist(),
                        "primary_health": primary_estimate.health.value,
                        "monitor_mean": monitor_estimate.mean.tolist(),
                        "monitor_covariance": monitor_estimate.covariance.tolist(),
                        "monitor_health": monitor_estimate.health.value,
                    }
                )

        start_state = state
        try:
            propagation = propagate_exact(
                state,
                command,
                1.0,
                float(streams.process_acceleration_mps2[tick]),
                production.exogenous_period_s,
                production,
            )
        except (ArithmeticError, ValueError, OverflowError):
            numerical_failure = True
            break
        evaluator.observe_interval(start_state, propagation)
        state = propagation.state
        history.append(state)
        fallback_time_s += production.exogenous_period_s * float(overridden)
        if (tick + 1) % command_stride == 0:
            evaluator.observe_margin(state, 1.0)
        if evaluator.collision:
            break

    summary = evaluator.finalize(state)
    primary_snapshot = primary_filter.snapshot()
    monitor_snapshot = monitor_filter.snapshot()
    primary_diverged = primary_snapshot.health is FilterHealth.DIVERGED
    monitor_diverged = monitor_snapshot.health is FilterHealth.DIVERGED
    required_diverged = primary_diverged or (arm == "PD" and monitor_diverged)
    failure_class: str | None = None
    if invalid_action:
        failure_class = "INVALID_ACTION"
    elif numerical_failure:
        failure_class = "NUMERICAL_FAILURE"
    elif required_diverged:
        failure_class = "ESTIMATOR_DIVERGED"
    analysis_hazard = bool(
        summary.physical_hazard_observed
        or summary.propellant_depleted
        or failure_class is not None
    )
    sustained_success = bool(summary.sustained_success and not analysis_hazard)
    recovery = classify_estimator_recovery(
        recovery_samples,
        fault_onset_s=spec.fault_onset_s,
        fault_end_s=spec.fault_end_s,
        failed=analysis_hazard,
        sustained_success=sustained_success,
        protected_arm=arm in {"PS", "PD"},
        fallback_latched=required_diverged and arm in {"PS", "PD"},
        config=study,
    )
    primary_error = _error_summary(primary_samples)
    monitor_error = _error_summary(monitor_samples)
    elapsed = state.time_s
    episode = Experiment003Episode(
        schema_version=study.schema_version,
        study_phase="design_validation_pilot",
        stratum_id=spec.stratum_id,
        root_seed_id=spec.root_seed_id,
        replicate=spec.replicate,
        arm=arm,
        run_order=run_order,
        attempt_status="valid" if failure_class is None else "adverse_valid",
        failure_class=failure_class,
        elapsed_time_s=elapsed,
        physical_hazard_observed=summary.physical_hazard_observed,
        analysis_hazard=analysis_hazard,
        collision=summary.collision,
        sustained_success=sustained_success,
        propellant_depleted=summary.propellant_depleted,
        braking_unreachable=summary.braking_unreachable,
        minimum_braking_margin_m=summary.minimum_braking_margin_m,
        minimum_range_m=summary.minimum_range_m,
        maximum_contiguous_negative_margin_s=summary.maximum_contiguous_negative_margin_s,
        recovery_state=recovery["recovery_state"],
        recovery_favorable_180=recovery["recovery_favorable_180"],
        restricted_time_unrecovered_s_180=recovery[
            "restricted_time_unrecovered_s_180"
        ],
        estimator_first_affected_s=recovery["estimator_first_affected_s"],
        qualifying_recovery_start_s=recovery["qualifying_recovery_start_s"],
        primary_estimator_diverged=primary_diverged,
        monitor_estimator_diverged=monitor_diverged,
        primary_accepted_updates=primary_snapshot.accepted_updates,
        monitor_accepted_updates=monitor_snapshot.accepted_updates,
        primary_innovation_rejections=primary_snapshot.innovation_rejections,
        monitor_innovation_rejections=monitor_snapshot.innovation_rejections,
        primary_invalid_packets=primary_snapshot.invalid_packets,
        monitor_invalid_packets=monitor_snapshot.invalid_packets,
        primary_max_abs_range_error_m=primary_error[0],
        monitor_max_abs_range_error_m=monitor_error[0],
        primary_max_abs_velocity_error_mps=primary_error[1],
        monitor_max_abs_velocity_error_mps=monitor_error[1],
        primary_nees_available_fraction=primary_error[2],
        monitor_nees_available_fraction=monitor_error[2],
        handover_entries=handover_entries,
        fallback_duty_cycle=fallback_time_s / elapsed if elapsed > 0.0 else 0.0,
        propellant_used_fraction=spec.initial_propellant - state.propellant,
        goal_dwell_final60_fraction=summary.goal_dwell_final60_fraction,
        fault_onset_s=spec.fault_onset_s,
        fault_end_s=spec.fault_end_s,
        scenario_hash=spec.scenario_hash,
        exogenous_hashes=spec.stream_hashes,
        config_hash=config_hash,
        policy_hash=policy.model_identity,
    )
    return episode, trace


def run_block(
    study: Experiment003Config,
    production,
    spec: Experiment003Scenario,
    policy: FrozenPolicy,
    config_hash: str,
) -> list[Experiment003Episode]:
    streams, hashes = materialize_exogenous(
        study,
        production,
        spec.stratum_id,
        spec.replicate,
        partition_code=study.pilot_partition_code,
    )
    for name, value in hashes.items():
        if spec.stream_hashes.get(name) != value:
            raise RuntimeError(f"exogenous hash drift for {spec.root_seed_id}/{name}")
    rows = []
    for run_order, arm in enumerate(spec.arm_run_order, start=1):
        row, _ = run_arm(
            study,
            production,
            spec,
            streams,
            arm,
            run_order,
            policy,
            config_hash,
        )
        rows.append(row)
    return rows


def run_pilot(
    study: Experiment003Config,
    production,
    policy: FrozenPolicy,
    config_hash: str,
    seed_manifest_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    if output.exists() or output.parent.exists():
        raise RuntimeError("refusing pre-existing Experiment 003 result path")
    scenarios = [
        _scenario_from_dict(json.loads(line))
        for line in Path(seed_manifest_path).read_text(encoding="utf-8").splitlines()
    ]
    if len(scenarios) != study.pilot_blocks:
        raise RuntimeError("pilot seed manifest does not contain the planned blocks")
    output.parent.mkdir(parents=True, exist_ok=False)
    started = time.time()
    episodes = 0
    with output.open("x", encoding="utf-8") as handle:
        for scenario in scenarios:
            for row in run_block(study, production, scenario, policy, config_hash):
                handle.write(canonical_json(row.to_dict()).decode() + "\n")
                episodes += 1
            handle.flush()
    if episodes != study.pilot_episodes:
        raise RuntimeError("pilot output does not contain the planned episode cells")
    return {
        "blocks": len(scenarios),
        "episodes": episodes,
        "elapsed_wall_s": time.time() - started,
        "episodes_sha256": sha256_bytes(output.read_bytes()),
    }
