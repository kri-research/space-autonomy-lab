"""Recorded diagnosis tests, not repeated campaign or timing measurements."""

from pathlib import Path
from fractions import Fraction
import hashlib
import json
import shutil
import pytest
from runtime_diagnosis_v1.summarize import verify_recorded
from runtime_diagnosis_v1.queue_probe import probe
from runtime_diagnosis_v1.worker import validate_case, STUDY

PACKAGE = Path(__file__).resolve().parents[1]
RECORDS = PACKAGE / "recorded"


def test_recorded_attempt_accounting():
    report = verify_recorded(RECORDS)
    assert report["passed"] and report["diagnostic_attempts"] == 13
    assert report["queue_witnesses"] == 2
    assert not report["original_campaign_valid"] and not report["repair_implemented"]


def test_tampered_diagnostic_evidence_is_rejected(tmp_path):
    target = tmp_path / "tampered"
    shutil.copytree(RECORDS, target)
    (target / "summary.json").write_text("{}\n")
    with pytest.raises(ValueError):
        verify_recorded(target)


def test_frozen_executables_unchanged():
    seal = json.loads((PACKAGE / "source_identity.json").read_text())
    for name, expected in seal["frozen_source_sha256"].items():
        assert hashlib.sha256((STUDY / name).read_bytes()).hexdigest() == expected


def test_queue_witnesses_reproduce_under_frozen_model():
    recorded = json.loads((RECORDS / "queue-probe.json").read_text())
    current = probe()
    for actual, expected in zip(current["rows"], recorded["rows"], strict=True):
        for key in (
            "attainable_vertex",
            "allowed_constant_disturbance_mps2",
            "side_residual_m",
            "endpoint_containment",
            "adjudication",
        ):
            assert actual[key] == expected[key]
    assert (
        current["source_sha256"]
        == hashlib.sha256((PACKAGE / "queue_probe.py").read_bytes()).hexdigest()
    )
    assert (
        recorded["source_sha256"]
        == hashlib.sha256((PACKAGE / "executed_source/queue_probe.py.txt").read_bytes()).hexdigest()
    )


def test_queue_witness_uses_an_attainable_input_before_action():
    recorded = json.loads((RECORDS / "queue-probe.json").read_text())
    payload = validate_case(137)["information"]
    for row in recorded["rows"]:
        h = payload["hypotheses"][row["hypothesis"]]
        assert all(
            Fraction(a) <= Fraction(v) <= Fraction(b)
            for a, v, b in zip(h["lower"], row["attainable_vertex"], h["upper"], strict=True)
        )
        assert Fraction(row["side_residual_m"][0]) > 0
        assert row["end_before_new_command_s"] == payload["age"] + payload["delay"] == 2
