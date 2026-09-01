from pathlib import Path

import numpy as np

from kri_space_autonomy.experiment_005.config import (
    COMMAND_ORDER,
    INERTIAL_STATE_ORDER,
    RELATIVE_STATE_ORDER,
    load_config,
)
from kri_space_autonomy.experiment_005.seeds import (
    STREAM_CODES,
    fixture_rng,
    validate_seed_contract,
)
from kri_space_autonomy.experiment_005.validation import run_foundation_checks


def config():
    return load_config("experiments/005/config.json")


def test_foundation_explicitly_separates_inertial_truth_from_online_hcw_model():
    study = config()
    assert study.truth_model == "nonlinear central-gravity two-body inertial Cartesian"
    assert study.controller_estimator_model == "Experiment 004 planar HCW"
    assert study.inertial_state_order == INERTIAL_STATE_ORDER
    assert study.relative_state_order == RELATIVE_STATE_ORDER
    assert study.command_order == COMMAND_ORDER
    assert study.production_integrator == "fixed-step-rk4"
    assert study.reference_integrator == "DOP853"


def test_seed_domains_are_new_disjoint_and_outcome_partitions_unmaterialized():
    study = config()
    result = validate_seed_contract(study, "experiments/005/seed-contract.json")
    assert result["passed"], result
    assert result["partition_codes"] == [51, 52, 53, 951]
    assert not Path("experiments/005/seeds").exists()
    assert not Path("experiments/005-pilot").exists()
    assert not Path("experiments/005-confirmatory").exists()
    assert not Path("results/experiment-005").exists()
    assert not Path("results/experiment-005-pilot").exists()
    assert not Path("results/experiment-005-confirmatory").exists()


def test_fixture_rng_is_deterministic_and_channel_separated():
    study = config()
    first = fixture_rng(
        study,
        geometry_case=1,
        challenge_case=2,
        replicate=0,
        stream="primary_navigation",
    ).random(8)
    replay = fixture_rng(
        study,
        geometry_case=1,
        challenge_case=2,
        replicate=0,
        stream="primary_navigation",
    ).random(8)
    monitor = fixture_rng(
        study,
        geometry_case=1,
        challenge_case=2,
        replicate=0,
        stream="monitor_navigation",
    ).random(8)
    assert np.array_equal(first, replay)
    assert not np.array_equal(first, monitor)
    assert len(STREAM_CODES) == 7


def test_foundation_validation_is_outcome_free_and_fail_closed():
    result = run_foundation_checks(config())
    assert result["passed"], result
    assert result["smallest_scientific_blocker"] is None
    assert result["experiment_004_outcomes_used_for_design"] is False
    assert result["experiment_005_calibration_partition_used"] is False
    assert result["experiment_005_pilot_partition_used"] is False
    assert result["experiment_005_confirmatory_partition_used"] is False
    assert result["outcome_campaign_executed"] is False
    assert result["scientific_findings_claimed"] is False
    assert all(check["passed"] for check in result["checks"].values())
