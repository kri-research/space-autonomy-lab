from pathlib import Path

from kri_space_autonomy.experiment_004_confirmatory.config import EXPECTED_BASE
from kri_space_autonomy.experiment_004_confirmatory.validation import (
    architecture_capability,
    information_boundaries,
    verify_partition_44_unmaterialized,
)
from kri_space_autonomy.experiment_004_confirmatory.workflow import (
    EXPECTED_BRANCH,
    PHASE_INAPPLICABLE_TESTS,
    SOURCE_GLOBS,
)


def test_requested_branch_base_and_additive_scope_are_frozen():
    assert EXPECTED_BRANCH == "experiment-004-confirmatory-design"
    assert EXPECTED_BASE == "57c1a272136e2e5a30afd01eea6f6adc45007bb3"
    assert "src/kri_space_autonomy/experiment_004_confirmatory/*.py" in SOURCE_GLOBS
    assert "tests/test_experiment_004_confirmatory_*.py" in SOURCE_GLOBS
    assert any("partition_44_remains_reserved" in test for test in PHASE_INAPPLICABLE_TESTS)


def test_preoutcome_event_and_command_discordance_capability_uses_only_fixtures():
    result = architecture_capability(Path.cwd())
    assert result["passed"], result
    assert all(result["partition_941_event_fixtures"].values())
    assert result["configuration_command_discordance_capable"] is True
    assert result["confirmatory_partition_used"] is False
    assert result["confirmatory_outcomes_generated"] is False


def test_information_and_truth_boundaries_remain_fail_closed():
    result = information_boundaries()
    assert result["passed"], result
    assert result["prohibited_online_names"] == []
    assert result["truth_evaluator_returns_data_to_online_path"] is False


def test_partition_44_has_no_seed_result_or_root_rows():
    result = verify_partition_44_unmaterialized(Path.cwd())
    assert result["passed"], result
    assert result["seed_or_result_paths_present"] == []
    assert result["materialized_root_rows"] == []
    assert result["generator_invoked"] is False
    assert result["outcomes_executed"] is False
