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
from kri_space_autonomy.experiment_002.evaluator import (
    IndependentEvaluator,
    RecoveryCorridor,
    classify_recovery,
)
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

from .config import CONFIRMATORY_STRATA, ConfirmatoryConfig
from .seeds import (
    ConfirmatoryScenarioSpec,
    materialize_exogenous,
    materialize_scenario,
)


@dataclass(frozen=True)
class ConfirmatoryEpisodeResult:
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
    study_config_hash: str
    production_config_hash: str
    policy_hash: str
    scenario_hash: str
    exogenous_hashes: dict[str, str]
    freeze_id: str
    controller_command_period_s: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _quantize(value: float, quantum: float) -> float:
    return float(np.rint(value / quantum) * quantum)


def _navigation_active(spec: ConfirmatoryScenarioSpec, time_s: float) -> bool:
    return bool(
        spec.navigation_onset_s is not None
        and time_s >= spec.navigation_onset_s
        and (spec.navigation_end_s is None or time_s < spec.navigation_end_s)
    )


def _actuator_effectiveness(spec: ConfirmatoryScenarioSpec, time_s: float) -> float:
    if (
        spec.actuator_onset_s is not None
        and spec.actuator_end_s is not None
        and spec.actuator_onset_s <= time_s < spec.actuator_end_s
    ):
        return float(spec.actuator_effectiveness)
    return 1.0


