from pathlib import Path

from kri_space_autonomy.experiment_002b.workflow import (
    HISTORICAL_EVIDENCE_PATHS,
    publication_boundary_scan,
)


def test_historical_experiment_002_evidence_is_tracked_and_unchanged():
    for path in HISTORICAL_EVIDENCE_PATHS:
        assert Path(path).is_file()
    assert not any(str(path).startswith("experiments/002b") for path in HISTORICAL_EVIDENCE_PATHS)


def test_publication_boundary_scan_passes_before_generated_outputs():
    result = publication_boundary_scan(Path.cwd())
    assert result["passed"], result
