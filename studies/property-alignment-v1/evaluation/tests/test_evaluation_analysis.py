"""Frozen analysis behavior on synthetic endpoint combinations."""

import pytest

from evaluation.analysis import analyze_rows
from evaluation.generator import STRATA


def row(index, status, *, eligible=True, valid=True, on_time=True, stratum=None):
    stratum = stratum or STRATA[index % len(STRATA)]
    decisive = status in {"certified_common_prefix", "proved_no_common_held_command"}
    return {
        "case_id": f"synthetic-{index}",
        "stratum": stratum,
        "index": index,
        "primary": {
            "eligible": eligible,
            "decisive": decisive,
            "on_time": on_time,
            "valid_certificate": valid,
            "on_time_decisive_valid": eligible and decisive and on_time and valid,
        },
        "candidate": {"status": status, "wall_s": 0.01},
        "pairwise_shortcut": {
            "applicable": status == "proved_no_common_held_command",
            "declares_compatible": status == "proved_no_common_held_command",
            "pairs": [],
        },
        "mean_shortcut": {
            "declares_safe": status == "proved_no_common_held_command",
            "false_safe_for_full_set": status == "proved_no_common_held_command",
        },
        "native_baselines": {"status": "not_run"},
    }


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (["certified_common_prefix"] * 8, 8),
        (["proved_no_common_held_command"] * 8, 8),
        (
            [
                "certified_common_prefix",
                "proved_no_common_held_command",
                "unresolved",
                "unresolved_budget",
            ]
            * 2,
            4,
        ),
    ],
)
def test_primary_counts_all_safe_all_adverse_and_discordant(statuses, expected):
    result = analyze_rows([row(i, value) for i, value in enumerate(statuses)])
    assert result["eligible"] == len(statuses)
    assert result["on_time_decisive_valid"] == expected


def test_missing_ambiguous_and_timeout_are_not_safe():
    statuses = [
        "unresolved",
        "unresolved_budget",
        "infrastructure_missing",
        "numerical_ambiguity",
    ]
    result = analyze_rows([row(i, value) for i, value in enumerate(statuses)])
    assert result["on_time_decisive_valid"] == 0
    assert result["invalid_definite_certificates"] == 0


def test_invalid_definite_certificate_is_counted_and_not_primary_success():
    bad = row(0, "certified_common_prefix", valid=False)
    result = analyze_rows([bad])
    assert result["invalid_definite_certificates"] == 1
    assert result["on_time_decisive_valid"] == 0


def test_ineligible_cases_do_not_enter_primary_denominator():
    rows = [
        row(0, "certified_common_prefix"),
        row(1, "proved_no_common_held_command", eligible=False),
    ]
    result = analyze_rows(rows)
    assert result["eligible"] == 1
    assert result["on_time_decisive_valid"] == 1
