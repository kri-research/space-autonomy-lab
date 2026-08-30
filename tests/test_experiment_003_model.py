import numpy as np
from scipy.integrate import solve_ivp

from kri_space_autonomy.experiment_003.config import load_config
from kri_space_autonomy.experiment_003.model import (
    observability_diagnostics,
    piecewise_disturbance_covariance,
    propagate_mean,
    transition_matrices,
)


def config():
    return load_config("experiments/003/config.json")


def test_exact_estimator_transition_matches_independent_dop853_reference():
    _, production = config()
    fixtures = (
        (np.array([100.0, -0.15, 0.0]), -0.04, 0.003),
        (np.array([6.5, -0.02, 0.03]), 0.05, -0.006),
        (np.array([20.0, 0.10, -0.05]), 0.0, 0.0),
    )
    for initial, command, disturbance in fixtures:
        expected = propagate_mean(
            initial,
            command,
            production.command_period_s,
            production.actuator_time_constant_s,
            disturbance,
        )

        def rhs(_time, state, _command=command, _disturbance=disturbance):
            return np.array(
                [
                    state[1],
                    state[2] + _disturbance,
                    (_command - state[2]) / production.actuator_time_constant_s,
                ]
            )

        reference = solve_ivp(
            rhs,
            (0.0, production.command_period_s),
            initial,
            method="DOP853",
            rtol=1e-13,
            atol=1e-14,
        ).y[:, -1]
        assert np.max(np.abs(expected - reference)) <= 2e-12


def test_exact_transition_has_constant_command_semigroup_property():
    _, production = config()
    initial = np.array([87.0, -0.12, 0.015])
    command = -0.03
    one = propagate_mean(initial, command, 1.0, production.actuator_time_constant_s)
    two_steps = propagate_mean(one, command, 1.0, production.actuator_time_constant_s)
    direct = propagate_mean(initial, command, 2.0, production.actuator_time_constant_s)
    assert np.allclose(two_steps, direct, atol=2e-14, rtol=2e-14)


def test_piecewise_process_covariance_is_exactly_symmetric_positive_semidefinite():
    study, production = config()
    covariance = piecewise_disturbance_covariance(
        production.command_period_s,
        production.exogenous_period_s,
        production.process_accel_sigma_mps2,
        study.actuator_model_process_sigma_mps2,
    )
    assert np.array_equal(covariance, covariance.T)
    assert np.linalg.eigvalsh(covariance)[0] >= -1e-20
    assert covariance[2, 2] == study.actuator_model_process_sigma_mps2**2
    assert covariance[1, 1] == 4 * (0.25**2) * production.process_accel_sigma_mps2**2


def test_scaled_discrete_system_is_observable_and_well_conditioned():
    study, production = config()
    diagnostics = observability_diagnostics(
        production.command_period_s,
        production.actuator_time_constant_s,
    )
    assert study.state_order == (
        "range_m",
        "relative_velocity_mps",
        "achieved_acceleration_mps2",
    )
    assert diagnostics.rank == 3
    assert diagnostics.smallest_singular_value > 1e-3
    assert diagnostics.condition_number < 1e5


def test_transition_matrix_state_order_is_explicit():
    _, production = config()
    transition, command = transition_matrices(
        production.command_period_s,
        production.actuator_time_constant_s,
    )
    assert transition.shape == (3, 3)
    assert command.shape == (3,)
    assert transition[0, 1] == production.command_period_s
    assert transition[2, 2] == np.exp(
        -production.command_period_s / production.actuator_time_constant_s
    )
