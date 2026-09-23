"""Mathematical and adversarial checks; none uses protected evaluation data."""

from fractions import Fraction as Q
from dataclasses import replace
import random
import pytest
from candidate.scalar import (
    ScalarBox,
    common_inputs,
    action_is_safe,
    acceleration_ceiling,
    quadratic_range,
    propagate_queue,
    held_duration_bracket,
)
from candidate.information import Hypothesis, InformationSet
from candidate.affine import verify_dual, obstruction, recheck_certificate, checked_outer_halfspaces
from candidate.certify import certify_action
from candidate.fixtures import fixtures, PAIR_ACTIONS
from adjudication.interval import Interval as I


def scalar_case(seed):
    r = random.Random(60620260923 + seed)
    center = Q(r.randrange(-80, 81), 100)
    radius = Q(r.randrange(0, 11), 100)
    speed = Q(r.randrange(-40, 41), 100)
    ve = Q(r.randrange(0, 6), 100)
    box = ScalarBox(center - radius, center + radius, speed - ve, speed + ve)
    t = r.choice([Q(1, 4), Q(1, 2), Q(1), Q(2)])
    umax = Q(r.randrange(5, 51), 100)
    eta = (Q(r.randrange(0, 11), 10), Q(1))
    w = Q(r.randrange(0, 6), 100)
    return box, t, {"authority": umax, "effectiveness": eta, "disturbance": w}


@pytest.mark.parametrize("seed", range(512))
def test_closed_form_against_exact_extrema(seed):
    box, t, kwargs = scalar_case(seed)
    interval = common_inputs([box], t, **kwargs)
    for j in range(17):
        u = kwargs["authority"] * Q(j - 8, 8)
        expected = interval["status"] == "exact_feasible_interval" and Q(
            interval["lower"]
        ) <= u <= Q(interval["upper"])
        assert action_is_safe([box], u, t, **kwargs) == expected
    if interval["status"] == "exact_feasible_interval":
        for u in (
            Q(interval["lower"]),
            Q(interval["upper"]),
            (Q(interval["lower"]) + Q(interval["upper"])) / 2,
        ):
            assert action_is_safe([box], u, t, **kwargs)


def test_exact_half_second_common_action_deadline():
    boxes = [ScalarBox(".9", ".9", ".2", ".2"), ScalarBox("-.9", "-.9", "-.2", "-.2")]
    at = common_inputs(boxes, Q(1, 2))
    assert at["lower"] == at["upper"] == "0"
    assert common_inputs(boxes, 1)["status"] == "proved_no_common_held_command"
    bracket = held_duration_bracket(boxes, 2)
    assert Q(bracket["lower_s"]) == Q(1, 2) < Q(bracket["upper_s"])
    assert Q(bracket["upper_s"]) - Q(bracket["lower_s"]) == Q(1, 2**29)


def test_individual_recovery_does_not_interchange_quantifiers():
    right = ScalarBox(".9", ".9", ".2", ".2")
    left = ScalarBox("-.9", "-.9", "-.2", "-.2")
    assert action_is_safe([right], Q(-2, 5), 1)
    assert action_is_safe([left], Q(2, 5), 1)
    assert common_inputs([left, right], 1)["status"] == "proved_no_common_held_command"


@pytest.mark.parametrize(
    "c,v,t", [(Q(1, 10), Q(1, 5), 2), (Q(1, 5), Q(1, 2), 2), (Q(1, 3), Q(2), 1)]
)
def test_stationary_bound_symbolic_rational_identity(c, v, t):
    stationary = 2 * c / v
    assert -4 * c / stationary**3 + 2 * v / stationary**2 == 0
    assert acceleration_ceiling(c, v, t) == -v * v / (2 * c)


def test_unit_scaling():
    box = ScalarBox(".9", ".95", ".2", ".3")
    a = Q(7)
    b = Q(3)
    original = common_inputs([box], 1, authority=2, disturbance=".01")
    scaled = ScalarBox(a * box.qlo, a * box.qhi, a / b * box.vlo, a / b * box.vhi)
    transformed = common_inputs(
        [scaled], b, halfwidth=a, authority=a / b**2 * 2, disturbance=a / b**2 * Q(".01")
    )
    assert Q(transformed["lower"]) == a / b**2 * Q(original["lower"])
    assert Q(transformed["upper"]) == a / b**2 * Q(original["upper"])


@pytest.mark.parametrize(
    "q,v,possible", [(1, 0, True), (1, "-.1", True), (1, ".1", False), ("1.01", 0, False)]
)
def test_closed_boundary_semantics(q, v, possible):
    b = ScalarBox(q, q, v, v)
    assert (common_inputs([b], 1)["status"] == "exact_feasible_interval") == possible


def test_queued_input_cannot_be_discarded():
    box = ScalarBox(".94", ".94", ".01", ".01")
    aged, safe = propagate_queue([box], [(1, ".1")])
    assert safe and aged[0].qhi == 1 and aged[0].vhi == Q(".11")
    assert common_inputs(aged, 1)["status"] == "proved_no_common_held_command"
    assert common_inputs([box], 1)["status"] == "exact_feasible_interval"


def test_queue_extremes_include_mid_interval_crossing():
    box = ScalarBox(".99", ".99", ".1", ".1")
    _, safe = propagate_queue([box], [(1, "-.2")])
    assert not safe
    assert quadratic_range(Q(".99"), Q(".1"), Q("-.2"), 1)[1] == Q("1.015")


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), "bad"])
def test_nonfinite_scalar_refused(bad):
    with pytest.raises(ValueError):
        ScalarBox(bad, 1, 0, 0)


