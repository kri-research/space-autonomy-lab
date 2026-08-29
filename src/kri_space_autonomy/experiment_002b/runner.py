from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.config import PILOT_STRATA, PilotConfig
from kri_space_autonomy.experiment_002.dynamics import (
    TruthState,
    actuator_effectiveness,
    propagate_exact,
)
from kri_space_autonomy.experiment_002.evaluator import (
    IndependentEvaluator,
)
from kri_space_autonomy.experiment_002.monitor import RuntimeGate
from kri_space_autonomy.experiment_002.policy import (
    FrozenPolicy,
    ReferenceController,
    SensorObservation,
)
from kri_space_autonomy.experiment_002.seeds import (
    ExogenousStreams,
    ScenarioSpec,
    canonical_json,
    sha256_bytes,
)

from .config import AmendmentConfig
from .seeds import materialize_exogenous_002b, materialize_scenario_002b


@dataclass(frozen=True)
class SensorPacket:
    packet_id: str
    channel: str
    sample_tick: int
    sample_time_s: float
    observation: SensorObservation
    fault_active: bool
    fault_affects_channel: bool


@dataclass(frozen=True)
class RateEpisodeResult:
    schema_version: str
    study_component: str
    episode_id: str
    root_seed_id: str
    stratum_id: str
    fault_subtype: str
    replicate: int
    arm: str
    command_period_s: float
    observation_period_s: float
    exogenous_period_s: float
    initial_propellant: float
    final_propellant: float
    propellant_used_fraction: float
    minimum_range_m: float
    minimum_braking_margin_m: float | None
    collision: bool
    physical_hazard_observed: bool
    analysis_hazard: bool
    sustained_success: bool
    propellant_depleted: bool
    failure_class: str | None
    command_decisions: int
    primary_sensor_packets: int
    monitor_sensor_packets: int
    gate_reason_counts: dict[str, int]
    handover_entries: int
    fallback_duty_cycle: float
    fault_onset_s: float | None
    fault_end_s: float | None
    first_primary_sample_on_or_after_fault_s: float | None
    first_monitor_sample_on_or_after_fault_s: float | None
    first_model_response_s: float | None
    first_command_on_or_after_fault_s: float | None
    first_override_on_or_after_fault_s: float | None
    first_executed_command_change_on_or_after_fault_s: float | None
    command_trace_sha256: str
    scenario_hash: str
    exogenous_hashes: dict[str, str]
    policy_hash: str
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quantize(value: float, quantum: float) -> float:
    return float(np.rint(value / quantum) * quantum)


def _fault_active(spec: ScenarioSpec, time_s: float) -> bool:
    return (
        spec.fault_onset_s is not None
        and time_s >= spec.fault_onset_s
        and (spec.fault_end_s is None or time_s < spec.fault_end_s)
    )


def _packet(
    channel: str,
    time_s: float,
    tick: int,
    history: list[TruthState],
    streams: ExogenousStreams,
    spec: ScenarioSpec,
    config: PilotConfig,
) -> SensorPacket:
    if channel == "primary":
        range_noise = streams.primary_range_noise_m[tick]
        velocity_noise = streams.primary_velocity_noise_mps[tick]
        latency_s = streams.primary_latency_s[tick]
    elif channel == "monitor":
        range_noise = streams.monitor_range_noise_m[tick]
        velocity_noise = streams.monitor_velocity_noise_mps[tick]
        latency_s = streams.monitor_latency_s[tick]
    else:
        raise ValueError("sensor channel must be primary or monitor")
    latency_ticks = round(float(latency_s) / config.exogenous_period_s)
    latent = history[max(0, tick - latency_ticks)]
    range_m: float | None = _quantize(
        latent.range_m + float(range_noise), config.range_quantization_m
    )
    velocity: float | None = _quantize(
        latent.relative_velocity_mps + float(velocity_noise),
        config.velocity_quantization_mps,
    )
    active = _fault_active(spec, time_s)
    affects = spec.fault_channel == channel or spec.fault_channel == "shared"
    quality = 1.0
    if active and affects and spec.fault_subtype == "range_bias":
        range_m += float(spec.range_bias_m)
        quality = 0.85
    elif active and affects and spec.fault_subtype == "dropout":
        range_m = None
        velocity = None
        quality = 0.0
    observation = SensorObservation(time_s, range_m, velocity, history[tick].propellant, quality)
    return SensorPacket(
        packet_id=f"{spec.root_seed_id}:{channel}:{tick:04d}",
        channel=channel,
        sample_tick=tick,
        sample_time_s=time_s,
        observation=observation,
        fault_active=active,
        fault_affects_channel=affects,
    )


