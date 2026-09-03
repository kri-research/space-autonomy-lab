from kri_space_autonomy.experiment_005_confirmatory.analysis import (
    exact_mission_power,
    exact_primary_sample_size,
)
from kri_space_autonomy.experiment_005_confirmatory.config import load_confirmatory_config
from kri_space_autonomy.experiment_005_confirmatory.validation import (
    synthetic_analysis_sign_checks,
)


def study():
    return load_confirmatory_config("experiments/005-confirmatory/config.json")


def test_exact_primary_sample_size_is_smallest_even_worst_case_design():
    config = study()
    result = exact_primary_sample_size(
        alpha=config.primary_one_sided_alpha,
        target_power=config.primary_target_power,
        planning_net_reduction=config.primary_planning_net_reduction,
    )
    previous = exact_primary_sample_size(
        alpha=config.primary_one_sided_alpha,
        target_power=0.899,
        planning_net_reduction=config.primary_planning_net_reduction,
    )
    assert result["roots"] == config.primary_roots == 1068
    assert result["critical_beneficial_discordances_if_all_discordant"] == 567
    assert result["achieved_alpha"] <= 0.025
    assert result["achieved_power"] >= 0.90
    assert previous["roots"] <= 1066


def test_gatekept_mission_test_is_not_sample_size_limiting():
    config = study()
    result = exact_mission_power(
        roots=config.primary_roots,
        alpha=config.primary_one_sided_alpha,
        margin=config.mission_harm_margin,
        planning_rate=config.mission_harm_planning_rate,
    )
    assert result["maximum_harms_for_rejection"] == 39
    assert result["achieved_alpha"] <= 0.025
    assert result["achieved_power"] > 0.9999999999


def test_synthetic_non_outcome_rows_lock_signs_gatekeeping_and_saturation():
    result = synthetic_analysis_sign_checks(study())
    assert result["passed"], result
    assert result["fixtures_are_synthetic_non_outcome_rows"] is True
    assert result["partition_53_used"] is False
    assert result["checks"]["beneficial_fixture_favorable"] is True
    assert result["checks"]["reversed_fixture_inconclusive"] is True
    assert result["checks"]["mission_harm_gate_closes"] is True
    assert result["checks"]["saturated_endpoint_inconclusive"] is True
    assert result["checks"]["covariance_failure_invalidates_inference"] is True
    assert result["checks"]["fault_activation_failure_invalidates_inference"] is True
