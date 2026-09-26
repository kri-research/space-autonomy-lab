from copy import deepcopy
from functools import cache

import pytest

from sa04.fixtures import FAULTS, METHODS, run
from sa04.trace import audit, seal


@cache
def result(fault, method="uncertainty_triggered"):
    return run(fault, method)


@pytest.mark.parametrize("fault", FAULTS)
@pytest.mark.parametrize("method", METHODS)
def test_all_explicit_faults_and_prior_scope(fault, method):
    summary, trace = result(fault, method)
    assert audit(trace) == []
    assert summary["terminal_uncredited"]
    assert not summary["physical_validation"]
    assert all(700 <= t <= 710 for t in summary["applied_times"])
    if fault in (
        "sensor_loss",
        "late_planner",
        "planner_failure",
        "checker_failure",
        "late_checker",
        "checker_channel_corrupt",
        "missed_application_window",
        "settings_changed",
        "unsafe_initial",
    ):
        if fault not in ("sensor_loss",):
            assert not summary["applied_times"]
    if fault == "unsafe_initial":
        assert (
            not summary["initial_protection"]
            and not summary["continuous_realized_model_containment"]
        )


@pytest.mark.parametrize(
    "mutation", ["stale_estimate", "certificate", "command_time", "unchanged_fallback", "ack"]
)
def test_semantic_tampering_fails_even_after_rehash(mutation):
    _, trace = result("nominal")
    rows = [
        {k: v for k, v in deepcopy(row).items() if k in ("at_ms", "event", "data")}
        for row in trace["events"]
    ]
    if mutation == "stale_estimate":
        next(r for r in rows if r["event"] == "check_input")["data"]["input"]["at_ms"] = 100
    elif mutation == "certificate":
        next(r for r in rows if r["event"] == "check_result")["data"]["binding"]["expires_ms"] = (
            9999
        )
    elif mutation == "command_time":
        r = next(r for r in rows if r["event"] == "command" and r["data"]["newly_applied"])
        r["at_ms"] = 699
    elif mutation == "unchanged_fallback":
        r = next(r for r in rows if r["event"] == "command")
        r["data"]["changed_from_coast"] = True
    else:
        next(r for r in rows if r["event"] == "acknowledgement")["data"]["physical"] = True
    assert audit(seal(rows))


def test_trace_truncation_and_reordering():
    _, trace = result("nominal")
    for mutate in (lambda t: t["events"].pop(), lambda t: t["events"].reverse()):
        changed = deepcopy(trace)
        mutate(changed)
        assert audit(changed)


def test_source_modules_have_no_truth_import():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "sa04"
    for name in ("wire.py", "compute.py", "gate.py", "service.py", "transport.py"):
        tree = ast.parse((root / name).read_text())
        assert not any(
            isinstance(n, ast.ImportFrom)
            and any(x in (n.module or "") for x in ("plant", "fixtures", "development"))
            for n in ast.walk(tree)
        )


def test_reported_saturation_revokes_pending_and_active_credit():
    summary, trace = result("actuator_saturation")
    later = [r["data"] for r in trace["events"] if r["event"] == "command" and r["at_ms"] >= 705]
    assert summary["applied_times"] == [700]
    assert later and all(not r["credited"] for r in later)
