from pathlib import Path

from kri_space_autonomy.experiment_005_confirmatory.config import (
    BASE_COMMIT,
    load_confirmatory_config,
)
from kri_space_autonomy.experiment_005_confirmatory.seeds import partition_53_unmaterialized
from kri_space_autonomy.experiment_005_confirmatory.validation import (
    execution_protocol_contract,
    lineage_integrity,
    matrix_and_outcome_boundary,
    sample_size_and_analysis_contract,
)
from kri_space_autonomy.experiment_005_confirmatory.workflow import (
    EXPECTED_BRANCH,
    PHASE_INAPPLICABLE_TESTS,
    SOURCE_GLOBS,
)


def study():
    return load_confirmatory_config("experiments/005-confirmatory/config.json")


def test_requested_branch_base_and_additive_scope_are_frozen():
    assert EXPECTED_BRANCH == "experiment-005-confirmatory-design-v2"
    assert BASE_COMMIT == "46c6de41afa46e7e43b1c6074e59ba54dd3d99b8"
    assert "src/kri_space_autonomy/experiment_005_confirmatory/*.py" in SOURCE_GLOBS
    assert "tests/test_experiment_005_confirmatory_*.py" in SOURCE_GLOBS
    assert any("replacement_closeout" in test for test in PHASE_INAPPLICABLE_TESTS)


def test_complete_repaired_lineage_and_blocker_audit_are_preserved():
    result = lineage_integrity(Path.cwd())
    assert result["passed"], result
    assert result["foundation_workflow_restored"] is True
    assert result["blocker_audit_preserved"] is True
    assert result["invalid_partition_52_preserved"] is True
    assert result["partition_54_closeout"]["passed"] is True
    assert result["partition_54_closeout"]["replay_byte_identical"] is True
    assert result["pre_design_complete_verifier"] is True


def test_design_is_outcome_free_and_uses_exact_inherited_cases():
    result = matrix_and_outcome_boundary(Path.cwd(), study())
    assert result["passed"], result
    assert result["partition_54_effect_rate_direction_or_discordance_used"] is False
    assert result["checks"]["pre_outcome_analysis_contract_inherited"] is True
    assert result["checks"]["no_observed_outcome_fields_imported"] is True


def test_power_execution_and_partition_contracts_are_ready_without_materialization():
    power = sample_size_and_analysis_contract(study())
    execution = execution_protocol_contract()
    partition = partition_53_unmaterialized(Path.cwd())
    assert power["passed"], power
    assert execution["passed"], execution
    assert partition["passed"], partition
    assert partition["seed_or_result_paths_present"] == []
    assert partition["historical_root_overlap"] == 0
