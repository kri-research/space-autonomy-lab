from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from .config import ARMS, PILOT_STRATA, PilotConfig
from .dynamics import TruthState, actuator_effectiveness, propagate_exact
from .evaluator import (
    IndependentEvaluator,
    RecoveryCorridor,
    classify_recovery,
)
from .monitor import RuntimeGate
from .policy import FrozenPolicy, ReferenceController, SensorObservation
from .seeds import (
    ExogenousStreams,
    ScenarioSpec,
    canonical_json,
    materialize_exogenous,
    materialize_partition_case,
    materialize_scenario,
    sha256_bytes,
)


@dataclass(frozen=True)
class EpisodeResult:
    schema_version: str
    study_phase: str
    stratum_id: str
    fault_subtype: str
    root_seed_id: str
    replicate: int
    arm: str
    run_order: int
    elapsed_time_s: float
    attempt_id: int
    attempt_status: str
    failure_class: str | None
    physical_hazard_observed: bool
    analysis_hazard: bool
    collision: bool
    sustained_success: bool
    propellant_depleted: bool
    braking_unreachable: bool
    recovery_state: str
    recovery_favorable_180: bool | None
    restricted_time_unrecovered_s_180: float | None
    minimum_braking_margin_m: float | None
    minimum_range_m: float
    maximum_contiguous_negative_margin_s: float
    handover_entries: int
    fallback_duty_cycle: float
    propellant_used_fraction: float
    goal_dwell_final60_fraction: float
    first_goal_entry_s: float | None
    fault_onset_s: float | None
    fault_end_s: float | None
    corridor_first_exit_s: float | None
    qualifying_reentry_start_s: float | None
    config_hash: str
    policy_hash: str
    scenario_hash: str
    exogenous_hashes: dict[str, str]
    controller_command_period_s: float

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