def _split_interval(
    start_s: float, end_s: float, spec: ScenarioSpec
) -> list[tuple[float, float]]:
    points = [start_s, end_s]
    if spec.fault_subtype == "actuator_degradation":
        for boundary in (spec.fault_onset_s, spec.fault_end_s):
            if boundary is not None and start_s < boundary < end_s:
                points.append(boundary)
    points.sort()
    return list(zip(points, points[1:], strict=False))


def run_pd_episode(
    amendment: AmendmentConfig,
    production: PilotConfig,
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    policy: FrozenPolicy,
    command_period_s: float,
    observation_period_s: float,
    config_hash: str,
    study_component: str,
    event_sink: Callable[[dict[str, Any]], None] | None = None,
    collect_command_trace: bool = False,
) -> tuple[RateEpisodeResult, list[tuple[float, float]] | None]:
    if command_period_s not in amendment.diagnostic_command_periods_s:
        raise ValueError("command period is outside the frozen 002b grid")
    if observation_period_s not in amendment.diagnostic_observation_periods_s:
        raise ValueError("observation period is outside the frozen 002b grid")
    runtime_config = replace(production, command_period_s=command_period_s)
    command_stride = round(command_period_s / production.exogenous_period_s)
    observation_stride = round(observation_period_s / production.exogenous_period_s)
    evaluator_stride = round(production.evaluator_period_s / production.exogenous_period_s)
    if min(command_stride, observation_stride, evaluator_stride) <= 0:
        raise ValueError("invalid timing stride")

    working_policy = FrozenPolicy(policy.weights, runtime_config)
    reference = ReferenceController(runtime_config)
    gate = RuntimeGate(runtime_config, reference, working_policy.model_identity)
    state = TruthState(
        0.0,
        spec.initial_range_m,
        spec.initial_velocity_mps,
        spec.initial_propellant,
        0.0,
    )
    history = [state]
    evaluator = IndependentEvaluator(runtime_config, state, 1.0)
    command = 0.0
    previous_command = 0.0
    previous_overridden = False
    overridden = False
    model_upset_applied = False
    failure_class: str | None = None
    fallback_time_s = 0.0
    handover_entries = 0
    gate_reasons: Counter[str] = Counter()
    primary_packet: SensorPacket | None = None
    monitor_packet: SensorPacket | None = None
    primary_packets = 0
    monitor_packets = 0
    command_decisions = 0
    first_primary_sample: float | None = None
    first_monitor_sample: float | None = None
    first_model_response: float | None = None
    first_command_after_fault: float | None = None
    first_override_after_fault: float | None = None
    first_change_after_fault: float | None = None
    trace_digest = hashlib.sha256()
    command_trace: list[tuple[float, float]] | None = [] if collect_command_trace else None
    episode_id = (
        f"{spec.root_seed_id}:c{command_period_s:g}:o{observation_period_s:g}"
    )

    for tick in range(production.n_exogenous_steps):
        time_s = tick * production.exogenous_period_s
        if tick % observation_stride == 0:
            primary_packet = _packet(
                "primary", time_s, tick, history, streams, spec, runtime_config
            )
            monitor_packet = _packet(
                "monitor", time_s, tick, history, streams, spec, runtime_config
            )
            primary_packets += 1
            monitor_packets += 1
            if spec.fault_onset_s is not None and time_s + 1e-12 >= spec.fault_onset_s:
                if first_primary_sample is None:
                    first_primary_sample = time_s
                if first_monitor_sample is None:
                    first_monitor_sample = time_s

        if tick % command_stride == 0:
            if primary_packet is None or monitor_packet is None:
                raise RuntimeError("command update occurred before the first sensor packet")
            if (
                spec.fault_subtype == "persistent_model_upset"
                and not model_upset_applied
                and spec.fault_onset_s is not None
                and time_s + 1e-12 >= spec.fault_onset_s
            ):
                working_policy = working_policy.corrupted_copy(
                    int(spec.model_weight_index), float(spec.model_normalized_magnitude)
                )
                model_upset_applied = True
                first_model_response = time_s
            decision = working_policy.decide(primary_packet.observation)
            gate_decision = gate.gate(monitor_packet.observation, decision)
            command = gate_decision.executed_acceleration_mps2
            overridden = gate_decision.overridden
            if not math.isfinite(command):
                failure_class = "INVALID_ACTION"
                command = 0.0
            reason = gate_decision.reason or "NONE"
            gate_reasons[reason] += 1
            command_decisions += 1
            if overridden and not previous_overridden:
                handover_entries += 1
            if spec.fault_onset_s is not None and time_s + 1e-12 >= spec.fault_onset_s:
                if first_command_after_fault is None:
                    first_command_after_fault = time_s
                if overridden and first_override_after_fault is None:
                    first_override_after_fault = time_s
                if abs(command - previous_command) > 1e-15 and first_change_after_fault is None:
                    first_change_after_fault = time_s
            previous_overridden = overridden
            previous_command = command
            event = {
                "schema_version": amendment.schema_version,
                "episode_id": episode_id,
                "command_index": command_decisions - 1,
                "decision_time_s": time_s,
                "command_period_s": command_period_s,
                "observation_period_s": observation_period_s,
                "proposed_acceleration_mps2": gate_decision.proposed_acceleration_mps2,
                "executed_acceleration_mps2": command,
                "overridden": overridden,
                "gate_reason": reason,
                "primary_packet_id": primary_packet.packet_id,
                "primary_sample_time_s": primary_packet.sample_time_s,
                "primary_packet_age_s": time_s - primary_packet.sample_time_s,
                "primary_range_m": primary_packet.observation.range_m,
                "primary_velocity_mps": primary_packet.observation.relative_velocity_mps,
                "primary_quality": primary_packet.observation.sensor_quality,
                "monitor_packet_id": monitor_packet.packet_id,
                "monitor_sample_time_s": monitor_packet.sample_time_s,
                "monitor_packet_age_s": time_s - monitor_packet.sample_time_s,
                "monitor_range_m": monitor_packet.observation.range_m,
                "monitor_velocity_mps": monitor_packet.observation.relative_velocity_mps,
                "monitor_quality": monitor_packet.observation.sensor_quality,
                "fault_active": _fault_active(spec, time_s),
                "model_upset_applied": model_upset_applied,
            }
            event_bytes = canonical_json(event)
            trace_digest.update(event_bytes + b"\n")
            if event_sink is not None:
                event_sink(event)
            if command_trace is not None:
                command_trace.append((time_s, command))

        interval_start = time_s
        interval_end = time_s + production.exogenous_period_s
        for segment_start, segment_end in _split_interval(interval_start, interval_end, spec):
            effectiveness = (
                actuator_effectiveness(
                    0.5 * (segment_start + segment_end),
                    spec.fault_onset_s,
                    spec.fault_end_s,
                    spec.actuator_effectiveness,
                )
                if spec.fault_subtype == "actuator_degradation"
                else 1.0
            )
            start_state = state
            try:
                propagation = propagate_exact(
                    state,
                    command,
                    effectiveness,
                    float(streams.process_acceleration_mps2[tick]),
                    segment_end - segment_start,
                    runtime_config,
                )
            except (ArithmeticError, ValueError, OverflowError):
                failure_class = "NUMERICAL_FAILURE"
                break
            evaluator.observe_interval(start_state, propagation)
            state = propagation.state
            if propagation.collision_time_s is not None:
                break
        if failure_class == "NUMERICAL_FAILURE":
            break
        fallback_time_s += production.exogenous_period_s * float(overridden)
        history.append(state)
        if (tick + 1) % evaluator_stride == 0:
            effectiveness = (
                actuator_effectiveness(
                    state.time_s,
                    spec.fault_onset_s,
                    spec.fault_end_s,
                    spec.actuator_effectiveness,
                )
                if spec.fault_subtype == "actuator_degradation"
                else 1.0
            )
            evaluator.observe_margin(state, effectiveness)
        if evaluator.collision:
            break

    summary = evaluator.finalize(state)
    analysis_hazard = (
        summary.physical_hazard_observed
        or summary.propellant_depleted
        or failure_class is not None
    )
    elapsed = state.time_s
    result = RateEpisodeResult(
        schema_version=amendment.schema_version,
        study_component=study_component,
        episode_id=episode_id,
        root_seed_id=spec.root_seed_id,
        stratum_id=spec.stratum_id,
        fault_subtype=spec.fault_subtype,
        replicate=spec.replicate,
        arm="PD",
        command_period_s=command_period_s,
        observation_period_s=observation_period_s,
        exogenous_period_s=production.exogenous_period_s,
        initial_propellant=spec.initial_propellant,
        final_propellant=state.propellant,
        propellant_used_fraction=spec.initial_propellant - state.propellant,
        minimum_range_m=summary.minimum_range_m,
        minimum_braking_margin_m=summary.minimum_braking_margin_m,
        collision=summary.collision,
        physical_hazard_observed=summary.physical_hazard_observed,
        analysis_hazard=analysis_hazard,
        sustained_success=summary.sustained_success and not analysis_hazard,
        propellant_depleted=summary.propellant_depleted,
        failure_class=failure_class,
        command_decisions=command_decisions,
        primary_sensor_packets=primary_packets,
        monitor_sensor_packets=monitor_packets,
        gate_reason_counts=dict(sorted(gate_reasons.items())),
        handover_entries=handover_entries,
        fallback_duty_cycle=fallback_time_s / elapsed if elapsed > 0.0 else 0.0,
        fault_onset_s=spec.fault_onset_s,
        fault_end_s=spec.fault_end_s,
        first_primary_sample_on_or_after_fault_s=first_primary_sample,
        first_monitor_sample_on_or_after_fault_s=first_monitor_sample,
        first_model_response_s=first_model_response,
        first_command_on_or_after_fault_s=first_command_after_fault,
        first_override_on_or_after_fault_s=first_override_after_fault,
        first_executed_command_change_on_or_after_fault_s=first_change_after_fault,
        command_trace_sha256=trace_digest.hexdigest(),
        scenario_hash=spec.scenario_hash,
        exogenous_hashes=spec.stream_hashes,
        policy_hash=policy.model_identity,
        config_hash=config_hash,
    )
    return result, command_trace


