from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import fields, replace
from pathlib import Path

import pytest

from kri_space_autonomy.experiment_004.config import load_config as load_e004_config
from kri_space_autonomy.experiment_005.config import load_config as load_e005_config
from kri_space_autonomy.experiment_005_transfer_pilot.config import (
    TransferPilotConfig,
    load_case_matrix,
    load_pilot_config,
)
from kri_space_autonomy.experiment_005_transfer_pilot.seeds import (
    test_fixture_scenario as make_test_fixture_scenario,
)
from kri_space_autonomy.experiment_005_transfer_pilot_replacement.runner import (
    PROCESS_START_METHOD,
    run_spawn_checkpointed_campaign,
)
from kri_space_autonomy.experiment_005_transfer_pilot_replacement.seeds import (
    partition_54_unmaterialized,
    replacement_pilot_config,
    validate_seed_contract,
)
from kri_space_autonomy.experiment_005_transfer_pilot_replacement.workflow import (
    CONTRACT_PATH,
    FREEZE_PATH,
    READINESS_PATH,
    science_unchanged,
    verify_freeze,
    verify_invalid_attempt,
)


def fixture_inputs():
    root = Path.cwd()
    pilot = load_pilot_config(root=root)
    foundation = load_e005_config(root=root)
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
    return run_spawn_checkpointed_campaign(
        directory,
        pilot=pilot,
        foundation=foundation,
        e004=e004,
        cases=cases,
        scenarios=scenarios,
        workers=workers,
        **kwargs,
    )


def test_amendment_preserves_invalid_closeout_and_scientific_design() -> None:
    root = Path.cwd()
    invalid = verify_invalid_attempt(root)
    science = science_unchanged(root)
    assert invalid["passed"], invalid
    assert invalid["completed_blocks"] == 0
    assert invalid["durable_episode_rows"] == 0
    assert invalid["scientific_endpoints_evaluated"] is False
    assert invalid["outcomes_used_for_amendment"] is False
    assert science["passed"], science
    assert science["changed_execution_identity_fields"] == ["pilot_partition_code"]
    assert science["scientific_field_drift"] == []
    assert science["metrics_thresholds_gates_changed"] is False


def test_partition_54_is_fresh_reserved_and_only_execution_identity_changes() -> None:
    root = Path.cwd()
    original = load_pilot_config(root=root)
    replacement = replacement_pilot_config(root)
    changed = [
        field.name
        for field in fields(TransferPilotConfig)
        if getattr(original, field.name) != getattr(replacement, field.name)
    ]
    assert changed == ["pilot_partition_code"]
    assert original.pilot_partition_code == 52
    assert replacement.pilot_partition_code == 54
    assert replacement.future_confirmatory_partition_code == 53
    assert partition_54_unmaterialized(root)["passed"]
    assert validate_seed_contract(replacement, root / CONTRACT_PATH, root=root)["passed"]


def test_spawn_runner_serial_parallel_resume_and_replay_are_byte_identical(
    tmp_path: Path,
) -> None:
    serial = run(tmp_path / "serial", workers=1)
    parallel = run(tmp_path / "parallel", workers=2)
    interrupted = run(tmp_path / "resume", workers=1, stop_after_for_test=1)
    resumed = run(tmp_path / "resume", workers=2)
    replay = run(tmp_path / "replay", workers=2)
    outputs = [
        (tmp_path / relative / "pilot-episodes.jsonl").read_bytes()
        for relative in ("serial", "parallel", "resume", "replay")
    ]
    assert serial["passed"] and parallel["passed"] and resumed["passed"] and replay["passed"]
    assert parallel["process_start_method"] == PROCESS_START_METHOD == "spawn"
    assert len(set(outputs)) == 1
    assert len({serial["output_sha256"], parallel["output_sha256"], replay["output_sha256"]}) == 1
    assert not interrupted["complete"] and interrupted["cells"] == 1
    assert resumed["completed_shards_reused"] == 1
    assert resumed["new_shards_written"] == 1
    rows = [json.loads(line) for line in outputs[0].splitlines()]
    assert [(row["root_seed_id"], row["configuration_id"]) for row in rows] == [
        (scenario.root_seed_id, configuration)
        for scenario in fixture_inputs()[-1]
        for configuration in scenario.configuration_run_order
    ]
    assert all(row["root_seed_id"].startswith("experiment005:951:") for row in rows)


