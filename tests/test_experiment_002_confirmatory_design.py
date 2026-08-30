import json
from pathlib import Path

from kri_space_autonomy.experiment_002_confirmatory.config import (
    CONFIRMATORY_STRATA,
    STRATUM_CODES,
    load_confirmatory_config,
)
from kri_space_autonomy.experiment_002_confirmatory.seeds import (
    _balanced_subtype_order,
    materialize_nonreserved_test_scenario,
    validate_seed_contract,
)


def test_final_design_matches_frozen_002d_power_resolution():
    study, production = load_confirmatory_config(
        "experiments/002-confirmatory/config.json"
    )
    resolution = json.loads(
        Path("results/experiment-002d/analysis.json").read_text(encoding="utf-8")
    )
    assert resolution["decision"] == "resolved_freeze_confirmatory_design"
    assert resolution["power"]["recommended_confirmatory_seeds_per_stratum"] == 1000
    assert resolution["power"]["recommended_confirmatory_episodes"] == 32000
    assert study.partition_code == 16
    assert study.seeds_per_stratum == 1000
    assert study.planned_blocks == 8000
    assert study.planned_episodes == 32000
    assert study.arms == ("R", "D", "PS", "PD")
    assert study.stratum_weight == 0.125
    assert production.horizon_s == 600.0
    assert production.command_period_s == 1.0


def test_seed_contract_has_exact_eight_strata_without_materialized_roots():
    study, _ = load_confirmatory_config(
        "experiments/002-confirmatory/config.json"
    )
    result = validate_seed_contract(
        study, "experiments/002-confirmatory/seed-contract.json"
    )
    assert result["passed"], result
    assert STRATUM_CODES == {
        name: index + 1 for index, name in enumerate(CONFIRMATORY_STRATA)
    }
    reservation = json.loads(
        Path("experiments/002/seeds/future_confirmatory_reserved.json").read_text(
            encoding="utf-8"
        )
    )
    assert reservation["partition_code"] == 16
    assert reservation["status"] == "reserved_not_materialized_or_executed"
    assert not Path("experiments/002-confirmatory/seeds").exists()
    assert not Path("results/experiment-002-confirmatory").exists()


def test_mixed_strata_are_exactly_balanced_in_a_nonreserved_test_domain():
    for stratum in (
        "F3_monitor_channel_fault",
        "F4_shared_cause_navigation",
    ):
        order = _balanced_subtype_order(2002, 916, stratum, 1000)
        assert order.count("range_bias") == 500
        assert order.count("dropout") == 500


def test_nonreserved_f7_fixture_preserves_original_combined_fault_bounds():
    study, production = load_confirmatory_config(
        "experiments/002-confirmatory/config.json"
    )
    scenario = materialize_nonreserved_test_scenario(
        study,
        production,
        "F7_combined_primary_dropout_actuator_degradation",
        17,
        partition_code=916,
    )
    assert 120.0 <= scenario.navigation_onset_s < 300.0
    assert 5.0 <= scenario.navigation_end_s - scenario.navigation_onset_s < 30.0
    gap = scenario.actuator_onset_s - scenario.navigation_onset_s
    assert -30.0 <= gap < 30.0
    assert 30.0 <= scenario.actuator_end_s - scenario.actuator_onset_s < 150.0
    assert 0.25 <= scenario.actuator_effectiveness < 0.75
    assert scenario.fault_onset_s == min(
        scenario.navigation_onset_s, scenario.actuator_onset_s
    )
    assert scenario.fault_end_s == max(
        scenario.navigation_end_s, scenario.actuator_end_s
    )
    assert set(scenario.arm_run_order) == set(study.arms)
