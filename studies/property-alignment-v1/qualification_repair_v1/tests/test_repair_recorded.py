"""Recorded development evidence, with no qualification or policy reruns."""

from pathlib import Path
import json
import math
from qualification_repair_v1.validation import verify

RECORD = Path(__file__).resolve().parents[1] / "recorded"


def test_retained_validation_is_bound_and_rechecks():
    result = verify(RECORD)
    assert result["passed"] and result["unique_inputs"] == 142


def test_unknown_and_physical_failure_not_conflated():
    summary = json.loads((RECORD / "summary.json").read_text())
    assert summary["serial_statuses"] == {
        "qualified": 135,
        "proved_precommand_violation": 5,
        "not_certified_by_library": 2,
    }
    assert summary["qualification_unknowns"] == 0
    assert summary["fixed_rechecks"] == summary["fixed_rechecks_passed"] == 282
    assert summary["serial_parallel_attempts"] == 284
    assert summary["additional_repeated_stress_attempts"] == 114
    assert not summary["new_freeze_created"] and summary["protected_candidate_evaluations"] == 0


def test_every_receipt_uses_genuine_types_and_finite_nonnegative_costs():
    for folder in ("serial", "parallel", "repeat-0", "repeat-1", "repeat-2"):
        for path in (RECORD / folder / "cases").glob("*.json"):
            row = json.loads(path.read_text())
            q = row["qualification"]
            assert type(q["eligible"]) is bool
            assert type(q["physical_impossibility_claim"]) is bool
            assert type(q["wall_s"]) is float and math.isfinite(q["wall_s"]) and q["wall_s"] >= 0
            assert all(type(x) is int and x >= 0 for x in q["counters"].values())
            assert all(
                type(h["hypothesis"]) is int and type(h["qualified"]) is bool
                for h in q["hypotheses"]
            )
