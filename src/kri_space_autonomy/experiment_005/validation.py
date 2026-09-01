from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_004.control import (
    DeterministicHoldController,
    EstimatedGeometryMonitor,
    observation_from_snapshot,
)
from kri_space_autonomy.experiment_004.dynamics import propagate_exact
from kri_space_autonomy.experiment_004.estimator import PlanarNavigationFilter
from kri_space_autonomy.experiment_004.measurements import PlanarNavigationPacket

from .config import Experiment005Config
from .dynamics import (
    angular_momentum,
    circular_chief_state,
    command_to_inertial,
    inertial_to_relative,
    lvlh_basis,
    pair_from_relative,
    pair_to_relative,
    propagate_fixed,
    relative_to_inertial,
    specific_energy,
    split_pair_state,
    two_body_pair_derivative,
)
from .geometry import (
    IndependentTruthEvaluator,
    NonlinearTruthSegment,
    admissible_position_excess_m,
    evaluate_truth_hold_segment,
    evaluate_truth_segment,
)
from .runner import run_checkpointed_fixture


def _frame_roundtrips(config: Experiment005Config) -> dict[str, Any]:
    fixtures = (
        np.array([0.0, -100.0, 0.0, 0.0, 0.12, 0.0]),
        np.array([10.0, -27.0, 0.0, 0.14, -0.14, 0.0]),
        np.array([-7.0, -65.0, 4.0, -0.08, 0.11, -0.015]),
    )
    position_errors: list[float] = []
    velocity_errors: list[float] = []
    basis_errors: list[float] = []
    determinant_errors: list[float] = []
    for phase in (0.0, 0.7, 2.4, 5.8):
        chief = circular_chief_state(
            config.gravitational_parameter_m3_s2,
            config.reference_radius_m,
            phase_rad=phase,
        )
        basis = lvlh_basis(chief)
        basis_errors.append(float(np.max(np.abs(basis.T @ basis - np.eye(3)))))
        determinant_errors.append(abs(float(np.linalg.det(basis)) - 1.0))
        for relative in fixtures:
            deputy = relative_to_inertial(chief, relative)
            observed = inertial_to_relative(chief, deputy)
            position_errors.append(float(np.max(np.abs(observed[:3] - relative[:3]))))
            velocity_errors.append(float(np.max(np.abs(observed[3:] - relative[3:]))))
    maximum_position = max(position_errors)
    maximum_velocity = max(velocity_errors)
    return {
        "passed": bool(
            maximum_position <= config.frame_roundtrip_position_tolerance_m
            and maximum_velocity <= config.frame_roundtrip_velocity_tolerance_mps
            and max(basis_errors) <= 5e-15
            and max(determinant_errors) <= 5e-15
        ),
        "fixtures": len(fixtures) * 4,
        "orbital_phases": 4,
        "includes_nonplanar_roundtrip_fixture": True,
        "maximum_position_error_m": maximum_position,
        "maximum_velocity_error_mps": maximum_velocity,
        "maximum_basis_orthonormality_error": max(basis_errors),
        "maximum_right_handed_determinant_error": max(determinant_errors),
        "acceptance": {
            "position_m": config.frame_roundtrip_position_tolerance_m,
            "velocity_mps": config.frame_roundtrip_velocity_tolerance_mps,
            "basis_abs": 5e-15,
        },
        "velocity_transform": "includes omega cross relative-position term",
    }


