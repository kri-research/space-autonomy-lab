"""Automated author-side adversarial fixtures, not external scientific review."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as Q
from itertools import product
import json
import pytest
from publication_v1.audit import ROOT, STUDY, outcomes, verify_manifest
from candidate.artifact import load_information
from candidate.affine import recheck_certificate, necessary_system, verify_dual
from candidate.scalar import ScalarBox, common_inputs, action_is_safe
from adjudication.interval import iv
from transfer_cart_v1.reference import R, enclose_curve
from execution_validation_v1.protocol import delay_compatibility


def fixture():
    info = json.loads((STUDY / "candidate/recorded_development/fixture_inputs.json").read_text())[
        "three_face_conflict"
    ]
    data = load_information(info)
    rows = json.loads((STUDY / "candidate/recorded_development/fixtures.json").read_text())
    certificate = next(x for x in rows if x["case"] == "three_face_conflict")["candidate"][
        "negative"
    ]
    return data, certificate


def test_all_scientific_inputs_bound_to_prior_commit():
    result = verify_manifest()
    assert result["files"] == 5744
    assert result["scientific_source_commit"] == "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8"


@pytest.mark.parametrize("damage", ["empty", "wrong_commit", "wrong_hash", "path_escape"])
def test_corrupted_publication_inventory_is_rejected(damage):
    doc = json.loads((ROOT / "evidence_manifest.json").read_text())
    if damage == "empty":
        doc["files"] = {}
    elif damage == "wrong_commit":
        doc["scientific_source_commit"] = "0" * 40
    elif damage == "wrong_hash":
        doc["files"][next(iter(doc["files"]))]["sha256"] = "0" * 64
    else:
        doc["files"]["../outside"] = {"sha256": "0" * 64, "bytes": 0}
    with pytest.raises(ValueError):
        verify_manifest(doc)


def test_all_principal_numeric_populations_remain_separate():
    result = outcomes()
    assert not result["inferential_populations_pooled"]
    assert result["campaign"]["statuses"] == {
        "certified_common_prefix": 725,
        "proved_no_common_held_command": 31,
        "unresolved": 9,
        "unresolved_budget": 3,
    }
    assert result["transfer"]["criterion"] == {
        "verified_prefix": 77,
        "verified_obstruction": 45,
        "unresolved": 6,
    }
    assert result["transfer"]["predictive_prefixes"] == 79
    assert result["host"]["physical_trials"] == 0 and result["host"]["external_reviews"] == 0


def test_genuine_three_way_certificate_survives_rational_recheck():
    info, cert = fixture()
    assert recheck_certificate(info, cert)["proved"]


@pytest.mark.parametrize(
    "damage", ["zero_weights", "negative_weight", "wrong_information", "wrong_model"]
)
def test_false_impossibility_certificates_cannot_be_substituted(damage):
    info, cert = fixture()
    cert = deepcopy(cert)
    if damage == "zero_weights":
        cert["weights"] = ["0"] * len(cert["weights"])
    elif damage == "negative_weight":
        cert["weights"][0] = "-1"
    elif damage == "wrong_information":
        cert["information_sha256"] = "0" * 64
    else:
        cert["model"] = "nonlinear"
    assert not recheck_certificate(info, cert)["proved"]


def test_outer_hull_is_not_an_attainable_witness_set():
    info, _ = fixture()
    with pytest.raises(ValueError):
        necessary_system(replace(info, kind="outer_enclosure"))


def test_dual_residual_cannot_be_ignored():
    # 1*u <= -0.01 is feasible within |u| <= 0.02. A negative RHS alone
    # would incorrectly assert impossibility; its uncancelled residual matters.
    result = verify_dual([(iv(1), iv(0))], [iv(Q("-0.01"))], [Q(1)], Q("0.02"))
    assert not result["proved"] and Q(result["margin_lower"]) < 0


def test_relaxed_union_halfspaces_do_not_certify_containment():
    from candidate.affine import checked_outer_halfspaces

    point = (Q("2.9"), Q("-29"))
    normals, limits = checked_outer_halfspaces()
    assert all(
        sum(a * b for a, b in zip(n, point, strict=True)) <= c
        for n, c in zip(normals, limits, strict=True)
    )
    assert not (-100 <= point[1] <= -30 and abs(point[0]) <= -point[1] / 10)
    assert (point[0] / 2) ** 2 + ((point[1] + 30) / 3) ** 2 > 1


@pytest.mark.parametrize("duration", [Q("0.2499"), Q("0.25"), Q("0.2501"), Q("0.5"), Q("0.5001")])
def test_scalar_prefix_never_substitutes_for_post_observation_recovery(duration):
    boxes = (
        ScalarBox(Q(".9"), Q(".9"), Q(".2"), Q(".2")),
        ScalarBox(Q("-.9"), Q("-.9"), Q("-.2"), Q("-.2")),
    )
    feasible = common_inputs(boxes, duration)["status"] == "exact_feasible_interval"
    assert feasible == (duration <= Q("0.5"))
    remaining = Q(1) - Q(".9") - Q(".2") * duration - Q(".2") ** 2 / (2 * Q(".4"))
    recoverable = remaining >= 0
    assert recoverable == (duration <= Q(".25"))
    if duration == Q(".2501"):
        assert feasible and not recoverable


@pytest.mark.parametrize(
    "position,speed",
    [(Q(".9999"), Q(".001")), (Q(1), Q(".001")), (Q(-1), Q("-.001")), (Q(".9"), Q("-.2"))],
)
def test_exact_scalar_bound_matches_independent_extrema_under_degradation(position, speed):
    box = ScalarBox(position, position, speed, speed)
    for duration, eta, disturbance in product(
        (Q(".001"), Q(".25"), Q(1)), ((Q(0), Q(1)), (Q(".8"), Q(1))), (Q(0), Q(".003"))
    ):
        ans = common_inputs((box,), duration, effectiveness=eta, disturbance=disturbance)
        for action in [Q(k, 100) for k in range(-40, 41, 5)]:
            expected = ans["status"] == "exact_feasible_interval" and Q(
                ans["lower"]
            ) <= action <= Q(ans["upper"])
            assert (
                action_is_safe((box,), action, duration, effectiveness=eta, disturbance=disturbance)
                == expected
            )


def test_ambiguous_numerical_boundary_is_not_safe():
    result = enclose_curve([R.value(1)], Q("0.001"), Q(1), max_cells=2)
    assert result["status"] == "unresolved"


def test_real_delay_bounds_are_required_even_when_host_reply_is_fast():
    unknown = delay_compatibility(1, 1000000)
    assert unknown["status"] == "unknown_physical_delays"
    assert not unknown["physical_compatibility_established"]
    zero = delay_compatibility(1, 0)
    assert zero["status"] == "incompatible_host_lower_bound"


def test_barrier_external_actions_and_transfer_failures_remain_reported():
    result = outcomes()
    assert result["development"]["predictive_contained"] == 10
    assert result["development"]["predictive_external_actions"] == 0
    assert result["development"]["barrier_continued_cases"] == 6
    assert result["development"]["barrier_external_actions"] == 48
    assert result["transfer"]["lag_mismatch"] == {"violation": 7, "contained": 4}
