from pathlib import Path

from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    FOUNDATION_FREEZE_ID,
    FOUNDATION_READINESS_ID,
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.validation import (
    foundation_identity,
    partition_52_authorization,
    partition_53_inert,
)


def test_foundation_source_hashes_and_readiness_identity_are_unchanged():
    result = foundation_identity(Path.cwd())
    assert result["passed"], result
    assert result["freeze_id"] == FOUNDATION_FREEZE_ID
    assert result["readiness_id"] == FOUNDATION_READINESS_ID
    assert result["source_mismatches"] == []
    transition = result["phase_transition"]
    assert transition["historical_partition_state_is_not_reasserted_as_current"] is True
    assert transition["foundation_files_modified"] is False


def test_partition_52_is_authorized_only_postfreeze_and_remains_absent():
    pilot = load_pilot_config(root=Path.cwd())
    result = partition_52_authorization(Path.cwd(), pilot)
    assert result["passed"], result
    assert result["generator_available_only_after_verified_design_freeze"] is True
    assert result["generator_invoked"] is False
    assert result["seed_or_result_paths_present"] == []


def test_partition_53_is_untouched_and_has_no_generator_or_roots():
    pilot = load_pilot_config(root=Path.cwd())
    result = partition_53_inert(Path.cwd(), pilot)
    assert result["passed"], result
    assert result["state"]["generator_available"] is False
    assert result["forbidden_symbols_found"] == []
    assert result["root_rows"] == []
    assert result["paths_present"] == []


def test_case_matrix_loads_without_materializing_any_future_partition():
    pilot = load_pilot_config(root=Path.cwd())
    cases = load_case_matrix()
    assert len(cases) == pilot.case_count == 10
    assert not Path("experiments/005-transfer-pilot/seeds").exists()
    assert not Path("results/experiment-005-transfer-pilot").exists()
    assert not Path("experiments/005-confirmatory").exists()
    assert not Path("results/experiment-005-confirmatory").exists()
