from fractions import Fraction as Q

import pytest

from iaa.types import identity, primitive
from sa04.compute import check_action, future_schedule, initial_arm, schedule_check
from sa04.fixtures import at_time, delivered_packet, initial_input
from sa04.gate import Gate


def setup():
    raw, truth = initial_input()
    receipts = delivered_packet(raw, truth, "range")
    payload = dict(input=at_time(raw, 650, receipts), action=["0", "1/50"])
    result, _ = check_action(payload)
    assert result["status"] == "checked_window_prefix"
    return Gate(raw, initial_arm(raw)), raw, payload, primitive(result)


def test_early_arrival_waits_then_window_and_fixed_expiry():
    gate, _, payload, proof = setup()
    assert gate.admit(proof, payload, 675)["scheduled"]
    assert not gate.tick(699)["newly_applied"]
    assert gate.tick(705, live_binding_sha256=identity(payload))["newly_applied"]
    assert gate.tick(1199)["action"] == ["0", "1/50"]
    assert gate.tick(1200)["action"] == ["0", "0"]
    assert gate.tick(4199)["credited"]
    assert not gate.tick(4200)["credited"]


@pytest.mark.parametrize("at", [99, 649, 701, 4201])
def test_bad_ready_times(at):
    gate, _, payload, proof = setup()
    assert not gate.admit(proof, payload, at)["scheduled"]


def test_missing_window_does_not_move_action():
    gate, _, payload, proof = setup()
    gate.admit(proof, payload, 675)
    value = gate.tick(711)
    assert not value["newly_applied"] and value["action"] == ["0", "0"]


def test_duplicate_and_later_mutation():
    gate, _, payload, proof = setup()
    assert gate.admit(proof, payload, 675)["scheduled"]
    assert not gate.admit(proof, payload, 675)["scheduled"]
    proof["binding"]["action"] = ["1", "1"]
    assert gate.tick(700, live_binding_sha256=identity(payload))["action"] == ["0", "1/50"]


@pytest.mark.parametrize(
    "field",
    [
        "payload_sha256",
        "observations_sha256",
        "history_sha256",
        "model_sha256",
        "sensors_sha256",
        "expires_ms",
        "application_window_ms",
        "action",
    ],
)
def test_certificate_cannot_be_rebound(field):
    gate, _, payload, proof = setup()
    proof["binding"][field] = "corrupt"
    assert not gate.admit(proof, payload, 675)["scheduled"]


@pytest.mark.parametrize("field", ["schema", "scope", "status", "uncertainty_sha256"])
def test_bad_certificate_scope(field):
    gate, _, payload, proof = setup()
    proof[field] = "unsupported"
    assert not gate.admit(proof, payload, 675)["scheduled"]


def test_stale_estimate_and_changed_assumptions():
    gate, _, payload, proof = setup()
    proof["uncertainty"]["at_ms"] = 100
    proof["uncertainty_sha256"] = identity(proof["uncertainty"])
    assert not gate.admit(proof, payload, 675)["scheduled"]
    gate, _, payload, _ = setup()
    payload["input"]["sensors"]["range_error_m"] = "1/10"
    proof, _ = check_action(payload)
    assert not gate.admit(primitive(proof), payload, 675)["scheduled"]


def test_invalidate_and_clock_regression():
    gate, _, payload, proof = setup()
    gate.admit(proof, payload, 675)
    gate.invalidate()
    assert not gate.tick(700)["credited"]
    with pytest.raises(ValueError):
        gate.tick(699)


@pytest.mark.parametrize("action", [["0.021", "0"], ["0.02", "0.02"], ["NaN", "0"]])
def test_saturation_never_silently_clipped(action):
    _, _, payload, _ = setup()
    payload["action"] = action
    with pytest.raises(ValueError):
        check_action(payload)


def test_jitter_enclosure_contains_separate_exact_hcw_reference():
    from iaa.enclosure import step
    from iaa.types import StateBox
    from sa02.oracle import hcw_point_bounds

    initial = (Q(0), Q(-45), Q(0), Q(0))
    u = (Q(0), Q(1, 50))
    box = StateBox.around(initial, (Q(1, 10000),) * 4)
    # Variable start means the first 10 ms includes every convex input 0..u.
    end, tube = step(box, u, 10, (Q(0), Q(1)))
    for eta in (Q(0), Q(2, 5), Q(1)):
        exact = hcw_point_bounds(initial, u, Q(1, 100), eta, (Q(0), Q(0)))
        assert all(
            a <= lo <= hi <= b for a, (lo, hi), b in zip(end.lower, exact, end.upper, strict=True)
        )
    assert schedule_check(box, future_schedule(650, (0, 0), u))[0]


def test_live_history_changed_after_admission_cannot_reuse_cached_result():
    gate, _, payload, proof = setup()
    assert gate.admit(proof, payload, 675)["scheduled"]
    tick = gate.tick(700, live_binding_sha256="different-observation-or-queue")
    assert not tick["newly_applied"] and tick["action"] == ["0", "0"]


def test_missing_live_binding_never_applies_a_cached_result():
    gate, _, payload, proof = setup()
    assert gate.admit(proof, payload, 675)["scheduled"]
    assert not gate.tick(700)["newly_applied"]


def test_admission_itself_must_finish_before_deadline(monkeypatch):
    import sa04.host as host

    gate, _, payload, proof = setup()
    times = iter((699_000_000, 700_000_001))
    monkeypatch.setattr(host, "monotonic_ns", lambda: next(times))
    admitted, before, complete = host.measured_admission(gate, proof, payload, 0)
    assert not admitted["scheduled"] and gate.pending is None
    assert admitted["reasons"] == ["admission_finished_after_deadline"]
    assert not gate.tick(701, live_binding_sha256=identity(payload))["newly_applied"]


def test_mutated_queue_and_dropped_observation_history_fail():
    gate, raw, payload, proof = setup()
    payload["input"]["queued_action"] = ["1/100", "0"]
    proof["binding"]["payload_sha256"] = identity(payload)
    assert not gate.admit(proof, payload, 675)["scheduled"]
