from pathlib import Path

import numpy as np

from kri_space_autonomy.assurance_report.policy import POLICY_SCHEMA_VERSION
from kri_space_autonomy.controller_adapter.contract import CONTRACT_VERSION
from kri_space_autonomy.experiment_003.config import ARMS, ESTIMATOR_STRATA, load_config
from kri_space_autonomy.experiment_003.estimator import FilterHealth, NavigationFilter
from kri_space_autonomy.experiment_003.evaluation import (
    OfflineEstimatorSample,
    classify_estimator_recovery,
)
from kri_space_autonomy.experiment_003.measurements import (
    MeasurementFault,
    navigation_packet,
)
from kri_space_autonomy.experiment_003.seeds import (
    STRATUM_CODES,
    STREAM_CODES,
    validate_seed_contract,
)
from kri_space_autonomy.experiment_003.seeds import test_fixture_rng as fixture_rng
from kri_space_autonomy.fault_suite.manifest import SCHEMA_VERSION as FAULT_SCHEMA_VERSION


def config():
    return load_config("experiments/003/config.json")


def test_design_has_exact_paired_arms_strata_and_small_pilot():
    study, _ = config()
    assert study.arms == ARMS == ("R", "D", "PS", "PD")
    assert study.strata == ESTIMATOR_STRATA
    assert study.pilot_roots_per_stratum == 64
    assert study.pilot_blocks == 448
    assert study.pilot_episodes == 1792
    assert len(STRATUM_CODES) == 7
    assert len(STREAM_CODES) == 6


def test_seed_contract_reserves_outcome_partitions_without_materializing_them():
    study, _ = config()
    result = validate_seed_contract(
        study,
        "experiments/003/seed-contract.json",
    )
    assert result["passed"], result
    assert result["generator_invoked"] is False
    assert result["outcome_seed_files_present"] is False
    assert result["outcome_result_files_present"] is False
    assert not Path("experiments/003/seeds").exists()
    assert not Path("results/experiment-003").exists()


def test_non_outcome_fixture_rng_is_deterministic_and_domain_separated():
    study, _ = config()
    first = fixture_rng(study, "E0_nominal", 0, "primary_measurement").random(8)
    replay = fixture_rng(study, "E0_nominal", 0, "primary_measurement").random(8)
    monitor = fixture_rng(study, "E0_nominal", 0, "monitor_measurement").random(8)
    assert np.array_equal(first, replay)
    assert not np.array_equal(first, monitor)


def test_measurement_faults_are_channel_bounded_and_bias_is_unannounced():
    study, production = config()
    filter_ = NavigationFilter(study, production)
    fault = MeasurementFault(
        "E1_primary_range_bias",
        "primary",
        10.0,
        20.0,
        range_bias_m=5.0,
    )
    primary = navigation_packet(
        sequence_id=10,
        measured_at_s=10.0,
        received_at_s=10.0,
        range_value_m=20.0,
        velocity_value_mps=-0.1,
        range_noise_m=0.0,
        velocity_noise_mps=0.0,
        range_quantization_m=production.range_quantization_m,
        velocity_quantization_mps=production.velocity_quantization_mps,
        nominal_covariance=filter_.nominal_measurement_covariance,
        channel="primary",
        fault=fault,
        previous_packet=None,
    )
    monitor = navigation_packet(
        sequence_id=10,
        measured_at_s=10.0,
        received_at_s=10.0,
        range_value_m=20.0,
        velocity_value_mps=-0.1,
        range_noise_m=0.0,
        velocity_noise_mps=0.0,
        range_quantization_m=production.range_quantization_m,
        velocity_quantization_mps=production.velocity_quantization_mps,
        nominal_covariance=filter_.nominal_measurement_covariance,
        channel="monitor",
        fault=fault,
        previous_packet=None,
    )
    assert primary is not None and monitor is not None
    assert primary.range_m == monitor.range_m + 5.0
    assert not hasattr(primary, "fault_active")
    assert not hasattr(primary, "fault_label")


def test_offline_recovery_uses_truth_only_after_runtime_execution():
    study, _ = config()
    samples = [
        OfflineEstimatorSample(
            float(time_s),
            2.0 if time_s < 20 else 0.1,
            0.1 if time_s < 20 else 0.005,
            0.0,
            20.0 if time_s < 20 else 1.0,
            FilterHealth.DEGRADED if time_s < 20 else FilterHealth.VALID,
        )
        for time_s in range(10, 61)
    ]
    result = classify_estimator_recovery(
        samples,
        fault_onset_s=10.0,
        fault_end_s=20.0,
        failed=False,
        sustained_success=True,
        protected_arm=True,
        fallback_latched=False,
        config=study,
    )
    assert result["recovery_state"] == "RECOVERED"
    assert result["estimator_first_affected_s"] == 10.0
    assert result["qualifying_recovery_start_s"] == 20.0


def test_stable_product_contract_versions_are_not_redefined():
    assert CONTRACT_VERSION == "1.0"
    assert FAULT_SCHEMA_VERSION == "kri-fault-suite/1.0"
    assert POLICY_SCHEMA_VERSION == "kri-assessment-policy/1.0"
