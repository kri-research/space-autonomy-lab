from __future__ import annotations

import hashlib
import inspect
from dataclasses import asdict
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from .config import Experiment004Config
from .control import DeterministicHoldController, observation_from_snapshot
from .dynamics import (
    closed_form_matrices,
    continuous_matrices,
    discrete_matrices,
    observability_diagnostics,
    piecewise_acceleration_covariance,
    propagate_exact,
)
from .estimator import FilterHealth, PacketDisposition, PlanarNavigationFilter
from .evaluation import IndependentPlanarEvaluator, TechnicalStatus
from .geometry import HCWSegment, evaluate_segment
from .measurements import PlanarNavigationPacket


def _packet(
    filter_: PlanarNavigationFilter,
    sequence: int,
    measured: float,
    received: float,
    state: np.ndarray,
) -> PlanarNavigationPacket:
    return PlanarNavigationPacket(
        sequence,
        measured,
        received,
        state,
        filter_.nominal_measurement_covariance,
    )


def _exact_dynamics_reference(config: Experiment004Config) -> dict[str, Any]:
    fixtures = (
        (
            np.array([0.0, -100.0, 0.0, 0.12]),
            np.array([0.001, 0.004]),
            1.0,
        ),
        (
            np.array([4.0, -40.0, -0.03, 0.08]),
            np.array([-0.007, 0.003]),
            0.25,
        ),
        (
            np.array([-3.0, -30.0, 0.02, -0.01]),
            np.array([0.0, 0.0]),
            10.0,
        ),
    )
    closed_form_errors: list[float] = []
    dop853_position_errors: list[float] = []
    dop853_velocity_errors: list[float] = []
    n = config.mean_motion_rad_s
    for initial, command, duration in fixtures:
        transition, command_map = discrete_matrices(n, duration)
        exact = transition @ initial + command_map @ command
        reference_transition, reference_command = closed_form_matrices(n, duration)
        analytical = reference_transition @ initial + reference_command @ command
        closed_form_errors.append(float(np.max(np.abs(exact - analytical))))

        radial_command = float(command[0])
        alongtrack_command = float(command[1])

        def rhs(
            _time,
            state,
            radial_acceleration=radial_command,
            alongtrack_acceleration=alongtrack_command,
        ):
            x_pos, _y_pos, vx, vy = state
            return np.array(
                [
                    vx,
                    vy,
                    3.0 * n**2 * x_pos + 2.0 * n * vy + radial_acceleration,
                    -2.0 * n * vx + alongtrack_acceleration,
                ],
                dtype=np.float64,
            )

        solution = solve_ivp(
            rhs,
            (0.0, duration),
            initial,
            method="DOP853",
            rtol=1e-12,
            atol=np.array([1e-12, 1e-12, 1e-14, 1e-14]),
            max_step=max(0.01, duration / 16.0),
        )
        if not solution.success or abs(solution.t[-1] - duration) > 1e-14:
            raise RuntimeError("independent DOP853 reference did not reach the endpoint")
        numerical = solution.y[:, -1]
        dop853_position_errors.append(float(np.max(np.abs(exact[:2] - numerical[:2]))))
        dop853_velocity_errors.append(float(np.max(np.abs(exact[2:] - numerical[2:]))))
    closed_max = max(closed_form_errors)
    position_max = max(dop853_position_errors)
    velocity_max = max(dop853_velocity_errors)
    return {
        "passed": bool(
            closed_max <= 2e-12
            and position_max <= 1e-10
            and velocity_max <= 1e-12
        ),
        "fixtures": len(fixtures),
        "augmented_exponential_vs_closed_form_max_abs_error": closed_max,
        "dop853_position_max_abs_error_m": position_max,
        "dop853_velocity_max_abs_error_mps": velocity_max,
        "acceptance": {
            "closed_form_max_abs": 2e-12,
            "position_m": 1e-10,
            "velocity_mps": 1e-12,
        },
        "references": [
            "independent analytical HCW state and input matrices",
            "independent scalar-equation DOP853 integration",
        ],
    }


