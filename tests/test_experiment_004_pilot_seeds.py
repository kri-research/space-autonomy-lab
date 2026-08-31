from pathlib import Path

import numpy as np
import pytest

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004_pilot.config import load_case_matrix, load_pilot_config
from kri_space_autonomy.experiment_004_pilot.seeds import (
    assert_materialization_targets_absent,
    materialize_pilot_seeds,
    validate_seed_contract,
)
from kri_space_autonomy.experiment_004_pilot.seeds import (
    test_fixture_scenario as make_test_fixture_scenario,
)


def inputs():
    return (
        load_pilot_config("experiments/004-pilot/config.json"),
        load_config("experiments/004/config.json"),
        load_case_matrix("experiments/004-pilot/case-matrix.json"),
    )


def test_seed_contract_freezes_counts_replay_and_disjoint_reserved_domains():
    pilot, _, _ = inputs()
    result = validate_seed_contract(
        pilot,
        "experiments/004-pilot/seed-contract.json",
        root=Path.cwd(),
    )
    assert result["passed"], result
    assert result["expected_root_rows"] == 44
    assert result["expected_episode_rows"] == 88
    assert result["historical_partition_43_overlap"] == 0
    assert result["partition_43_materialized"] is False
    assert result["partition_44_materialized"] is False


def test_fixture_roots_streams_and_balanced_order_are_deterministic_without_partition_43():
    pilot, foundation, cases = inputs()
    case = cases[4]
    scenarios = [
        make_test_fixture_scenario(pilot, foundation, case, replicate)
        for replicate in range(4)
    ]
    replay, replay_streams = make_test_fixture_scenario(pilot, foundation, case, 0)
    assert scenarios[0][0] == replay
    assert np.array_equal(
        scenarios[0][1].process_acceleration_mps2,
        replay_streams.process_acceleration_mps2,
    )
    assert all(item[0].partition_code == 941 for item in scenarios)
    assert len({item[0].root_seed_id for item in scenarios}) == 4
    first_positions = [item[0].configuration_run_order[0] for item in scenarios]
    assert first_positions.count("primary_reference") == 2
    assert first_positions.count("independent_monitor_gate") == 2


def test_partition_43_generator_refuses_before_a_verified_design_freeze(tmp_path):
    pilot, foundation, cases = inputs()
    with pytest.raises(RuntimeError, match="before verified pilot design freeze"):
        materialize_pilot_seeds(pilot, foundation, cases, root=tmp_path)
    assert not (tmp_path / "experiments/004-pilot/seeds").exists()


def test_write_once_targets_refuse_preexisting_seed_or_result_paths(tmp_path):
    seed_path = tmp_path / "experiments/004-pilot/seeds"
    seed_path.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="pre-existing"):
        assert_materialization_targets_absent(tmp_path)
    seed_path.rmdir()
    result_path = tmp_path / "results/experiment-004-pilot"
    result_path.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="pre-existing"):
        assert_materialization_targets_absent(tmp_path)


def test_no_reserved_output_is_created_by_design_or_tests():
    assert not Path("experiments/004-pilot/seeds").exists()
    assert not Path("results/experiment-004-pilot").exists()
    assert not Path("experiments/004-confirmatory").exists()
    assert not Path("results/experiment-004-confirmatory").exists()