def _command_mapping(config: Experiment005Config) -> dict[str, Any]:
    commands = (
        np.array([config.max_acceleration_mps2, 0.0, 0.0]),
        np.array([0.0, config.max_acceleration_mps2, 0.0]),
        np.array(
            [
                config.max_acceleration_mps2 / np.sqrt(2.0),
                -config.max_acceleration_mps2 / np.sqrt(2.0),
                0.0,
            ]
        ),
    )
    norm_errors: list[float] = []
    roundtrip_errors: list[float] = []
    axis_errors: list[float] = []
    rotating_vector_changes: list[float] = []
    for phase in (0.0, 1.1, 3.0, 5.6):
        chief = circular_chief_state(
            config.gravitational_parameter_m3_s2,
            config.reference_radius_m,
            phase_rad=phase,
        )
        basis = lvlh_basis(chief)
        for index, command in enumerate(commands):
            inertial = command_to_inertial(chief, command)
            norm_errors.append(abs(float(np.linalg.norm(inertial) - np.linalg.norm(command))))
            roundtrip_errors.append(float(np.max(np.abs(basis.T @ inertial - command))))
            if index < 2:
                axis_errors.append(
                    float(
                        np.max(
                            np.abs(
                                inertial
                                - config.max_acceleration_mps2 * basis[:, index]
                            )
                        )
                    )
                )
        later = circular_chief_state(
            config.gravitational_parameter_m3_s2,
            config.reference_radius_m,
            config.command_period_s,
            phase_rad=phase,
        )
        rotating_vector_changes.append(
            float(
                np.linalg.norm(
                    command_to_inertial(later, commands[0])
                    - command_to_inertial(chief, commands[0])
                )
            )
        )
    maximum_error = max((*norm_errors, *roundtrip_errors, *axis_errors))
    return {
        "passed": bool(
            maximum_error <= config.command_mapping_tolerance_mps2
            and min(rotating_vector_changes) > 0.0
        ),
        "fixtures": len(commands) * 4,
        "maximum_mapping_error_mps2": maximum_error,
        "minimum_one_interval_inertial_direction_change_mps2": min(
            rotating_vector_changes
        ),
        "acceptance_mps2": config.command_mapping_tolerance_mps2,
        "held_quantity": "LVLH command components",
        "inertial_mapping": "recomputed from instantaneous chief frame at every RK4 stage",
        "constant_inertial_vector_used": False,
    }


def _reference_propagation(
    state: np.ndarray,
    command: np.ndarray,
    config: Experiment005Config,
    duration_s: float,
) -> np.ndarray:
    atol = np.array(
        [config.reference_position_atol_m] * 3
        + [config.reference_velocity_atol_mps] * 3
        + [config.reference_position_atol_m] * 3
        + [config.reference_velocity_atol_mps] * 3,
        dtype=np.float64,
    )
    solution = solve_ivp(
        lambda _time, vector: two_body_pair_derivative(
            vector, command, config.gravitational_parameter_m3_s2
        ),
        (0.0, duration_s),
        state,
        method=config.reference_integrator,
        rtol=config.reference_rtol,
        atol=atol,
        max_step=min(0.25, duration_s),
    )
    if not solution.success or abs(float(solution.t[-1]) - duration_s) > 1e-12:
        raise RuntimeError("independent DOP853 reference failed to reach the endpoint")
    return solution.y[:, -1]


def _production_accuracy(config: Experiment005Config) -> dict[str, Any]:
    chief = circular_chief_state(
        config.gravitational_parameter_m3_s2, config.reference_radius_m
    )
    diagonal = config.max_acceleration_mps2 / np.sqrt(2.0)
    fixtures = (
        (
            np.array([0.0, -100.0, 0.0, 0.0, 0.12, 0.0]),
            np.zeros(3),
            config.validation_horizon_s,
        ),
        (
            np.array([10.0, -27.0, 0.0, 0.14, -0.14, 0.0]),
            np.array([diagonal, -diagonal, 0.0]),
            60.0,
        ),
        (
            np.array([-10.0, -100.0, 0.0, -0.14, 0.14, 0.0]),
            np.array([config.max_acceleration_mps2, 0.0, 0.0]),
            1.0,
        ),
    )
    position_errors: list[float] = []
    velocity_errors: list[float] = []
    for relative, command, duration in fixtures:
        initial = pair_from_relative(chief, relative)
        production = propagate_fixed(
            initial,
            command,
            config.gravitational_parameter_m3_s2,
            duration,
            config.production_max_step_s,
        )
        reference = _reference_propagation(initial, command, config, duration)
        chief_production, deputy_production = split_pair_state(production)
        chief_reference, deputy_reference = split_pair_state(reference)
        position_errors.append(
            max(
                float(np.linalg.norm(chief_production[:3] - chief_reference[:3])),
                float(np.linalg.norm(deputy_production[:3] - deputy_reference[:3])),
            )
        )
        velocity_errors.append(
            max(
                float(np.linalg.norm(chief_production[3:] - chief_reference[3:])),
                float(np.linalg.norm(deputy_production[3:] - deputy_reference[3:])),
            )
        )
    maximum_position = max(position_errors)
    maximum_velocity = max(velocity_errors)
    return {
        "passed": bool(
            maximum_position <= config.production_position_tolerance_m
            and maximum_velocity <= config.production_velocity_tolerance_mps
        ),
        "fixtures": len(fixtures),
        "durations_s": [item[2] for item in fixtures],
        "maximum_position_error_m": maximum_position,
        "maximum_velocity_error_mps": maximum_velocity,
        "acceptance": {
            "position_m": config.production_position_tolerance_m,
            "velocity_mps": config.production_velocity_tolerance_mps,
        },
        "production": {
            "method": config.production_integrator,
            "maximum_step_s": config.production_max_step_s,
            "endpoint_and_command_discontinuity_split": True,
        },
        "independent_reference": {
            "method": config.reference_integrator,
            "rtol": config.reference_rtol,
            "position_atol_m": config.reference_position_atol_m,
            "velocity_atol_mps": config.reference_velocity_atol_mps,
        },
    }


