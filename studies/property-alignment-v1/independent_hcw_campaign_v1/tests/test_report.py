"""Adversarial ledger and deterministic transcript tests using exposed fixtures."""

from copy import deepcopy
from fractions import Fraction as Q
import json
import pytest
from independent_hcw_audit_v1.protocol import ROOT as ENGINE, SETTINGS
from independent_hcw_audit_v1.schema import read_info
from independent_hcw_audit_v1.certificates import check_prefix
from independent_hcw_campaign_v1.population import first_qualifying, check_episode_semantics
from independent_hcw_campaign_v1.report import category, summarize
from independent_hcw_campaign_v1.trace import trace_prefix, verify_trace


def fixtures():
    return json.loads((ENGINE / "development_cases.json").read_text())


def selection_inputs():
    p = [{"stratum": "a", "index": i} for i in range(4)]
    q = {
        "a__" + format(i, "05d") + "": {
            "qualification": {
                "eligible": i != 1,
                "status": "qualified" if i != 1 else "not_certified_by_library",
            }
        }
        for i in range(4)
    }
    return p, q


def test_first_eligible_not_first_indices():
    p, q = selection_inputs()
    assert first_qualifying(p, q, 2, ("a",)) == {"a": [0, 2]}


@pytest.mark.parametrize(
    "change", ["missing", "extra", "unknown", "status", "duplicate", "order", "exhausted"]
)
def test_selection_rejects_ambiguous_or_incomplete(change):
    p, q = selection_inputs()
    if change == "missing":
        del q["a__00000"]
    if change == "extra":
        q["a__99999"] = deepcopy(q["a__00000"])
    if change == "unknown":
        q["a__00000"]["qualification"]["eligible"] = None
    if change == "status":
        q["a__00000"]["qualification"]["status"] = "not_certified_by_library"
    if change == "duplicate":
        p.append(p[0])
    if change == "order":
        p.reverse()
    if change == "exhausted":
        for row in q.values():
            row["qualification"] = {"eligible": False, "status": "not_certified_by_library"}
    with pytest.raises(ValueError):
        first_qualifying(p, q, 2, ("a",))


@pytest.mark.parametrize(
    "original,result,expected",
    [
        ("certified_common_prefix", {"status": "verified_prefix"}, "verified_original_certificate"),
        (
            "proved_no_common_held_command",
            {"status": "verified_obstruction"},
            "verified_original_certificate",
        ),
        (
            "certified_common_prefix",
            {"status": "numerically_unresolved"},
            "independent_numerical_nonresolution",
        ),
        (
            "proved_no_common_held_command",
            {"status": "binding_invalid_evidence"},
            "malformed_or_binding_invalid_evidence",
        ),
        (
            "certified_common_prefix",
            {"status": "contradicted_prefix", "witness": {"proved": True}},
            "verified_contrary_witness",
        ),
        ("unresolved", {"status": "no_on_time_certificate"}, "original_no_on_time_certificate"),
        (
            "unresolved_budget",
            {"status": "no_on_time_certificate"},
            "original_no_on_time_certificate",
        ),
        ("certified_common_prefix", {"status": "audit_timeout"}, "audit_timeout"),
    ],
)
def test_discrepancies_are_different_meanings(original, result, expected):
    assert category(original, result) == expected


@pytest.mark.parametrize(
    "old,result",
    [
        ("unresolved_budget", {"status": "verified_prefix"}),
        ("unresolved", {"status": "verified_obstruction"}),
        ("certified_common_prefix", {"status": "verified_obstruction"}),
        ("certified_common_prefix", {"status": "contradicted_prefix"}),
        ("proved_no_common_held_command", {"status": "no_on_time_certificate"}),
    ],
)
def test_nondelivery_or_proof_failure_cannot_be_changed(old, result):
    with pytest.raises(ValueError):
        category(old, result)


@pytest.mark.parametrize(
    "field,value",
    [("wall_s", True), ("wall_s", float("nan")), ("deadline_exceeded", True), ("action", None)],
)
def test_original_timing_and_command_preservation(field, value):
    j = next(
        x
        for x in fixtures()
        if x["kind"] == "recorded_episode"
        and x["episode"]["candidate"]["status"] == "certified_common_prefix"
    )
    check_episode_semantics(j["episode"])
    j["episode"]["candidate"][field] = value
    with pytest.raises(ValueError):
        check_episode_semantics(j["episode"])


def transcript():
    j = next(x for x in fixtures() if x["key"] == "pair-three_face_pair_01")
    info = read_info(j["information"])
    u = tuple(map(Q, j["candidate"]["action"]))
    settings = SETTINGS["numerical"]
    result = check_prefix(
        info,
        u,
        max_cells=settings["max_cells_per_prefix"],
        min_width=Q(settings["minimum_time_width_s"]),
    )
    trace = trace_prefix(info, u, result, settings)
    return info, u, result, settings, trace


def test_actual_core_transcript_has_continuous_leaves_and_scaled_margins():
    info, u, result, settings, trace = transcript()
    checked = verify_trace(info, u, result, settings, trace)
    assert checked["complete_containment"] and checked["leaves"] > 0
    assert all(Q(x["slack_lower"]) >= 0 for x in trace["leaves"])


@pytest.mark.parametrize(
    "change",
    [
        "missing_leaf",
        "duplicated_leaf",
        "wrong_enclosure",
        "wrong_slack",
        "queue",
        "hypothesis",
        "units",
        "event",
    ],
)
def test_altered_transcript_does_not_pass(change):
    info, u, result, settings, trace = transcript()
    if change == "missing_leaf":
        trace["leaves"].pop()
    if change == "duplicated_leaf":
        trace["leaves"].append(deepcopy(trace["leaves"][-1]))
    if change == "wrong_enclosure":
        trace["leaves"][0]["state_endpoints_dyadic"][0][0] = "0"
    if change == "wrong_slack":
        trace["leaves"][0]["slack_lower"] = "999"
    if change == "queue":
        trace["queue_sha256"] = "0" * 64
    if change == "hypothesis":
        trace["leaves"][0]["hypothesis"] = True
    if change == "units":
        trace["state_units"] = ["km"] * 4
    if change == "event":
        trace["leaves"][0]["time_s"] = ["0", "1"]
    with pytest.raises(ValueError):
        verify_trace(info, u, result, settings, trace)


def test_summary_requires_all_selected_records():
    with pytest.raises(ValueError):
        summarize([], [], {})
