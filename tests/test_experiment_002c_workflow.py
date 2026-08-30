from pathlib import Path

from kri_space_autonomy.experiment_002c.workflow import (
    NUMERICAL_PATH,
    RESULT_OUTPUTS,
    repository_hygiene_scan,
    verify_historical_records,
)


def test_historical_experiment_002_and_002b_records_verify_unchanged():
    result = verify_historical_records(Path.cwd())
    assert result["passed"], result
    assert result["experiment_002b_freeze_id"] == (
        "4bb93ac705f29108b06fc080fde5a8d944ebd3bac00137d60063128b5e79bfb7"
    )


def test_002c_outputs_are_separate_and_numerical_only():
    assert NUMERICAL_PATH.as_posix().startswith("results/experiment-002c/")
    assert len(RESULT_OUTPUTS) == len(set(RESULT_OUTPUTS))
    assert not any("operational-episodes" in path.name for path in RESULT_OUTPUTS)
    assert not any("rate-decomposition" in path.name for path in RESULT_OUTPUTS)


def test_repository_publication_privacy_scan_passes_before_outcomes():
    result = repository_hygiene_scan(Path.cwd())
    assert result["passed"], result
