"""Post-execution certificate revalidation guards; no new controller trials."""

from pathlib import Path
from collections import Counter
import json
import pytest
from candidate.fixtures import fixtures
from candidate.verification import replay

DATA = Path(__file__).resolve().parents[1] / "recorded_development"


def test_revalidation_covers_original_on_time_positive_categories():
    checks = replay.positive_checks(DATA)
    counts = Counter(kind for _, kind, _, _ in checks)
    assert counts["candidate"] == 48
    assert counts["fixed_pair_action"] == 3
    assert counts["nonlinear_same_action"] == 18
    assert counts["predictive"] + counts["barrier"] == 4
    assert all(old["status"] == "certified_common_prefix" for _, _, _, old in checks)


def test_revalidation_rejects_a_failed_saved_prefix(monkeypatch):
    info = fixtures()["midpoint_known"]
    old = {"information_sha256": info.identity(), "action": ["0", "0"], "model": "hcw"}
    monkeypatch.setattr(replay, "positive_checks", lambda _: [("x", "candidate", info, old)])
    monkeypatch.setattr(replay, "certify_action", lambda *a: {"status": "unresolved"})
    with pytest.raises(ValueError, match="failed revalidation"):
        replay.prefix_replay(DATA)


def test_revalidation_rejects_wrong_hypothesis_identity(monkeypatch):
    info = fixtures()["midpoint_known"]
    old = {"information_sha256": "wrong"}
    monkeypatch.setattr(replay, "positive_checks", lambda _: [("x", "candidate", info, old)])
    with pytest.raises(ValueError, match="Wrong saved prefix input"):
        replay.prefix_replay(DATA)


def test_output_cannot_overwrite_source_evidence(monkeypatch):
    monkeypatch.setenv("SAL_EVIDENCE_ROOT", str(DATA))
    with pytest.raises(ValueError, match="outside all source repositories"):
        replay.run(DATA, DATA / "new-output")


def test_failed_revalidation_keeps_explicit_failed_receipt(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "manifest.json").write_text("{}")
    monkeypatch.setenv("SAL_EVIDENCE_ROOT", str(source))
    monkeypatch.setattr(replay, "verify", lambda _: None)

    def fail(_):
        raise ArithmeticError("Deliberate validation fault")

    monkeypatch.setattr(replay, "prefix_replay", fail)
    output = tmp_path / "output"
    with pytest.raises(ArithmeticError):
        replay.run(source, output)
    assert json.loads((output / "verification.json").read_text())["passed"] is False
