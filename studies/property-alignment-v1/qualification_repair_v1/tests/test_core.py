"""Proof obligations and adversarial fixtures, never protected evaluation outcomes."""

from dataclasses import replace
from fractions import Fraction as Q
import pytest
from adjudication.flow import Model, propagate_schedule
from adjudication.polynomial import PolynomialArc
from adjudication.engine import adjudicate
from candidate.certify import execution_schedule, certify_action
from candidate.information import Hypothesis, InformationSet
from evaluation.generator import make_case
from runtime_diagnosis_v1.worker import validate_case
from evaluation.runner import _information
from specification.contract import load_property
from qualification_repair_v1 import core


def stationary(x=0, y=-60):
    return PolynomialArc(Q(0), Q(1), ((Q(x),), (Q(y),), (Q(0),), (Q(0),)))


@pytest.mark.parametrize("xy", [(0, -60), (0, -28), (5, -50), (-5, -50), (0, -100), (0, -27)])
def test_closed_union_and_boundary_fixtures(xy):
    arc = stationary(*xy)
    answer = core.check_window([arc], load_property(), 0, 1)
    assert answer["status"] == "validated_containment"
    assert answer["continuous_range_coverage"] and answer["range_evaluations"] > 0
    assert adjudicate([arc], load_property(), end=1)["status"] == "validated_containment"


@pytest.mark.parametrize("xy", [(6, -50), (0, -101), (0, -26), (0, 0), (Q("2.4"), Q("-28.5"))])
def test_outside_never_safe(xy):
    assert (
        core.check_window([stationary(*xy)], load_property(), 0, 1)["status"]
        == "validated_violation"
    )


def test_between_probe_excursion_cannot_pass_from_sampling():
    t = Q(123, 1000)
    eps = Q(1, 1000000)
    arc = PolynomialArc(Q(0), Q(1), ((5 + eps - t * t, 2 * t, -1), (-50,), (0,), (0,)))
    assert all(
        core._physical(core.bounds(arc.point(q), load_property())) == "validated_containment"
        for q in (Q(0), Q(1, 2), Q(1))
    )
    assert core.check_window([arc], load_property(), 0, 1)["status"] != "validated_containment"


def test_point_containment_does_not_override_exhausted_range_budget():
    arc = PolynomialArc(Q(0), Q(1), ((Q("4.9375"), Q(".5"), -1), (-50,), (0,), (0,)))
    assert core.check_window([arc], load_property(), 0, 1, max_cells=1)["status"] == "unresolved"
    assert core.check_window([arc], load_property(), 0, 1)["status"] == "validated_containment"


@pytest.mark.parametrize("bad", [[], [stationary(), stationary()], [object()]])
def test_incomplete_or_malformed_window_refused(bad):
    with pytest.raises(ValueError):
        core.check_window(bad, load_property(), 0, 1)


def test_state_reset_refused():
    a = stationary()
    b = PolynomialArc(Q(1), Q(2), ((1,), (-60,), (0,), (0,)))
    with pytest.raises(ValueError):
        core.check_window([a, b], load_property(), 0, 2)


@pytest.mark.parametrize("cells", [0, -1, True, 1.5])
def test_invalid_budget_refused(cells):
    with pytest.raises(ValueError):
        core.check_window([stationary()], load_property(), 0, 1, max_cells=cells)


def test_uncertainty_point_returns_unknown_not_physical_violation():
    h = Hypothesis((Q("4.999"), -50, 0, 0), (Q("5.001"), -50, 0, 0))
    arcs = propagate_schedule(Model("hcw"), h.enclosure(), [(0, Q(1, 4), (0, 0))])
    out = core.check_window(arcs, load_property(), 0, Q(1, 4))
    assert out["status"] == "unresolved" and not out["continuous_range_coverage"]
    assert out["range_evaluations"] == 0


def test_queue_violation_detected_before_any_library_action():
    info = _information(validate_case(137))
    out = core.qualify(info)
    assert out["status"] == "proved_precommand_violation" and out["eligible"] is False
    assert out["counters"]["continuation_propagations"] == 0
    assert core.recheck_queue_witness(info, out["queue_witness"])
    assert Q(out["queue_witness"]["time_s"]) <= info.application_time


