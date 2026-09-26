import ast
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as Q
from itertools import product
from pathlib import Path

import pytest

from iaa.plant import SensorFaults, flow, observe
from iaa.types import ObservationPacket, StateBox, encode
from sa02.model import Budget
from sa03.development import Case, prepare, run
from sa03.forecast import ACTIONS, action_check, outcome_partition
from sa03.policy import build_option, decide, dispatch, verify_tree


def test_changed_evaluation_truth_cannot_change_preobservation_plan():
    a = prepare(Case("a", actual_initial=(0, Q(-203, 5), 0, 0)))
    b = prepare(Case("b", actual_initial=(0, Q(-197, 5), 0, 0)))
    assert a.identity() == b.identity()
    assert encode(decide(a, "decision_aware")) == encode(decide(b, "decision_aware"))


@pytest.mark.parametrize("channel", ["range", "bearing"])
def test_each_physical_boundary_reading_is_covered_by_its_conditioned_outer_branch(channel):
    context = prepare(Case("boundary"))
    domain, leaves, _ = outcome_partition(context, channel, Budget(50000))
    for x, y in product((Q(-1, 100), Q(0), Q(1, 100)), (Q(-204, 5), Q(-40), Q(-196, 5))):
        initial = (x, y, 0, 0)
        acquired = flow(initial, (0, 0), Q(1, 4))
        pair, _ = observe(acquired, 250, 1, SensorFaults())
        p = next(p for p in pair if p.channel == channel)
        error = (
            context.sensors.range_error_m
            if channel == "range"
            else context.sensors.bearing_error_rad
        )
        for delta in (-error, 0, error):
            reading = Q(str(p.value)) + delta
            found = [leaf for leaf in leaves if leaf["reading"].contains(reading)]
            assert domain.contains(reading) and found
            truth = flow(initial, (0, 0), Q(7, 10))
            assert any(
                leaf["cells"] and any(c.contains_state(truth) for c in leaf["cells"])
                for leaf in found
            )


@pytest.mark.parametrize("action", ACTIONS)
def test_task_progress_bound_dominates_separate_numeric_flow(action):
    box = StateBox.around((Q(1, 2), -45, 0, 0), (Q(1, 100), Q(1, 100), Q(1, 10000), Q(1, 10000)))
    checked = action_check(box, action, Budget(1000))
    assert checked["safe"]
    for initial in product(*zip(box.lower, box.upper, strict=True)):
        for eta in (Q(4, 5), Q(1)):
            after = flow(initial, action, Q(1, 2), eta)
            delta = sum(
                (after[j] - target) ** 2 - (float(initial[j]) - target) ** 2
                for j, target in enumerate((0, -40))
            )
            assert delta <= float(checked["task_change_upper_m2"]) + 1e-10


def test_partition_with_one_unsuccessful_branch_never_claims_universal_benefit():
    c = prepare(Case("broad", broad_faults=True))
    tree = build_option(c, "range", Budget(50000))
    assert tree["all_outcome_protection"]
    assert not tree["all_reading_useful"]
    assert any(leaf["result"] and not leaf["result"]["useful"] for leaf in tree["leaves"])
    good_only = deepcopy(tree)
    good_only["leaves"] = tuple(
        leaf for leaf in good_only["leaves"] if leaf["result"] and leaf["result"]["useful"]
    )
    good_only["all_reading_useful"] = True
    assert not verify_tree(c, good_only)


def test_delayed_receipt_uses_checked_fallback_and_duplicate_conflict_cannot_select_branch():
    c = prepare(Case("c"))
    tree = build_option(c, "range", Budget(50000))
    p = ObservationPacket("sa03-" + c.identity()[:16] + "-range", 1, "range", 40.6, 250, 690)
    policy = dict(certificate=tree, status="checked_tree", context_sha256=c.identity())
    result = dispatch(c, policy, (p,), 700)
    assert result["status"] == "late_or_invalid_receipt_fallback" and result["credited"]
    p = replace(p, available_ms=290)
    result = dispatch(c, policy, (p, replace(p, value=39.4)), 700)
    assert result["status"] == "conflicting_receipt_fallback" and result["credited"]


def test_forged_optimistic_tree_cannot_be_dispatched():
    c = prepare(Case("c"))
    plan = decide(c, "fixed_range")
    plan["certificate"]["all_reading_useful"] = not plan["certificate"]["all_reading_useful"]
    assert not dispatch(c, plan, (), 700)["credited"]


def test_unmodeled_bias_is_reported_without_fictitious_detection():
    case = Case("outside", range_bias_m=0.5)
    result, _, _ = run(case, "fixed_range")
    assert not result["configured_observation_assumptions_satisfied"]
    assert result["real_time_feasible"] is False


def test_production_policy_cannot_import_plant_or_development_truth():
    root = Path(__file__).resolve().parents[1] / "sa03"
    for file in ("policy.py", "model.py", "forecast.py"):
        tree = ast.parse((root / file).read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(
            any(s in m for s in ("plant", "development", "fixtures", "oracle")) for m in imports
        )
        assert "actual_initial" not in (root / file).read_text()


@pytest.mark.parametrize(
    "method", ["fixed_range", "fixed_bearing", "uncertainty_triggered", "decision_aware"]
)
def test_comparators_validate_on_same_adequate_control_fixture(method):
    case = Case(
        "own-check",
        prior_radii=(Q(1, 100), Q(1, 100), Q(1, 10000), Q(1, 10000)),
        actual_initial=(0, -40, 0, 0),
    )
    result, _, _ = run(case, method)
    assert result["continuous_realized_containment"]
    assert result["realized_dispatch"]["credited"]
    assert result["mission_dwell_proved"]


def test_unknown_retained_hypothesis_and_model_identity_are_rejected():
    c = prepare(Case("c"))
    cell = replace(c.estimate.cells[0], hypothesis="invented")
    with pytest.raises(ValueError, match="hypothesis"):
        replace(c, estimate=replace(c.estimate, cells=(cell,)))
    with pytest.raises(ValueError, match="identity"):
        replace(c, sensors=replace(c.sensors, range_error_m=Q(1, 5)))


def test_bad_numerics_are_unresolved_without_partial_tree(monkeypatch):
    import sa03.policy as policy

    def fail(*args, **kw):
        raise ArithmeticError("injected arithmetic failure")

    monkeypatch.setattr(policy, "outcome_partition", fail)
    result = policy.decide(prepare(Case("c")), "fixed_range")
    assert result["status"] == "unresolved_numerics_or_input"
    assert result["certificate"] is None


def test_request_cannot_be_issued_before_planner_finishes():
    from sa03.model import Timing

    with pytest.raises(ValueError):
        Timing(acquire_ms=200)
    t = Timing()
    assert t.acquire_ms == t.now_ms + t.planner_model_ms + t.request_lead_ms


def test_low_budget_stops_before_computing_a_plan():
    c = prepare(Case("empty-budget", budget_mj=2))
    result = decide(c, "decision_aware")
    assert result["operations"] == 0 and result["modeled_cost_mj"] == 0
    assert result["certificate"] is None
