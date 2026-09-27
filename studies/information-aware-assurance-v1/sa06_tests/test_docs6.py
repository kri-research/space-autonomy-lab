import json
from pathlib import Path


def test_external_evidence_stays_separate_from_internal_checks():
    here = Path(__file__).resolve().parents[1] / "sa06"
    data = json.loads((here / "external-evidence.json").read_text())
    assert data["external_result_provenance_verified"] is False
    assert data["overall_stage_without_external_evidence"] == "partially_complete"
    assert data["target_processor_measurements"].startswith("pending_")
    assert data["physical_trials"].startswith("pending_")
    assert data["independent_external_integration"].startswith("pending_")


def test_mapping_has_formal_edition_identity_and_no_conformance_claim():
    here = Path(__file__).resolve().parents[1] / "sa06"
    data = json.loads((here / "source-map.json").read_text())
    note = (here / "IMPLEMENTATION_NOTE.md").read_text()
    assert data["standard"]["edition"] == "KRI-STD-001-V2.0"
    assert data["standard"]["sha256"] in note
    assert "not every applicable requirement" in note
    for section in ("4.1", "4.2", "4.3", "4.4", "5.1", "5.2", "6.2", "6.3", "6.4"):
        assert "Section " + section in note
