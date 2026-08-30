from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_002.config import PilotConfig
from kri_space_autonomy.experiment_002.dynamics import TruthState, propagate_exact
from kri_space_autonomy.experiment_002.evaluator import IndependentEvaluator
from kri_space_autonomy.experiment_002.monitor import RuntimeGate
from kri_space_autonomy.experiment_002.policy import (
    FrozenPolicy,
    ReferenceController,
    SensorObservation,
)
from kri_space_autonomy.experiment_002.seeds import (
    ExogenousStreams,
    canonical_json,
    sha256_bytes,
)

from .config import CombinedInformationConfig
from .seeds import (
    CombinedScenarioSpec,
    materialize_exogenous_002d,
    materialize_scenario_002d,
)


@dataclass(frozen=True)
class InformationEpisodeResult:
    schema_version: str
    study_phase: str
    stratum_id: str
    fault_subtype: str
    root_seed_id: str
    replicate: int
    arm: str
    run_order: int
    elapsed_time_s: float
    failure_class: str | None
    physical_hazard_observed: bool
    analysis_hazard: bool
    collision: bool
    sustained_success: bool
    propellant_depleted: bool
    braking_unreachable: bool
    minimum_braking_margin_m: float | None
    minimum_range_m: float
    maximum_contiguous_negative_margin_s: float
    fallback_duty_cycle: float
    propellant_used_fraction: float
    goal_dwell_final60_fraction: float
    dropout_onset_s: float
    dropout_end_s: float
    actuator_onset_gap_s: float
    actuator_onset_s: float
    actuator_end_s: float
    actuator_effectiveness: float
    study_config_hash: str
    production_config_hash: str
    policy_hash: str
    scenario_hash: str
    exogenous_hashes: dict[str, str]
    controller_command_period_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quantize(value: float, quantum: float) -> float:
    return float(np.rint(value / quantum) * quantum)


def _primary_dropout_active(spec: CombinedScenarioSpec, time_s: float) -> bool:
    return spec.dropout_onset_s <= time_s < spec.dropout_end_s


def _actuator_effectiveness(spec: CombinedScenarioSpec, time_s: float) -> float:
    if spec.actuator_onset_s <= time_s < spec.actuator_end_s:
        return spec.actuator_effectiveness
    return 1.0


