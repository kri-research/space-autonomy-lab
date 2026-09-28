from copy import deepcopy
from fractions import Fraction as Q
from importlib import import_module

import pytest


def setup(component):
    t = import_module("kri_assurance_eval._vendor.iaa.types")
    m = import_module("kri_assurance_eval._vendor.sa02.model")
    i = import_module("kri_assurance_eval._vendor.sa02.intervals")
    e = import_module("kri_assurance_eval._vendor.sa02.estimator")
    sensors = m.SensorContract(
        hypotheses=(m.FaultHypothesis("zero", (i.interval(0),) * 4),), initial_splits=0
    )
    prior = t.StateBox.around((0, -45, 0, 0), (Q(1, 20), Q(1, 20), Q(1, 1000), Q(1, 1000)))
    present = t.ObservationPacket("same", 0, "range", 45.0, 0, 40, 2, "m")
    hist = (m.HistorySegment(0, 100, (0, 0)),)
    return t, m, e, sensors, prior, present, hist


@pytest.mark.parametrize("uncertainty", [2, 3, 100])
@pytest.mark.parametrize("same_id", [False, True])
def test_future_content_does_not_change_admissibility(component, uncertainty, same_id):
    t, m, e, c, p, present, hist = setup(component)
    future = t.ObservationPacket(
        "same" if same_id else "new", 1, "range", 46.0, 250, 1000, uncertainty, "m"
    )
    expected = e.Observer(p, c).update((present,), hist, 100)
    actual = e.Observer(p, c).update((present, future), hist, 100)
    assert actual.cells == expected.cells
    assert actual.status == expected.status == "updated"
    assert actual.diagnostics["ignored_invalid"] == 0
    assert actual.diagnostics["ignored_future"] == 1
    assert (
        actual.diagnostics["retained_packet_identity"]
        == expected.diagnostics["retained_packet_identity"]
    )


def test_available_invalid_and_conflicting_packets_remain_rejected(component):
    t, m, e, c, p, present, hist = setup(component)
    bad = t.ObservationPacket("new", 1, "range", 45.0, 0, 40, 3, "m")
    conflict = t.ObservationPacket("same", 0, "range", 46.0, 0, 40, 2, "m")
    assert (
        e.Observer(p, c).update((present, bad), hist, 100).status == "unsupported_packets_ignored"
    )
    assert (
        e.Observer(p, c).update((present, conflict), hist, 100).status
        == "inconsistent_observations"
    )


def test_future_packet_validated_when_it_arrives(component):
    t, m, e, c, p, present, hist = setup(component)
    bad = t.ObservationPacket("new", 1, "range", 45.0, 250, 1000, 3, "m")
    observer = e.Observer(p, c)
    assert observer.update((present, bad), hist, 100).status == "updated"
    arrived = observer.update((bad,), (m.HistorySegment(0, 1000, (0, 0)),), 1000)
    assert arrived.status == "unsupported_packets_ignored"


@pytest.mark.parametrize("uncertainty", [2, 3])
def test_public_delivered_only_boundary_unchanged(component, request_data, uncertainty):
    packet = component.observation_packet("future", 1, "range", 45.0, 250, 1000, uncertainty)
    request_data["current_input"]["packets"] = [packet]
    assert component.assess(request_data)["status"] == "unsupported_input"
    with pytest.raises(ValueError):
        component.estimate_snapshot(request_data["current_input"])


def test_malformed_availability_not_silently_ignored(component):
    t, m, e, c, p, present, hist = setup(component)
    bad = deepcopy(present)
    object.__setattr__(bad, "available_ms", True)
    assert e.Observer(p, c).update((bad,), hist, 100).status == "unsupported_packets_ignored"


def test_all_ten_examples_and_replay(component):
    from kri_assurance_eval.examples import examples
    from kri_assurance_eval.integrity import verify_installation

    assert verify_installation()["component_version"] == "0.1.1"
    for case in examples():
        receipt = component.record(case["request"])
        assert receipt["result"]["status"] == case["expected_status"]
        assert component.replay(receipt)
        wrong = deepcopy(receipt)
        wrong["result"]["candidate_applied_in_simulation"] = not wrong["result"][
            "candidate_applied_in_simulation"
        ]
        identity = import_module("kri_assurance_eval._vendor.iaa.types").identity
        wrong["sha256"] = identity({k: v for k, v in wrong.items() if k != "sha256"})
        assert not component.replay(wrong)


def test_old_version_not_silently_accepted(component, request_data):
    request_data["contract"]["component_version"] = "0.1.0"
    assert component.assess(request_data)["status"] == "unsupported_input"
