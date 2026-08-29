from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from kri_space_autonomy.experiment_002.config import PILOT_STRATA, PilotConfig
from kri_space_autonomy.experiment_002.dynamics import (
    PropagationResult,
    TruthState,
    actuator_effectiveness,
    propagate_exact,
)
from kri_space_autonomy.experiment_002.evaluator import IndependentEvaluator
from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_002.seeds import ExogenousStreams, ScenarioSpec, sha256_bytes

from .config import AmendmentConfig
from .runner import _materialize_case, _split_interval, run_pd_episode


@dataclass(frozen=True)
class TraceSummary:
    final_state: TruthState
    collision: bool
    physical_hazard_observed: bool
    propellant_depleted: bool
    sustained_success: bool
    minimum_range_m: float
    minimum_braking_margin_m: float | None
    maximum_contiguous_negative_margin_s: float
    goal_dwell_final60_fraction: float
    first_goal_entry_s: float | None


class HighAccuracyReference:
    """Independent adaptive ODE reference; does not import production propagation code."""

    def __init__(self, config: PilotConfig, rtol: float, atol: float):
        self.config = config
        self.rtol = rtol
        self.atol = atol

    @staticmethod
    def _roots(
        function: Callable[[float], float],
        duration: float,
        samples: int = 65,
    ) -> list[float]:
        grid = np.linspace(0.0, duration, samples)
        values = [float(function(float(time_s))) for time_s in grid]
        roots: list[float] = []
        for left, right, f_left, f_right in zip(
            grid[:-1], grid[1:], values[:-1], values[1:], strict=False
        ):
            if f_left == 0.0:
                roots.append(float(left))
            if f_left * f_right < 0.0:
                roots.append(
                    float(
                        brentq(
                            function,
                            float(left),
                            float(right),
                            xtol=5e-15,
                            rtol=4.0 * np.finfo(float).eps,
                        )
                    )
                )
        if values[-1] == 0.0:
            roots.append(float(duration))
        return sorted(set(roots))

    def _single_piece(
        self,
        state: TruthState,
        command: float,
        effectiveness: float,
        disturbance: float,
        duration: float,
    ) -> PropagationResult:
        if duration <= 0.0:
            return PropagationResult(
                state,
                state.range_m,
                state.range_m,
                abs(state.relative_velocity_mps),
                state.time_s if state.range_m <= self.config.collision_range_m else None,
                state.propellant <= 0.0,
            )
        if state.range_m <= self.config.collision_range_m:
            collision_state = TruthState(
                state.time_s,
                self.config.collision_range_m,
                state.relative_velocity_mps,
                state.propellant,
                state.achieved_acceleration_mps2,
            )
            return PropagationResult(
                collision_state,
                self.config.collision_range_m,
                self.config.collision_range_m,
                abs(state.relative_velocity_mps),
                state.time_s,
                state.propellant <= 0.0,
            )
        depleted_at_start = state.propellant <= 0.0
        if depleted_at_start:
            state = TruthState(
                state.time_s,
                state.range_m,
                state.relative_velocity_mps,
                0.0,
                0.0,
            )
            command = 0.0
        bounded_command = max(
            -self.config.max_acceleration_mps2,
            min(self.config.max_acceleration_mps2, command),
        )
        target = effectiveness * bounded_command
        initial = np.array(
            [
                state.range_m,
                state.relative_velocity_mps,
                state.achieved_acceleration_mps2,
                state.propellant,
            ],
            dtype=np.float64,
        )

        def derivative(_time_s: float, values: np.ndarray) -> np.ndarray:
            achieved = values[2]
            return np.array(
                [
                    values[1],
                    achieved + disturbance,
                    (target - achieved) / self.config.actuator_time_constant_s,
                    0.0
                    if depleted_at_start
                    else -self.config.propellant_cost_per_delta_v * abs(achieved),
                ],
                dtype=np.float64,
            )

        def collision_event(_time_s: float, values: np.ndarray) -> float:
            return float(values[0] - self.config.collision_range_m)

        collision_event.terminal = True  # type: ignore[attr-defined]
        collision_event.direction = -1.0  # type: ignore[attr-defined]

        def depletion_event(_time_s: float, values: np.ndarray) -> float:
            return float(values[3])

        depletion_event.terminal = True  # type: ignore[attr-defined]
        depletion_event.direction = -1.0  # type: ignore[attr-defined]
        events = [collision_event] if depleted_at_start else [collision_event, depletion_event]
        solution = solve_ivp(
            derivative,
            (0.0, duration),
            initial,
            method="DOP853",
            rtol=self.rtol,
            atol=self.atol,
            dense_output=True,
            max_step=duration / 8.0,
            events=events,
        )
        if not solution.success or solution.sol is None:
            raise RuntimeError(f"high-accuracy reference failed: {solution.message}")
        local_end = float(solution.t[-1])
        dense = solution.sol
        velocity_roots = self._roots(lambda value: float(dense(value)[1]), local_end)
        acceleration_roots = self._roots(
            lambda value: float(dense(value)[2] + disturbance), local_end
        )
        range_candidates = [0.0, local_end, *velocity_roots]
        velocity_candidates = [0.0, local_end, *acceleration_roots]
        range_values = [float(dense(value)[0]) for value in range_candidates]
        velocity_values = [abs(float(dense(value)[1])) for value in velocity_candidates]
        terminal = np.asarray(dense(local_end), dtype=np.float64)
        collision_local = (
            float(solution.t_events[0][0])
            if len(solution.t_events) >= 1 and len(solution.t_events[0])
            else None
        )
        depletion_local = (
            float(solution.t_events[1][0])
            if not depleted_at_start
            and len(solution.t_events) >= 2
            and len(solution.t_events[1])
            else None
        )
        terminal_state = TruthState(
            state.time_s + local_end,
            self.config.collision_range_m
            if collision_local is not None
            else float(terminal[0]),
            float(terminal[1]),
            max(0.0, float(terminal[3])),
            float(terminal[2]),
        )
        first = PropagationResult(
            terminal_state,
            min(range_values),
            max(range_values),
            max(velocity_values),
            state.time_s + collision_local if collision_local is not None else None,
            depleted_at_start or depletion_local is not None,
        )
        if collision_local is not None or depletion_local is None:
            return first
        depleted = TruthState(
            first.state.time_s,
            first.state.range_m,
            first.state.relative_velocity_mps,
            0.0,
            0.0,
        )
        remaining = duration - local_end
        if remaining <= 1e-14:
            return PropagationResult(
                depleted,
                first.minimum_range_m,
                first.maximum_range_m,
                first.maximum_abs_velocity_mps,
                None,
                True,
            )
        second = self._single_piece(depleted, 0.0, effectiveness, disturbance, remaining)
        return PropagationResult(
            second.state,
            min(first.minimum_range_m, second.minimum_range_m),
            max(first.maximum_range_m, second.maximum_range_m),
            max(first.maximum_abs_velocity_mps, second.maximum_abs_velocity_mps),
            second.collision_time_s,
            True,
        )

    def propagate(
        self,
        state: TruthState,
        command: float,
        effectiveness: float,
        disturbance: float,
        duration: float,
    ) -> PropagationResult:
        return self._single_piece(state, command, effectiveness, disturbance, duration)


