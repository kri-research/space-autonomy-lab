from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as Q
from functools import cache

import pytest

from iaa.types import encode
from sa02.model import Budget
from sa03.development import cases, prepare
from sa03.forecast import outcome_partition, waiting_check
from sa03.model import RequestLedger, Timing
from sa03.policy import build_option, decide, dispatch, verify_tree


@cache
def context(name="alongtrack_ambiguity"):
    return prepare(next(c for c in cases() if c.name == name))


@cache
def option(channel):
    return build_option(context(), channel, Budget(50000))


def test_reading_partition_has_no_holes():
    for channel in ("range", "bearing"):
        domain, leaves, _ = outcome_partition(context(), channel, Budget(50000))
        assert leaves[0]["reading"].lo == domain.lo
        assert leaves[-1]["reading"].hi == domain.hi
        assert all(
            a["reading"].hi == b["reading"].lo for a, b in zip(leaves, leaves[1:], strict=False)
        )
        assert any(leaf["cells"] for leaf in leaves)


def test_actual_generated_tree_verifies_and_forged_branches_fail():
    c = context()
    tree = option("range")
    assert tree["all_outcome_protection"] and verify_tree(c, tree)
    damaged = deepcopy(tree)
    damaged["leaves"] = damaged["leaves"][:-1]
    assert not verify_tree(c, damaged)
    damaged = deepcopy(tree)
    damaged["all_reading_useful"] = not damaged["all_reading_useful"]
    assert not verify_tree(c, damaged)
    damaged = deepcopy(tree)
    damaged["protected_until_ms"] += 1
    assert not verify_tree(c, damaged)


def test_unsafe_wait_cannot_be_repaired_by_favourable_future_reading():
    c = context("unsafe_wait")
    assert not waiting_check(c, Budget(50000))
    tree = build_option(c, "range", Budget(50000))
    assert not tree["all_outcome_protection"] and tree["status"] == "unresolved"


def test_invalid_assumptions_and_late_result_remain_separate():
    c = replace(context(), assumptions_supported=False)
    assert decide(c, "decision_aware")["status"] == "invalid_assumptions"
    c = context("declared_late_range")
    tree = build_option(c, "range", Budget(50000))
    assert tree["status"] == "late" and not tree["all_outcome_protection"]


def test_resource_limits_never_certify_partial_trees():
    for name in ("model_work_budget_exhaustion", "partition_budget_exhaustion"):
        plan = decide(context(name), "decision_aware")
        assert plan["status"] == "resource_exhausted" and plan["certificate"] is None


def test_request_deduplication_busy_window_and_budget():
    ledger = RequestLedger(1)
    assert ledger.reserve("r", 100, 700, Q(1, 5)) == "reserved"
    assert ledger.reserve("r", 100, 700, Q(1, 5)) == "duplicate"
    assert ledger.reserve("s", 200, 800, Q(1, 5)) == "request_in_flight"
    assert ledger.reserve("t", 700, 1200, 1) == "resource_exhausted"
    assert ledger.available == Q(4, 5)


def test_no_late_dispatch_or_false_negative_input():
    c = context()
    plan = decide(c, "decision_aware")
    assert dispatch(c, plan, (), 701)["status"] == "late"
    with pytest.raises(ValueError, match="attainable"):
        c.estimate.negative_certificate_input()
    assert all(not x.get("negative_certificate") for x in plan["candidates"])


def test_already_adequate_action_avoids_requested_information():
    plan = decide(context("already_goal_eligible"), "decision_aware")
    assert plan["certificate"]["channel"] is None
    assert plan["certificate"]["all_reading_useful"]


def test_missing_reading_uses_prechecked_same_horizon_branch():
    c = context()
    tree = option("range")
    plan = dict(certificate=tree, status="checked_tree", context_sha256=c.identity())
    out = dispatch(c, plan, (), 700)
    assert out["credited"] and out["action"] == tree["no_observation"]["action"]
    assert out["protected_until_ms"] == 4200


def test_repeatable_policy_no_future_observation_argument():
    import inspect

    assert tuple(inspect.signature(decide).parameters) == ("context", "method")
    a = decide(context("already_goal_eligible"), "decision_aware")
    assert encode(a) == encode(decide(context("already_goal_eligible"), "decision_aware"))


def test_invalid_timing_never_silently_shifts_action():
    with pytest.raises(ValueError):
        Timing(apply_ms=800)
