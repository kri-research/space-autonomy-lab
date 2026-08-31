import inspect
from pathlib import Path

import pytest

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004_confirmatory.config import load_confirmatory_config
from kri_space_autonomy.experiment_004_confirmatory.seeds import (
    assert_materialization_targets_absent,
    load_confirmatory_cases,
    materialize_confirmatory_seeds,
)
from kri_space_autonomy.experiment_004_pilot.config import load_pilot_config


def inputs():
    study = load_confirmatory_config("experiments/004-confirmatory/config.json")
    return (
        study,
        load_pilot_config("experiments/004-pilot/config.json"),
        load_config("experiments/004/config.json"),
        load_confirmatory_cases(study=study),
    )


def test_generator_is_exact_freeze_gated_but_not_invoked_by_design_tests():
    source = inspect.getsource(materialize_confirmatory_seeds)
    assert "verify_freeze(project_root, require_unmaterialized=True)" in source
    assert "freeze_id != verification" in source
    assert "readiness_id != verification" in source
    assert "seed_contract_sha256 != verification" in source
    assert "partition-44 root count drift" in source
    assert not Path("experiments/004-confirmatory/seeds").exists()
    assert not Path("results/experiment-004-confirmatory").exists()


def test_generator_refuses_without_a_verified_freeze_and_writes_nothing(tmp_path):
    study, pilot, foundation, cases = inputs()
    with pytest.raises(RuntimeError, match="before verified freeze"):
        materialize_confirmatory_seeds(
            study,
            pilot,
            foundation,
            cases,
            root=tmp_path,
            freeze_id="not-a-freeze",
            readiness_id="not-readiness",
            seed_contract_sha256="not-contract",
        )
    assert not (tmp_path / "experiments/004-confirmatory/seeds").exists()
    assert not (tmp_path / "results/experiment-004-confirmatory").exists()


def test_write_once_targets_refuse_seed_or_result_preexistence(tmp_path):
    seed_path = tmp_path / "experiments/004-confirmatory/seeds"
    seed_path.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="pre-existing"):
        assert_materialization_targets_absent(tmp_path)
    seed_path.rmdir()
    result_path = tmp_path / "results/experiment-004-confirmatory"
    result_path.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="pre-existing"):
        assert_materialization_targets_absent(tmp_path)
