from kri_space_autonomy.experiment_004_confirmatory.config import load_confirmatory_config
from kri_space_autonomy.experiment_004_confirmatory.validation import (
    synthetic_analysis_sign_checks,
)


def test_synthetic_non_outcome_fixtures_lock_adverse_signs_and_gatekeeping():
    study = load_confirmatory_config("experiments/004-confirmatory/config.json")
    result = synthetic_analysis_sign_checks(study)
    assert result["passed"], result
    assert result["fixtures_are_synthetic_non_outcome_rows"] is True
    assert result["partition_44_used"] is False
    assert result["beneficial_fixture_decision"] == "favorable"
    assert result["beneficial_fixture_primary_difference"] < 0.0
    assert result["reversed_fixture_decision"] == "inconclusive"
    assert result["mission_harm_fixture_passed"] is False
