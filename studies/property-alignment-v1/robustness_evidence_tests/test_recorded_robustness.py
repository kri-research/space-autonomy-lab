"""Post-run artifact checks outside the frozen numerical package."""

import hashlib
import json
import shutil
import pytest
from boundary_robustness_v1.study import ROOT, verify_results
from independent_hcw_audit_v1.schema import identity

FROZEN = ROOT / "frozen/study.json"
STUDY_ID = json.loads(FROZEN.read_text())["study_id"]


def copy(tmp_path):
    out = tmp_path / "copy"
    shutil.copytree(ROOT / "recorded", out)
    return out


def reseal(out):
    path = out / "completion.json"
    doc = json.loads(path.read_text())
    doc["files"] = {
        p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob("*")
        if p.is_file() and p.name != "completion.json"
    }
    path.write_text(json.dumps(doc))


def test_all_registered_searches_and_evaluations_present():
    r = verify_results(ROOT / "recorded", FROZEN, STUDY_ID)
    assert r["passed"] and r["evaluations"] == 122 and r["searches"] == 12
    assert not r["original_campaign_executed"]


def test_missing_evaluation_cannot_pass(tmp_path):
    out = copy(tmp_path)
    next((out / "evaluations").glob("*.json")).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_results(out, FROZEN, STUDY_ID)


def test_changed_bytes_cannot_pass(tmp_path):
    out = copy(tmp_path)
    path = next((out / "evaluations").glob("*.json"))
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError):
        verify_results(out, FROZEN, STUDY_ID)


def test_resealed_false_bound_rejected_by_recalculation(tmp_path):
    out = copy(tmp_path)
    path = next((out / "evaluations").glob("*.json"))
    row = json.loads(path.read_text())
    result = row["result"]
    result["shifted_obstruction_margin_lower_m"] = "100"
    result["result_sha256"] = identity({k: v for k, v in result.items() if k != "result_sha256"})
    path.write_text(json.dumps(row))
    reseal(out)
    with pytest.raises(ValueError, match="calculation changed"):
        verify_results(out, FROZEN, STUDY_ID, recompute=True)


def test_changed_reported_lower_radius_rejected(tmp_path):
    out = copy(tmp_path)
    path = out / "summary.json"
    doc = json.loads(path.read_text())
    doc["searches"][0]["lower_radius"] = "1"
    path.write_text(json.dumps(doc))
    reseal(out)
    with pytest.raises(ValueError):
        verify_results(out, FROZEN, STUDY_ID)


def test_wrong_study_identity_rejected():
    with pytest.raises(ValueError):
        verify_results(ROOT / "recorded", FROZEN, "0" * 64)


def test_original_triple_and_commands_not_optimized():
    summary = json.loads((ROOT / "recorded/summary.json").read_text())
    assert summary["fixed_commands_unchanged"] and not summary["original_campaigns_executed"]
    assert not summary["physical_validation"] and not summary["independent_human_review"]


def test_all_noncertified_upper_bounds_retained():
    summary = json.loads((ROOT / "recorded/summary.json").read_text())
    for search in summary["searches"]:
        if not search["cap_passed"]:
            assert search["noncertified_upper"] is not None
            assert any(not p["admitted"] for p in search["probes"])


def test_stress_does_not_claim_failure_inside_smaller_certificate():
    data = json.loads((ROOT / "recorded/stress.json").read_text())
    assert len(data) == 3 and all(
        r["initial_status"] == "contained" and r["fixed_command_counterexample"] for r in data
    )
    assert all("not within a claimed smaller certified family" in r["scope"] for r in data)


def test_public_presentation_manifest_and_normalization():
    folder = ROOT / "presentation"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert {p.name for p in folder.iterdir() if p.is_file() and p.name != "manifest.json"} == set(
        manifest["files"]
    )
    for name, h in manifest["files"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == h
    for name, record in manifest["serialization_normalization"]["files"].items():
        assert (
            record["public_sha256"] == manifest["files"][name]
            and record["raw_local_generation_preserved"]
        )
        assert record["raw_sha256"] != record["public_sha256"]


def test_public_frontier_is_derived_from_exact_recorded_bounds():
    import csv
    import io
    from boundary_robustness_v1.presentation import frontier

    summary = json.loads((ROOT / "recorded/summary.json").read_text())
    expected = frontier(summary)
    actual = list(csv.DictReader((ROOT / "presentation/frontier.csv").open()))
    assert actual == [{k: str(v) for k, v in row.items()} for row in expected]
    raw = io.StringIO(newline="")
    writer = csv.DictWriter(raw, fieldnames=list(expected[0]))
    writer.writeheader()
    writer.writerows(expected)
    manifest = json.loads((ROOT / "presentation/manifest.json").read_text())
    assert (
        hashlib.sha256(raw.getvalue().encode()).hexdigest()
        == manifest["serialization_normalization"]["files"]["frontier.csv"]["raw_sha256"]
    )


def test_public_sensitivity_rows_match_all_registered_lower_bounds():
    import csv
    import io

    summary = json.loads((ROOT / "recorded/summary.json").read_text())
    expected = []
    for row in summary["searches"]:
        expected.append(
            {
                "family": row["family"],
                "criterion": row["gate"],
                **row["lower_parameters"],
                "lower_radius": row["lower_radius"],
                "noncertified_upper": row["noncertified_upper"],
                "cap_passed": row["cap_passed"],
            }
        )
    actual = list(csv.DictReader((ROOT / "presentation/sensitivity.csv").open()))
    assert actual == [{k: "" if v is None else str(v) for k, v in row.items()} for row in expected]
    raw = io.StringIO(newline="")
    writer = csv.DictWriter(raw, fieldnames=list(expected[0]))
    writer.writeheader()
    writer.writerows(expected)
    manifest = json.loads((ROOT / "presentation/manifest.json").read_text())
    assert (
        hashlib.sha256(raw.getvalue().encode()).hexdigest()
        == manifest["serialization_normalization"]["files"]["sensitivity.csv"]["raw_sha256"]
    )