@pytest.mark.parametrize(
    "field,value",
    [
        ("time_s", "3"),
        ("effectiveness", "2"),
        ("disturbance", ["1", "0"]),
        ("origin", ["1000", "0", "0", "0"]),
        ("information_sha256", "wrong"),
        ("hypothesis", True),
        ("model", "nonlinear"),
    ],
)
def test_fabricated_negative_witness_refused(field, value):
    info = _information(validate_case(137))
    witness = core.queue_witness(info, 0)
    witness[field] = value
    assert not core.recheck_queue_witness(info, witness)


@pytest.mark.parametrize("kind", ["outer_enclosure_only", "covariance_only"])
def test_unsupported_information_is_not_impossible_or_eligible(kind):
    info = replace(_information(validate_case(137)), kind=kind)
    assert core.queue_witness(info, 0) is None
    out = core.qualify(info)
    assert out["status"] == "unsupported_information" and out["eligible"] is None
    assert not out["physical_impossibility_claim"]


def test_failed_arithmetic_blocks_qualification(monkeypatch):
    info = InformationSet((Hypothesis.point((0, -60, 0, 0)),))

    def fail(*args, **kwargs):
        raise ArithmeticError("injected invalid enclosure")

    monkeypatch.setattr(core, "_continuation", fail)
    out = core.qualify(info)
    assert out["eligible"] is None and out["status"] == "unresolved_computation"
    assert out["last_phase"] == "continuation" and out["error_type"] == "ArithmeticError"


def test_unresolved_sufficient_search_not_turned_into_impossibility(monkeypatch):
    info = InformationSet((Hypothesis.point((0, -60, 0, 0)),))
    monkeypatch.setattr(
        core, "check_window", lambda *a, **k: {"status": "unresolved", "reason": "fixture"}
    )
    out = core.qualify(info)
    assert out["status"] == "not_certified_by_library" and out["eligible"] is False
    assert not out["physical_impossibility_claim"]
    assert len(out["hypotheses"][0]["attempts"]) == 13


def test_queue_cache_is_reused_and_state_matches_original_schedule():
    info, _ = make_case("development", "timing_bounded_pair", 0)
    h = info.hypotheses[0]
    q, end = core._queue_arcs(info, h)
    cache = core._QueueCache(info.identity(), h, end)
    for a in ((0, 0), (Q("-.005"), 0)):
        tail = core._continuation(info, cache, a)
        original = propagate_schedule(Model("hcw"), h.enclosure(), execution_schedule(info, a))
        assert tuple(q) + tail == tuple(original)
    wrong = replace(info, disturbance=Q("0.00002"))
    with pytest.raises(ValueError):
        core._continuation(wrong, cache, (0, 0))
    out = core.qualify(info)
    assert out["counters"]["queue_propagations"] == 2


@pytest.mark.parametrize(
    "s", ["interior_pair", "radial_boundary", "three_face_boundary", "timing_bounded_pair"]
)
@pytest.mark.parametrize("i", range(4))
def test_development_qualification_positive_replayed_by_original(s, i):
    info, _ = make_case("development", s, i)
    out = core.qualify(info)
    assert out["eligible"] is not None
    if out["eligible"]:
        for h in out["hypotheses"]:
            single = replace(info, hypotheses=(info.hypotheses[h["hypothesis"]],))
            old = certify_action(single, tuple(Q(v) for v in h["witness_action"]))
            assert old["status"] == "certified_common_prefix"
    elif out["physical_impossibility_claim"]:
        assert core.recheck_queue_witness(info, out["queue_witness"])


def test_no_queue_zero_authority_known_interior():
    info = InformationSet((Hypothesis.point((0, -60, 0, 0)),), authority=Q(0))
    assert core.qualify(info)["eligible"] is True


def test_unknown_model_not_implicitly_added():
    assert core.Model("hcw").kind == "hcw"
    with pytest.raises(ValueError):
        core.qualify({"kind": "nonlinear"})
