from pathlib import Path

from kri_space_autonomy.experiment_002_confirmatory.workflow import (
    EPISODES_PATH,
    EXPECTED_BASE,
    EXPECTED_BRANCH,
    SEEDS_DIR,
    SOURCE_GLOBS,
    repository_hygiene_scan,
    verify_historical_records,
    verify_unmaterialized_reservation,
)


def test_historical_experiments_verify_unchanged_through_002d():
    result = verify_historical_records(Path.cwd())
    assert result["passed"], result
    assert result["experiment_002c_numerical_decision"] == "pass"
    assert result["experiment_002d_decision"] == (
        "resolved_freeze_confirmatory_design"
    )
    assert result["recommended_confirmatory_seeds_per_stratum"] == 1000
    assert result["recommended_confirmatory_episodes"] == 32000


def test_requested_branch_base_and_imported_source_freeze_are_exact():
    assert EXPECTED_BRANCH == "experiment-002-confirmatory"
    assert EXPECTED_BASE == "2a16735050ec636e58f02658641d79f39b151924"
    frozen_sources = set(SOURCE_GLOBS)
    for name in (
        "analysis",
        "config",
        "dynamics",
        "evaluator",
        "monitor",
        "policy",
        "runner",
        "seeds",
    ):
        assert f"src/kri_space_autonomy/experiment_002/{name}.py" in frozen_sources


def test_freeze_phase_requires_partition_16_to_remain_unmaterialized():
    result = verify_unmaterialized_reservation(Path.cwd())
    assert result["passed"], result
    assert result["partition_code"] == 16
    assert result["status"] == "reserved_not_materialized_or_executed"
    assert not (Path.cwd() / SEEDS_DIR).exists()
    assert not (Path.cwd() / EPISODES_PATH.parent).exists()


def test_repository_publication_privacy_scan_passes_for_final_design():
    result = repository_hygiene_scan(Path.cwd())
    assert result["passed"], result
