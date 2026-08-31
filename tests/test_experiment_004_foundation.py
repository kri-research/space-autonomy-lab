from pathlib import Path

import numpy as np

from kri_space_autonomy.controller_adapter.contract import CONTRACT_VERSION
from kri_space_autonomy.experiment_004.config import (
    ACTION_ORDER,
    STATE_ORDER,
    load_config,
)
from kri_space_autonomy.experiment_004.evaluation import TechnicalStatus
from kri_space_autonomy.experiment_004.seeds import (
    STREAM_CODES,
    fixture_rng,
    validate_seed_contract,
)
from kri_space_autonomy.experiment_004.validation import run_foundation_checks


def config():
    return load_config("experiments/004/config.json")


def test_foundation_freezes_planar_state_orbit_and_exterior_hold_geometry():
    study = config()
    assert study.state_order == STATE_ORDER
    assert study.action_order == ACTION_ORDER
    assert study.coordinate_frame == "target-centered LVLH rotating with a circular chief orbit"
    assert study.hard_body_radius_m == 2.0
    assert study.keep_out_radius_m == 10.0
    assert study.hold_center_m == (0.0, -30.0)
    assert study.hold_center_m[1] + study.hold_position_halfwidth_m[1] < -study.keep_out_radius_m


def test_seed_contract_separates_all_pre_outcome_and_future_domains():
    study = config()
    result = validate_seed_contract(study, "experiments/004/seed-contract.json")
    assert result["passed"], result
    assert result["partition_codes"] == [41, 42, 43, 44, 941]
    assert result["pilot_materialized"] is False
    assert result["future_confirmatory_materialized"] is False
    assert not Path("experiments/004/seeds").exists()
    assert not Path("experiments/004-confirmatory").exists()
    assert not Path("results/experiment-004").exists()
    assert not Path("results/experiment-004-confirmatory").exists()


def test_non_outcome_fixture_rng_is_deterministic_and_domain_separated():
    study = config()
    first = fixture_rng(
        study,
        case_code=1,
        replicate=0,
        stream="primary_measurement",
    ).random(8)
    replay = fixture_rng(
        study,
        case_code=1,
        replicate=0,
        stream="primary_measurement",
    ).random(8)
    monitor = fixture_rng(
        study,
        case_code=1,
        replicate=0,
        stream="monitor_measurement",
    ).random(8)
    assert np.array_equal(first, replay)
    assert not np.array_equal(first, monitor)
    assert len(STREAM_CODES) == 8


def test_physical_mission_estimator_monitor_and_shared_fault_domains_are_separate():
    status = TechnicalStatus(
        primary_estimator_fault=True,
        monitor_estimator_fault=False,
        monitor_logic_fault=True,
        shared_cause_fault=False,
    )
    assert status.primary_estimator_fault
    assert not status.monitor_estimator_fault
    assert status.monitor_logic_fault
    assert not status.shared_cause_fault
    assert status.any_fault


def test_fail_closed_foundation_validation_uses_no_outcome_partition():
    result = run_foundation_checks(config())
    assert result["passed"], result
    assert result["outcome_campaign_executed"] is False
    assert result["pilot_partition_used"] is False
    assert result["future_confirmatory_partition_used"] is False
    assert result["scientific_findings_claimed"] is False
    assert all(item["passed"] for item in result["checks"].values())


def test_stable_scalar_product_contract_is_not_redefined():
    assert CONTRACT_VERSION == "1.0"
