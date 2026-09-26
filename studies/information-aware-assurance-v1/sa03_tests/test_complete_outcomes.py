"""Extra complete-outcome checks, separate from the recorded development population."""

from dataclasses import replace
from fractions import Fraction as Q

import pytest

from iaa.plant import SensorFaults, flow, observe
from iaa.types import StateBox, encode
from sa02.estimator import Observer
from sa02.model import Budget, HistorySegment
from sa03.development import Case, prepare
from sa03.forecast import outcome_partition
from sa03.model import Context
from sa03.policy import build_option, decide, dispatch, verify_tree


@pytest.mark.parametrize("channel", ["range", "bearing"])
@pytest.mark.parametrize("eta", [Q(4, 5), Q(1)])
def test_timestamp_bias_and_nonzero_queue_keep_realized_world_in_every_matching_leaf(channel, eta):
    # Independent binary64 corroboration of the analytical cover, not calibration.
    from sa02.model import SensorContract

    initial = (Q(1, 2), Q(-45), Q(1, 100), Q(-1, 50))
    prior = StateBox.around(initial, (Q(1, 100),) * 2 + (Q(1, 10000),) * 2)
    sensors = SensorContract(initial_splits=0)
    estimate = Observer(prior, sensors).update((), (HistorySegment(0, 100, (0, 0)),), 100)
    queue = (Q(1, 100), Q(-1, 100))
    context = Context(estimate, sensors, queued_action=queue)
    domain, leaves, _ = outcome_partition(context, channel, Budget(50000))
    bias = (Q(3, 10), Q(-1, 5), Q(1, 4), Q(1, 100))
    faults = SensorFaults(
        start_ms=0, common_position_bias_m=(0.3, -0.2), range_bias_m=0.25, bearing_bias_rad=0.01
    )
    w = (Q(1, 100000), Q(-1, 100000))
    at100 = flow(initial, (0, 0), Q(1, 10), eta, w)
    at200 = flow(at100, queue, Q(1, 10), eta, w)
    application = flow(at200, (0, 0), Q(1, 2), eta, w)
    error = sensors.range_error_m if channel == "range" else sensors.bearing_error_rad
    for acquisition_ms in (248, 250, 252):
        acquired = flow(at200, (0, 0), Q(acquisition_ms - 200, 1000), eta, w)
        packets, _ = observe(acquired, 250, 1, faults)
        value = next(p.value for p in packets if p.channel == channel)
        for factor in (-Q(99, 100), Q(0), Q(99, 100)):
            reading = Q(str(value)) + factor * error
            matching = [leaf for leaf in leaves if leaf["reading"].contains(reading)]
            assert domain.contains(reading) and matching
            for leaf in matching:
                assert any(
                    c.hypothesis == "persistent_shared_and_channels"
                    and c.contains_state(application)
                    and all(b.contains(v) for b, v in zip(c.bounds[4:], bias, strict=True))
                    for c in leaf["cells"]
                )


def test_one_unresolved_reading_prevents_universal_protection(monkeypatch):
    import sa03.policy as policy

    original = policy.choose_action
    calls = 0

    def fail_one(cells, budget):
        nonlocal calls
        calls += 1
        if calls == 3:
            return None, [{"safe": False, "useful": False, "reason": "injected_search_failure"}]
        return original(cells, budget)

    monkeypatch.setattr(policy, "choose_action", fail_one)
    context = prepare(Case("one-unresolved-branch"))
    result = build_option(context, "range", Budget(50000))
    assert calls > 3
    assert result["status"] == "unresolved" and not result["all_outcome_protection"]
    assert not result["negative_certificate"]
    assert any(leaf["retained_cells"] and leaf["result"] is None for leaf in result["leaves"])
    assert not verify_tree(context, result)


def test_missing_observation_action_is_mandatory(monkeypatch):
    import sa03.policy as policy

    monkeypatch.setattr(policy, "choose_action", lambda cells, budget: (None, []))
    result = build_option(prepare(Case("missing-branch")), "range", Budget(50000))
    assert result["status"] == "unresolved"
    assert result["reason"] == "no_supported_missing_observation_branch"
    assert not result["all_outcome_protection"]


def test_assumption_and_queue_changes_invalidate_an_existing_tree():
    context = prepare(Case("bindings"))
    plan = decide(context, "fixed_range")
    changed = replace(context, queued_action=(Q(1, 100), Q(0)))
    assert not verify_tree(changed, plan["certificate"])
    assert not dispatch(changed, plan, (), 700)["credited"]
    invalid = replace(context, assumptions_supported=False)
    assert not verify_tree(invalid, plan["certificate"])
    assert not dispatch(invalid, plan, (), 700)["credited"]


def test_future_conflicting_receipt_cannot_change_current_received_action():
    from iaa.types import ObservationPacket

    context = prepare(Case("receipt-order"))
    plan = decide(context, "fixed_range")
    pid = "sa03-" + context.identity()[:16] + "-range"
    received = ObservationPacket(pid, 1, "range", 40.6, 250, 290)
    future = replace(received, value=39.4, available_ms=850)
    actual = dispatch(context, plan, (received, future), 700)
    expected = dispatch(context, plan, (received,), 700)
    assert encode(actual) == encode(expected)


def test_existing_observation_conditioned_estimate_connects_to_sensing_policy():
    context = prepare(Case("observed-history", warm_packets=True))
    assert context.estimate.status == "updated"
    assert context.estimate.diagnostics["retained_packets"] == 2
    policy = decide(context, "decision_aware")
    assert policy["certificate"]["all_outcome_protection"]
    assert verify_tree(context, policy["certificate"])
    assert policy["certificate"]["channel"] is None