def _effectiveness(spec: ScenarioSpec, start_s: float, end_s: float) -> float:
    if spec.fault_subtype != "actuator_degradation":
        return 1.0
    return actuator_effectiveness(
        0.5 * (start_s + end_s),
        spec.fault_onset_s,
        spec.fault_end_s,
        spec.actuator_effectiveness,
    )


def _commands_for_pattern(
    pattern: str,
    amendment: AmendmentConfig,
    production: PilotConfig,
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    policy: FrozenPolicy,
    config_hash: str,
) -> tuple[list[tuple[float, float]], str | None]:
    if pattern == "pd_operational":
        source_result, trace = run_pd_episode(
            amendment,
            production,
            spec,
            streams,
            policy,
            amendment.operational_command_period_s,
            amendment.operational_observation_period_s,
            config_hash,
            "fixed_replay_trace_generation",
            collect_command_trace=True,
        )
        if trace is None:
            raise RuntimeError("PD replay command trace was not collected")
        return trace, source_result.failure_class
    count = round(production.horizon_s / amendment.operational_command_period_s)
    commands: list[tuple[float, float]] = []
    for index in range(count):
        time_s = index * amendment.operational_command_period_s
        if pattern == "maximum_closing":
            command = -production.max_acceleration_mps2
        elif pattern == "maximum_separating":
            command = production.max_acceleration_mps2
        elif pattern == "alternating_extrema":
            command = production.max_acceleration_mps2 * (1.0 if index % 2 == 0 else -1.0)
        else:
            raise ValueError(f"unknown replay pattern: {pattern}")
        commands.append((time_s, command))
    return commands, None


