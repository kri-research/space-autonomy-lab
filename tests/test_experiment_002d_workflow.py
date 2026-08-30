from pathlib import Path

from kri_space_autonomy.experiment_002c.workflow import repository_hygiene_scan
from kri_space_autonomy.experiment_002d.workflow import (
    EPISODES_PATH,
    RESULT_OUTPUTS,
    verify_historical_records,
)


def test_historical_experiments_002_002b_002c_verify_unchanged():
    result = verify_historical_records(Path.cwd())
    assert result["passed"], result
    assert result["experiment_002c_freeze_id"] == (
        "8157fefc06ea1aec4121b475d0ffa068576c8f98807406205c8f47f2120e479a"
    )
    assert result["original_design_source_verified_before_freeze"]


def test_002d_outputs_are_separate_and_bounded():
    assert EPISODES_PATH.as_posix().startswith("results/experiment-002d/")
    assert len(RESULT_OUTPUTS) == len(set(RESULT_OUTPUTS))
    assert not any("confirmatory" in path.name for path in RESULT_OUTPUTS)


def test_repository_publication_privacy_scan_passes_before_outcomes():
    result = repository_hygiene_scan(Path.cwd())
    assert result["passed"], result
