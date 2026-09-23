"""Cheap diagnostic guards; no protected policies or qualification are executed."""

import json
from pathlib import Path
import pytest
from runtime_diagnosis_v1.worker import validate_case, atomic_new, read_protocol, run, STUDY


@pytest.mark.parametrize("index", [136, 137, 179, 180, 181, 182])
def test_only_declared_retired_input_hashes(index):
    payload = validate_case(index)
    assert payload["index"] == index
    assert payload["stratum"] == "timing_bounded_pair"


@pytest.mark.parametrize("index", [-1, 0, 32, 138, 183, 319, 320, 999])
def test_unselected_inputs_refused(index):
    with pytest.raises(ValueError):
        validate_case(index)


def test_receipt_cannot_overwrite(tmp_path):
    path = tmp_path / "receipt.json"
    atomic_new(path, {"original": True})
    with pytest.raises(FileExistsError):
        atomic_new(path, {"original": False})
    assert json.loads(path.read_text()) == {"original": True}


@pytest.mark.parametrize(
    "path",
    [
        STUDY / "evaluation/new",
        STUDY.parents[3] / "evidence/new",
        STUDY.parents[3] / ".research/tasks/08/protected-v1/new-diagnostic",
    ],
)
def test_protected_paths_refused(path):
    assert not path.exists()
    with pytest.raises(ValueError):
        run(137, "plain", path)
    assert not path.exists()


def test_original_scientific_run_not_in_plan():
    p = read_protocol()
    assert p["candidate_full_set_evaluation"] is False
    assert p["original_evaluation_valid"] is False
    assert all(set(s["indices"]) <= set(x["index"] for x in p["inputs"]) for s in p["plan"])
    assert max(s.get("workers", 1) for s in p["plan"]) == 4
    assert p["whole_diagnostic_wall_limit_s"] == 900


def test_no_production_driver_invocation():
    source = (Path(__file__).resolve().parents[1] / "run.py").read_text()
    assert '-m","evaluation.execute' not in source
    assert "runtime_diagnosis_v1.worker" in source