def _sensor_observation(
    channel: str,
    time_s: float,
    tick: int,
    history: list[TruthState],
    streams: ExogenousStreams,
    spec: ScenarioSpec,
    config: PilotConfig,
) -> SensorObservation:
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
    latency_ticks = round(latency_s / config.exogenous_period_s)
    latent = history[max(0, tick - latency_ticks)]
    range_m = _quantize(latent.range_m + float(range_noise), config.range_quantization_m)
    velocity = _quantize(
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
    return SensorObservation(time_s, range_m, velocity, history[tick].propellant, quality)


def _split_interval(start_s: float, end_s: float, spec: ScenarioSpec) -> list[tuple[float, float]]:
    points = [start_s, end_s]
    if spec.fault_subtype == "actuator_degradation":
        for boundary in (spec.fault_onset_s, spec.fault_end_s):
            if boundary is not None and start_s < boundary < end_s:
                points.append(boundary)
    points.sort()
    return list(zip(points, points[1:], strict=False))


def run_arm(
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    arm: str,
    run_order: int,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    config: PilotConfig,
    config_hash: str,
    command_period_s: float | None = None,
    collect_trace: bool = False,
) -> tuple[EpisodeResult, list[TruthState] | None]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm}")
    period = command_period_s or config.command_period_s
    if period not in {1.0, 0.5, 0.25}:
        raise ValueError("command period must be one of the prespecified sensitivity values")
    runtime_config = replace(config, command_period_s=period)
    reference = ReferenceController(runtime_config)
    working_policy = FrozenPolicy(policy.weights, runtime_config)
    expected_identity = working_policy.model_identity
    gate = RuntimeGate(runtime_config, reference, expected_identity)
    state = TruthState(
        0.0,
        spec.initial_range_m,
        spec.initial_velocity_mps,
        spec.initial_propellant,
        0.0,
    )
    history = [state]
    trace = [state] if collect_trace else None
    evaluator = IndependentEvaluator(runtime_config, state, 1.0)
    corridor_samples = [(0.0, corridor.contains(state))]
    command = 0.0
    overridden = False
    previous_overridden = False
    fallback_time_s = 0.0
    handover_entries = 0
    model_upset_applied = False
    numerical_failure = False
    invalid_action = False
    command_stride = round(period / config.exogenous_period_s)
    evaluator_stride = round(config.evaluator_period_s / config.exogenous_period_s)

    for tick in range(config.n_exogenous_steps):
        time_s = tick * config.exogenous_period_s
        if tick % command_stride == 0:
            primary = _sensor_observation(
                "primary", time_s, tick, history, streams, spec, runtime_config
            )
            monitor = _sensor_observation(
                "monitor", time_s, tick, history, streams, spec, runtime_config
            )
            if (
                spec.fault_subtype == "persistent_model_upset"
                and not model_upset_applied
                and spec.fault_onset_s is not None
                and time_s >= spec.fault_onset_s
                and arm in {"D", "PS", "PD"}
            ):
                working_policy = working_policy.corrupted_copy(
                    int(spec.model_weight_index), float(spec.model_normalized_magnitude)
                )
                model_upset_applied = True
            if arm == "R":
                decision = reference.decide(primary)
                command = decision.commanded_acceleration_mps2
                overridden = False
            else:
                decision = working_policy.decide(primary)
                if arm == "D":
                    command = decision.commanded_acceleration_mps2
                    overridden = False
                else:
                    gate_observation = primary if arm == "PS" else monitor
                    gate_decision = gate.gate(gate_observation, decision)
                    command = gate_decision.executed_acceleration_mps2
                    overridden = gate_decision.overridden
            if not math.isfinite(command):
                invalid_action = True
                command = 0.0
            if overridden and not previous_overridden:
                handover_entries += 1
            previous_overridden = overridden

        interval_start = time_s
        interval_end = time_s + config.exogenous_period_s
        for segment_start, segment_end in _split_interval(interval_start, interval_end, spec):
            if spec.fault_subtype == "actuator_degradation":
                effectiveness = actuator_effectiveness(
                    0.5 * (segment_start + segment_end),
                    spec.fault_onset_s,
                    spec.fault_end_s,
                    spec.actuator_effectiveness,
                )
            else:
                effectiveness = 1.0
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
                numerical_failure = True
                break
            evaluator.observe_interval(start_state, propagation)
            state = propagation.state
            if propagation.collision_time_s is not None:
                break
        if numerical_failure:
            break
        fallback_time_s += config.exogenous_period_s * float(overridden)
        history.append(state)
        if trace is not None:
            trace.append(state)
        if state.time_s + 1e-12 >= (len(corridor_samples)) * config.evaluator_period_s:
            corridor_samples.append((state.time_s, corridor.contains(state)))
        if (tick + 1) % evaluator_stride == 0:
            current_effectiveness = (
                actuator_effectiveness(
                    state.time_s,
                    spec.fault_onset_s,
                    spec.fault_end_s,
                    spec.actuator_effectiveness,
                )
                if spec.fault_subtype == "actuator_degradation"
                else 1.0
            )
            evaluator.observe_margin(state, current_effectiveness)
        if evaluator.collision:
            break

    summary = evaluator.finalize(state)
    failure_class: str | None = None
    if invalid_action:
        failure_class = "INVALID_ACTION"
    elif numerical_failure:
        failure_class = "NUMERICAL_FAILURE"
    analysis_hazard = (
        summary.physical_hazard_observed or summary.propellant_depleted or failure_class is not None
    )
    sustained_success = summary.sustained_success and not analysis_hazard
    failed_recovery = analysis_hazard or failure_class is not None
    recovery = classify_recovery(
        corridor_samples,
        spec.fault_onset_s,
        spec.fault_end_s,
        failed_recovery,
        sustained_success,
        spec.fault_subtype == "persistent_model_upset",
        gate.integrity_latched,
        arm,
        runtime_config,
    )
    elapsed = state.time_s
    result = EpisodeResult(
        schema_version=config.schema_version,
        study_phase="pilot",
        stratum_id=spec.stratum_id,
        fault_subtype=spec.fault_subtype,
        root_seed_id=spec.root_seed_id,
        replicate=spec.replicate,
        arm=arm,
        run_order=run_order,
        elapsed_time_s=elapsed,
        attempt_id=1,
        attempt_status="valid" if failure_class is None else "adverse_valid",
        failure_class=failure_class,
        physical_hazard_observed=summary.physical_hazard_observed,
        analysis_hazard=analysis_hazard,
        collision=summary.collision,
        sustained_success=sustained_success,
        propellant_depleted=summary.propellant_depleted,
        braking_unreachable=summary.braking_unreachable,
        recovery_state=recovery["recovery_state"],
        recovery_favorable_180=recovery["recovery_favorable_180"],
        restricted_time_unrecovered_s_180=recovery["restricted_time_unrecovered_s_180"],
        minimum_braking_margin_m=summary.minimum_braking_margin_m,
        minimum_range_m=summary.minimum_range_m,
        maximum_contiguous_negative_margin_s=summary.maximum_contiguous_negative_margin_s,
        handover_entries=handover_entries,
        fallback_duty_cycle=fallback_time_s / elapsed if elapsed > 0.0 else 0.0,
        propellant_used_fraction=spec.initial_propellant - state.propellant,
        goal_dwell_final60_fraction=summary.goal_dwell_final60_fraction,
        first_goal_entry_s=summary.first_goal_entry_s,
        fault_onset_s=spec.fault_onset_s,
        fault_end_s=spec.fault_end_s,
        corridor_first_exit_s=recovery["corridor_first_exit_s"],
        qualifying_reentry_start_s=recovery["qualifying_reentry_start_s"],
        config_hash=config_hash,
        policy_hash=policy.model_identity,
        scenario_hash=spec.scenario_hash,
        exogenous_hashes=spec.stream_hashes,
        controller_command_period_s=period,
    )
    return result, trace