def test_nonnegative_dual_residual_budget():
    rows = [(I(1, 1), I(0, 0)), (I(-1, -1), I(0, 0))]
    rhs = [I(-0.1, -0.1), I(-0.1, -0.1)]
    assert verify_dual(rows, rhs, ["1/2", "1/2"], ".02")["proved"]
    assert not verify_dual(rows, rhs, ["-1", "1"], ".02")["proved"]
    wide = [(I(-10, 10), I(0, 0)), (I(-10, 10), I(0, 0))]
    assert not verify_dual(wide, rhs, ["1/2", "1/2"], ".02")["proved"]


def test_finite_outer_bounds_cover_both_geometries():
    normals, limits = checked_outer_halfspaces()
    assert len(normals) == len(limits) == 6


def test_three_state_obstruction_and_pair_prefixes():
    fs = fixtures()
    certificate = obstruction(fs["three_face_conflict"])
    assert certificate["status"] == "proved_no_common_held_command", certificate
    assert recheck_certificate(fs["three_face_conflict"], certificate)["proved"]
    for name, action in PAIR_ACTIONS.items():
        assert certify_action(fs[name], action)["status"] == "certified_common_prefix"
    for i in range(3):
        smaller = replace(
            fs["three_face_conflict"],
            hypotheses=tuple(
                h for j, h in enumerate(fs["three_face_conflict"].hypotheses) if j != i
            ),
        )
        assert obstruction(smaller)["status"] == "unresolved"


def test_attainability_not_outer_enclosure_vertices():
    fs = fixtures()
    info = replace(fs["opposed_radial"], kind="outer_enclosure_only")
    assert obstruction(info)["status"] == "unresolved"
    assert obstruction(fs["opposed_radial"], force_failure=True)["status"] == "unresolved"


def test_fabricated_or_stale_certificate_refused():
    info = fixtures()["outward_boundary"]
    c = obstruction(info)
    assert c["status"] == "proved_no_common_held_command"
    assert not recheck_certificate(fixtures()["hold_bounded"], c)["proved"]
    tampered = dict(c, weights=["0"] * len(c["weights"]))
    assert not recheck_certificate(info, tampered)["proved"]


def test_correlated_union_does_not_become_intersection_or_hull():
    info = fixtures()["correlated_union"]
    assert certify_action(info, (0, 0))["status"] == "certified_common_prefix"
    outer = replace(info, hypotheses=(info.hull(),), kind="outer_enclosure_only")
    assert certify_action(outer, (0, 0))["status"] == "unresolved"
    assert obstruction(outer)["status"] == "unresolved"


def test_geometric_outer_relaxation_is_never_safe_label():
    info = fixtures()["outer_geometry_false_safe"]
    assert obstruction(info)["status"] == "unresolved"
    assert certify_action(info, (0, 0))["status"] == "unresolved"


def test_covariance_unknown_model_and_failed_evaluation():
    info = fixtures()["hold_bounded"]
    assert certify_action(replace(info, kind="covariance_only"), (0, 0))["status"] == "unresolved"
    assert certify_action(info, (0, 0), model="invalid")["status"] == "unresolved"
    assert certify_action(info, (0, 0), max_cells=1)["status"] == "unresolved"
    assert certify_action(info, (".021", 0))["status"] == "unresolved"


def test_no_missing_history_or_unit_coercion():
    point = Hypothesis.point((0, -30, 0, 0))
    with pytest.raises(ValueError):
        InformationSet((point,), age=1)
    with pytest.raises(ValueError):
        InformationSet((point,), units=("km", "km", "km/s", "km/s"))
    with pytest.raises(ValueError):
        InformationSet((point,), delay=True)
    with pytest.raises(ValueError):
        InformationSet((point,), effectiveness=(-1, 1))


def test_declared_common_bias_cannot_be_authenticated_into_truth():
    info = fixtures()["opposed_radial"]
    readings = []
    for hypothesis in info.hypotheses:
        true = hypothesis.lower
        bias = (-true[0], Q(0), -true[2], Q(0))
        readings.append(tuple(x + b for x, b in zip(true, bias, strict=True)))
    assert readings[0] == readings[1] == (0, -70, 0, 0)
    # Authenticating either identical packet adds no information to this declared model.
    assert obstruction(info)["status"] == "proved_no_common_held_command"
    mean = InformationSet((Hypothesis.point(readings[0]),))
    assert certify_action(mean, (0, 0))["status"] == "certified_common_prefix"
    assert certify_action(info, (0, 0))["status"] == "unresolved"


def test_permutation_symmetry_and_duplicate_hypotheses():
    from candidate.scalar import common_inputs

    b = [ScalarBox(".9", ".9", ".2", ".2"), ScalarBox("-.9", "-.9", "-.2", "-.2")]
    assert common_inputs(b, 1)["status"] == common_inputs(list(reversed(b)), 1)["status"]
    assert common_inputs(b, 1)["lower"] == common_inputs(b + b, 1)["lower"]
    info = fixtures()["three_face_conflict"]
    assert (
        obstruction(replace(info, hypotheses=tuple(reversed(info.hypotheses))))["status"]
        == "proved_no_common_held_command"
    )


def test_late_answer_is_not_an_applied_safety_command():
    from candidate.certify import decide

    result = decide(fixtures()["hold_bounded"], budget_s=1.0e-12)
    assert result["status"] == "unresolved_budget"
    assert result["action"] is None


def test_adapter_preserves_history_and_input_information():
    from candidate.comparators import at_time, center_error

    info = InformationSet(
        (Hypothesis.point((0, -70, 0, 0)),), age=1, delay=1, queue=((Q(".01"), 0), (0, Q(".01")))
    )
    estimate, error = center_error(at_time(info, 2))
    assert estimate[0] > 0.01 and estimate[1] > -70
    assert all(x >= 0 for x in error)
