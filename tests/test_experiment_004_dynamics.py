import numpy as np
from scipy.integrate import solve_ivp

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.dynamics import (
    closed_form_matrices,
    continuous_matrices,
    discrete_matrices,
    observability_diagnostics,
    piecewise_acceleration_covariance,
    propagate_exact,
)


def config():
    return load_config("experiments/004/config.json")


def test_orbital_reference_and_hcw_sign_convention_are_explicit():
    study = config()
    assert study.central_body == "Earth"
    assert study.reference_radius_m == 6_778_137.0
    assert study.mean_motion_rad_s == study.derived_mean_motion_rad_s
    assert 5553.0 < study.orbital_period_s < 5554.0
    transition_rate, input_rate = continuous_matrices(study.mean_motion_rad_s)
    assert transition_rate[2, 0] == 3.0 * study.mean_motion_rad_s**2
    assert transition_rate[2, 3] == 2.0 * study.mean_motion_rad_s
    assert transition_rate[3, 2] == -2.0 * study.mean_motion_rad_s
    assert np.array_equal(
        input_rate,
        np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]),
    )


def test_augmented_exponential_matches_independent_closed_form():
    study = config()
    for duration in (0.0, 0.25, 1.0, 10.0, 600.0):
        observed = discrete_matrices(study.mean_motion_rad_s, duration)
        expected = closed_form_matrices(study.mean_motion_rad_s, duration)
        assert np.allclose(observed[0], expected[0], rtol=2e-12, atol=2e-12)
        assert np.allclose(observed[1], expected[1], rtol=2e-12, atol=2e-12)


def test_exact_zoh_propagation_matches_scalar_dop853_reference():
    study = config()
    initial = np.array([4.0, -40.0, -0.03, 0.08])
    command = np.array([-0.007, 0.003])
    expected = propagate_exact(initial, command, study.mean_motion_rad_s, 1.0)
    n = study.mean_motion_rad_s

    def rhs(_time, state):
        x_pos, _y_pos, vx, vy = state
        return np.array(
            [
                vx,
                vy,
                3.0 * n**2 * x_pos + 2.0 * n * vy + command[0],
                -2.0 * n * vx + command[1],
            ]
        )

    solution = solve_ivp(
        rhs,
        (0.0, 1.0),
        initial,
        method="DOP853",
        rtol=1e-12,
        atol=np.array([1e-12, 1e-12, 1e-14, 1e-14]),
        max_step=0.05,
    )
    assert solution.success
    assert np.max(np.abs(expected[:2] - solution.y[:2, -1])) <= 1e-10
    assert np.max(np.abs(expected[2:] - solution.y[2:, -1])) <= 1e-12


def test_exact_transition_and_input_maps_have_semigroup_property():
    study = config()
    phi_a, gamma_a = discrete_matrices(study.mean_motion_rad_s, 0.4)
    phi_b, gamma_b = discrete_matrices(study.mean_motion_rad_s, 0.6)
    phi, gamma = discrete_matrices(study.mean_motion_rad_s, 1.0)
    assert np.allclose(phi, phi_b @ phi_a, rtol=2e-13, atol=2e-13)
    assert np.allclose(gamma, phi_b @ gamma_a + gamma_b, rtol=2e-13, atol=2e-13)


def test_piecewise_acceleration_covariance_is_exact_symmetric_psd():
    study = config()
    covariance = piecewise_acceleration_covariance(
        study.mean_motion_rad_s,
        study.command_period_s,
        study.process_acceleration_draw_period_s,
        study.process_acceleration_sigma_mps2,
    )
    assert np.array_equal(covariance, covariance.T)
    assert np.linalg.eigvalsh(covariance)[0] >= -1e-20
    assert covariance.shape == (4, 4)


def test_full_and_position_only_sampled_systems_are_observable():
    study = config()
    full = observability_diagnostics(
        study.mean_motion_rad_s,
        study.command_period_s,
        position_only=False,
    )
    position = observability_diagnostics(
        study.mean_motion_rad_s,
        study.command_period_s,
        position_only=True,
    )
    assert full.rank == 4
    assert position.rank == 4
    assert position.smallest_singular_value > 1e-4
    assert position.condition_number < 1e7