def _materialize_case(
    amendment: AmendmentConfig,
    production: PilotConfig,
    partition: str,
    stratum: str,
    replicate: int,
) -> tuple[ScenarioSpec, ExogenousStreams]:
    spec = materialize_scenario_002b(amendment, production, partition, stratum, replicate)
    streams, hashes = materialize_exogenous_002b(
        amendment, production, partition, stratum, replicate
    )
    for name, digest in hashes.items():
        if spec.stream_hashes[name] != digest:
            raise RuntimeError(f"exogenous hash drift for {spec.root_seed_id}/{name}")
    return spec, streams


def run_operational_validation(
    amendment: AmendmentConfig,
    production: PilotConfig,
    policy: FrozenPolicy,
    config_hash: str,
    output_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    count = 0
    with output.open("w", encoding="utf-8") as handle:
        for stratum in PILOT_STRATA:
            for replicate in range(amendment.operational_seeds_per_stratum):
                spec, streams = _materialize_case(
                    amendment, production, "operational", stratum, replicate
                )
                result, _ = run_pd_episode(
                    amendment,
                    production,
                    spec,
                    streams,
                    policy,
                    amendment.operational_command_period_s,
                    amendment.operational_observation_period_s,
                    config_hash,
                    "operational_validation",
                )
                handle.write(canonical_json(result.to_dict()).decode() + "\n")
                handle.flush()
                count += 1
    if count != amendment.operational_blocks:
        raise RuntimeError("operational output does not contain the frozen episode count")
    return {
        "episodes": count,
        "elapsed_wall_s": time.time() - started,
        "sha256": sha256_bytes(output.read_bytes()),
    }


def run_rate_decomposition(
    amendment: AmendmentConfig,
    production: PilotConfig,
    policy: FrozenPolicy,
    config_hash: str,
    episodes_path: str | Path,
    events_path: str | Path,
) -> dict[str, Any]:
    episodes = Path(episodes_path)
    events = Path(events_path)
    episodes.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    episode_count = 0
    event_count = 0
    with episodes.open("w", encoding="utf-8") as episode_handle:
        with events.open("wb") as raw_handle:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_handle, mtime=0
            ) as gzip_handle:
                with io.TextIOWrapper(gzip_handle, encoding="utf-8") as event_handle:

                    def sink(event: dict[str, Any]) -> None:
                        nonlocal event_count
                        event_handle.write(canonical_json(event).decode() + "\n")
                        event_count += 1

                    for stratum in PILOT_STRATA:
                        for replicate in range(amendment.rate_seeds_per_stratum):
                            spec, streams = _materialize_case(
                                amendment,
                                production,
                                "rate_decomposition",
                                stratum,
                                replicate,
                            )
                            for command_period in amendment.diagnostic_command_periods_s:
                                for observation_period in (
                                    amendment.diagnostic_observation_periods_s
                                ):
                                    result, _ = run_pd_episode(
                                        amendment,
                                        production,
                                        spec,
                                        streams,
                                        policy,
                                        command_period,
                                        observation_period,
                                        config_hash,
                                        "rate_decomposition",
                                        event_sink=sink,
                                    )
                                    episode_handle.write(
                                        canonical_json(result.to_dict()).decode() + "\n"
                                    )
                                    episode_handle.flush()
                                    episode_count += 1
    if episode_count != amendment.rate_episodes:
        raise RuntimeError("rate output does not contain the frozen episode count")
    return {
        "episodes": episode_count,
        "command_events": event_count,
        "elapsed_wall_s": time.time() - started,
        "episodes_sha256": sha256_bytes(episodes.read_bytes()),
        "events_gzip_sha256": sha256_bytes(events.read_bytes()),
    }


def load_scenario_from_manifest(path: str | Path, stratum: str, replicate: int) -> ScenarioSpec:
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["stratum_id"] == stratum and int(row["replicate"]) == replicate:
            fields = {
                key: row[key]
                for key in ScenarioSpec.__dataclass_fields__
            }
            fields["arm_run_order"] = tuple(fields["arm_run_order"])
            return ScenarioSpec(**fields)
    raise KeyError((stratum, replicate))