def _trace_summary(
    mode: str,
    production: PilotConfig,
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    commands: list[tuple[float, float]],
    reference: HighAccuracyReference,
) -> tuple[TraceSummary, list[TruthState]]:
    state = TruthState(
        0.0,
        spec.initial_range_m,
        spec.initial_velocity_mps,
        spec.initial_propellant,
        0.0,
    )
    states = [state]
    evaluator = IndependentEvaluator(production, state, 1.0)
    evaluator_stride = round(production.evaluator_period_s / production.exogenous_period_s)
    command_stride = round(1.0 / production.exogenous_period_s)
    command = 0.0
    command_index = 0
    for tick in range(production.n_exogenous_steps):
        if tick % command_stride == 0:
            command_time, command = commands[command_index]
            expected_time = tick * production.exogenous_period_s
            if abs(command_time - expected_time) > 1e-12:
                raise RuntimeError("fixed command trace timestamp drift")
            command_index += 1
        interval_start = tick * production.exogenous_period_s
        interval_end = interval_start + production.exogenous_period_s
        for segment_start, segment_end in _split_interval(interval_start, interval_end, spec):
            effectiveness = _effectiveness(spec, segment_start, segment_end)
            start_state = state
            if mode == "production_exact":
                propagation = propagate_exact(
                    state,
                    command,
                    effectiveness,
                    float(streams.process_acceleration_mps2[tick]),
                    segment_end - segment_start,
                    production,
                )
            elif mode == "independent_reference":
                propagation = reference.propagate(
                    state,
                    command,
                    effectiveness,
                    float(streams.process_acceleration_mps2[tick]),
                    segment_end - segment_start,
                )
            else:
                raise ValueError(mode)
            evaluator.observe_interval(start_state, propagation)
            state = propagation.state
            states.append(state)
            if propagation.collision_time_s is not None:
                break
        if (tick + 1) % evaluator_stride == 0:
            evaluator.observe_margin(state, _effectiveness(spec, state.time_s, state.time_s))
        if evaluator.collision:
            break
    summary = evaluator.finalize(state)
    return (
        TraceSummary(
            final_state=state,
            collision=summary.collision,
            physical_hazard_observed=summary.physical_hazard_observed,
            propellant_depleted=summary.propellant_depleted,
            sustained_success=summary.sustained_success,
            minimum_range_m=summary.minimum_range_m,
            minimum_braking_margin_m=summary.minimum_braking_margin_m,
            maximum_contiguous_negative_margin_s=summary.maximum_contiguous_negative_margin_s,
            goal_dwell_final60_fraction=summary.goal_dwell_final60_fraction,
            first_goal_entry_s=summary.first_goal_entry_s,
        ),
        states,
    )


def _optional_error(left: float | None, right: float | None) -> float:
    if left is None or right is None:
        return 0.0 if left is right else math.inf
    return abs(left - right)


