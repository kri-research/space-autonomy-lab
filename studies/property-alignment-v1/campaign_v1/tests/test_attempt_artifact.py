"""Record integrity tests only; protected policies are never rerun."""

from copy import deepcopy
from pathlib import Path
import pytest
from campaign_v1 import attempt as a
from evaluation.generator import case_payload

DATA = Path(__file__).resolve().parents[1] / "recorded_attempt"


def example():
    payload = case_payload("protected", "interior_pair", 32)
    row = a.load(DATA / "qualification/interior_pair__00032.json")
    return deepcopy(row), payload


def test_complete_attempt_accounting_without_policies(monkeypatch):
    import candidate.certify
    import evaluation.qualification

    def forbidden(*args, **kwargs):
        raise AssertionError("Scientific execution is prohibited in artifact verification")

    monkeypatch.setattr(candidate.certify, "decide", forbidden)
    monkeypatch.setattr(candidate.certify, "certify_action", forbidden)
    monkeypatch.setattr(evaluation.qualification, "qualification", forbidden)
    result, ledger = a.audit(DATA)
    assert result["passed"] and not result["campaign_valid"]
    assert result["qualification_counts"] == {
        "completed_eligible": 1011,
        "started_without_receipt": 4,
        "not_started": 137,
    }
    assert len(ledger) == 1152
    assert result["candidate_evaluations"] == 0
    assert result["primary_estimate"] is None and result["confidence_interval"] is None


@pytest.mark.parametrize("raw", ['{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":1,"x":2}'])
def test_invalid_json_is_refused(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        a.load(path)


@pytest.mark.parametrize("name", ["../other", "/absolute", "a/../b"])
def test_unsafe_artifact_members_refused(tmp_path, name):
    with pytest.raises(ValueError):
        a.member(tmp_path, name)


def test_valid_qualification_fields():
    row, payload = example()
    assert a.validate_qualification(row, payload) is True


def test_boolean_not_integer_eligibility():
    row, payload = example()
    row["qualification"]["eligible"] = 1
    with pytest.raises(ValueError):
        a.validate_qualification(row, payload)


def test_wrong_identity_refused():
    row, payload = example()
    row["case_id"] = "0" * 64
    with pytest.raises(ValueError):
        a.validate_qualification(row, payload)


def test_omitted_hypothesis_refused():
    row, payload = example()
    row["qualification"]["hypotheses"].pop()
    with pytest.raises(ValueError):
        a.validate_qualification(row, payload)


def test_no_qualifying_witness_refused():
    row, payload = example()
    row["qualification"]["hypotheses"][0]["witness_action"] = ["1/100", "1/100"]
    with pytest.raises(ValueError):
        a.validate_qualification(row, payload)


def test_physical_bound_refused():
    row, payload = example()
    row["qualification"]["hypotheses"][0]["attempts"][0]["action"] = ["1", "0"]
    with pytest.raises(ValueError):
        a.validate_qualification(row, payload)


def test_prefix_must_not_be_relabelled_recovery():
    row, payload = example()
    row["qualification"]["full_recovery_claim"] = True
    with pytest.raises(ValueError):
        a.validate_qualification(row, payload)


def test_exact_manifest_catches_changed_source_record(monkeypatch):
    original = a.sha

    def changed(path):
        return (
            "0" * 64
            if Path(path) == DATA / "qualification/interior_pair__00032.json"
            else original(path)
        )

    monkeypatch.setattr(a, "sha", changed)
    with pytest.raises(ValueError, match="Artifact bytes changed"):
        a.audit(DATA)


def test_summary_is_write_once(tmp_path):
    dest = tmp_path / "summary"
    a.export(DATA, dest)
    with pytest.raises(FileExistsError):
        a.export(DATA, dest)