def test_importable_module_cli_exercises_spawn_path(tmp_path: Path) -> None:
    output = tmp_path / "fixture-validation.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "kri_space_autonomy.experiment_005_transfer_pilot_replacement.workflow",
            "fixture-validate",
            "--output",
            str(output),
        ],
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["passed"]
    assert evidence["invocation_mode"] == "importable_module_cli"
    assert evidence["process_start_method"] == "spawn"
    assert evidence["checks"]["serial_parallel_scientific_bytes_identical"]
    assert evidence["checks"]["deterministic_replay_bytes_identical"]
    assert evidence["replacement_partition_materialized"] is False
    assert evidence["replacement_partition_executed"] is False


def test_corrupt_duplicate_and_terminal_failure_evidence_fail_closed(tmp_path: Path) -> None:
    run(tmp_path / "corrupt", workers=1, stop_after_for_test=1)
    shard = tmp_path / "corrupt/shards/cell-000000.json"
    shard.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="checkpoint shard"):
        run(tmp_path / "corrupt", workers=2)

    run(tmp_path / "duplicate", workers=1, stop_after_for_test=1)
    duplicate = tmp_path / "duplicate/shards/cell-000000-copy.json"
    duplicate.write_text("{}\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unexpected or duplicate"):
        run(tmp_path / "duplicate", workers=2)

    _, _, _, _, case, _ = fixture_inputs()
    with pytest.raises(RuntimeError, match="worker failure fixture"):
        run(
            tmp_path / "failure",
            workers=2,
            fail_case_id_for_test=case.id,
        )
    failures = list((tmp_path / "failure/shards/failures").glob("*.json"))
    assert len(failures) == 1
    failure = json.loads(failures[0].read_text(encoding="utf-8"))
    assert failure["attempt_number"] == 1
    assert failure["terminal_state"] == "failed_no_retry_or_replacement"
    with pytest.raises(RuntimeError, match="terminal failed cell"):
        run(tmp_path / "failure", workers=2)


def test_runner_refuses_partition_52_and_partition_53(tmp_path: Path) -> None:
    pilot, foundation, e004, cases, _, scenarios = fixture_inputs()
    for partition in (52, 53):
        forbidden = tuple(
            replace(scenario, partition_code=partition) for scenario in scenarios
        )
        with pytest.raises(ValueError, match=f"partition {partition} is unavailable"):
            run_spawn_checkpointed_campaign(
                tmp_path / f"p{partition}",
                pilot=pilot,
                foundation=foundation,
                e004=e004,
                cases=cases,
                scenarios=forbidden,
                workers=2,
            )



def test_shallow_github_pull_request_lineage_uses_event_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kri_space_autonomy.experiment_005_transfer_pilot_replacement import workflow

    merge_sha = "c" * 40
    base_sha = "a" * 40
    head_sha = "b" * 40
    event_path = tmp_path / "event.json"
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": base_sha},
                    "head": {"sha": head_sha},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_SHA", merge_sha)
    monkeypatch.setattr(
        workflow,
        "_git",
        lambda _root, *args: (
            f"Merge {head_sha} into {base_sha}"
            if args == ("log", "-1", "--format=%s")
            else ""
        ),
    )
    accepted = workflow._github_ci_lineage(tmp_path, merge_sha)
    assert accepted["passed"], accepted
    event_path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": base_sha},
                    "head": {"sha": "d" * 40},
                }
            }
        ),
        encoding="utf-8",
    )
    rejected = workflow._github_ci_lineage(tmp_path, merge_sha)
    assert not rejected["passed"]


def test_frozen_amendment_verifies_when_present() -> None:
    root = Path.cwd()
    if not (root / FREEZE_PATH).exists() or not (root / READINESS_PATH).exists():
        pytest.skip("amendment freeze is written after pre-freeze validation")
    verification = verify_freeze(root, require_unmaterialized=True)
    assert verification["passed"], verification
    assert verification["decision"] == "READY"
    assert verification["source_lineage"]["passed"] is True
    assert verification["partition_54_materialized"] is False
    assert verification["partition_54_executed"] is False
    assert verification["partition_53_untouched"] is True
