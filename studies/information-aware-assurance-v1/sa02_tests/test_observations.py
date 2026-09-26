import math
from dataclasses import replace
from fractions import Fraction as Q

import pytest

from iaa.assurance import check
from iaa.plant import SensorFaults, flow, observe
from iaa.types import Command, ObservationPacket, StateBox, Status
from sa02.bridge import checker_input
from sa02.estimator import Observer, predict_to_application
from sa02.intervals import interval
from sa02.model import (
    FaultHypothesis,
    HistorySegment,
    SensorContract,
    initial_cells,
    merge_cells,
)


def history(t):
    return (HistorySegment(0, t, (0, 0)),) if t else ()


def initial():
    return StateBox.around((0, -45, 0, 0), (1, 1, Q(1, 100), Q(1, 100)))


def no_bias(**kw):
    return SensorContract(
        hypotheses=(FaultHypothesis("nominal", (interval(0),) * 4),), initial_splits=0, **kw
    )


def pair(y=-45, t=0, sequence=0, **faults):
    return observe((0, y, 0, 0), t, sequence, SensorFaults(**faults))[0]


def test_nominal_contracts_position_and_preserves_actual_state():
    est = Observer(initial(), no_bias()).update(pair(), history(100), 100)
    assert est.status == "updated" and est.contains_state((0, -45, 0, 0))
    assert est.hull().upper[1] - est.hull().lower[1] < Q(1, 10)
    assert est.scope == "outer_observation_consistency_only"
    with pytest.raises(ValueError, match="attainable"):
        est.negative_certificate_input()
    assert check(checker_input(est), Command((0, 0), 200, 700, "r")).status == Status.BOUNDED_PREFIX


def test_indistinguishable_bias_explanations_remain():
    z = interval(0)
    con = SensorContract(
        hypotheses=(
            FaultHypothesis("zero", (z, z, z, z)),
            FaultHypothesis("one_metre", (z, z, interval(1), z)),
        ),
        initial_splits=0,
    )
    p = pair(y=-45)[0]
    est = Observer(initial(), con).update((p,), history(100), 100)
    assert set(est.diagnostics["hypotheses"]) == {"zero", "one_metre"}
    assert est.contains_state((0, -45, 0, 0)) and est.contains_state((0, -44, 0, 0))


def test_incompatible_hypothesis_excluded_by_actual_interval_constraint():
    z = interval(0)
    con = SensorContract(
        hypotheses=(
            FaultHypothesis("zero", (z, z, z, z)),
            FaultHypothesis("bias_one", (z, z, interval(1), z)),
        ),
        initial_splits=0,
    )
    box = StateBox.around((0, -45, 0, 0), (Q(1, 100),) * 4)
    p = replace(pair()[0], value=46.0)
    est = Observer(box, con).update((p,), history(100), 100)
    assert est.diagnostics["hypotheses"] == ["bias_one"]


def test_delayed_out_of_order_replay_uses_acquisition_time():
    early = tuple(replace(p, available_ms=900) for p in pair(t=0))
    late = pair(t=500, sequence=1)
    observer = Observer(initial(), no_bias())
    first = observer.update(late, history(600), 600)
    assert first.contains_state((0, -45, 0, 0))
    est = observer.update(early, history(1000), 1000)
    batch = Observer(initial(), no_bias()).update(early + late, history(1000), 1000)
    assert est.diagnostics["replayed_out_of_order"]
    assert est.cells == batch.cells and est.contains_state((0, -45, 0, 0))


def test_future_data_cannot_narrow_current_decision():
    p = pair(t=500, sequence=1)
    a = Observer(initial()).update(p, history(100), 100)
    b = Observer(initial()).update((), history(100), 100)
    assert a.cells == b.cells and a.diagnostics["ignored_future"] == 2


def test_missing_and_stale_are_prediction_not_fictitious_observations():
    observer = Observer(initial(), no_bias())
    first = observer.update(pair(), history(100), 100)
    est = observer.update((), history(1000), 1000)
    assert first.status == "updated" and est.status == "prediction_only_missing_or_stale"
    assert est.contains_state((0, -45, 0, 0)) and est.diagnostics["retained_packets"] == 2


def test_contradiction_is_latched_and_never_physical_impossibility():
    observer = Observer(initial(), no_bias())
    good = pair()[0]
    bad = replace(good, packet_id="contradiction", value=100.0)
    est = observer.update((good, bad), history(100), 100)
    assert est.status == "inconsistent_observations" and not est.cells
    assert est.prior_at_decision is not None
    assert checker_input(est).kind == "unsupported"
    assert observer.update((), history(200), 200).status == "inconsistent_observations"


def test_duplicate_is_idempotent_but_conflicting_identity_is_rejected():
    p = pair()
    observer = Observer(initial(), no_bias())
    a = observer.update(p, history(100), 100)
    b = observer.update(p, history(100), 100)
    assert a.cells == b.cells and b.diagnostics["retained_packets"] == 2
    c = observer.update((replace(p[0], value=46.0),), history(100), 100)
    assert c.status == "inconsistent_observations"


