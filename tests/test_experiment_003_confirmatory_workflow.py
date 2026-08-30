import json
from pathlib import Path

from kri_space_autonomy.experiment_003_confirmatory.workflow import (
    EXPECTED_BASE,
    EXPECTED_BRANCH,
    SOURCE_GLOBS,
    _foundation_manifest,
    dependency_runtime_identity,
    verify_unmaterialized_reservation,
)


def test_requested_branch_base_and_additive_source_scope_are_exact():
    assert EXPECTED_BRANCH == "experiment-003-confirmatory-design"
    assert EXPECTED_BASE == "bcc1085d15a997a1b82a639830ab689ffb8baff0"
    assert "src/kri_space_autonomy/experiment_003_confirmatory/*.py" in SOURCE_GLOBS
    assert "tests/test_experiment_003_confirmatory_*.py" in SOURCE_GLOBS


def test_frozen_foundation_identity_and_prospective_n_resolution_are_recorded():
    foundation = _foundation_manifest(Path.cwd())
    analysis = json.loads(
        Path("results/experiment-003/analysis.json").read_text(encoding="utf-8")
    )
    resolution = analysis["future_sample_size_resolution"]
    assert foundation["freeze_id"] == (
        "d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297"
    )
    assert resolution["selected_roots_per_stratum"] == 750
    assert resolution["observed_pilot_effect_used_as_alternative"] is False
    assert analysis["primary_effect_direction_used_for_progression"] is False
    assert analysis["primary_hypotheses_tested"] is False


def test_runtime_dependencies_match_frozen_foundation_and_partition_32_is_absent():
    runtime = dependency_runtime_identity(Path.cwd())
    reservation = verify_unmaterialized_reservation(Path.cwd())
    assert runtime["passed"], runtime
    assert runtime["mismatches"] == []
    assert runtime["platform_match_required"] is False
    assert reservation["passed"], reservation
    assert reservation["partition_code"] == 32
    assert reservation["expected_roots"] == 5250
    assert not Path("experiments/003-confirmatory/seeds").exists()
    assert not Path("results/experiment-003-confirmatory").exists()
