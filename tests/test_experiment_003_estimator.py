import inspect

import numpy as np

from kri_space_autonomy.experiment_002.policy import PolicyDecision, ReferenceController
from kri_space_autonomy.experiment_003.config import load_config
from kri_space_autonomy.experiment_003.estimator import (
    FilterHealth,
    NavigationFilter,
    NavigationPacket,
    PacketDisposition,
)
from kri_space_autonomy.experiment_003.interfaces import (
    EstimatedRuntimeGate,
    policy_observation,
)
from kri_space_autonomy.experiment_003.model import propagate_mean


def config():
    return load_config("experiments/003/config.json")


def packet(filter_, sequence, measured, received, state, factor=1.0):
    return NavigationPacket(
        sequence,
        measured,
        received,
        float(state[0]),
        float(state[1]),
        filter_.nominal_measurement_covariance * factor,
    )


def test_current_measurement_update_is_deterministic_and_finite():
    study, production = config()
    first = NavigationFilter(study, production)
    second = NavigationFilter(study, production)
    state = np.array([100.0, -0.15, 0.0])
    first_result = first.ingest(packet(first, 0, 0.0, 0.0, state))
    second_result = second.ingest(packet(second, 0, 0.0, 0.0, state))
    assert first_result.disposition is PacketDisposition.ACCEPTED
    assert second_result.disposition is PacketDisposition.ACCEPTED
    assert np.array_equal(first.snapshot().mean, second.snapshot().mean)
    assert np.array_equal(first.snapshot().covariance, second.snapshot().covariance)
    assert first.snapshot().health is FilterHealth.VALID


def test_one_second_fixed_lag_replay_matches_in_sequence_filtering():
    study, production = config()
    command = -0.02
    state0 = np.array([100.0, -0.15, 0.0])
    state1 = propagate_mean(
        state0,
        command,
        production.command_period_s,
        production.actuator_time_constant_s,
    )

    in_sequence = NavigationFilter(study, production)
    in_sequence.ingest(packet(in_sequence, 0, 0.0, 0.0, state0))
    in_sequence.advance(command, 1.0)
    in_sequence.ingest(packet(in_sequence, 1, 1.0, 1.0, state1))

    delayed = NavigationFilter(study, production)
    delayed.advance(command, 1.0)
    delayed.ingest(packet(delayed, 0, 0.0, 1.0, state0))
    delayed.ingest(packet(delayed, 1, 1.0, 1.0, state1))

    assert np.allclose(delayed.snapshot().mean, in_sequence.snapshot().mean, atol=1e-13)
    assert np.allclose(
        delayed.snapshot().covariance,
        in_sequence.snapshot().covariance,
        atol=1e-13,
    )
    assert delayed.snapshot().accepted_updates == 2


def test_stale_duplicate_is_rejected_without_reusing_the_measurement():
    study, production = config()
    filter_ = NavigationFilter(study, production)
    state = np.array([100.0, -0.15, 0.0])
    original = packet(filter_, 0, 0.0, 0.0, state)
    filter_.ingest(original)
    filter_.advance(0.0, 1.0)
    stale = NavigationPacket(
        original.sequence_id,
        original.measured_at_s,
        1.0,
        original.range_m,
        original.relative_velocity_mps,
        original.reported_covariance,
    )
    diagnostic = filter_.ingest(stale)
    assert diagnostic.disposition is PacketDisposition.DUPLICATE
    assert filter_.snapshot().health is FilterHealth.DEGRADED
    assert filter_.snapshot().invalid_packets == 1


def test_prediction_only_health_degrades_after_frozen_limit():
    study, production = config()
    filter_ = NavigationFilter(study, production)
    filter_.ingest(packet(filter_, 0, 0.0, 0.0, np.array([100.0, -0.15, 0.0])))
    assert filter_.advance(0.0, 1.0).health is FilterHealth.VALID
    assert filter_.advance(0.0, 2.0).health is FilterHealth.VALID
    assert filter_.advance(0.0, 3.0).health is FilterHealth.DEGRADED


def test_covariance_underreporting_fixture_triggers_innovation_rejection():
    study, production = config()
    filter_ = NavigationFilter(study, production)
    state0 = np.array([100.0, -0.15, 0.0])
    filter_.ingest(packet(filter_, 0, 0.0, 0.0, state0))
    filter_.advance(0.0, 1.0)
    biased = np.array([105.0, -0.15, 0.0])
    diagnostic = filter_.ingest(
        packet(
            filter_,
            1,
            1.0,
            1.0,
            biased,
            study.covariance_underreporting_factor,
        )
    )
    assert diagnostic.disposition is PacketDisposition.INNOVATION_REJECTED
    assert diagnostic.nis is not None and diagnostic.nis > study.nis_reject_threshold
    assert filter_.snapshot().health is FilterHealth.DEGRADED


def test_long_nominal_replay_preserves_covariance_integrity():
    study, production = config()
    filter_ = NavigationFilter(study, production)
    filter_.ingest(packet(filter_, 0, 0.0, 0.0, filter_.snapshot().mean))
    for step in range(1, 601):
        prior = filter_.advance(0.0, float(step))
        diagnostic = filter_.ingest(
            packet(filter_, step, float(step), float(step), prior.mean)
        )
        assert diagnostic.disposition is PacketDisposition.ACCEPTED
        covariance = filter_.snapshot().covariance
        assert np.all(np.isfinite(covariance))
        assert np.max(np.abs(covariance - covariance.T)) <= 1e-15
        assert np.linalg.eigvalsh(covariance)[0] >= -1e-12
    assert filter_.snapshot().health is FilterHealth.VALID


def test_divergence_fails_closed_and_runtime_gate_uses_no_hidden_state():
    study, production = config()
    filter_ = NavigationFilter(study, production)
    diverged = filter_.advance(1e9, 1.0)
    assert diverged.health is FilterHealth.DIVERGED
    observation = policy_observation(diverged, 0.9, 1.0)
    assert observation.range_m is None
    assert observation.relative_velocity_mps is None
    fallback = ReferenceController(production)
    gate = EstimatedRuntimeGate(study, production, fallback, "expected")
    decision = PolicyDecision(-0.05, 1.0, -1.0, "expected")
    result = gate.gate(diverged, 0.9, decision)
    assert result.overridden
    assert result.reason == "ESTIMATOR_DIVERGED"

    import kri_space_autonomy.experiment_003.estimator as estimator_module
    import kri_space_autonomy.experiment_003.interfaces as interface_module

    online_source = inspect.getsource(estimator_module) + inspect.getsource(interface_module)
    assert "TruthState" not in online_source
    assert "IndependentEvaluator" not in online_source