def _sensor_observation(
    channel: str,
    time_s: float,
    tick: int,
    history: list[TruthState],
    streams: ExogenousStreams,
    spec: CombinedScenarioSpec,
    production: PilotConfig,
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
    latency_ticks = round(float(latency_s) / production.exogenous_period_s)
    latent = history[max(0, tick - latency_ticks)]
    range_m: float | None = _quantize(
        latent.range_m + float(range_noise), production.range_quantization_m
    )
    velocity: float | None = _quantize(
        latent.relative_velocity_mps + float(velocity_noise),
        production.velocity_quantization_mps,
    )
    quality = 1.0
    if channel == "primary" and _primary_dropout_active(spec, time_s):
        range_m = None
        velocity = None
        quality = 0.0
    return SensorObservation(time_s, range_m, velocity, history[tick].propellant, quality)


def _split_interval(
    start_s: float,
    end_s: float,
    spec: CombinedScenarioSpec,
) -> list[tuple[float, float]]:
    points = [start_s, end_s]
    for boundary in (spec.actuator_onset_s, spec.actuator_end_s):
        if start_s < boundary < end_s:
            points.append(boundary)
    points.sort()
    return list(zip(points, points[1:], strict=False))


def run_information_arm(
    spec: CombinedScenarioSpec,
    streams: ExogenousStreams,
    arm: str,
    run_order: int,
    policy: FrozenPolicy,
    production: PilotConfig,
    study_config_hash: str,
    production_config_hash: str,
) -> InformationEpisodeResult:
    if arm not in {"D", "PD"}:
        raise ValueError("Experiment 002d runs only D and PD")
    reference = ReferenceController(production)
    working_policy = FrozenPolicy(policy.weights, production)
    gate = RuntimeGate(production, reference, working_policy.model_identity)
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
    overridden = False
    fallback_time_s = 0.0
    invalid_action = False
    numerical_failure = False
    command_stride = round(production.command_period_s / production.exogenous_period_s)
    evaluator_stride = round(production.evaluator_period_s / production.exogenous_period_s)

    for tick in range(production.n_exogenous_steps):
        time_s = tick * production.exogenous_period_s
        if tick % command_stride == 0:
            primary = _sensor_observation(
                "primary", time_s, tick, history, streams, spec, production
            )
            decision = working_policy.decide(primary)
            if arm == "D":
                command = decision.commanded_acceleration_mps2
                overridden = False
            else:
                monitor = _sensor_observation(
                    "monitor", time_s, tick, history, streams, spec, production
                )
                gate_decision = gate.gate(monitor, decision)
                command = gate_decision.executed_acceleration_mps2
                overridden = gate_decision.overridden
            if not math.isfinite(command):
                invalid_action = True
                command = 0.0

        interval_start = time_s
        interval_end = time_s + production.exogenous_period_s
        for segment_start, segment_end in _split_interval(
            interval_start, interval_end, spec
        ):
            effectiveness = _actuator_effectiveness(
                spec, 0.5 * (segment_start + segment_end)
            )
            start_state = state
            try:
                propagation = propagate_exact(
                    state,
                    command,
                    effectiveness,
                    float(streams.process_acceleration_mps2[tick]),
                    segment_end - segment_start,
                    production,
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
        fallback_time_s += production.exogenous_period_s * float(overridden)
        history.append(state)
        if (tick + 1) % evaluator_stride == 0:
            evaluator.observe_margin(state, _actuator_effectiveness(spec, state.time_s))
        if evaluator.collision:
            break

    summary = evaluator.finalize(state)
    failure_class: str | None = None
    if invalid_action:
        failure_class = "INVALID_ACTION"
    elif numerical_failure:
        failure_class = "NUMERICAL_FAILURE"
    analysis_hazard = bool(
        summary.physical_hazard_observed
        or summary.propellant_depleted
        or failure_class is not None
    )
    sustained_success = bool(summary.sustained_success and not analysis_hazard)
    elapsed = state.time_s
    return InformationEpisodeResult(
        schema_version=spec.schema_version,
        study_phase="combined_fault_information",
        stratum_id=spec.stratum_id,
        fault_subtype=spec.fault_subtype,
        root_seed_id=spec.root_seed_id,
        replicate=spec.replicate,
        arm=arm,
        run_order=run_order,
        elapsed_time_s=elapsed,
        failure_class=failure_class,
        physical_hazard_observed=summary.physical_hazard_observed,
        analysis_hazard=analysis_hazard,
        collision=summary.collision,
        sustained_success=sustained_success,
        propellant_depleted=summary.propellant_depleted,
        braking_unreachable=summary.braking_unreachable,
        minimum_braking_margin_m=summary.minimum_braking_margin_m,
        minimum_range_m=summary.minimum_range_m,
        maximum_contiguous_negative_margin_s=(
            summary.maximum_contiguous_negative_margin_s
        ),
        fallback_duty_cycle=fallback_time_s / elapsed if elapsed > 0.0 else 0.0,
        propellant_used_fraction=spec.initial_propellant - state.propellant,
        goal_dwell_final60_fraction=summary.goal_dwell_final60_fraction,
        dropout_onset_s=spec.dropout_onset_s,
        dropout_end_s=spec.dropout_end_s,
        actuator_onset_gap_s=spec.actuator_onset_gap_s,
        actuator_onset_s=spec.actuator_onset_s,
        actuator_end_s=spec.actuator_end_s,
        actuator_effectiveness=spec.actuator_effectiveness,
        study_config_hash=study_config_hash,
        production_config_hash=production_config_hash,
        policy_hash=policy.model_identity,
        scenario_hash=spec.scenario_hash,
        exogenous_hashes=spec.stream_hashes,
        controller_command_period_s=production.command_period_s,
    )


def run_information_block(
    study: CombinedInformationConfig,
    production: PilotConfig,
    replicate: int,
    policy: FrozenPolicy,
    study_config_hash: str,
    production_config_hash: str,
) -> list[InformationEpisodeResult]:
    spec = materialize_scenario_002d(study, production, replicate)
    streams, stream_hashes = materialize_exogenous_002d(study, production, replicate)
    for name, digest in stream_hashes.items():
        if spec.stream_hashes[name] != digest:
            raise RuntimeError(f"exogenous hash drift for {spec.root_seed_id}/{name}")
    rows = []
    for run_order, arm in enumerate(spec.arm_run_order, start=1):
        rows.append(
            run_information_arm(
                spec,
                streams,
                arm,
                run_order,
                policy,
                production,
                study_config_hash,
                production_config_hash,
            )
        )
    return rows


def run_information_study(
    study: CombinedInformationConfig,
    production: PilotConfig,
    policy: FrozenPolicy,
    study_config_hash: str,
    production_config_hash: str,
    output_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    block_count = 0
    episode_count = 0
    with output.open("w", encoding="utf-8") as handle:
        for replicate in range(study.information_seeds):
            rows = run_information_block(
                study,
                production,
                replicate,
                policy,
                study_config_hash,
                production_config_hash,
            )
            for row in rows:
                handle.write(canonical_json(row.to_dict()).decode() + "\n")
                episode_count += 1
            handle.flush()
            block_count += 1
    if block_count != study.planned_blocks or episode_count != study.planned_episodes:
        raise RuntimeError("002d output does not contain the frozen expected cells")
    return {
        "blocks": block_count,
        "episodes": episode_count,
        "elapsed_wall_s": time.monotonic() - started,
        "episodes_sha256": sha256_bytes(output.read_bytes()),
    }


def load_information_rows(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
