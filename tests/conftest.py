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
PHASE_INAPPLICABLE_TESTS = set(PRE_OUTCOME_DESELECTS) | E005_PREMATERIALIZATION_TESTS


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Deselect superseded pre-materialization guards after the recorded phase change."""

    root = Path(str(config.rootpath))
    closed_attempt = (
        root
        / "results/experiment-005-transfer-pilot/invalid-attempt-audit.json"
    ).is_file()
    if not closed_attempt:
        return
    phase_inapplicable = set(PHASE_INAPPLICABLE_TESTS)
    replacement_executed = (
        root
        / "results/experiment-005-transfer-pilot-replacement/execution-summary.json"
    ).is_file()
    if replacement_executed:
        phase_inapplicable.update(E005_REPLACEMENT_PREMATERIALIZATION_TESTS)
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
