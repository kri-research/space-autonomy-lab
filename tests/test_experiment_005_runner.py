from pathlib import Path

import pytest

from kri_space_autonomy.experiment_005.runner import (
    default_workers,
    run_checkpointed_fixture,
)


def test_fresh_serial_and_parallel_fixture_outputs_are_byte_equivalent(tmp_path: Path):
    serial = run_checkpointed_fixture(
        tmp_path / "serial", workers=1, task_count=8, iterations=500
    )
    parallel = run_checkpointed_fixture(
        tmp_path / "parallel", workers=2, task_count=8, iterations=500
    )
    assert serial["passed"] and parallel["passed"]
    assert serial["output_sha256"] == parallel["output_sha256"]
    assert (tmp_path / "serial/fixture-rows.jsonl").read_bytes() == (
        tmp_path / "parallel/fixture-rows.jsonl"
    ).read_bytes()


def test_restart_executes_missing_frozen_cells_only(tmp_path: Path):
    interrupted = run_checkpointed_fixture(
        tmp_path / "resume",
        workers=1,
        task_count=8,
        iterations=500,
        stop_after_for_test=3,
    )
    assert not interrupted["complete"]
    assert interrupted["cells"] == 3
    resumed = run_checkpointed_fixture(
        tmp_path / "resume", workers=2, task_count=8, iterations=500
    )
    fresh = run_checkpointed_fixture(
        tmp_path / "fresh", workers=1, task_count=8, iterations=500
    )
    assert resumed["completed_shards_reused"] == 3
    assert resumed["new_shards_written"] == 5
    assert resumed["output_sha256"] == fresh["output_sha256"]


def test_corrupt_shard_and_conflicting_output_fail_closed(tmp_path: Path):
    run_checkpointed_fixture(
        tmp_path / "corrupt",
        workers=1,
        task_count=4,
        iterations=100,
        stop_after_for_test=2,
    )
    shard = tmp_path / "corrupt/shards/cell-000000.json"
    shard.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checkpoint shard"):
        run_checkpointed_fixture(
            tmp_path / "corrupt", workers=2, task_count=4, iterations=100
        )

    run_checkpointed_fixture(
        tmp_path / "conflict", workers=1, task_count=4, iterations=100
    )
    output = tmp_path / "conflict/fixture-rows.jsonl"
    output.write_text("conflict\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="conflicts"):
        run_checkpointed_fixture(
            tmp_path / "conflict", workers=2, task_count=4, iterations=100
        )


def test_lock_and_worker_policy_are_fail_closed(tmp_path: Path):
    assert default_workers(15) == 8
    assert default_workers(4) == 1
    checkpoint = tmp_path / "locked/shards"
    checkpoint.mkdir(parents=True)
    (checkpoint / ".campaign.lock").write_text("stale\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="locked"):
        run_checkpointed_fixture(
            tmp_path / "locked", workers=2, task_count=4, iterations=100
        )
