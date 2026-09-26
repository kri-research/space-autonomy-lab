from dataclasses import replace
from fractions import Fraction as Q

import pytest

from iaa.types import ObservationPacket, StateBox
from sa02.bridge import checker_input
from sa02.estimator import Observer
from sa02.intervals import interval
from sa02.model import FaultHypothesis, HistorySegment, SensorContract


def setup():
    box = StateBox.around((0, -45, 0, 0), (1, 1, 0, 0))
    con = SensorContract(
        hypotheses=(FaultHypothesis("clean", (interval(0),) * 4),), initial_splits=0
    )
    history = (HistorySegment(0, 100, (0, 0)),)
    packet = ObservationPacket("p", 0, "range", 45.0, 0, 40)
    return box, con, history, packet


def test_inconsistency_cannot_be_cleared_by_resource_exhaustion():
    box, con, history, p = setup()
    observer = Observer(box, con)
    bad = replace(p, packet_id="bad", value=100.0)
    first = observer.update((p, bad), history, 100)
    assert first.status == "inconsistent_observations"
    after = observer.update((p,) * 513, history, 100)
    assert after.status == "inconsistent_observations"
    assert not after.cells and checker_input(after).kind == "unsupported"


def test_estimate_schema_must_be_valid_for_positive_bridge():
    box, con, history, p = setup()
    estimate = Observer(box, con).update((p,), history, 100)
    with pytest.raises(ValueError, match="schema"):
        checker_input(replace(estimate, schema="unknown-estimator-schema"))


def test_contract_cannot_change_through_mutable_hypothesis_list():
    hypotheses = [FaultHypothesis("clean", (interval(0),) * 4)]
    contract = SensorContract(hypotheses=hypotheses)
    hypotheses.clear()
    assert len(contract.hypotheses) == 1


def test_latent_bias_boundaries_are_retained_across_repeated_packets():
    box, _, history, p = setup()
    z = interval(0)
    con = SensorContract(
        hypotheses=(FaultHypothesis("bias", (z, z, interval(Q(2, 5)), z)),), initial_splits=0
    )
    observer = Observer(box, con)
    packets = tuple(replace(p, packet_id=f"repeat-{i}", sequence=i, value=45.41) for i in range(4))
    est = observer.update(packets, history, 100)
    assert est.contains_state((0, -45, 0, 0))
    assert all(c.bounds[6].contains(Q(2, 5)) for c in est.cells)


@pytest.mark.parametrize("duration", [Q(1, 100), Q(1, 5), Q(1), Q(3)])
@pytest.mark.parametrize("eta", [Q(4, 5), Q(1)])
def test_hcw_propagation_contains_independent_rational_matrix_tail(duration, eta):
    from iaa.types import StateBox
    from sa02.estimator import advance
    from sa02.model import Budget, HistorySegment
    from sa02.oracle import hcw_point_bounds

    initial = (Q(1, 2), Q(-45), Q(1, 100), Q(-1, 50))
    action = (Q(1, 100), Q(-1, 100))
    oracle = hcw_point_bounds(initial, action, duration, eta, (Q(1, 100000), Q(-1, 100000)))
    box = StateBox.around(initial, (Q(1, 10000),) * 4)
    ms = int(duration * 1000)
    result, _ = advance(box, (HistorySegment(0, ms, action),), 0, ms, Budget(1000))
    assert all(
        a <= lo <= hi <= b
        for a, (lo, hi), b in zip(result.lower, oracle, result.upper, strict=True)
    )


def test_full_observer_retains_static_exact_bias_oracle_vertices():
    from sa02.intervals import Interval
    from sa02.oracle import vertices

    z = interval(0)
    box = StateBox.around((0, -45, 0, 0), (0, 1, 0, 0))
    con = SensorContract(
        hypotheses=(FaultHypothesis("persistent", (z, z, Interval(-1, 1), z)),),
        initial_splits=0,
        range_error_m=Q(1, 10),
    )
    packet = ObservationPacket("linear-range", 0, "range", 45.0, 0, 0, timestamp_uncertainty_ms=0)
    est = Observer(box, con).update((packet,), (), 0)
    reference = vertices([(-46, -44), (-1, 1)], [((-1, 1), Q(449, 10), Q(451, 10))])
    assert reference
    for y, bias in reference:
        assert any(c.contains_state((0, y, 0, 0)) and c.bounds[6].contains(bias) for c in est.cells)


def test_biases_and_window_are_immutable_input_snapshots():
    biases = [interval(0)] * 4
    window = [0, 100]
    hypothesis = FaultHypothesis("stable", biases, window)
    biases[0] = interval(1)
    window[1] = 200
    assert hypothesis.biases[0] == interval(0)
    assert hypothesis.active_window_ms == (0, 100)


def test_sensor_family_evaluation_is_not_inferred_from_fixture_name():
    from iaa.fixtures import Fixture
    from iaa.plant import SensorFaults
    from sa02.development import injected_offset_schedule_covered

    contract = SensorContract()
    unsupported = Fixture("arbitrary-name", faults=SensorFaults(range_bias_m=2.0))
    supported = Fixture("sa02_outside_sensor_model", faults=SensorFaults(range_bias_m=0.3))
    assert not injected_offset_schedule_covered(unsupported, contract)
    assert injected_offset_schedule_covered(supported, contract)
    assert injected_offset_schedule_covered(Fixture("no-fault"), contract)


@pytest.mark.parametrize("offset", [-2, 2])
@pytest.mark.parametrize("sign", [-1, 1])
def test_extreme_shared_bias_and_acquisition_time_bounds(offset, sign):
    from iaa.plant import SensorFaults, flow, observe

    x = (0.5, -45.0, 0.02, -0.03)
    action = (Q(1, 100), Q(-1, 100))
    true_time = (500 + offset) / 1000
    actual = flow(x, action, true_time, 0.8)
    fault = SensorFaults(
        start_ms=0,
        common_position_bias_m=(sign * 0.5, -sign * 0.5),
        range_bias_m=sign * 0.4,
        bearing_bias_rad=sign * 0.02,
    )
    packets, _ = observe(actual, 500, 0, fault)
    initial = StateBox.around(x, (Q(1, 10000),) * 4)
    estimate = Observer(initial).update(packets, (HistorySegment(0, 600, action),), 600)
    assert estimate.contains_state(flow(x, action, 0.6, 0.8))
    assert "persistent_shared_and_channels" in estimate.diagnostics["hypotheses"]


def test_numerical_failure_is_explicit_and_cannot_reach_positive_checker(monkeypatch):
    import sa02.estimator as implementation

    box, con, history, p = setup()

    def fail(*args):
        raise ArithmeticError("injected validation failure")

    monkeypatch.setattr(implementation, "sqrt_bounds", fail)
    estimate = Observer(box, con).update((p,), history, 100)
    assert estimate.status == "numerical_or_history_failure"
    assert not estimate.cells and checker_input(estimate).kind == "unsupported"
