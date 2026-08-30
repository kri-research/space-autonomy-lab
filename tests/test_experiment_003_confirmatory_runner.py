from kri_space_autonomy.experiment_002.policy import FrozenPolicy
from kri_space_autonomy.experiment_003.seeds import materialize_test_scenario
from kri_space_autonomy.experiment_003_confirmatory.config import (
    load_confirmatory_config,
)
from kri_space_autonomy.experiment_003_confirmatory.runner import (
    run_block_for_partition,
)


def test_confirmatory_runner_is_a_thin_phase_wrapper_in_nonoutcome_test_domain():
    study, foundation, production = load_confirmatory_config(
        "experiments/003-confirmatory/config.json"
    )
    scenario, _ = materialize_test_scenario(
        foundation,
        production,
        "E0_nominal",
        41,
    )
    policy = FrozenPolicy.load(
        "artifacts/experiment-002/policy-primary.npz",
        "artifacts/experiment-002/policy-primary.manifest.json",
        production,
    )
    rows = run_block_for_partition(
        study,
        foundation,
        production,
        scenario,
        policy,
        "test-config-hash",
        partition_code=foundation.test_fixture_partition_code,
    )
    assert len(rows) == 4
    assert {row.arm for row in rows} == set(study.arms)
    assert all(row.study_phase == "confirmatory" for row in rows)
    assert all(row.schema_version == study.schema_version for row in rows)
    assert all(row.root_seed_id == scenario.root_seed_id for row in rows)