def _circular_invariants(config: Experiment005Config) -> dict[str, Any]:
    chief_initial = circular_chief_state(
        config.gravitational_parameter_m3_s2, config.reference_radius_m
    )
    pair_initial = pair_from_relative(chief_initial, np.zeros(6))
    propagated = propagate_fixed(
        pair_initial,
        np.zeros(3),
        config.gravitational_parameter_m3_s2,
        config.validation_horizon_s,
        config.production_max_step_s,
    )
    chief_final, deputy_final = split_pair_state(propagated)
    analytic = circular_chief_state(
        config.gravitational_parameter_m3_s2,
        config.reference_radius_m,
        config.validation_horizon_s,
    )
    initial_energy = specific_energy(
        chief_initial, config.gravitational_parameter_m3_s2
    )
    final_energy = specific_energy(chief_final, config.gravitational_parameter_m3_s2)
    initial_momentum = angular_momentum(chief_initial)
    final_momentum = angular_momentum(chief_final)
    energy_relative_drift = abs(final_energy - initial_energy) / abs(initial_energy)
    momentum_relative_drift = float(
        np.linalg.norm(final_momentum - initial_momentum)
        / np.linalg.norm(initial_momentum)
    )
    radius_error = abs(float(np.linalg.norm(chief_final[:3])) - config.reference_radius_m)
    expected_speed = np.sqrt(
        config.gravitational_parameter_m3_s2 / config.reference_radius_m
    )
    speed_error = abs(float(np.linalg.norm(chief_final[3:])) - expected_speed)
    coincident_error = float(np.max(np.abs(chief_final - deputy_final)))
    analytic_position_error = float(np.linalg.norm(chief_final[:3] - analytic[:3]))
    analytic_velocity_error = float(np.linalg.norm(chief_final[3:] - analytic[3:]))
    return {
        "passed": bool(
            radius_error <= config.circular_radius_tolerance_m
            and speed_error <= config.circular_speed_tolerance_mps
            and energy_relative_drift <= config.invariant_relative_drift_tolerance
            and momentum_relative_drift <= config.invariant_relative_drift_tolerance
            and coincident_error == 0.0
        ),
        "horizon_s": config.validation_horizon_s,
        "radius_error_m": radius_error,
        "speed_error_mps": speed_error,
        "specific_energy_relative_drift": energy_relative_drift,
        "angular_momentum_relative_drift": momentum_relative_drift,
        "coincident_deputy_max_abs_error": coincident_error,
        "analytic_position_error_m": analytic_position_error,
        "analytic_velocity_error_mps": analytic_velocity_error,
        "acceptance": {
            "radius_m": config.circular_radius_tolerance_m,
            "speed_mps": config.circular_speed_tolerance_mps,
            "relative_invariant_drift": config.invariant_relative_drift_tolerance,
            "coincident_state_abs": 0.0,
        },
    }