def run_block(
    config: PilotConfig,
    stratum: str,
    replicate: int,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    config_hash: str,
    command_period_s: float | None = None,
) -> list[EpisodeResult]:
    spec = materialize_scenario(config, stratum, replicate)
    streams, stream_hashes = materialize_exogenous(config, stratum, replicate)
    for name, digest in stream_hashes.items():
        if spec.stream_hashes[name] != digest:
            raise RuntimeError(f"exogenous hash drift for {spec.root_seed_id}/{name}")
    rows = []
    for run_order, arm in enumerate(spec.arm_run_order, start=1):
        row, _ = run_arm(
            spec,
            streams,
            arm,
            run_order,
            policy,
            corridor,
            config,
            config_hash,
            command_period_s,
        )
        rows.append(row)
    return rows


def run_pilot(
    config: PilotConfig,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    config_hash: str,
    output_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    episode_count = 0
    block_count = 0
    with output.open("w", encoding="utf-8") as handle:
        for replicate in range(config.seeds_per_stratum):
            for stratum in PILOT_STRATA:
                rows = run_block(config, stratum, replicate, policy, corridor, config_hash)
                for row in rows:
                    handle.write(canonical_json(row.to_dict()).decode())
                    handle.write("\n")
                    episode_count += 1
                handle.flush()
                block_count += 1
    if block_count != config.planned_blocks or episode_count != config.planned_episodes:
        raise RuntimeError("pilot output did not contain the canonical expected cells")
    return {
        "blocks": block_count,
        "episodes": episode_count,
        "elapsed_wall_s": time.time() - started,
        "episodes_sha256": sha256_bytes(output.read_bytes()),
    }


def calibrate_recovery_corridor(
    config: PilotConfig,
    policy: FrozenPolicy,
    config_hash: str,
    output_path: str | Path,
) -> RecoveryCorridor:
    ranges: list[float] = []
    speeds: list[float] = []
    propellant: list[float] = []
    placeholder = RecoveryCorridor(0.0, 1e9, 1e9, 0.0, "none", "none", "none")
    for index in range(500):
        spec, streams = materialize_partition_case(config, "metric_calibration", index)
        _, trace = run_arm(
            spec,
            streams,
            "R",
            1,
            policy,
            placeholder,
            config,
            config_hash,
            collect_trace=True,
        )
        if trace is None:
            raise RuntimeError("calibration trace was not collected")
        ranges.extend(state.range_m for state in trace)
        speeds.extend(abs(state.relative_velocity_mps) for state in trace)
        propellant.extend(state.propellant for state in trace)
    min_range = max(2.0, math.floor((float(np.quantile(ranges, 0.001)) - 0.25) * 20.0) / 20.0)
    max_range = math.ceil((float(np.quantile(ranges, 0.999)) + 0.25) * 20.0) / 20.0
    max_speed = math.ceil((float(np.quantile(speeds, 0.999)) + 0.02) * 1000.0) / 1000.0
    min_propellant = max(
        config.propellant_reserve,
        math.floor((float(np.quantile(propellant, 0.001)) - 0.01) * 1000.0) / 1000.0,
    )
    fields = {
        "min_range_m": min_range,
        "max_range_m": max_range,
        "max_abs_velocity_mps": max_speed,
        "min_propellant": min_propellant,
        "calibration_partition": "metric_calibration:500 disjoint seeds",
        "calibration_method": (
            "reference-arm truth at 0.25 s; range q0.001/q0.999 expanded by 0.25 m, "
            "absolute-speed q0.999 expanded by 0.02 m/s, propellant q0.001 reduced by "
            "0.01 and floored at reserve; outward deterministic rounding"
        ),
    }
    unsigned = {"schema_version": config.schema_version, **fields}
    digest = sha256_bytes(canonical_json(unsigned))
    corridor = RecoveryCorridor(**fields, calibration_sha256=digest)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": config.schema_version, **asdict(corridor)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return corridor


def load_recovery_corridor(path: str | Path) -> RecoveryCorridor:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    digest = data.pop("calibration_sha256")
    actual = sha256_bytes(canonical_json(data))
    if actual != digest:
        raise ValueError("recovery corridor hash mismatch")
    data.pop("schema_version")
    return RecoveryCorridor(**data, calibration_sha256=digest)
