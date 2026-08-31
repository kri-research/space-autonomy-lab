import inspect

import numpy as np

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.control import (
    DeterministicHoldController,
    EstimatedGeometryMonitor,
    PlanarControllerDecision,
    observation_from_snapshot,
)
from kri_space_autonomy.experiment_004.dynamics import propagate_exact
from kri_space_autonomy.experiment_004.estimator import (
    FilterHealth,
    PacketDisposition,
    PlanarNavigationFilter,
)
from kri_space_autonomy.experiment_004.measurements import (
    MeasurementFault,
    PlanarNavigationPacket,
    navigation_packet,
)


def config():
    return load_config("experiments/004/config.json")


def packet(filter_, sequence, measured, received, state, factor=1.0):
    return PlanarNavigationPacket(
        sequence,
        measured,
        received,
        np.asarray(state, dtype=np.float64),
        filter_.nominal_measurement_covariance * factor,
    )


def test_four_state_current_measurement_update_is_deterministic():
    study = config()
    first = PlanarNavigationFilter(study)
    second = PlanarNavigationFilter(study)
    state = study.initial_mean_array
    first_update = first.ingest(packet(first, 0, 0.0, 0.0, state))
    second_update = second.ingest(packet(second, 0, 0.0, 0.0, state))
    assert first_update.disposition is PacketDisposition.ACCEPTED
    assert second_update.disposition is PacketDisposition.ACCEPTED
    assert np.array_equal(first.snapshot().mean, second.snapshot().mean)
    assert np.array_equal(first.snapshot().covariance, second.snapshot().covariance)
    assert first.snapshot().health is FilterHealth.VALID


def test_one_period_fixed_lag_replay_matches_chronological_filtering():
    study = config()
    command = np.array([0.001, 0.002])
    state0 = study.initial_mean_array
    state1 = propagate_exact(state0, command, study.mean_motion_rad_s, 1.0)
    direct = PlanarNavigationFilter(study)
    direct.ingest(packet(direct, 0, 0.0, 0.0, state0))
    direct.advance(command, 1.0)
    direct.ingest(packet(direct, 1, 1.0, 1.0, state1))
    delayed = PlanarNavigationFilter(study)
    delayed.advance(command, 1.0)
    delayed.ingest(packet(delayed, 0, 0.0, 1.0, state0))
    delayed.ingest(packet(delayed, 1, 1.0, 1.0, state1))
    assert np.allclose(direct.snapshot().mean, delayed.snapshot().mean, atol=1e-12)
    assert np.allclose(direct.snapshot().covariance, delayed.snapshot().covariance, atol=1e-12)
    assert delayed.snapshot().accepted_updates == 2


def test_duplicate_and_off_grid_packets_fail_closed():
    study = config()
    filter_ = PlanarNavigationFilter(study)
    original = packet(filter_, 0, 0.0, 0.0, study.initial_mean_array)
    filter_.ingest(original)
    filter_.advance(np.zeros(2), 1.0)
    duplicate = PlanarNavigationPacket(
        original.sequence_id,
        original.measured_at_s,
        1.0,
        original.measurement,
        original.reported_covariance,
    )
    assert filter_.ingest(duplicate).disposition is PacketDisposition.DUPLICATE
    off_grid = PlanarNavigationPacket(
        2,
        0.5,
        1.0,
        original.measurement,
        original.reported_covariance,
    )
    assert filter_.ingest(off_grid).disposition is PacketDisposition.INVALID
    assert filter_.snapshot().health is FilterHealth.DEGRADED


def test_packet_covariance_units_shape_symmetry_and_positive_definiteness_are_enforced():
    study = config()
    covariance = study.nominal_measurement_covariance
    PlanarNavigationPacket(0, 0.0, 0.0, study.initial_mean_array, covariance)
    asymmetric = covariance.copy()
    asymmetric[0, 1] = 1.0
    try:
        PlanarNavigationPacket(0, 0.0, 0.0, study.initial_mean_array, asymmetric)
    except ValueError as exc:
        assert "symmetric" in str(exc)
    else:
        raise AssertionError("asymmetric covariance was accepted")


def test_fault_topology_is_channel_bounded_and_not_exposed_in_packet():
    study = config()
    fault = MeasurementFault(
        "bias",
        "primary",
        10.0,
        20.0,
        additive_bias=(5.0, 0.0, 0.0, 0.0),
    )
    kwargs = {
        "sequence_id": 10,
        "measured_at_s": 10.0,
        "received_at_s": 10.0,
        "latent_state": np.array([0.0, -50.0, 0.0, 0.0]),
        "measurement_noise": np.zeros(4),
        "quantization": np.asarray(study.measurement_quantization),
        "nominal_covariance": study.nominal_measurement_covariance,
        "fault": fault,
        "previous_packet": None,
    }
    primary = navigation_packet(channel="primary", **kwargs)
    monitor = navigation_packet(channel="monitor", **kwargs)
    assert primary is not None and monitor is not None
    assert primary.measurement[0] == monitor.measurement[0] + 5.0
    assert not hasattr(primary, "fault")
    assert not hasattr(primary, "channel")


def test_vector_controller_and_monitor_receive_estimates_not_simulator_state():
    study = config()
    filter_ = PlanarNavigationFilter(study)
    filter_.ingest(packet(filter_, 0, 0.0, 0.0, study.initial_mean_array))
    controller = DeterministicHoldController(study)
    observation = observation_from_snapshot(filter_.snapshot())
    decision = controller.decide(observation)
    assert decision.acceleration_mps2.shape == (2,)
    assert np.linalg.norm(decision.acceleration_mps2) <= study.max_acceleration_mps2 + 1e-12
    monitor = EstimatedGeometryMonitor(study, controller, controller.controller_identity)
    gated = monitor.gate(filter_.snapshot(), decision)
    assert gated.executed_acceleration_mps2.shape == (2,)

    import kri_space_autonomy.experiment_004.control as control_module
    import kri_space_autonomy.experiment_004.estimator as estimator_module

    online_source = inspect.getsource(control_module) + inspect.getsource(estimator_module)
    assert "latent_state" not in online_source
    assert "fault_parameters" not in online_source
    assert "IndependentPlanarEvaluator" not in online_source


def test_divergence_and_wrong_controller_identity_override():
    study = config()
    filter_ = PlanarNavigationFilter(study)
    diverged = filter_.advance(np.array([1e9, 1e9]), 1.0)
    assert diverged.health is FilterHealth.DIVERGED
    controller = DeterministicHoldController(study)
    monitor = EstimatedGeometryMonitor(study, controller, controller.controller_identity)
    wrong = PlanarControllerDecision(np.zeros(2), "wrong")
    result = monitor.gate(diverged, wrong)
    assert result.overridden
    assert result.reason == "CONTROLLER_INTEGRITY"
