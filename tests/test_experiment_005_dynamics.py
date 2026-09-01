import numpy as np

from kri_space_autonomy.experiment_005.config import load_config
from kri_space_autonomy.experiment_005.dynamics import (
    circular_chief_state,
    command_to_inertial,
    inertial_to_relative,
    lvlh_angular_velocity_local,
    lvlh_basis,
    pair_from_relative,
    pair_to_relative,
    propagate_fixed,
    relative_to_inertial,
    rk4_step,
    split_pair_state,
)


def config():
    return load_config("experiments/005/config.json")


def test_frame_roundtrip_includes_rotating_velocity_term_at_multiple_phases():
    study = config()
    relative = np.array([-7.0, -65.0, 4.0, -0.08, 0.11, -0.015])
    for phase in (0.0, 0.7, 2.4, 5.8):
        chief = circular_chief_state(
            study.gravitational_parameter_m3_s2,
            study.reference_radius_m,
            phase_rad=phase,
        )
        deputy = relative_to_inertial(chief, relative)
        observed = inertial_to_relative(chief, deputy)
        assert np.max(np.abs(observed[:3] - relative[:3])) <= (
            study.frame_roundtrip_position_tolerance_m
        )
        assert np.max(np.abs(observed[3:] - relative[3:])) <= (
            study.frame_roundtrip_velocity_tolerance_mps
        )
        naive_relative_velocity = lvlh_basis(chief).T @ (deputy[3:] - chief[3:])
        rotating_term = np.cross(lvlh_angular_velocity_local(chief), relative[:3])
        assert np.allclose(naive_relative_velocity, relative[3:] + rotating_term)
        assert not np.allclose(naive_relative_velocity, relative[3:])


def test_local_command_mapping_is_norm_preserving_and_rotates_inertially():
    study = config()
    command = np.array([study.max_acceleration_mps2, 0.0, 0.0])
    chief0 = circular_chief_state(
        study.gravitational_parameter_m3_s2, study.reference_radius_m
    )
    chief1 = circular_chief_state(
        study.gravitational_parameter_m3_s2,
        study.reference_radius_m,
        study.command_period_s,
    )
    inertial0 = command_to_inertial(chief0, command)
    inertial1 = command_to_inertial(chief1, command)
    assert np.linalg.norm(inertial0) == np.linalg.norm(command)
    assert np.allclose(lvlh_basis(chief0).T @ inertial0, command, atol=1e-15)
    assert not np.array_equal(inertial0, inertial1)


def test_partial_interval_uses_canonical_full_steps_plus_endpoint_remainder():
    study = config()
    chief = circular_chief_state(
        study.gravitational_parameter_m3_s2, study.reference_radius_m
    )
    initial = pair_from_relative(chief, study.initial_relative_state)
    command = np.array([0.001, -0.002, 0.0])
    first = rk4_step(
        initial,
        command,
        study.gravitational_parameter_m3_s2,
        study.production_max_step_s,
    )
    expected = rk4_step(
        first,
        command,
        study.gravitational_parameter_m3_s2,
        0.15 - study.production_max_step_s,
    )
    observed = propagate_fixed(
        initial,
        command,
        study.gravitational_parameter_m3_s2,
        0.15,
        study.production_max_step_s,
    )
    assert np.array_equal(observed, expected)


def test_coincident_unforced_chief_and_deputy_remain_identical_under_rk4():
    study = config()
    chief = circular_chief_state(
        study.gravitational_parameter_m3_s2, study.reference_radius_m
    )
    initial = pair_from_relative(chief, np.zeros(6))
    final = propagate_fixed(
        initial,
        np.zeros(3),
        study.gravitational_parameter_m3_s2,
        60.0,
        study.production_max_step_s,
    )
    chief_final, deputy_final = split_pair_state(final)
    assert np.array_equal(chief_final, deputy_final)
    assert np.array_equal(pair_to_relative(final), np.zeros(6))
