import json
from pathlib import Path

from kri_space_autonomy.experiment_005_confirmatory.config import (
    CASE_WEIGHTS,
    PRIMARY_CASES,
    ROOTS_BY_CASE,
    load_confirmatory_config,
)
from kri_space_autonomy.experiment_005_confirmatory.seeds import (
    load_confirmatory_cases,
    partition_53_unmaterialized,
    validate_seed_contract,
)


def study():
    return load_confirmatory_config("experiments/005-confirmatory/config.json")


def test_confirmatory_question_population_and_counts_are_exact():
    config = study()
    assert config.cases == PRIMARY_CASES
    assert config.case_weights == CASE_WEIGHTS
    assert config.roots_by_case == ROOTS_BY_CASE
    assert config.configurations == ("primary_reference", "independent_monitor_gate")
    assert config.primary_roots == 1068
    assert config.planned_blocks == 1068
    assert config.planned_episodes == 2136
    assert config.replay_blocks == 16
    assert config.replay_episodes == 32
    assert config.minimum_covariance_eigenvalue_lower_bound == -1e-12
    assert config.maximum_covariance_trace_exclusive_upper_bound == 1_000_000.0
    assert config.partition_54_outcomes_used_for_design is False


def test_scientific_population_uses_only_frozen_stochastic_primary_cases():
    config = study()
    cases = load_confirmatory_cases(study=config)
    assert tuple(case.id for case in cases) == config.cases
    assert all(case.fixture == "stochastic_bounded_initial_state" for case in cases)
    assert all(case.horizon_kind == "standard" for case in cases)
    assert {case.case_code for case in cases} == {1, 2}


def test_partition_53_contract_is_fixed_and_unmaterialized():
    config = study()
    result = validate_seed_contract(
        config,
        "experiments/005-confirmatory/seed-contract.json",
        root=Path.cwd(),
        require_unmaterialized=True,
    )
    assert result["passed"], result
    assert result["expected_root_rows"] == 1068
    assert result["expected_episode_rows"] == 2136
    assert result["expected_replay_root_rows"] == 16
    assert result["expected_replay_episode_rows"] == 32
    assert partition_53_unmaterialized(Path.cwd())["passed"]
    contract = json.loads(Path("experiments/005-confirmatory/seed-contract.json").read_text())
    assert contract["generator_invoked"] is False
    assert contract["maximum_retries"] == 0
    assert contract["maximum_replacement_roots"] == 0
    assert contract["replacement_extension_or_count_drift_allowed"] is False
    assert contract["outcome_dependent_materialization_allowed"] is False
