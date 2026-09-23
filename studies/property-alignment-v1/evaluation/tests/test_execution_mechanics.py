"""Serial/parallel and checkpoint-continuation equivalence on calibration fixtures."""

import json
import pytest
from evaluation.tests import clocked_fixture

from evaluation.episode import scientific_signature
from evaluation.generator import STRATA
from evaluation.runner import run_fixed_namespace, run_resumable_namespace


@pytest.fixture(autouse=True)
def deterministic_policy_clock(monkeypatch):
    # Mechanical equivalence excludes environmental deadline variation.
    # Parent scheduling and subprocess watchdog clocks are not patched.
    monkeypatch.setattr("evaluation.runner._episode_worker", clocked_fixture.episode_worker)
    monkeypatch.setattr("evaluation.runner.run_case", clocked_fixture.run_case)


def signatures(directory):
    rows = [json.loads(path.read_text()) for path in sorted((directory / "cases").glob("*.json"))]
    rows.sort(key=lambda row: (STRATA.index(row["stratum"]), row["index"]))
    return [scientific_signature(row) for row in rows]


def test_serial_parallel_equivalence(tmp_path):
    serial = tmp_path / "serial"
    parallel = tmp_path / "parallel"
    run_fixed_namespace("calibration", 1, serial, workers=1, include_native=False)
    run_fixed_namespace("calibration", 1, parallel, workers=2, include_native=False)
    assert signatures(serial) == signatures(parallel)


def test_checkpoint_continuation_matches_fresh_serial(tmp_path):
    fresh = tmp_path / "fresh"
    checkpoint = tmp_path / "checkpoint"
    run_fixed_namespace("calibration", 1, fresh, workers=1, include_native=False)
    first = run_resumable_namespace(
        "calibration",
        1,
        checkpoint,
        max_new=2,
        include_native=False,
    )
    assert first["completed"] == 2 and not first["complete"]
    second = run_resumable_namespace(
        "calibration",
        1,
        checkpoint,
        max_new=None,
        include_native=False,
    )
    assert second["complete"]
    assert second["signatures"] == signatures(fresh)