def _truth_geometry(config: Experiment005Config) -> dict[str, Any]:
    chief = circular_chief_state(
        config.gravitational_parameter_m3_s2, config.reference_radius_m
    )

    def segment(relative: list[float], duration: float = 1.0) -> NonlinearTruthSegment:
        return NonlinearTruthSegment(
            pair_from_relative(chief, np.asarray(relative, dtype=np.float64)),
            np.zeros(3),
            config,
            duration,
        )

    crossing = segment([5.0, 0.0, 0.0, -10.0, 0.0, 0.0])
    crossing_result = evaluate_truth_segment(crossing, config)
    safe_result = evaluate_truth_segment(
        segment([0.0, -50.0, 0.0, 0.0, 0.0, 0.0]), config
    )
    radial_result = evaluate_truth_segment(
        segment([8.0, -50.0, 0.0, 0.0, 0.0, 0.0]), config
    )
    lower_exit_result = evaluate_truth_segment(
        segment([0.0, -101.0, 0.0, 0.0, 0.0, 0.0], 0.1), config
    )
    upper_exit_result = evaluate_truth_segment(
        segment([0.0, -26.0, 0.0, 0.0, 0.0, 0.0], 0.1), config
    )
    hold = segment([0.0, -30.0, 0.0, 0.0, 0.0, 0.0])
    hold_result = evaluate_truth_hold_segment(hold, config)
    boundary_result = evaluate_truth_segment(
        segment([config.hard_body_radius_m, 0.0, 0.0, 0.0, 0.0, 0.0], 0.01),
        config,
    )
    evaluator = IndependentTruthEvaluator(config)
    evaluator.observe(crossing)
    physical = evaluator.finalize()
    checks = {
        "interior_collision_crossing_detected": bool(
            crossing_result.collision
            and np.linalg.norm(crossing.relative_state_at(0.0)[:3])
            > config.hard_body_radius_m
            and np.linalg.norm(crossing.relative_state_at(1.0)[:3])
            > config.hard_body_radius_m
        ),
        "closed_collision_boundary": boundary_result.collision,
        "safe_approach_segment": bool(
            not safe_result.collision
            and not safe_result.keep_out_entry
            and not safe_result.corridor_departure
        ),
        "radial_corridor_departure": radial_result.corridor_departure,
        "lower_longitudinal_exit_departure": lower_exit_result.corridor_departure,
        "upper_longitudinal_exit_departure": upper_exit_result.corridor_departure,
        "hold_union_is_admissible": bool(
            admissible_position_excess_m(hold.relative_state_at(0.0), config) <= 0.0
        ),
        "hold_fixture_inside": hold_result.entirely_inside,
        "evaluator_uses_truth_crossing": physical.collision,
        "planar_truth_remains_planar": max(
            safe_result.maximum_abs_crosstrack_m,
            radial_result.maximum_abs_crosstrack_m,
            hold_result.maximum_speed_excess_mps * 0.0,
        )
        <= 1e-9,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "crossing_minimum_separation_m": crossing_result.minimum_separation_m,
        "crossing_minimum_time_s": crossing_result.minimum_separation_time_s,
        "lower_exit_excess_m": lower_exit_result.maximum_admissible_position_excess_m,
        "upper_exit_excess_m": upper_exit_result.maximum_admissible_position_excess_m,
        "event_source": "nonlinear chief/deputy inertial truth transformed to LVLH offline",
        "admissible_position_set": "closed approach corridor union closed hold ellipse",
        "historical_false_safe_behavior_reused": False,
        "evidence_returned_to_online_components": False,
    }


