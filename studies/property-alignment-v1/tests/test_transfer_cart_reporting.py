"""Post-execution artifact checks; no protected policy or trajectory is rerun."""

from copy import deepcopy
from pathlib import Path
import json
import pytest
from transfer_cart_v1.audit import verify_artifact, verify_row, primary
from transfer_cart_v1.schema import read

PKG = Path(__file__).resolve().parents[1] / "transfer_cart_v1"


def first():
    case = read(PKG / "recorded/inputs.json")[0]
    row = json.loads((PKG / "recorded/cases.jsonl").read_text().splitlines()[0])
    return case, row


def test_final_transfer_artifact_recomputes_without_policy():
    s = verify_artifact(PKG / "recorded")
    assert s["cases"] == 128 and s["implementation_failures"] == 0
    assert s["methods"]["lag_aware_common_command"]["outcomes"] == {
        "verified_prefix": 77,
        "verified_obstruction": 45,
        "unresolved": 6,
    }
    assert s["all_pairs_certified_joint_obstructions"] == 9


@pytest.mark.parametrize(
    "field,value",
    [("case_id", "wrong"), ("index", True), ("stratum", "unknown"), ("namespace", "calibration")],
)
def test_cart_outcome_identity_corruption(field, value):
    case, row = first()
    row[field] = value
    with pytest.raises(ValueError):
        verify_row(case, row)


@pytest.mark.parametrize(
    "field,value",
    [
        ("wall_s", float("nan")),
        ("wall_s", -1),
        ("wall_s", True),
        ("on_time", 1),
        ("status", "safe"),
        ("action", ["99", "0"]),
    ],
)
def test_cart_prediction_corruption(field, value):
    case, row = first()
    row["methods"]["lag_aware_common_command"]["prediction"][field] = value
    with pytest.raises(ValueError):
        verify_row(case, row)


def test_reproduction_is_reference_only():
    r = read(PKG / "reproduction/clean_reproduction.json")
    assert r["passed"] and r["comparisons"] == 738 and r["mismatches"] == []
    assert r["forbidden_modules_loaded"] == []


def test_unverified_reference_is_not_success():
    _, row = first()
    entry = deepcopy(row["methods"]["lag_aware_common_command"])
    entry["reference"]["status"] = "unresolved"
    assert primary(entry) == "unverified_prefix"


def test_no_missing_competing_method():
    case, row = first()
    del row["methods"]["robust_predictive_prefix"]
    with pytest.raises(ValueError):
        verify_row(case, row)
