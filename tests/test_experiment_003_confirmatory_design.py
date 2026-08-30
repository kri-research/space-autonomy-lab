import json
from pathlib import Path

from kri_space_autonomy.experiment_003.config import ESTIMATOR_STRATA
from kri_space_autonomy.experiment_003_confirmatory.config import (
    PRIMARY_SENSITIVITIES,
    load_confirmatory_config,
)
from kri_space_autonomy.experiment_003_confirmatory.seeds import (
    PRIOR_SEED_DIRECTORIES,
    validate_seed_contract,
)


def test_confirmatory_design_is_exactly_seven_by_750_by_four():
    study, foundation, production = load_confirmatory_config(
        "experiments/003-confirmatory/config.json"
    )
    assert study.roots_per_stratum == 750
    assert study.stratum_count == len(ESTIMATOR_STRATA) == 7
    assert study.stratum_weight == 1.0 / 7.0
    assert study.arms == ("R", "D", "PS", "PD")
    assert study.planned_blocks == 5250
    assert study.planned_episodes == 21000
    assert study.replay_roots_per_stratum == 30
    assert study.replay_episodes == 840
    assert foundation.confirmatory_partition_code == study.partition_code == 32
    assert production.horizon_s == 600.0


def test_analysis_and_seed_contract_are_frozen_without_partition_32_materialization():
    study, _, _ = load_confirmatory_config("experiments/003-confirmatory/config.json")
    result = validate_seed_contract(
        study,
        "experiments/003-confirmatory/seed-contract.json",
    )
    assert result["passed"], result
    assert study.bootstrap_replicates == 50_000
    assert study.bootstrap_seed == 300318
    assert study.secondary_randomization_replicates == 200_000
    assert study.secondary_randomization_seed == 300319
    assert study.h2_noninferiority_margin == -0.03
    assert study.primary_sensitivities == PRIMARY_SENSITIVITIES
    assert not Path("experiments/003-confirmatory/seeds").exists()
    assert not Path("results/experiment-003-confirmatory").exists()


def test_seed_contract_covers_all_prior_seed_directories_and_fixed_replay():
    contract = json.loads(
        Path("experiments/003-confirmatory/seed-contract.json").read_text(encoding="utf-8")
    )
    assert Path("experiments/003/seeds") in PRIOR_SEED_DIRECTORIES
    assert contract["partition_code"] == 32
    assert contract["expected_root_rows"] == 5250
    assert contract["expected_episode_rows"] == 21000
    assert contract["replay_roots_per_stratum"] == 30
    assert contract["expected_replay_episode_rows"] == 840
    assert contract["replacement_or_extension_allowed"] is False
    assert contract["outcome_dependent_materialization_allowed"] is False