def _hcw_mismatch(config: Experiment005Config) -> dict[str, Any]:
    chief = circular_chief_state(
        config.gravitational_parameter_m3_s2, config.reference_radius_m
    )
    limit = config.velocity_envelope_abs_mps
    commands = (
        np.zeros(2),
        np.array([config.max_acceleration_mps2, 0.0]),
        np.array([-config.max_acceleration_mps2, 0.0]),
        np.array([0.0, config.max_acceleration_mps2]),
        np.array([0.0, -config.max_acceleration_mps2]),
    )
    position_mismatches: list[float] = []
    velocity_mismatches: list[float] = []
    fixtures = 0
    for x_position in config.radial_envelope_m:
        for y_position in config.alongtrack_envelope_m:
            for radial_velocity in (-limit, limit):
                for alongtrack_velocity in (-limit, limit):
                    initial = np.array(
                        [x_position, y_position, radial_velocity, alongtrack_velocity]
                    )
                    relative6 = np.array(
                        [
                            x_position,
                            y_position,
                            0.0,
                            radial_velocity,
                            alongtrack_velocity,
                            0.0,
                        ]
                    )
                    for command in commands:
                        truth = propagate_fixed(
                            pair_from_relative(chief, relative6),
                            np.array([command[0], command[1], 0.0]),
                            config.gravitational_parameter_m3_s2,
                            config.command_period_s,
                            config.production_max_step_s,
                        )
                        truth_relative = pair_to_relative(truth)
                        linear = propagate_exact(
                            initial,
                            command,
                            config.mean_motion_rad_s,
                            config.command_period_s,
                        )
                        position_mismatches.append(
                            float(np.linalg.norm(truth_relative[:2] - linear[:2]))
                        )
                        velocity_mismatches.append(
                            float(np.linalg.norm(truth_relative[3:5] - linear[2:]))
                        )
                        fixtures += 1
    scale_mismatches: dict[str, float] = {}
    base = np.array([10.0, -100.0, 0.14, -0.14])
    for scale in (1.0, 0.5, 0.25):
        planar = base * scale
        relative = np.array([planar[0], planar[1], 0.0, planar[2], planar[3], 0.0])
        truth = propagate_fixed(
            pair_from_relative(chief, relative),
            np.zeros(3),
            config.gravitational_parameter_m3_s2,
            60.0,
            config.production_max_step_s,
        )
        truth_relative = pair_to_relative(truth)
        linear = propagate_exact(
            planar, np.zeros(2), config.mean_motion_rad_s, 60.0
        )
        scale_mismatches[str(scale)] = float(
            np.linalg.norm(truth_relative[:2] - linear[:2])
        )
    values = [scale_mismatches[str(scale)] for scale in (1.0, 0.5, 0.25)]
    observed_orders = [
        float(np.log(values[index] / values[index + 1]) / np.log(2.0))
        for index in range(2)
    ]
    finite = bool(
        np.all(np.isfinite(position_mismatches))
        and np.all(np.isfinite(velocity_mismatches))
        and np.all(np.isfinite(values))
    )
    structural_local_limit = bool(
        values[0] > values[1] > values[2] > 0.0
        and min(observed_orders) >= 1.5
        and max(observed_orders) <= 2.5
    )
    maximum_position = max(position_mismatches)
    maximum_velocity = max(velocity_mismatches)
    return {
        "passed": finite and structural_local_limit and fixtures == 80,
        "fixtures": fixtures,
        "prospective_envelope": {
            "radial_m": list(config.radial_envelope_m),
            "alongtrack_m": list(config.alongtrack_envelope_m),
            "velocity_abs_mps": config.velocity_envelope_abs_mps,
            "velocity_derivation": (
                "max(E004 initial speed, E004 hold speed) plus one maximum command increment"
            ),
            "command_norm_max_mps2": config.max_acceleration_mps2,
            "interval_s": config.command_period_s,
        },
        "maximum_position_mismatch_m": maximum_position,
        "maximum_velocity_mismatch_mps": maximum_velocity,
        "maximum_position_mismatch_over_keep_out_radius": (
            maximum_position / config.keep_out_radius_m
        ),
        "scaled_unforced_60s_position_mismatch_m": scale_mismatches,
        "scaled_observed_orders": observed_orders,
        "quadratic_local_limit_gate": structural_local_limit,
        "absolute_mismatch_acceptance_threshold": None,
        "interpretation": (
            "descriptive truth/model discrepancy; no outcome or favorable absolute gate"
        ),
    }