def _structural_dynamics(config: Experiment004Config) -> dict[str, Any]:
    n = config.mean_motion_rad_s
    transition_rate, input_rate = continuous_matrices(n)
    transition_one, command_one = discrete_matrices(n, 1.0)
    transition_a, command_a = discrete_matrices(n, 0.4)
    transition_b, command_b = discrete_matrices(n, 0.6)
    semigroup_transition = transition_b @ transition_a
    semigroup_command = transition_b @ command_a + command_b
    state = np.array([12.0, -80.0, 0.03, -0.02])
    invariant_initial = state[3] + 2.0 * n * state[0]
    propagated = propagate_exact(state, np.zeros(2), n, 600.0)
    invariant_final = propagated[3] + 2.0 * n * propagated[0]
    radial_derivative = transition_rate @ np.array([1.0, 0.0, 0.0, 0.0])
    alongtrack_velocity_derivative = transition_rate @ np.array([0.0, 0.0, 0.0, 1.0])
    outward_velocity_derivative = transition_rate @ np.array([0.0, 0.0, 1.0, 0.0])
    checks = {
        "continuous_shape": transition_rate.shape == (4, 4) and input_rate.shape == (4, 2),
        "radial_gravity_gradient_sign": bool(radial_derivative[2] > 0.0),
        "alongtrack_to_radial_coriolis_sign": bool(
            alongtrack_velocity_derivative[2] > 0.0
        ),
        "radial_to_alongtrack_coriolis_sign": bool(
            outward_velocity_derivative[3] < 0.0
        ),
        "input_axes": bool(
            input_rate[2, 0] == 1.0
            and input_rate[3, 1] == 1.0
            and np.count_nonzero(input_rate) == 2
        ),
        "semigroup_transition": bool(
            np.allclose(transition_one, semigroup_transition, rtol=2e-13, atol=2e-13)
        ),
        "semigroup_command": bool(
            np.allclose(command_one, semigroup_command, rtol=2e-13, atol=2e-13)
        ),
        "unforced_invariant": bool(
            abs(invariant_final - invariant_initial) <= 2e-14
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "mean_motion_rad_s": n,
        "derived_mean_motion_rad_s": config.derived_mean_motion_rad_s,
        "orbital_period_s": config.orbital_period_s,
        "unforced_invariant_abs_error_mps": float(
            abs(invariant_final - invariant_initial)
        ),
        "state_order": list(config.state_order),
        "action_order": list(config.action_order),
        "state_units": list(config.state_units),
        "action_units": list(config.action_units),
    }


def _geometry_checks(config: Experiment004Config) -> dict[str, Any]:
    crossing = HCWSegment(
        np.array([5.0, 0.0, -10.0, 0.0]),
        np.zeros(2),
        config.mean_motion_rad_s,
        1.0,
        maximum_duration_s=config.event_interval_max_s,
    )
    crossing_result = evaluate_segment(crossing, config)
    safe = HCWSegment(
        np.array([0.0, -50.0, 0.0, 0.0]),
        np.zeros(2),
        config.mean_motion_rad_s,
        1.0,
        maximum_duration_s=config.event_interval_max_s,
    )
    safe_result = evaluate_segment(safe, config)
    corridor_departure = HCWSegment(
        np.array([8.0, -50.0, 0.0, 0.0]),
        np.zeros(2),
        config.mean_motion_rad_s,
        1.0,
        maximum_duration_s=config.event_interval_max_s,
    )
    departure_result = evaluate_segment(corridor_departure, config)
    times = np.linspace(0.0, 1.0, 20001)
    dense_minimum = min(float(np.linalg.norm(crossing.state_at(float(t))[:2])) for t in times)
    boundary = HCWSegment(
        np.array([config.hard_body_radius_m, 0.0, 0.0, 0.0]),
        np.zeros(2),
        config.mean_motion_rad_s,
        0.01,
        maximum_duration_s=config.event_interval_max_s,
    )
    boundary_result = evaluate_segment(boundary, config)
    checks = {
        "interior_crossing_detected": bool(
            crossing_result.collision
            and np.linalg.norm(crossing.start_state[:2]) > config.hard_body_radius_m
            and np.linalg.norm(crossing.state_at(1.0)[:2]) > config.hard_body_radius_m
        ),
        "dense_arc_reference": abs(
            crossing_result.minimum_separation_m - dense_minimum
        )
        <= 1e-6,
        "boundary_is_closed": boundary_result.collision,
        "safe_segment_not_hazard": bool(
            not safe_result.collision and not safe_result.keep_out_entry
        ),
        "corridor_departure_detected": departure_result.corridor_departure,
        "nominal_corridor_segment_inside": not safe_result.corridor_departure,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "interior_crossing_minimum_m": crossing_result.minimum_separation_m,
        "dense_reference_minimum_m": dense_minimum,
        "boundary_semantics": "collision and keep-out disks are closed sets",
        "event_path": "exact HCW arc split at intervals no longer than one second",
    }


def _estimator_checks(config: Experiment004Config) -> dict[str, Any]:
    full = observability_diagnostics(
        config.mean_motion_rad_s,
        config.command_period_s,
        position_only=False,
    )
    position = observability_diagnostics(
        config.mean_motion_rad_s,
        config.command_period_s,
        position_only=True,
    )
    process = piecewise_acceleration_covariance(
        config.mean_motion_rad_s,
        config.command_period_s,
        config.process_acceleration_draw_period_s,
        config.process_acceleration_sigma_mps2,
    )
    state0 = config.initial_mean_array
    command = np.array([0.001, 0.002])
    state1 = propagate_exact(state0, command, config.mean_motion_rad_s, 1.0)
    direct = PlanarNavigationFilter(config)
    direct.ingest(_packet(direct, 0, 0.0, 0.0, state0))
    direct.advance(command, 1.0)
    direct.ingest(_packet(direct, 1, 1.0, 1.0, state1))
    delayed = PlanarNavigationFilter(config)
    delayed.advance(command, 1.0)
    delayed.ingest(_packet(delayed, 0, 0.0, 1.0, state0))
    delayed.ingest(_packet(delayed, 1, 1.0, 1.0, state1))
    fixed_lag_mean = float(np.max(np.abs(direct.snapshot().mean - delayed.snapshot().mean)))
    fixed_lag_covariance = float(
        np.max(np.abs(direct.snapshot().covariance - delayed.snapshot().covariance))
    )
    replay = PlanarNavigationFilter(config)
    replay.ingest(_packet(replay, 0, 0.0, 0.0, replay.snapshot().mean))
    minimum_eigenvalue = np.inf
    maximum_asymmetry = 0.0
    maximum_trace = 0.0
    for step in range(1, 601):
        prior = replay.advance(np.zeros(2), float(step))
        disposition = replay.ingest(
            _packet(replay, step, float(step), float(step), prior.mean)
        ).disposition
        if disposition is not PacketDisposition.ACCEPTED:
            raise RuntimeError("nominal covariance replay rejected an exact packet")
        covariance = replay.snapshot().covariance
        minimum_eigenvalue = min(
            minimum_eigenvalue,
            float(np.linalg.eigvalsh(covariance)[0]),
        )
        maximum_asymmetry = max(
            maximum_asymmetry,
            float(np.max(np.abs(covariance - covariance.T))),
        )
        maximum_trace = max(maximum_trace, float(np.trace(covariance)))
    divergence_filter = PlanarNavigationFilter(config)
    divergence = divergence_filter.advance(np.array([1e9, 1e9]), 1.0)
    checks = {
        "full_measurement_observability": full.rank == 4,
        "position_only_observability": bool(
            position.rank == 4
            and position.smallest_singular_value > 1e-4
            and position.condition_number < 1e7
        ),
        "process_covariance_symmetric": bool(
            np.max(np.abs(process - process.T)) <= 1e-20
        ),
        "process_covariance_psd": bool(np.linalg.eigvalsh(process)[0] >= -1e-20),
        "fixed_lag_mean": fixed_lag_mean <= 1e-12,
        "fixed_lag_covariance": fixed_lag_covariance <= 1e-12,
        "long_replay_finite_psd": bool(
            minimum_eigenvalue > 1e-12
            and maximum_asymmetry <= 1e-15
            and maximum_trace < config.covariance_trace_limit
        ),
        "divergence_fails_closed": divergence.health is FilterHealth.DIVERGED,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "full_observability": {
            "rank": full.rank,
            "smallest_scaled_singular_value": full.smallest_singular_value,
            "scaled_condition_number": full.condition_number,
        },
        "position_only_observability": {
            "rank": position.rank,
            "smallest_scaled_singular_value": position.smallest_singular_value,
            "scaled_condition_number": position.condition_number,
        },
        "process_covariance_minimum_eigenvalue": float(np.linalg.eigvalsh(process)[0]),
        "fixed_lag_maximum_mean_difference": fixed_lag_mean,
        "fixed_lag_maximum_covariance_difference": fixed_lag_covariance,
        "covariance_long_replay": {
            "steps": 601,
            "minimum_eigenvalue": minimum_eigenvalue,
            "maximum_asymmetry": maximum_asymmetry,
            "maximum_trace": maximum_trace,
        },
        "divergence_reason": divergence.reason.value,
    }


def _sanity_replay(config: Experiment004Config) -> dict[str, Any]:
    filter_ = PlanarNavigationFilter(config)
    controller = DeterministicHoldController(config)
    state = config.initial_mean_array
    evaluator = IndependentPlanarEvaluator(config)
    digest = hashlib.sha256()
    filter_.ingest(_packet(filter_, 0, 0.0, 0.0, state))
    maximum_command_norm = 0.0
    for step in range(int(config.numerical_fixture_horizon_s)):
        snapshot = filter_.snapshot()
        decision = controller.decide(observation_from_snapshot(snapshot))
        command = decision.acceleration_mps2
        maximum_command_norm = max(maximum_command_norm, float(np.linalg.norm(command)))
        segment = HCWSegment(
            state,
            command,
            config.mean_motion_rad_s,
            config.command_period_s,
            maximum_duration_s=config.event_interval_max_s,
        )
        evaluator.observe(segment)
        state = segment.state_at(config.command_period_s)
        next_time = float(step + 1)
        filter_.advance(command, next_time)
        filter_.ingest(_packet(filter_, step + 1, next_time, next_time, state))
        digest.update(np.asarray(state, dtype="<f8").tobytes())
        digest.update(np.asarray(command, dtype="<f8").tobytes())
        digest.update(np.asarray(filter_.snapshot().covariance, dtype="<f8").tobytes())
    summary = evaluator.finalize(TechnicalStatus())
    return {
        "digest": digest.hexdigest(),
        "maximum_command_norm_mps2": maximum_command_norm,
        "final_state": state.tolist(),
        "physical": asdict(summary.physical),
        "mission": asdict(summary.mission),
        "controller_identity": controller.controller_identity,
        "passed": bool(
            maximum_command_norm <= config.max_acceleration_mps2 + 1e-12
            and not summary.physical.collision
            and not summary.physical.unauthorized_keep_out_entry
            and summary.mission.hold_acquired
        ),
        "interpretation": "deterministic numerical and mission-feasibility fixture only",
    }


def _information_boundary_check() -> dict[str, Any]:
    import kri_space_autonomy.experiment_004.control as control_module
    import kri_space_autonomy.experiment_004.estimator as estimator_module

    source = inspect.getsource(control_module) + inspect.getsource(estimator_module)
    prohibited = [
        token
        for token in (
            "latent_state",
            "fault_parameters",
            "root_seed_id",
            "IndependentPlanarEvaluator",
            "TechnicalStatus",
        )
        if token in source
    ]
    return {
        "passed": not prohibited,
        "prohibited_tokens_found": prohibited,
        "online_inputs": [
            "timestamped navigation estimate",
            "estimate covariance and health",
            "proposed vector command",
            "frozen controller identity",
        ],
        "offline_only": [
            "physical trajectory",
            "fault identity and schedule",
            "geometric outcome summary",
            "estimation error diagnostics",
        ],
    }


def run_foundation_checks(config: Experiment004Config) -> dict[str, Any]:
    exact = _exact_dynamics_reference(config)
    structural = _structural_dynamics(config)
    geometry = _geometry_checks(config)
    estimator = _estimator_checks(config)
    first_replay = _sanity_replay(config)
    second_replay = _sanity_replay(config)
    deterministic = {
        "passed": bool(
            first_replay["passed"]
            and second_replay["passed"]
            and first_replay["digest"] == second_replay["digest"]
            and first_replay["controller_identity"]
            == second_replay["controller_identity"]
        ),
        "first": first_replay,
        "second_digest": second_replay["digest"],
    }
    boundaries = _information_boundary_check()
    technical_separation = TechnicalStatus(
        primary_estimator_fault=True,
        monitor_estimator_fault=False,
        monitor_logic_fault=True,
        shared_cause_fault=False,
    )
    separation = {
        "passed": bool(
            technical_separation.primary_estimator_fault
            and not technical_separation.monitor_estimator_fault
            and technical_separation.monitor_logic_fault
            and not technical_separation.shared_cause_fault
        ),
        "fields": asdict(technical_separation),
        "aggregate_primary_endpoint_defined": False,
    }
    checks = {
        "exact_dynamics_reference": exact,
        "units_signs_and_structure": structural,
        "continuous_geometry_events": geometry,
        "observability_and_covariance": estimator,
        "deterministic_replay_and_mission_sanity": deterministic,
        "online_information_boundary": boundaries,
        "outcome_domain_separation": separation,
    }
    return {
        "passed": all(bool(value["passed"]) for value in checks.values()),
        "checks": checks,
        "outcome_campaign_executed": False,
        "pilot_partition_used": False,
        "future_confirmatory_partition_used": False,
        "scientific_findings_claimed": False,
    }
