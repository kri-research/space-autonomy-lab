import ast
import json
from fractions import Fraction as Q

import pytest

from post_audit_v1.assemble import STUDY
from sa05.posthoc_attainability_v1 import audit


def test_exact_constants_and_pulse():
    assert audit.LATEST_ENTRY == Q(11, 5)
    assert audit.DRIFT == Q(1497, 3125000)
    assert audit.deviation(Q(11, 5)) == Q(1067131, 78125000)
    independent_integral = audit.AUTHORITY * (
        audit.LATEST_ENTRY * (audit.END - audit.START) - (audit.END**2 - audit.START**2) / 2
    )
    assert independent_integral == Q(1, 80)
    assert audit.INITIAL_SPEED + (audit.AUTHORITY + audit.DRIFT) * audit.HORIZON < Q(1, 5)


def test_all_fixed_input_opportunities_and_original_eligibility():
    result = audit.analyze(STUDY / "sa05/held-inputs.json")
    assert result["checked_in_model_units"] == 96
    assert result["initially_ineligible"] == 81
    assert result["excluded_initially_ineligible"] == 80
    assert result["summary"]["nominal"]["initially_ineligible_not_excluded"] == [
        "held_out-nominal-019"
    ]
    assert result["summary"]["bounded_faults"]["initially_ineligible_not_excluded"] == []
    assert result["minimum_exclusion_gap_m"] == "3382729/2500000000"
    original = json.loads((STUDY / "sa05/recorded/results.json").read_text())
    by_unit = {r["unit"]: r for r in result["checks"]}
    for row in original:
        if row["unit"] in by_unit:
            assert (
                row["initially_goal_eligible"] == by_unit[row["unit"]]["initially_eligible_exact"]
            )
    assert result["post_hoc"] is True and result["new_experiment"] is False


def test_touching_coordinate_is_not_a_strict_exclusion():
    p = Q(7, 20) + audit.deviation(audit.LATEST_ENTRY)
    low, _ = audit.coordinate_range(p, 0)
    assert low == Q(7, 20)
    result = audit.classify((p, -40, 0, 0))
    assert not result["entry_excluded"]
    assert not result["initially_eligible_exact"]
    assert not result["non_exclusion_establishes_feasibility"]


def test_positive_and_negative_controls():
    assert not audit.classify((0, -40, 0, 0))["entry_excluded"]
    assert audit.classify((0, -45, 0, 0))["entry_excluded"]
    with pytest.raises(ValueError):
        audit.classify((0, -40, 1, 0))
    with pytest.raises(ValueError):
        audit.classify((9, -40, 0, 0))
    with pytest.raises(ValueError):
        audit.deviation(-1)


def test_whole_time_envelope_contains_piecewise_exact_extremes():
    for j in range(441):
        t = Q(j, 200)
        for p, v in ((Q(3, 10), Q(-1, 25)), (Q(-4), Q(1, 25))):
            low, high = audit.coordinate_range(p, v)
            assert low <= p + v * t - audit.deviation(t)
            assert p + v * t + audit.deviation(t) <= high


def test_unrecognized_inputs_fail(tmp_path):
    target = tmp_path / "inputs.json"
    target.write_bytes((STUDY / "sa05/held-inputs.json").read_bytes() + b" ")
    with pytest.raises(ValueError):
        audit.analyze(target)


def test_no_numerical_or_policy_imports():
    tree = ast.parse((STUDY / "sa05/posthoc_attainability_v1/audit.py").read_text())
    modules = [n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    modules += [
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    ]
    assert set(modules) <= {"argparse", "hashlib", "json", "collections", "fractions", "pathlib"}