def _mechanical_architecture_fixture(config: Experiment005Config) -> dict[str, Any]:
    e004 = load_e004_config("experiments/004/config.json")
    primary = PlanarNavigationFilter(e004)
    monitor_filter = PlanarNavigationFilter(e004)
    controller = DeterministicHoldController(e004)
    fallback = DeterministicHoldController(e004)
    gate = EstimatedGeometryMonitor(
        e004, fallback, expected_controller_identity=controller.controller_identity
    )
    chief = circular_chief_state(
        config.gravitational_parameter_m3_s2, config.reference_radius_m
    )
    truth = pair_from_relative(chief, config.initial_relative_state)

    def packet(filter_: PlanarNavigationFilter, sequence: int, time_s: float, state: np.ndarray):
        return PlanarNavigationPacket(
            sequence,
            time_s,
            time_s,
            state,
            filter_.nominal_measurement_covariance,
        )

    planar = config.initial_relative_state_planar
    primary.ingest(packet(primary, 0, 0.0, np.asarray(planar)))
    monitor_filter.ingest(packet(monitor_filter, 0, 0.0, np.asarray(planar)))
    maximum_model_residual_position = 0.0
    maximum_model_residual_velocity = 0.0
    overrides = 0
    for step in range(8):
        proposed = controller.decide(observation_from_snapshot(primary.snapshot()))
        decision = gate.gate(monitor_filter.snapshot(), proposed)
        overrides += int(decision.overridden)
        command = decision.executed_acceleration_mps2
        current_relative = pair_to_relative(truth)
        hcw_prediction = propagate_exact(
            np.array(
                [
                    current_relative[0],
                    current_relative[1],
                    current_relative[3],
                    current_relative[4],
                ]
            ),
            command,
            config.mean_motion_rad_s,
            config.command_period_s,
        )
        truth = propagate_fixed(
            truth,
            np.array([command[0], command[1], 0.0]),
            config.gravitational_parameter_m3_s2,
            config.command_period_s,
            config.production_max_step_s,
        )
        next_relative = pair_to_relative(truth)
        maximum_model_residual_position = max(
            maximum_model_residual_position,
            float(np.linalg.norm(next_relative[:2] - hcw_prediction[:2])),
        )
        maximum_model_residual_velocity = max(
            maximum_model_residual_velocity,
            float(np.linalg.norm(next_relative[3:5] - hcw_prediction[2:])),
        )
        next_time = float(step + 1)
        primary.advance(command, next_time)
        monitor_filter.advance(command, next_time)
        planar_measurement = np.array(
            [next_relative[0], next_relative[1], next_relative[3], next_relative[4]]
        )
        primary.ingest(packet(primary, step + 1, next_time, planar_measurement))
        monitor_filter.ingest(
            packet(monitor_filter, step + 1, next_time, planar_measurement)
        )
    return {
        "passed": bool(
            np.all(np.isfinite(truth))
            and primary is not monitor_filter
            and maximum_model_residual_position > 0.0
            and maximum_model_residual_velocity > 0.0
        ),
        "steps": 8,
        "primary_monitor_filter_instances_distinct": primary is not monitor_filter,
        "controller_estimator_prediction_model": "Experiment 004 planar HCW",
        "physical_truth_model": config.truth_model,
        "truth_model_mismatch_hidden": False,
        "maximum_one_step_position_model_residual_m": maximum_model_residual_position,
        "maximum_one_step_velocity_model_residual_mps": maximum_model_residual_velocity,
        "monitor_overrides": overrides,
        "interpretation": "deterministic interface fixture only; no mission outcome evaluated",
        "scientific_partition_accessed": False,
    }


def _information_boundary() -> dict[str, Any]:
    import kri_space_autonomy.experiment_004.control as control_module
    import kri_space_autonomy.experiment_004.estimator as estimator_module

    online_source = inspect.getsource(control_module) + inspect.getsource(estimator_module)
    prohibited = [
        token
        for token in (
            "pair_to_relative",
            "NonlinearTruthSegment",
            "IndependentTruthEvaluator",
            "TruthPhysicalSummary",
            "gravitational_parameter_m3_s2",
        )
        if token in online_source
    ]
    evaluator_source = inspect.getsource(IndependentTruthEvaluator)
    evaluator_prohibited = [
        token
        for token in (
            "DeterministicHoldController",
            "PlanarNavigationFilter",
            "EstimatedGeometryMonitor",
            "fault_label",
        )
        if token in evaluator_source
    ]
    return {
        "passed": not prohibited and not evaluator_prohibited,
        "online_truth_tokens_found": prohibited,
        "evaluator_online_tokens_found": evaluator_prohibited,
        "online_inputs": [
            "timestamped HCW navigation estimate",
            "estimate covariance and health",
            "proposed LVLH acceleration",
            "controller identity",
        ],
        "offline_truth_only": [
            "chief and deputy inertial Cartesian states",
            "LVLH truth transform",
            "physical event geometry",
            "truth-versus-HCW discrepancy",
        ],
        "physical_evidence_returned_online": False,
    }


