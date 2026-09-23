"""Read-only regression tests for the complete retained developmental artifact."""

from pathlib import Path
from protective.artifact import verify, check_manifest, read
from protective.binding import verify_seal

ROOT = Path(__file__).resolve().parents[1]


def test_active_execution_sources_unchanged():
    seal = verify_seal()
    for name in ["recorded_tuning", "recorded_development"]:
        assert read(ROOT / name / "seal.json") == seal


def test_complete_development_records_and_plans():
    r = verify(ROOT / "recorded_development", "compare")
    assert r["cells"] == 72 and r["decisions"] == 21600 and r["states"] == 86472


def test_complete_valid_tuning_records():
    r = verify(ROOT / "recorded_tuning", "tune")
    assert r["cells"] == 4 and r["decisions"] == 1200


def test_all_invalid_serialization_attempts_retained():
    failed = ROOT / "retained_attempts/serialization-v1/execution"
    check_manifest(failed)
    report = read(failed / "results.json")
    assert report["count"] == 4
    assert all(
        "JSON" in r["execution_error"] and r["physical_status"] == "unresolved"
        for r in report["rows"]
    )


def test_backup_validation_has_true_terminal_continuation():
    data = ROOT / "recorded_validation"
    check_manifest(data)
    r = read(data / "results.json")["backup"]
    assert r["statuses"] == {
        "feasible_predictive_plan": 1,
        "stored_tube_feedback": 159,
        "terminal_feedback": 140,
    }
    assert (
        r["adjudication"]["status"] == "validated_containment"
        and r["adjudication"]["hold_acquired"] == "satisfied"
    )


def test_analysis_does_not_credit_external_guard_as_filter_success():
    data = ROOT / "recorded_analysis"
    check_manifest(data)
    r = read(data / "results.json")
    arms = {a["arm"]: a for a in r["arms"]}
    assert r["counts"]["cells"] == 72
    assert (
        arms["predictive"]["contained"] == 10
        and arms["predictive"]["entirely_filter_protected"] == 10
    )
    assert (
        arms["tracking"]["contained"] == 10 and arms["tracking"]["entirely_filter_protected"] == 0
    )
    assert arms["barrier"]["contained"] == 10 and arms["barrier"]["entirely_filter_protected"] == 4
    assert arms["barrier"]["external_guard_decisions"] == 48
    assert all(a["infeasible_control_violations"] == 2 for a in arms.values())
