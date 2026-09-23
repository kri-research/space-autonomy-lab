"""Final runner and freeze binding tests using calibration/synthetic inputs only."""

from copy import deepcopy
import pytest
from evaluation.calibrate_jobs import calibrate
from evaluation.execute import verify_freeze, _missing_episode
from evaluation.freeze import identity_fields
from evaluation.safety import atomic_json, canonical_hash
from evaluation.generator import case_payload


def test_production_coordinator_calibration_and_interruption(tmp_path, monkeypatch):
    from evaluation.tests.clocked_fixture import perform

    # Deterministic child policy clocks; real parent watchdogs and start markers.
    monkeypatch.setattr("evaluation.jobs._perform", perform)
    result = calibrate(tmp_path / "calibration")
    assert result["passed"] and result["cases"] == 8
    assert result["protected_case_evaluations"] == 0
    assert result["completed_receipts_preserved"]
    assert result["interrupted_started_case_not_rerun"]


def test_freeze_recomputes_identifier_before_any_execution(tmp_path, monkeypatch):
    import evaluation.freeze as freeze

    monkeypatch.setattr(freeze, "source_inventory", lambda: {})
    doc = {
        "component_sha256": {},
        "source_sha256": {},
        "protected_campaign_executed": False,
        "design": {"target_total": 768},
    }
    doc["evaluation_id"] = canonical_hash(identity_fields(doc))
    atomic_json(tmp_path / "freeze.json", doc)
    assert (
        verify_freeze(tmp_path / "freeze.json", doc["evaluation_id"])["design"]["target_total"]
        == 768
    )
    altered = deepcopy(doc)
    altered["design"]["target_total"] = 4
    atomic_json(tmp_path / "changed.json", altered)
    with pytest.raises(ValueError):
        verify_freeze(tmp_path / "changed.json", doc["evaluation_id"])


def test_whole_execution_timeout_is_a_retained_outcome():
    p = case_payload("calibration", "interior_pair", 0)
    for reason, expected in [
        ("worker_wall_timeout", "execution_timeout"),
        ("worker_failed_exit_1", "execution_failure_unclassified"),
        ("interrupted_started_case_no_retry", "infrastructure_missing"),
    ]:
        r = _missing_episode(p, reason)
        assert r["candidate"]["status"] == expected
        assert r["primary"]["eligible"] and not r["primary"]["on_time_decisive_valid"]


def test_evaluation_identity_cannot_silently_start_again_elsewhere(tmp_path):
    from evaluation.safety import bind_run

    identity = "1" * 64
    first = bind_run(tmp_path / "registry", identity, tmp_path / "first", "2" * 64)
    assert bind_run(tmp_path / "registry", identity, tmp_path / "first", "2" * 64) == first
    with pytest.raises(ValueError):
        bind_run(tmp_path / "registry", identity, tmp_path / "second", "2" * 64)
    with pytest.raises(ValueError):
        bind_run(tmp_path / "registry", identity, tmp_path / "first", "3" * 64)
