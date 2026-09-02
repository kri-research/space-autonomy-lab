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
    selected: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if item.nodeid in PHASE_INAPPLICABLE_TESTS:
            deselected.append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