@pytest.mark.parametrize("angle", [math.pi, -math.pi, math.pi - 1e-8, -math.pi + 1e-8])
def test_bearing_wrap_does_not_exclude_negative_x_axis(angle):
    box = StateBox.around((-45, 0, 0, 0), (Q(1, 100),) * 4)
    p = ObservationPacket("b", 0, "bearing", angle, 0, 70, unit="rad")
    e = Observer(box, no_bias()).update((p,), history(100), 100)
    assert e.cells and e.contains_state(flow((-45, 0, 0, 0), (0, 0), 0.1))


def test_origin_bearing_is_explicitly_uninformative():
    box = StateBox.around((0, 0, 0, 0), (0, 0, 0, 0))
    p = ObservationPacket("b", 0, "bearing", 0.0, 0, 0, unit="rad", timestamp_uncertainty_ms=0)
    e = Observer(box, no_bias()).update((p,), (), 0)
    assert e.diagnostics["bearing_degeneracy"] and e.contains_state((0, 0, 0, 0))


def test_timestamp_uncertainty_bound_and_malformed_packets_visible():
    p = replace(pair()[0], timestamp_uncertainty_ms=100)
    e = Observer(initial()).update((p, {"truth": 0}), history(100), 100)
    assert e.status == "unsupported_packets_ignored" and e.diagnostics["ignored_invalid"] == 2
    assert checker_input(e).kind == "unsupported"


def test_state_at_actual_acquisition_in_timestamp_interval_retained():
    x = (Q(1, 2), Q(-45), Q(1, 100), Q(1, 50))
    packet = pair()[0]
    state = flow(x, (0, 0), 0.501)
    p = replace(
        packet,
        packet_id="uncertain",
        value=math.hypot(state[0], state[1]),
        acquired_ms=500,
        available_ms=550,
    )
    box = StateBox.around(x, (Q(1, 10000),) * 4)
    e = Observer(box, no_bias()).update((p,), history(600), 600)
    assert e.contains_state(flow(x, (0, 0), 0.6))


def test_window_straddling_branches_are_not_false_exclusions():
    h = SensorContract().hypotheses[-1]
    assert h.modes(4998, 5002) == (True, False)
    assert h.modes(9998, 10002) == (True, False)
    assert h.modes(6000, 6000) == (True,)
    assert h.modes(10000, 10000) == (False,)


def test_memory_coarsening_preserves_union_and_hypotheses():
    contract = SensorContract(max_cells=4, initial_splits=2)
    original = initial_cells(initial(), replace(contract, max_cells=64))
    compressed, merges = merge_cells(original, 4)
    assert merges and len(compressed) == 4
    for c in original:
        parent = next(x for x in compressed if x.hypothesis == c.hypothesis)
        assert all(
            a.lo <= b.lo <= b.hi <= a.hi for a, b in zip(parent.bounds, c.bounds, strict=True)
        )


def test_operation_exhaustion_retains_only_fully_propagated_prior():
    e = Observer(initial(), no_bias(max_operations=1)).update(pair(), history(100), 100)
    assert e.status == "resource_exhausted_prior_only" and not e.cells
    e = Observer(initial(), no_bias(max_operations=3)).update(pair(), history(100), 100)
    assert e.status == "resource_exhausted_prior_only" and e.cells
    assert e.contains_state((0, -45, 0, 0))


def test_packet_capacity_retains_old_constraints_without_pruning_hypotheses():
    e = Observer(initial(), no_bias(max_packets=1)).update(pair(), history(100), 100)
    assert e.status == "resource_exhausted_retained_constraints"
    assert e.diagnostics["retained_packets"] == 1 and e.contains_state((0, -45, 0, 0))


def test_history_changes_and_missing_intervals_fail_closed():
    o = Observer(initial())
    o.update(pair(), history(100), 100)
    bad = (HistorySegment(0, 200, (Q(1, 100), 0)),)
    assert o.update((), bad, 200).status == "unsupported_changed_command_history"
    assert Observer(initial()).update((), (), 100).status == "numerical_or_history_failure"


def test_application_age_uses_the_actual_known_queue():
    e = Observer(initial(), no_bias()).update(pair(), history(100), 100)
    q = (HistorySegment(100, 200, (0, 0)),)
    p = predict_to_application(e, q, 200)
    assert p.at_ms == 200 and p.contains_state((0, -45, 0, 0))
    with pytest.raises(ValueError):
        predict_to_application(e, (), 200)
    with pytest.raises(ValueError):
        p.negative_certificate_input()


def test_out_of_contract_bias_need_not_be_detected():
    # Correct time and syntactically valid packet, but unmodelled 0.5 m bias.
    box = StateBox.around((0, -45, 0, 0), (1, 1, 0, 0))
    p = replace(pair()[0], value=45.5)
    e = Observer(box, no_bias()).update((p,), history(100), 100)
    assert e.status == "updated" and e.cells
    assert not e.contains_state((0, -45, 0, 0))
