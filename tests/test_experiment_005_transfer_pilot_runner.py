import json
from pathlib import Path

import pytest

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_005.config import load_config as load_e005_config
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.runner import (
    run_checkpointed_campaign,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    test_fixture_scenario as make_test_fixture_scenario,
)


def fixture_inputs():
    pilot = load_pilot_config(root=Path.cwd())
    foundation = load_e005_config(root=Path.cwd())
    e004 = load_e004_config()
    cases = load_case_matrix()
    case = next(item for item in cases if item.id == "T02_truth_keep_out_crossing_fixture")
    scenarios = tuple(
        make_test_fixture_scenario(pilot, foundation, e004, case, replicate)[0]
        for replicate in range(2)
    )
    return pilot, foundation, e004, cases, case, scenarios


def run(directory: Path, *, workers: int, **kwargs):
    pilot, foundation, e004, cases, _, scenarios = fixture_inputs()
    return run_checkpointed_campaign(
        directory,
        pilot=pilot,
        foundation=foundation,
        e004=e004,
        cases=cases,
        scenarios=scenarios,
        workers=workers,
        **kwargs,
    )


def test_serial_parallel_and_resume_are_canonical(tmp_path):
    serial = run(tmp_path / "serial", workers=1)
    parallel = run(tmp_path / "parallel", workers=2)
    partial = run(tmp_path / "resume", workers=1, stop_after_for_test=1)
    resumed = run(tmp_path / "resume", workers=2)
    assert serial["passed"] and parallel["passed"] and resumed["passed"]
    assert serial["output_sha256"] == parallel["output_sha256"]
    assert serial["output_sha256"] == resumed["output_sha256"]
    assert not partial["complete"] and partial["cells"] == 1
    assert resumed["completed_shards_reused"] == 1
    assert resumed["new_shards_written"] == 1
    rows = [
        json.loads(line)
        for line in (tmp_path / "serial/pilot-episodes.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 4
    assert all(row["physical_keep_out_entry"] for row in rows)
    assert all(not row["physical_collision"] for row in rows)
    assert all(row["root_seed_id"].startswith("experiment005:951:") for row in rows)


def test_corrupt_shard_fails_without_recomputation(tmp_path):
    run(tmp_path / "corrupt", workers=1, stop_after_for_test=1)
    shard = tmp_path / "corrupt/shards/cell-000000.json"
    shard.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checkpoint shard"):
        run(tmp_path / "corrupt", workers=2)


def test_worker_failure_is_terminal_preserved_and_never_retried(tmp_path):
    _, _, _, _, case, _ = fixture_inputs()
    with pytest.raises(RuntimeError, match="worker failure fixture"):
        run(
            tmp_path / "failure",
            workers=1,
            fail_case_id_for_test=case.id,
        )
    failures = list((tmp_path / "failure/shards/failures").glob("*.json"))
    assert len(failures) == 1
    evidence = json.loads(failures[0].read_text())
    assert evidence["attempt_number"] == 1
    assert evidence["terminal_state"] == "failed_no_retry_or_replacement"
    with pytest.raises(RuntimeError, match="terminal failed cell"):
        run(tmp_path / "failure", workers=1)
