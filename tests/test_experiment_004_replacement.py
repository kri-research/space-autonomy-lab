from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004_pilot.config import load_pilot_config
from kri_space_autonomy.experiment_004_pilot.runner import _scenario_from_row
from kri_space_autonomy.experiment_004_replacement.config import load_confirmatory_config
from kri_space_autonomy.experiment_004_replacement.runner import (
    checkpoint_fixture_run,
    default_workers,
    run_confirmatory_block,
)
from kri_space_autonomy.experiment_004_replacement.seeds import (
    load_confirmatory_cases,
    materialize_confirmatory_scenario,
    validate_seed_contract,
)
from kri_space_autonomy.experiment_004_replacement.workflow import (
    partition_45_unmaterialized,
    science_unchanged,
    validate,
    verify_invalid_attempt,
)


def test_replacement_preserves_science_and_reserves_fresh_partition() -> None:
    root = Path.cwd()
    study = load_confirmatory_config()
    assert study.confirmatory_partition_code == 45
    assert study.planned_blocks == 1452
    assert study.planned_episodes == 2904
    assert study.replay_blocks == 64
    assert study.replay_episodes == 128
    assert science_unchanged(root)["passed"]
    assert partition_45_unmaterialized(root)["passed"]
    assert validate_seed_contract(
        study, "experiments/004-replacement-confirmatory/seed-contract.json", root=root
    )["passed"]


def test_invalid_partition_44_attempt_is_audited_without_inference() -> None:
    audit = verify_invalid_attempt(Path.cwd())
    assert audit["passed"]
    observed = audit["observed"]
    assert observed["durable_episode_rows"] == 602
    assert observed["complete_paired_blocks"] == 301
    assert observed["H1_status"] == observed["H2_status"] == "not_tested"
    assert not observed["partial_outcomes_used_for_replacement_design"]
    assert not observed["partition_reusable"]


def test_partition_45_seed_derivation_is_fresh_and_deterministic() -> None:
    study = load_confirmatory_config()
    pilot = load_pilot_config("experiments/004-pilot/config.json")
    foundation = load_config("experiments/004/config.json")
    case = load_confirmatory_cases(study=study)[0]
    first = materialize_confirmatory_scenario(
        study, pilot, foundation, case, 0, freeze_id="test-freeze"
    )
    second = materialize_confirmatory_scenario(
        study, pilot, foundation, case, 0, freeze_id="test-freeze"
    )
    assert first == second
    assert first.partition_code == 45
    assert first.root_seed_id.startswith("experiment004:45:")
    assert "experiment004:44:" not in first.root_seed_id


def test_checkpoint_resume_is_idempotent_and_byte_deterministic(tmp_path: Path) -> None:
    interrupted = checkpoint_fixture_run(
        tmp_path / "resume", workers=1, task_count=6, iterations=1000, stop_after_for_test=2
    )
    assert not interrupted["complete"]
    assert interrupted["blocks"] == 2
    resumed = checkpoint_fixture_run(tmp_path / "resume", workers=2, task_count=6, iterations=1000)
    fresh = checkpoint_fixture_run(tmp_path / "fresh", workers=1, task_count=6, iterations=1000)
    assert resumed["passed"] and fresh["passed"]
    assert resumed["completed_shards_reused"] == 2
    assert resumed["episodes_sha256"] == fresh["episodes_sha256"]
    assert (tmp_path / "resume/episodes.jsonl").read_bytes() == (
        tmp_path / "fresh/episodes.jsonl"
    ).read_bytes()


def test_corrupt_checkpoint_fails_closed(tmp_path: Path) -> None:
    checkpoint_fixture_run(
        tmp_path / "case", workers=1, task_count=4, iterations=100, stop_after_for_test=2
    )
    shard = tmp_path / "case/shards/block-000000.json"
    shard.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checkpoint shard"):
        checkpoint_fixture_run(tmp_path / "case", workers=2, task_count=4, iterations=100)


def test_runner_refuses_retired_partition_44() -> None:
    study = load_confirmatory_config()
    pilot = load_pilot_config("experiments/004-pilot/config.json")
    foundation = load_config("experiments/004/config.json")
    cases = {case.id: case for case in load_confirmatory_cases(study=study)}
    row = json.loads(Path("experiments/004-pilot/seeds/pilot.jsonl").read_text().splitlines()[0])
    scenario = replace(_scenario_from_row(row), partition_code=44)
    with pytest.raises(ValueError, match="partition 44 is permanently retired"):
        run_confirmatory_block(
            study,
            pilot,
            foundation,
            cases[scenario.case_id],
            scenario,
            freeze_id=scenario.design_freeze_id,
        )


def test_worker_policy_and_pre_freeze_validation() -> None:
    assert default_workers(15) == 8
    assert default_workers(4) == 1
    assert default_workers(1) == 1
    result = validate(Path.cwd())
    assert result["passed"], result
