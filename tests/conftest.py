from __future__ import annotations

from pathlib import Path

import pytest

from kri_space_autonomy.experiment_004_closeout import PRE_OUTCOME_DESELECTS

E005_PREMATERIALIZATION_TESTS = {
    (
        "tests/test_experiment_005_foundation.py::"
        "test_seed_domains_are_new_disjoint_and_outcome_partitions_unmaterialized"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_calibration.py::"
        "test_calibration_does_not_materialize_partition_52_or_touch_53"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_seeds.py::"
        "test_seed_contract_freezes_partition_52_counts_and_partition_53_absence"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_workflow.py::"
        "test_partition_52_is_authorized_only_postfreeze_and_remains_absent"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_workflow.py::"
        "test_case_matrix_loads_without_materializing_any_future_partition"
    ),
}
E005_REPLACEMENT_PREMATERIALIZATION_TESTS = {
    (
        "tests/test_experiment_005_transfer_pilot_replacement.py::"
        "test_partition_54_is_fresh_reserved_and_only_execution_identity_changes"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_replacement.py::"
        "test_frozen_amendment_verifies_when_present"
    ),
}
E005_CONFIRMATORY_POSTEXECUTION_TESTS = {
    (
        "tests/test_experiment_005_confirmatory_design.py::"
        "test_partition_53_contract_is_fixed_and_unmaterialized"
    ),
    (
        "tests/test_experiment_005_confirmatory_seeds.py::"
        "test_generator_is_exact_freeze_gated_but_not_invoked_by_design_tests"
    ),
    (
        "tests/test_experiment_005_confirmatory_validation.py::"
        "test_power_execution_and_partition_contracts_are_ready_without_materialization"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_workflow.py::"
        "test_partition_53_is_untouched_and_has_no_generator_or_roots"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_closeout.py::"
        "test_invalid_partition_52_attempt_is_preserved_and_verified"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_replacement.py::"
        "test_amendment_preserves_invalid_closeout_and_scientific_design"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_replacement_closeout.py::"
        "test_partition_54_execution_and_frozen_gates_validate"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_replacement_closeout.py::"
        "test_closeout_is_descriptive_and_leaves_partition_53_untouched"
    ),
    (
        "tests/test_experiment_005_transfer_pilot_replacement_closeout.py::"
        "test_public_closeout_package_verifies_when_materialized"
    ),
}
SHALLOW_HISTORY_TESTS = {
    (
        "tests/test_experiment_005_confirmatory_validation.py::"
        "test_complete_repaired_lineage_and_blocker_audit_are_preserved"
    ),
}
PHASE_INAPPLICABLE_TESTS = set(PRE_OUTCOME_DESELECTS) | E005_PREMATERIALIZATION_TESTS


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Deselect guards superseded by recorded phase changes.

    Full-history lineage checks remain active locally. A shallow CI checkout cannot
    resolve the frozen historical commit chain, so only the history-dependent test is
    deselected there; stored immutable identities remain covered by the phase package.
    """

    root = Path(str(config.rootpath))
    closed_attempt = (
        root / "results/experiment-005-transfer-pilot/invalid-attempt-audit.json"
    ).is_file()
    if not closed_attempt:
        return

    phase_inapplicable = set(PHASE_INAPPLICABLE_TESTS)
    replacement_executed = (
        root / "results/experiment-005-transfer-pilot-replacement/execution-summary.json"
    ).is_file()
    if replacement_executed:
        phase_inapplicable.update(E005_REPLACEMENT_PREMATERIALIZATION_TESTS)

    confirmatory_closed = (
        root / "docs/experiment-005-confirmatory-closeout.json"
    ).is_file()
    if confirmatory_closed:
        phase_inapplicable.update(E005_CONFIRMATORY_POSTEXECUTION_TESTS)

    if (root / ".git/shallow").is_file():
        phase_inapplicable.update(SHALLOW_HISTORY_TESTS)

    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if item.nodeid in phase_inapplicable:
            deselected.append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
