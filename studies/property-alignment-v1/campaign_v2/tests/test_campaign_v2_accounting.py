"""Reporting regressions operate only on recorded or deliberately corrupted copies."""

from copy import deepcopy
from pathlib import Path
import io
import tarfile
import pytest
from campaign_v2.audit import (
    Records,
    audit,
    decode,
    qualification_claim,
    episode_claim,
)
from campaign_v2.artifact import verify_artifact
from campaign_v2.report import quantile, timing
from evaluation.analysis import analyze_rows
from evaluation_v2.receipts import seal

ARTIFACT = Path(__file__).resolve().parents[1] / "recorded"


@pytest.fixture(scope="module")
def saved():
    return audit(ARTIFACT / "raw_records.jsonl")


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}'])
def test_strict_numeric_and_duplicate_keys(raw):
    with pytest.raises(ValueError):
        decode(raw)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../b", "a\\b"])
def test_archive_path_rejected(tmp_path, name):
    path = tmp_path / "bad.tar.gz"
    with tarfile.open(path, "w:gz") as t:
        m = tarfile.TarInfo(name)
        m.size = 2
        t.addfile(m, io.BytesIO(b"{}"))
    with pytest.raises(ValueError):
        Records(path)


def test_duplicate_archive_member_rejected(tmp_path):
    path = tmp_path / "bad.tar.gz"
    with tarfile.open(path, "w:gz") as t:
        for _ in range(2):
            m = tarfile.TarInfo("same.json")
            m.size = 2
            t.addfile(m, io.BytesIO(b"{}"))
    with pytest.raises(ValueError):
        Records(path)


def test_complete_recorded_membership_and_analysis(saved):
    checked, analysis, qs, rows, inputs, selected = saved
    assert checked["passed"] and checked["frozen_analysis_reproduced"]
    assert len(qs) == len(inputs) == 1152 and len(rows) == len(selected) == 768
    assert analysis["planned_denominator"] == 768 and analysis["missing_selected"] == []
    assert checked["new_numerical_replay"] is False


def test_archive_matches_all_saved_tables():
    assert verify_artifact(ARTIFACT)["passed"]


def reseal(row):
    row.pop("receipt_sha256", None)
    return seal(row)


def test_boolean_index_cannot_impersonate_integer(saved):
    _, _, qs, _, inputs, _ = saved
    row = deepcopy(qs[0])
    row["index"] = bool(row["index"])
    with pytest.raises(ValueError):
        qualification_claim(reseal(row), inputs[0])


def test_unknown_eligibility_cannot_enter_selection(saved):
    _, _, qs, _, inputs, _ = saved
    row = deepcopy(qs[0])
    row["qualification"]["eligible"] = None
    row["qualification"]["status"] = "unresolved_computation"
    with pytest.raises(ValueError):
        qualification_claim(reseal(row), inputs[0])


def test_invalid_library_action_rejected(saved):
    _, _, qs, _, inputs, _ = saved
    i = next(i for i, r in enumerate(qs) if r["qualification"]["eligible"])
    row = deepcopy(qs[i])
    row["qualification"]["hypotheses"][0]["witness_action"] = ["1", "0"]
    with pytest.raises(ValueError):
        qualification_claim(reseal(row), inputs[i])


def test_selected_qualification_cannot_change(saved):
    _, _, _, rows, _, selected = saved
    row = deepcopy(rows[0])
    q = deepcopy(row["qualification"])
    q["information_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        episode_claim(row, selected[0], q)


def test_invalid_definite_proof_is_not_excluded_from_denominator(saved):
    _, analysis, _, rows, _, selected = saved
    copy = deepcopy(rows)
    i = next(i for i, r in enumerate(copy) if r["primary"]["decisive"])
    copy[i]["primary"]["valid_certificate"] = False
    copy[i]["primary"]["on_time_decisive_valid"] = False
    out = analyze_rows(
        copy, protected=True, expected_keys=[(p["stratum"], p["index"]) for p in selected]
    )
    assert out["planned_denominator"] == 768 and out["invalid_definite_certificates"] >= 1
    assert not out["validity_claim_gate_passed"]
    assert out["on_time_decisive_valid"] <= analysis["on_time_decisive_valid"]


def test_missing_selected_record_withholds_interval(saved):
    _, _, _, rows, _, selected = saved
    out = analyze_rows(
        rows[:-1], protected=True, expected_keys=[(p["stratum"], p["index"]) for p in selected]
    )
    assert out["planned_denominator"] == 768 and not out["campaign_complete"]
    assert "balanced_coverage" not in out and len(out["missing_selected"]) == 1


def test_duplicate_episode_refused(saved):
    _, _, _, rows, _, selected = saved
    with pytest.raises(ValueError):
        analyze_rows(
            [*rows, rows[0]],
            protected=True,
            expected_keys=[(p["stratum"], p["index"]) for p in selected],
        )


def test_report_verification_never_executes_scientific_trials(monkeypatch):
    import candidate.certify
    import candidate.affine
    import evaluation.episode
    import evaluation.qualification
    import qualification_repair_v1.core
    import qualification_repair_v1.recheck
    import adjudication.engine
    import adjudication.flow

    def prohibited(*args, **kwargs):
        raise AssertionError("Scientific computation called by a read-only artifact audit")

    targets = {
        candidate.certify: ["decide", "certify_action"],
        candidate.affine: ["obstruction", "recheck_certificate"],
        evaluation.episode: ["run_case", "decide", "certify_action", "recheck_certificate"],
        evaluation.qualification: ["qualification"],
        qualification_repair_v1.core: ["qualify"],
        qualification_repair_v1.recheck: ["recheck"],
        adjudication.engine: ["adjudicate"],
        adjudication.flow: ["propagate_schedule"],
    }
    for module, names in targets.items():
        for name in names:
            monkeypatch.setattr(module, name, prohibited)
    assert verify_artifact(ARTIFACT)["passed"]


def test_descriptive_timing_missingness_retained():
    result = timing([1.0, 2.0, None, 4.0])
    assert result["observed"] == 3 and result["missing"] == 1 and result["median_s"] == 2
    assert quantile([1.0, 2.0, 4.0], 0.95) == pytest.approx(3.8)


def test_incomplete_raw_directory_not_complete(tmp_path):
    with pytest.raises(ValueError):
        audit(tmp_path)


@pytest.mark.parametrize(
    "content",
    [
        b'{"path":"../escape","raw_utf8":"x"}\n',
        b'{"path":"a","raw_utf8":2}\n',
        b'{"path":"a","raw_utf8":"x"}\n{"path":"a","raw_utf8":"x"}\n',
    ],
)
def test_text_bundle_rejects_unsafe_or_duplicate_members(tmp_path, content):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(content)
    with pytest.raises(ValueError):
        Records(path)