def _sensor_observation(
    channel: str,
    time_s: float,
    tick: int,
    history: list[TruthState],
    streams: ExogenousStreams,
    spec: ConfirmatoryScenarioSpec,
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
    affects = spec.navigation_channel in {channel, "shared"}
    if _navigation_active(spec, time_s) and affects:
        if spec.navigation_subtype == "range_bias":
            range_m += float(spec.range_bias_m)
            quality = 0.85
        elif spec.navigation_subtype == "dropout":
            range_m = None
            velocity = None
            quality = 0.0
    return SensorObservation(time_s, range_m, velocity, history[tick].propellant, quality)


def _split_interval(
    start_s: float,
    end_s: float,
    spec: ConfirmatoryScenarioSpec,
) -> list[tuple[float, float]]:
    points = [start_s, end_s]
    for boundary in (spec.actuator_onset_s, spec.actuator_end_s):
        if boundary is not None and start_s < boundary < end_s:
            points.append(boundary)
    points.sort()
    return list(zip(points, points[1:], strict=False))


def run_confirmatory_arm(
    spec: ConfirmatoryScenarioSpec,
    streams: ExogenousStreams,
    arm: str,
    run_order: int,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    study: ConfirmatoryConfig,
    production: PilotConfig,
    study_config_hash: str,
    production_config_hash: str,
    freeze_id: str,
) -> ConfirmatoryEpisodeResult:
    if arm not in study.arms:
        raise ValueError(f"unknown arm: {arm}")
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
    corridor_samples = [(0.0, corridor.contains(state))]
    command = 0.0
    overridden = False
    previous_overridden = False
    fallback_time_s = 0.0
    handover_entries = 0
    model_upset_applied = False
    failure_class: str | None = None
    command_stride = round(production.command_period_s / production.exogenous_period_s)
    evaluator_stride = round(production.evaluator_period_s / production.exogenous_period_s)

    for tick in range(production.n_exogenous_steps):
        time_s = tick * production.exogenous_period_s
        if tick % command_stride == 0:
            try:
                primary = _sensor_observation(
                    "primary", time_s, tick, history, streams, spec, production
                )
                monitor = _sensor_observation(
                    "monitor", time_s, tick, history, streams, spec, production
                )
                if (
                    spec.model_onset_s is not None
                    and not model_upset_applied
                    and time_s >= spec.model_onset_s
                    and arm in {"D", "PS", "PD"}
                ):
                    working_policy = working_policy.corrupted_copy(
                        int(spec.model_weight_index),
                        float(spec.model_normalized_magnitude),
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
            except Exception:
                failure_class = "CONTROLLER_FAILURE"
                break
            if not math.isfinite(command):
                failure_class = "INVALID_ACTION"
                break
            if overridden and not previous_overridden:
                handover_entries += 1
            previous_overridden = overridden

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
                failure_class = "NUMERICAL_FAILURE"
                break
            evaluator.observe_interval(start_state, propagation)
            state = propagation.state
            if propagation.collision_time_s is not None:
                break
        if failure_class is not None:
            break
        fallback_time_s += production.exogenous_period_s * float(overridden)
        history.append(state)
        if state.time_s + 1e-12 >= len(corridor_samples) * production.evaluator_period_s:
            corridor_samples.append((state.time_s, corridor.contains(state)))
        if (tick + 1) % evaluator_stride == 0:
            evaluator.observe_margin(state, _actuator_effectiveness(spec, state.time_s))
        if evaluator.collision:
            break

    summary = evaluator.finalize(state)
    analysis_hazard = bool(
        summary.physical_hazard_observed
        or summary.propellant_depleted
        or failure_class is not None
    )
    sustained_success = bool(summary.sustained_success and not analysis_hazard)
    recovery = classify_recovery(
        corridor_samples,
        spec.fault_onset_s,
        spec.fault_end_s,
        analysis_hazard,
        sustained_success,
        spec.fault_subtype == "persistent_model_upset",
        gate.integrity_latched,
        arm,
        production,
    )
    if failure_class is not None and spec.fault_onset_s is not None:
        recovery = {
            **recovery,
            "recovery_state": "FAILED",
            "recovery_favorable_180": False,
            "restricted_time_unrecovered_s_180": production.recovery_deadline_s,
        }
    elapsed = state.time_s
    return ConfirmatoryEpisodeResult(
        schema_version=study.schema_version,
        study_phase="confirmatory",
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
        restricted_time_unrecovered_s_180=recovery[
            "restricted_time_unrecovered_s_180"
        ],
        minimum_braking_margin_m=summary.minimum_braking_margin_m,
        minimum_range_m=summary.minimum_range_m,
        maximum_contiguous_negative_margin_s=(
            summary.maximum_contiguous_negative_margin_s
        ),
        handover_entries=handover_entries,
        fallback_duty_cycle=fallback_time_s / elapsed if elapsed > 0.0 else 0.0,
        propellant_used_fraction=spec.initial_propellant - state.propellant,
        goal_dwell_final60_fraction=summary.goal_dwell_final60_fraction,
        first_goal_entry_s=summary.first_goal_entry_s,
        fault_onset_s=spec.fault_onset_s,
        fault_end_s=spec.fault_end_s,
        corridor_first_exit_s=recovery["corridor_first_exit_s"],
        qualifying_reentry_start_s=recovery["qualifying_reentry_start_s"],
        study_config_hash=study_config_hash,
        production_config_hash=production_config_hash,
        policy_hash=policy.model_identity,
        scenario_hash=spec.scenario_hash,
        exogenous_hashes=spec.stream_hashes,
        freeze_id=freeze_id,
        controller_command_period_s=production.command_period_s,
    )


def run_scenario_block(
    spec: ConfirmatoryScenarioSpec,
    streams: ExogenousStreams,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    study: ConfirmatoryConfig,
    production: PilotConfig,
    study_config_hash: str,
    production_config_hash: str,
    freeze_id: str,
) -> list[ConfirmatoryEpisodeResult]:
    rows = []
    for run_order, arm in enumerate(spec.arm_run_order, start=1):
        rows.append(
            run_confirmatory_arm(
                spec,
                streams,
                arm,
                run_order,
                policy,
                corridor,
                study,
                production,
                study_config_hash,
                production_config_hash,
                freeze_id,
            )
        )
    return rows


def run_confirmatory_block(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    stratum: str,
    replicate: int,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    study_config_hash: str,
    production_config_hash: str,
    freeze_id: str,
) -> list[ConfirmatoryEpisodeResult]:
    spec = materialize_scenario(study, production, stratum, replicate)
    streams, stream_hashes = materialize_exogenous(
        study, production, stratum, replicate
    )
    for name, digest in stream_hashes.items():
        if spec.stream_hashes[name] != digest:
            raise RuntimeError(f"exogenous hash drift for {spec.root_seed_id}/{name}")
    return run_scenario_block(
        spec,
        streams,
        policy,
        corridor,
        study,
        production,
        study_config_hash,
        production_config_hash,
        freeze_id,
    )


def run_confirmatory_campaign(
    study: ConfirmatoryConfig,
    production: PilotConfig,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    study_config_hash: str,
    production_config_hash: str,
    freeze_id: str,
    output_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    block_count = 0
    episode_count = 0
    with output.open("x", encoding="utf-8") as handle:
        for replicate in range(study.seeds_per_stratum):
            for stratum in CONFIRMATORY_STRATA:
                rows = run_confirmatory_block(
                    study,
                    production,
                    stratum,
                    replicate,
                    policy,
                    corridor,
                    study_config_hash,
                    production_config_hash,
                    freeze_id,
                )
                for row in rows:
                    handle.write(canonical_json(row.to_dict()).decode() + "\n")
                    episode_count += 1
                handle.flush()
                block_count += 1
    if block_count != study.planned_blocks or episode_count != study.planned_episodes:
        raise RuntimeError("confirmatory output does not contain the frozen expected cells")
    return {
        "blocks": block_count,
        "episodes": episode_count,
        "elapsed_wall_s": time.monotonic() - started,
        "episodes_sha256": sha256_bytes(output.read_bytes()),
    }


def load_episode_rows(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
    ]
