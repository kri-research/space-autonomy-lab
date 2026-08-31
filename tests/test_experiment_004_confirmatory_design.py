import json
from pathlib import Path

from kri_space_autonomy.experiment_004_confirmatory.analysis import exact_primary_sample_size
from kri_space_autonomy.experiment_004_confirmatory.config import (
    ASSURANCE_STRATA,
    PRIMARY_STRATA,
    ROOTS_BY_STRATUM,
    load_confirmatory_config,
)
from kri_space_autonomy.experiment_004_confirmatory.seeds import (
    load_confirmatory_cases,
    validate_seed_contract,
)


def study():
    return load_confirmatory_config("experiments/004-confirmatory/config.json")


def test_confirmatory_population_arms_and_counts_are_exact():
    config = study()
    assert config.strata == ASSURANCE_STRATA
    assert config.primary_strata == PRIMARY_STRATA
    assert config.roots_by_stratum == ROOTS_BY_STRATUM
    assert config.configurations == ("primary_reference", "independent_monitor_gate")
    assert config.primary_roots == 1068
    assert config.planned_blocks == 1452
    assert config.planned_episodes == 2904
    assert config.replay_blocks == 64
    assert config.replay_episodes == 128
    assert all(count % 2 == 0 for count in config.roots_by_stratum.values())


def test_scientific_population_excludes_forced_physical_fixtures():
    config = study()
    cases = load_confirmatory_cases(study=config)
    assert tuple(case.id for case in cases) == config.strata
    assert all(case.fixture == "stochastic_bounded_initial_state" for case in cases)
    assert not any(case.id.startswith(("P01_", "P02_", "P03_")) for case in cases)


def test_exact_primary_sample_size_is_smallest_even_worst_case_design():
    config = study()
    result = exact_primary_sample_size(
        alpha=config.primary_one_sided_alpha,
        target_power=config.primary_target_power,
        planning_net_reduction=config.primary_planning_net_reduction,
    )
    assert result["roots"] == config.primary_roots == 1068
    assert result["critical_beneficial_discordances_if_all_discordant"] == 567
    assert result["achieved_alpha"] <= 0.025
    assert result["achieved_power"] >= 0.90
    assert 0.9005 < result["achieved_power"] < 0.9007


def test_partition_44_contract_is_fixed_and_unmaterialized():
    config = study()
    result = validate_seed_contract(
        config,
        "experiments/004-confirmatory/seed-contract.json",
        root=Path.cwd(),
    )
    assert result["passed"], result
    assert result["partition_code"] == 44
    assert result["expected_root_rows"] == 1452
    assert result["expected_episode_rows"] == 2904
    assert result["historical_partition_44_overlap"] == 0
    assert not Path("experiments/004-confirmatory/seeds").exists()
    assert not Path("results/experiment-004-confirmatory").exists()
    contract = json.loads(Path("experiments/004-confirmatory/seed-contract.json").read_text())
    assert contract["generator_invoked"] is False
    assert contract["replacement_extension_or_count_drift_allowed"] is False
    assert contract["outcome_dependent_materialization_allowed"] is False