def _runner_architecture() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="experiment-005-runner-fixture-") as temporary:
        root = Path(temporary)
        serial = run_checkpointed_fixture(
            root / "serial", workers=1, task_count=8, iterations=400
        )
        parallel = run_checkpointed_fixture(
            root / "parallel", workers=2, task_count=8, iterations=400
        )
        interrupted = run_checkpointed_fixture(
            root / "resume",
            workers=1,
            task_count=8,
            iterations=400,
            stop_after_for_test=3,
        )
        resumed = run_checkpointed_fixture(
            root / "resume", workers=2, task_count=8, iterations=400
        )
        corrupt_root = root / "corrupt"
        partial = run_checkpointed_fixture(
            corrupt_root,
            workers=1,
            task_count=4,
            iterations=100,
            stop_after_for_test=2,
        )
        shard = corrupt_root / "shards/cell-000000.json"
        shard.write_text("{}\n", encoding="utf-8")
        corrupt_failed_closed = False
        try:
            run_checkpointed_fixture(
                corrupt_root, workers=2, task_count=4, iterations=100
            )
        except RuntimeError as exc:
            corrupt_failed_closed = "checkpoint shard" in str(exc)
        serial_bytes = (root / "serial/fixture-rows.jsonl").read_bytes()
        parallel_bytes = (root / "parallel/fixture-rows.jsonl").read_bytes()
        resumed_bytes = (root / "resume/fixture-rows.jsonl").read_bytes()
    checks = {
        "serial_complete": serial["passed"],
        "parallel_complete": parallel["passed"],
        "serial_parallel_byte_equivalent": serial_bytes == parallel_bytes,
        "interruption_left_incomplete": bool(
            not interrupted["complete"] and interrupted["cells"] == 3
        ),
        "resume_missing_cells_only": bool(
            resumed["passed"]
            and resumed["completed_shards_reused"] == 3
            and resumed["new_shards_written"] == 5
        ),
        "resume_matches_fresh": resumed_bytes == serial_bytes,
        "corrupt_shard_fails_closed": corrupt_failed_closed,
        "corrupt_fixture_was_incomplete": not partial["complete"],
        "no_scientific_partition_access": not any(
            item["scientific_partition_accessed"]
            for item in (serial, parallel, resumed)
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "serial_sha256": serial["output_sha256"],
        "parallel_sha256": parallel["output_sha256"],
        "resumed_sha256": resumed["output_sha256"],
        "architecture": {
            "parallelism": "process pool",
            "canonical_order": "ascending frozen cell index",
            "checkpoint_publication": "same-directory no-clobber hard-link publication",
            "durability": "file and containing-directory fsync where supported",
            "orchestrator_concurrency": "exclusive campaign lock; stale lock fails closed",
            "restart": "validate completed shards then execute missing frozen cells only",
            "corruption": "fail closed without automatic recomputation",
        },
        "outcome_campaign_executed": False,
    }


def run_foundation_checks(config: Experiment005Config) -> dict[str, Any]:
    checks = {
        "frame_roundtrips": _frame_roundtrips(config),
        "command_mapping": _command_mapping(config),
        "production_rk4_vs_dop853": _production_accuracy(config),
        "circular_orbit_invariants": _circular_invariants(config),
        "truth_space_event_geometry": _truth_geometry(config),
        "local_hcw_limit_and_mismatch": _hcw_mismatch(config),
        "autonomy_assurance_mechanics_fixture": _mechanical_architecture_fixture(config),
        "online_offline_evidence_boundary": _information_boundary(),
        "future_runner_fixture": _runner_architecture(),
    }
    failed = [name for name, result in checks.items() if not result["passed"]]
    return {
        "passed": not failed,
        "checks": checks,
        "smallest_scientific_blocker": failed[0] if failed else None,
        "phase": "pre_outcome_nonlinear_truth_foundation",
        "experiment_004_outcomes_used_for_design": False,
        "experiment_005_calibration_partition_used": False,
        "experiment_005_pilot_partition_used": False,
        "experiment_005_confirmatory_partition_used": False,
        "outcome_campaign_executed": False,
        "scientific_findings_claimed": False,
        "truth_model": config.truth_model,
        "online_model": config.controller_estimator_model,
        "evidence_boundary": {
            "physical_evaluator": "offline nonlinear inertial truth only",
            "online_controller_estimator": "Experiment 004 planar HCW only",
            "physical_evidence_returned_online": False,
        },
    }
