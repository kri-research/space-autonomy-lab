import ast
from copy import deepcopy
from fractions import Fraction as Q
from pathlib import Path

import pytest

from iaa.types import StateBox, identity, primitive
from sa02.model import HistorySegment
from sa03.model import Timing
from sa05.design import DEVELOPMENT_SEED, METHODS, STRATA, make_case, population
from sa05.experiment import packet, plan, run, sensors


def fixture():
    c = make_case(DEVELOPMENT_SEED, "development", "nominal", 999)
    c.update(
        prior_center=["0", "-40", "0", "0"],
        prior_radii=["1/100", "1/100", "1/10000", "1/10000"],
        initial_state=["0", "-40", "0", "0"],
        warm_channel=None,
    )
    return c


@pytest.mark.parametrize("method", METHODS)
def test_each_baseline_on_its_own_success_fixture(method):
    row, evidence, timing = run(fixture(), method)
    assert row["mission_completion"] and not row["acquired_goal"]
    assert row["constraint_status"] == "numerically_contained"
    assert timing["planner_ns"] > 0 and timing["checker_ns"] > 0
    assert evidence["emitted"]["physical_actuation"] is False


def test_exogenous_streams_and_split_are_stable_and_distinct():
    counts = {s: 2 for s in STRATA}
    a = population(DEVELOPMENT_SEED, "development", counts)
    assert a == population(DEVELOPMENT_SEED, "development", counts)
    b = population(DEVELOPMENT_SEED, "held_out", counts)
    assert not set(c["unit"] for c in a) & set(c["unit"] for c in b)
    assert [c["initial_state"] for c in a] != [c["initial_state"] for c in b]
    for c in a:
        assert set(c["method_order"]) == set(METHODS)
        assert StateBox.around(
            [Q(x) for x in c["prior_center"]], [Q(x) for x in c["prior_radii"]]
        ).contains([Q(x) for x in c["initial_state"]])


def test_plan_has_no_truth_input_and_false_state_changes_only_measurements():
    c = fixture()
    con = sensors("nominal")
    raw = dict(
        initial=primitive(StateBox.around((0, -40, 0, 0), (0.1, 0.1, 0.002, 0.002))),
        sensors=primitive(con),
        packets=[],
        history=primitive((HistorySegment(0, 100, (0, 0)),)),
        at_ms=100,
        queued_action=["0", "0"],
        timing=primitive(Timing()),
    )
    assert plan(raw, "decision_aware") == plan(deepcopy(raw), "decision_aware")
    import inspect

    assert tuple(inspect.signature(plan).parameters) == ("raw", "method")
    assert "initial_state" not in inspect.getsource(plan)
    a = packet(c, (0, -40, 0, 0), "range", 250)
    b = packet(c, (0, -41, 0, 0), "range", 250)
    assert a[0].value != b[0].value
    assert a[0].available_ms == b[0].available_ms


@pytest.mark.parametrize(
    "field,value", [("planner_ready_ms", 151), ("checker_ready_ms", 701), ("application_ms", 715)]
)
def test_late_results_do_not_shift_the_deadline(field, value):
    c = fixture()
    c[field] = value
    row, _, _ = run(c, "decision_aware")
    assert not row["candidate_applied"]
    assert row["protective_continuation_used"]


def test_lost_observation_preserves_checked_finite_continuation():
    c = fixture()
    c["range_lost"] = True
    row, _, _ = run(c, "fixed_range")
    assert row["observation_requests"] == 1 and row["delivered_requests"] == 0
    assert row["constraint_status"] == "numerically_contained"
    assert row["finite_expiry_ms"] == 4200


def test_native_and_external_dynamics_are_not_relabelled_as_independent_checker():
    source = (Path(__file__).resolve().parents[1] / "sa05/dynamics.py").read_text()
    modules = [n.module or "" for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)]
    assert not any(m.startswith(("iaa", "sa02", "sa03", "sa04")) for m in modules)
    assert identity(fixture()) == identity(deepcopy(fixture()))
