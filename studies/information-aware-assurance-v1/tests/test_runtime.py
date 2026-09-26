import ast
from functools import cache
from pathlib import Path

import pytest

from iaa.fixtures import Fixture, fixtures
from iaa.runtime import run
from iaa.types import encode


@cache
def result(name):
    return run(next(f for f in fixtures() if f.name == name))


@pytest.mark.parametrize("name", [f.name for f in fixtures()])
def test_complete_fixture_accounting_and_information_boundary(name):
    summary, records = result(name)
    assert summary["physical_execution"] is False
    assert summary["full_recovery_proved"] is False
    assert summary["hardware_energy_measured"] is False
    assert (
        summary["protection_gap_ms"] + summary["conditional_guard_coverage_ms"]
        == summary["horizon_ms"]
    )
    assert [r.at_ms for r in records] == sorted(r.at_ms for r in records)
    arrivals = {}
    for r in records:
        if r.event == "observation_available":
            packet = r.details["packet"]
            assert packet["available_ms"] == r.at_ms
            arrivals[packet["packet_id"]] = r.at_ms
        if r.event == "decision_snapshot":
            assert r.details["measurement_set_update"] == "unsupported_in_SA01"
            for pid in r.details["proposal"]["packet_ids"]:
                assert arrivals[pid] <= r.at_ms
    assert records[-1].event == "evaluation" and records[-1].at_ms == summary["horizon_ms"]
    assert "NaN" not in encode(records) and "Infinity" not in encode(records)


def test_unsupported_and_expired_are_not_safety_certificates():
    summary, _ = result("unsupported_checker")
    assert summary["scheduled_decisions"] == 0
    assert summary["unsupported_decisions"] == summary["decision_count"]
    assert summary["protection_gap_ms"] == summary["horizon_ms"]
    summary, events = result("late_and_missing_decisions")
    assert summary["late_rejections"] == 2 and summary["lost_responses"] == 11
    assert summary["protection_gap_ms"] > 0
    assert any(
        r.event == "applied_command"
        and r.details["mode"] == "uncredited_output_after_protection_expiry"
        for r in events
    )


def test_boundary_entry_and_model_mismatch_remain_adverse():
    summary, _ = result("coast_entry_failure")
    assert summary["first_numerical_exit_ms"] is not None
    assert summary["scheduled_decisions"] == 0
    assert summary["model_mission_completed"] is False
    summary, _ = result("outside_model_actuator")
    assert summary["assumptions_valid"] is False
    assert summary["protection_gap_ms"] >= 24000


def test_work_budget_counts_failed_requests_and_expiry():
    summary, _ = result("work_budget_exhaustion")
    from fractions import Fraction

    assert Fraction(summary["work_spent_model_mj"]) <= 40
    assert summary["protection_gap_ms"] > 0


def test_no_privileged_imports_in_controller():
    source = (Path(__file__).resolve().parents[1] / "iaa/controller.py").read_text()
    tree = ast.parse(source)
    modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any("plant" in m or "runtime" in m or "fixtures" in m for m in modules)
    assert "truth" not in [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]


def test_deterministic_small_loop():
    fixture = Fixture("short-replay", horizon_ms=2000, additional_request_ms=())
    assert encode(run(fixture)) == encode(run(fixture))


def test_zero_latency_acquisition_is_delivered_in_same_tick():
    from iaa.plant import SensorFaults

    fixture = Fixture(
        "zero-delay",
        horizon_ms=1000,
        additional_request_ms=(),
        faults=SensorFaults(range_delay_ms=0, bearing_delay_ms=0),
    )
    _, events = run(fixture)
    arrivals = [r for r in events if r.event == "observation_available"]
    assert len([r for r in arrivals if r.at_ms == 0]) == 2
    decision = next(r for r in events if r.event == "decision_snapshot")
    assert decision.details["proposal"]["choice"] == "execute"
