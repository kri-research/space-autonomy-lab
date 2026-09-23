"""Adversarial freeze/receipt tests. No protected algorithm is executed."""

from copy import deepcopy
import pytest
from evaluation.analysis import analyze_rows
from evaluation.execute import run_protected
from evaluation.freeze import identity_fields, exact_command, RETIRED_INPUT_COUNT
from evaluation.generator import STRATA
from evaluation.runner import run_fixed_namespace, run_resumable_namespace
from evaluation.safety import atomic_json, strict_json, canonical_hash, mean_evidence
from evaluation.statistics import (
    conditional_mean_interval,
    hoeffding_half_width,
    bounded_difference_interval,
)
from evaluation.tests.test_evaluation_analysis import row


def test_atomic_failure_does_not_publish_partial_json(tmp_path):
    dest = tmp_path / "receipt.json"
    with pytest.raises(ValueError):
        atomic_json(dest, {"bad": float("nan")})
    assert not dest.exists()
    atomic_json(dest, {"good": True})
    prior = dest.read_bytes()
    with pytest.raises(FileExistsError):
        atomic_json(dest, {"good": False})
    assert dest.read_bytes() == prior


@pytest.mark.parametrize("text", ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'])
def test_strict_json_rejects_ambiguity(tmp_path, text):
    p = tmp_path / "bad.json"
    p.write_text(text)
    with pytest.raises(ValueError):
        strict_json(p)


def test_failed_sufficient_check_is_not_false_safe():
    r = row(0, "unresolved")
    r["mean_shortcut"] = {
        "declares_safe": True,
        "false_safe_for_full_set": True,
        "full_set_recheck": "unresolved",
    }
    assert mean_evidence(r) == "unresolved"
    assert analyze_rows([r])["mean_shortcut_false_safe"] == 0


def test_genuine_full_set_obstruction_can_refute_shortcut():
    r = row(0, "proved_no_common_held_command")
    assert mean_evidence(r) == "confirmed_false_safe"
    r["primary"]["valid_certificate"] = False
    assert mean_evidence(r) == "unresolved"


@pytest.mark.parametrize("status", ["unresolved", "infrastructure_missing", "unresolved_budget"])
def test_missing_none_timing_does_not_break_analysis(status):
    r = row(0, status)
    r["candidate"]["wall_s"] = None
    assert analyze_rows([r])["on_time_decisive_valid"] == 0


def test_duplicate_and_invented_success_refused():
    r = row(0, "unresolved")
    with pytest.raises(ValueError):
        analyze_rows([r, deepcopy(r)])
    r["primary"]["on_time_decisive_valid"] = True
    with pytest.raises(ValueError):
        analyze_rows([r])


def test_protected_denominator_cannot_be_reduced():
    r = row(0, "certified_common_prefix")
    with pytest.raises(ValueError):
        analyze_rows([r], protected=True)
    expected = [(s, i) for s in STRATA for i in range(192)]
    result = analyze_rows([r], protected=True, expected_keys=expected)
    assert result["planned_denominator"] == 768 and not result["campaign_complete"]
    assert "balanced_coverage" not in result
    assert len(result["missing_selected"]) == 767


def test_no_alternative_protected_entry_point(tmp_path):
    with pytest.raises(PermissionError):
        run_protected(tmp_path / "not-read", "fake", tmp_path / "out", 4)
    with pytest.raises(ValueError):
        run_fixed_namespace("protected", 1, tmp_path / "fixed")
    with pytest.raises(ValueError):
        run_resumable_namespace("protected", 1, tmp_path / "resume")
    assert not (tmp_path / "out").exists()


def test_freeze_identity_covers_parameters_and_command_is_explicit():
    original = {"source_commit": "a", "design": {"n": 768}, "resources": {"workers": 4}}
    changed = deepcopy(original)
    changed["design"]["n"] = 4
    assert canonical_hash(identity_fields(original)) != canonical_hash(identity_fields(changed))
    assert "--authorize-task08" in exact_command("ABC")
    assert "--evaluation-id ABC" in exact_command("ABC")
    assert RETIRED_INPUT_COUNT == 32


@pytest.mark.parametrize("alpha", [0, 1, float("nan"), -1])
def test_statistics_rejects_invalid_alpha(alpha):
    with pytest.raises(ValueError):
        hoeffding_half_width(768, alpha)


def test_paired_nan_refused():
    with pytest.raises(ValueError):
        bounded_difference_interval([0, float("nan")])


def test_extreme_results_retain_nonzero_uncertainty():
    for k in (0, 768):
        interval = conditional_mean_interval(k, 768)
        assert interval["upper"] - interval["lower"] > 0.049
        assert "conditional" in interval["target"]
        assert interval["fixed_generator_mean_requires_independence"]


def test_heterogeneous_concentration_numerically():
    import numpy as np

    distribution = np.array([1.0])
    for p in [0.0, 0.25, 0.6, 1.0] * 192:
        distribution = np.convolve(distribution, [1 - p, p])
    x = np.arange(769) / 768
    target = (0 + 0.25 + 0.6 + 1) / 4
    radius = hoeffding_half_width(768)
    assert distribution[np.abs(x - target) > radius].sum() <= 0.05


def test_dependent_timing_target_is_not_a_fixed_iid_mean():
    # Perfectly dependent outcomes all equal one Bernoulli draw.
    # p_1=.5 and p_i=observed X_1 thereafter, so the conditional target differs
    # from the fixed marginal .5 and the documented distinction is material.
    n = 768
    for x in (0, 1):
        predictable_mean = (0.5 + (n - 1) * x) / n
        ci = conditional_mean_interval(n * x, n)
        assert ci["lower"] <= predictable_mean <= ci["upper"]
        assert not ci["lower"] <= 0.5 <= ci["upper"]
