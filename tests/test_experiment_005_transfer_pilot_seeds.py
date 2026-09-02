from pathlib import Path

import numpy as np
import pytest

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_005.config import load_config as load_e005_config
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    assert_materialization_targets_absent,
    materialize_pilot_seeds,
    validate_seed_contract,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    test_fixture_scenario as make_test_fixture_scenario,
)


def inputs():
    return (
        load_pilot_config(root=Path.cwd()),
        load_e005_config(root=Path.cwd()),
        load_e004_config(),
        load_case_matrix(),
    )


def test_seed_contract_freezes_partition_52_counts_and_partition_53_absence():
    pilot, _, _, _ = inputs()
    result = validate_seed_contract(
        pilot,
        "experiments/005-transfer-pilot/seed-contract.json",
        root=Path.cwd(),
    )
    assert result["passed"], result
    assert result["expected_root_rows"] == 20
    assert result["expected_episode_rows"] == 40
    assert result["partition_52_overlap"] == 0
    assert result["partition_53_overlap"] == 0
    assert result["partition_52_materialized"] is False
    assert result["partition_53_materialized"] is False


def test_fixture_roots_streams_and_order_are_deterministic_without_partition_52():
    pilot, foundation, e004, cases = inputs()
    case = cases[3]
    scenarios = [
        make_test_fixture_scenario(pilot, foundation, e004, case, replicate)
        for replicate in range(2)
    ]
    replay, replay_streams = make_test_fixture_scenario(
        pilot, foundation, e004, case, 0
    )
    assert scenarios[0][0] == replay
    assert np.array_equal(
        scenarios[0][1].process_acceleration_mps2,
        replay_streams.process_acceleration_mps2,
    )
    assert all(item[0].partition_code == 951 for item in scenarios)
    assert len({item[0].root_seed_id for item in scenarios}) == 2
    assert {item[0].configuration_run_order[0] for item in scenarios} == {
        "primary_reference",
        "independent_monitor_gate",
    }


def test_partition_52_materializer_refuses_without_verified_design_freeze(tmp_path):
    pilot, foundation, e004, cases = inputs()
    with pytest.raises(RuntimeError, match="before verified design freeze"):
        materialize_pilot_seeds(
            pilot, foundation, e004, cases, root=tmp_path
        )
    assert not (tmp_path / "experiments/005-transfer-pilot/seeds").exists()


def test_write_once_targets_and_partition_53_fail_closed(tmp_path):
    seed_path = tmp_path / "experiments/005-transfer-pilot/seeds"
    seed_path.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="pre-existing"):
        assert_materialization_targets_absent(tmp_path)
    seed_path.rmdir()
    confirmatory = tmp_path / "experiments/005-confirmatory"
    confirmatory.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="partition 53"):
        assert_materialization_targets_absent(tmp_path)
