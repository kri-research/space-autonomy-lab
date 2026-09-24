"""Read-only host-record integrity checks, outside the measured source freeze."""

import json
from pathlib import Path
import pytest
from execution_validation_v1.artifact import verify
from execution_validation_v1.analysis import validate_sample
from execution_validation_v1.physical import readiness, REQUIRED, NUMERIC

ROOT = Path(__file__).resolve().parents[1] / "execution_validation_v1"


def sample():
    for line in (ROOT / "recorded/raw_records.jsonl").read_text().splitlines():
        row = json.loads(line)
        if "/samples/" in row["path"]:
            return json.loads(row["raw_utf8"])
    raise AssertionError("No samples")


def test_all_measurements_and_reference_checks_preserved():
    result = verify(ROOT / "recorded")
    assert result["passed"] and result["samples"] == 192 and result["warmup"] == 24
    assert result["fixed_output_checks"] == 162 and result["failed_fixed_output_checks"] == 0
    assert result["physical_trials"] == 0 and result["independent_reviews"] == 0


@pytest.mark.parametrize(
    "field,value",
    [("roundtrip_ns", -1), ("validated_ns", True), ("encoded_ns", -1), ("received_ns", 0)],
)
def test_bad_measurement_timestamps(field, value):
    row = sample()
    row["parent_timing"][field] = value
    with pytest.raises(ValueError):
        validate_sample(row)


def test_simulation_not_relabelled_hardware():
    row = sample()
    row["physical_actuation"] = True
    with pytest.raises(ValueError):
        validate_sample(row)


def test_filled_form_does_not_authorize_movement():
    c = {k: "test_artifact" for k in REQUIRED}
    c.update({k: "0.001" for k in NUMERIC})
    c.update(metrology_independent_of_controller=True, model_assumptions_reviewed=True)
    result = readiness(c)
    assert (
        result["structural_readiness"]
        and not result["authorization_verified"]
        and not result["may_energize_equipment"]
    )


def test_every_evidence_level_reported_truthfully():
    levels = json.loads((ROOT / "recorded/evidence_levels.json").read_text())
    assert len(levels) == 6 and levels[0]["status"] == "measured"
    assert all(x["status"] == "not_performed" for x in levels[2:])