def compare_fixed_trace(
    pattern: str,
    amendment: AmendmentConfig,
    production: PilotConfig,
    spec: ScenarioSpec,
    streams: ExogenousStreams,
    policy: FrozenPolicy,
    config_hash: str,
) -> dict[str, Any]:
    commands, source_failure = _commands_for_pattern(
        pattern, amendment, production, spec, streams, policy, config_hash
    )
    reference = HighAccuracyReference(
        production, amendment.reference_rtol, amendment.reference_atol
    )
    exact_summary, exact_states = _trace_summary(
        "production_exact", production, spec, streams, commands, reference
    )
    reference_summary, reference_states = _trace_summary(
        "independent_reference", production, spec, streams, commands, reference
    )
    aligned = len(exact_states) == len(reference_states)
    state_errors: list[float] = []
    if aligned:
        for exact, observed in zip(exact_states, reference_states, strict=True):
            state_errors.extend(
                [
                    abs(exact.range_m - observed.range_m),
                    abs(exact.relative_velocity_mps - observed.relative_velocity_mps),
                    abs(exact.achieved_acceleration_mps2 - observed.achieved_acceleration_mps2),
                    abs(exact.propellant - observed.propellant),
                ]
            )
    else:
        state_errors.append(math.inf)
    metric_errors = {
        "minimum_range_m": abs(
            exact_summary.minimum_range_m - reference_summary.minimum_range_m
        ),
        "minimum_braking_margin_m": _optional_error(
            exact_summary.minimum_braking_margin_m,
            reference_summary.minimum_braking_margin_m,
        ),
        "maximum_contiguous_negative_margin_s": abs(
            exact_summary.maximum_contiguous_negative_margin_s
            - reference_summary.maximum_contiguous_negative_margin_s
        ),
        "goal_dwell_final60_fraction": abs(
            exact_summary.goal_dwell_final60_fraction
            - reference_summary.goal_dwell_final60_fraction
        ),
        "first_goal_entry_s": _optional_error(
            exact_summary.first_goal_entry_s, reference_summary.first_goal_entry_s
        ),
        "final_propellant": abs(
            exact_summary.final_state.propellant - reference_summary.final_state.propellant
        ),
    }
    classifications = (
        "collision",
        "physical_hazard_observed",
        "propellant_depleted",
        "sustained_success",
    )
    classification_match = all(
        getattr(exact_summary, field) == getattr(reference_summary, field)
        for field in classifications
    )
    maximum_state_error = max(state_errors, default=0.0)
    maximum_metric_error = max(metric_errors.values(), default=0.0)
    maximum_error = max(maximum_state_error, maximum_metric_error)
    return {
        "pattern": pattern,
        "root_seed_id": spec.root_seed_id,
        "stratum_id": spec.stratum_id,
        "command_count": len(commands),
        "command_trace_sha256": sha256_bytes(
            json.dumps(commands, separators=(",", ":")).encode()
        ),
        "source_controller_failure": source_failure,
        "state_records_aligned": aligned,
        "state_records": len(exact_states),
        "maximum_state_error": maximum_state_error,
        "metric_errors": metric_errors,
        "maximum_metric_error": maximum_metric_error,
        "maximum_state_or_metric_error": maximum_error,
        "classification_match": classification_match,
        "production_classifications": {
            field: getattr(exact_summary, field) for field in classifications
        },
        "reference_classifications": {
            field: getattr(reference_summary, field) for field in classifications
        },
        "passed": bool(
            source_failure is None
            and aligned
            and classification_match
            and maximum_error <= amendment.numerical_error_tolerance
        ),
    }


def run_fixed_command_replay(
    amendment: AmendmentConfig,
    production: PilotConfig,
    policy: FrozenPolicy,
    config_hash: str,
    output_path: str | Path,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for stratum in PILOT_STRATA:
        for replicate in range(amendment.replay_seeds_per_stratum):
            spec, streams = _materialize_case(
                amendment, production, "fixed_replay", stratum, replicate
            )
            for pattern in amendment.replay_command_patterns:
                cases.append(
                    compare_fixed_trace(
                        pattern,
                        amendment,
                        production,
                        spec,
                        streams,
                        policy,
                        config_hash,
                    )
                )
    maximum_error = max(case["maximum_state_or_metric_error"] for case in cases)
    payload = {
        "schema_version": amendment.schema_version,
        "method": (
            "complete 600 s identical timestamped command traces; production float64 exact "
            "propagator versus independent SciPy DOP853 adaptive ODE reference"
        ),
        "reference": {
            "implementation": "scipy.integrate.solve_ivp/DOP853",
            "rtol": amendment.reference_rtol,
            "atol": amendment.reference_atol,
            "production_propagator_imported_by_reference": False,
        },
        "tolerance": amendment.numerical_error_tolerance,
        "cases": cases,
        "case_count": len(cases),
        "maximum_state_or_metric_error": maximum_error,
        "all_classifications_match": all(case["classification_match"] for case in cases),
        "passed": all(case["passed"] for case in cases),
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload
