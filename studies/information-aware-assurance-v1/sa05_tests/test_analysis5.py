import math

import pytest
from scipy.stats import binomtest

from sa05.analysis import binary_pair, exact_discordance_p, holm, rate_interval, summarize
from sa05.design import METHODS


@pytest.mark.parametrize("wins,losses", [(0, 0), (1, 0), (10, 0), (0, 10), (3, 4), (20, 12)])
def test_exact_p_against_independent_library(wins, losses):
    expected = binomtest(wins, wins + losses, 0.5).pvalue if wins + losses else 1.0
    assert abs(exact_discordance_p(wins, losses) - expected) < 1e-14


@pytest.mark.parametrize("value", [True, False])
def test_all_success_or_failure_does_not_imply_equality(value):
    r = binary_pair([value] * 10, [value] * 10)
    assert r["risk_difference"] == 0 and r["exact_p"] == 1
    assert (
        r["conservative_simultaneous_interval"][0] < 0 < r["conservative_simultaneous_interval"][1]
    )


def test_discordance_and_missing_are_not_hidden():
    r = binary_pair([True] * 12, [False] * 12)
    assert r["wins"] == 12 and r["exact_p"] < 0.001
    r = binary_pair([None, True], [True, None])
    assert r["missing_pairs"] == 2 and r["exact_p"] is None
    assert r["missing_data_identification_interval"] == [-0.5, 0.5]


def test_zero_failure_interval_is_not_zero_risk():
    assert rate_interval(0, 32)[1] > 0.1
    assert rate_interval(32, 32)[0] < 1


def test_holm_preserves_family_and_monotonicity():
    assert holm([0.01, 0.03, 0.04, 1]) == [0.04, 0.09, 0.09, 1]
    assert holm([0.01, None, 0.2, 1])[0] == 0.04


def test_incomplete_duplicate_membership_fails():
    cases = [dict(unit="x", stratum="nominal")]
    with pytest.raises(ValueError):
        summarize(cases, [])
    with pytest.raises(ValueError):
        summarize(
            cases, [dict(unit="x", method=m) for m in METHODS] + [dict(unit="x", method=METHODS[0])]
        )


def test_invalid_data_is_not_coerced_to_success():
    with pytest.raises(ValueError):
        binary_pair([math.nan], [True])
    with pytest.raises(ValueError):
        binary_pair([1], [True])


def test_outside_assumption_mixture_has_no_binomial_inference():
    from sa05.artifact import PACKAGE, read_json

    old = read_json(PACKAGE / "development_recorded/results.json")
    cases = read_json(PACKAGE / "development_recorded/inputs.json")
    result = summarize(cases, old)
    assert all(
        r["acquisition_rate_exact95"] is None
        for r in result["absolute"]
        if r["stratum"] == "outside_assumptions"
    )
    assert all(r["stratum"] != "outside_assumptions" for r in result["primary"])
