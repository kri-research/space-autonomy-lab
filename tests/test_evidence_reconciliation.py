from __future__ import annotations

import copy
import gzip
import importlib
import io
import shutil
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

publication = importlib.import_module("check_reconciliation_publication")
reconciliation = importlib.import_module("reconcile_e005_records")
supplement = importlib.import_module("verify_evidence_supplement")


@pytest.fixture(scope="module")
def original_members():
    return supplement.read_original_members(ROOT)


@pytest.fixture(scope="module")
def frozen():
    return reconciliation.load_frozen(ROOT)


def tiny_rows(adverse: bool):
    return [
        {
            "case_id": reconciliation.CASES[0],
            "root_seed_id": "fixture-0",
            "configuration_id": arm,
            "physical_collision": False,
            "physical_keep_out_entry": False,
            "physical_corridor_departure": adverse,
            "hold_acquired": True,
            "monitor_override_commands": 0,
        }
        for arm in reconciliation.CONFIGURATIONS
    ]


def test_zero_discordances_distinguish_all_safe_and_all_adverse(frozen):
    analysis, config, _ = frozen
    for adverse in (False, True):
        rows = tiny_rows(adverse)
        counts = reconciliation.summarize(rows)
        gate = analysis._primary_gate([(rows[0], rows[1])], config)
        assert gate["discordant_pairs"] == 0
        assert gate["gate_minus_reference_risk_difference"] == 0.0
        assert gate["one_sided_exact_p"] == 1.0 and gate["passed"] is False
        assert counts["paired_adverse_table"]["both_adverse"] == int(adverse)
        assert counts["paired_adverse_table"]["both_safe"] == int(not adverse)
        descriptive = analysis._descriptive_summary(rows, config)
        assert descriptive[config.cases[0]][config.configurations[0]]["physical_adverse"] == int(
            adverse
        )
        mission = analysis._mission_gate([(rows[0], rows[1])], config, primary_passed=False)
        assert mission["status"] == "not_tested_primary_gate_closed"
        assert mission["passed"] is None and mission["one_sided_exact_p"] is None


def test_independent_paired_table_covers_all_four_cells():
    rows = []
    for index, (left, right) in enumerate(
        ((False, False), (True, False), (False, True), (True, True))
    ):
        pair = tiny_rows(False)
        for row, flag in zip(pair, (left, right), strict=True):
            row["root_seed_id"] = f"fixture-{index}"
            row["physical_corridor_departure"] = flag
        rows.extend(pair)
    counts = reconciliation.summarize(rows)
    assert counts["paired_roots"] == 4
    assert set(counts["paired_adverse_table"].values()) == {1}


@pytest.mark.parametrize("value", [0, 1, "false", None, [], {}])
def test_outcome_truthiness_is_rejected(value):
    rows = tiny_rows(False)
    rows[0]["physical_corridor_departure"] = value
    with pytest.raises(ValueError, match="booleans"):
        reconciliation.summarize(rows)


def test_incomplete_and_duplicate_pairs_are_rejected():
    pair = tiny_rows(False)
    for rows in (pair[:1], pair + pair[:1]):
        with pytest.raises(ValueError):
            reconciliation.summarize(rows)


@pytest.mark.parametrize(
    "field,value",
    [
        ("primary_fault_active_packets", True),
        ("maximum_covariance_trace", "0.1"),
        ("minimum_separation_m", float("inf")),
        ("physical_collision", 0),
        ("final_truth_relative_state", [0.0] * 5),
        ("scenario_hash", "wrong"),
    ],
)
def test_strict_episode_types_reject_permissive_inputs(original_members, field, value):
    rows = reconciliation.jsonl(
        original_members[reconciliation.RESULTS + "campaign/confirmatory-episodes.jsonl"]
    )
    row = copy.deepcopy(rows[0])
    row[field] = value
    with pytest.raises(ValueError):
        reconciliation.check_row_types(row)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'{"x":Infinity}'])
def test_strict_json_rejects_duplicate_and_nonfinite_values(raw):
    with pytest.raises(ValueError):
        supplement.strict_json(raw)


def test_real_record_counts_and_types_match_new_dated_analysis(original_members):
    rows = reconciliation.jsonl(
        original_members[reconciliation.RESULTS + "campaign/confirmatory-episodes.jsonl"]
    )
    seeds = reconciliation.jsonl(original_members[reconciliation.SEEDS + "confirmatory.jsonl"])
    reconciliation.validate_records(rows, seeds)
    counts = reconciliation.summarize(rows)
    recorded = supplement.strict_json(
        (ROOT / supplement.SUPPLEMENT / "e005-reconciliation.json").read_bytes()
    )
    assert recorded["record_kind"].startswith("post-release recomputation")
    assert recorded["analysis_created_utc"].startswith("2026-09-09")
    assert counts == recorded["computation"]["independent_counts"]
    assert counts["paired_adverse_table"] == {
        "both_safe": 0,
        "reference_adverse_gate_safe": 0,
        "gate_adverse_reference_safe": 0,
        "both_adverse": 1068,
    }
    assert recorded["computation"]["frozen_analysis_result"]["validity"]["passed"] is True
    for values in counts["totals_by_configuration"].values():
        assert (
            values["physical_adverse"]
            == values["corridor_departure"]
            == values["hold_acquired"]
            == 1068
        )
        assert values["collision"] == values["keep_out_entry"] == 0


def test_archive_payload_checks_all_original_members(original_members):
    assert len(original_members) == 1092
    assert sum(map(len, original_members.values())) == 13716631
    assert supplement.verify(ROOT)["status"] == "VERIFIED_CONTENT_IDENTITIES"


def archive_fixture(entries, inventory_entries=None, kind=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in entries:
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            if kind:
                member.type = kind
                member.linkname = "target"
                member.size = 0
            archive.addfile(member, io.BytesIO(raw) if not kind else None)
    files = [
        {"path": name, "bytes": len(raw), "sha256": supplement.sha256(raw)}
        for name, raw in (inventory_entries if inventory_entries is not None else entries)
    ]
    inventory = {
        "files": files,
        "member_count": len(files),
        "total_member_bytes": sum(f["bytes"] for f in files),
    }
    return gzip.compress(stream.getvalue(), mtime=0), inventory


def test_tiny_archive_roundtrip_is_in_memory():
    raw, inventory = archive_fixture([("results/fixture.json", b"{}\n")])
    assert supplement.validate_archive(raw, inventory) == {"results/fixture.json": b"{}\n"}


@pytest.mark.parametrize("name", ["/absolute", "../escape", "a/../escape", "a//b", "a\\b", "C:bad"])
def test_archive_unsafe_paths_rejected(name):
    raw, inventory = archive_fixture([(name, b"{}")])
    with pytest.raises(ValueError):
        supplement.validate_archive(raw, inventory)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE])
def test_archive_links_and_nonregular_members_rejected(kind):
    raw, inventory = archive_fixture([("fixture", b"")], kind=kind)
    with pytest.raises(ValueError):
        supplement.validate_archive(raw, inventory)


@pytest.mark.parametrize("change", ["duplicate", "extra", "missing", "corrupt", "size"])
def test_archive_membership_and_content_fail_closed(change):
    expected = [("one", b"original")]
    members = expected.copy()
    if change == "duplicate":
        members += expected
    if change == "extra":
        members += [("extra", b"new")]
    if change == "missing":
        members = []
    if change == "corrupt":
        members = [("one", b"modified")]
    if change == "size":
        members = [("one", b"short")]
    raw, inventory = archive_fixture(members, expected)
    with pytest.raises(ValueError):
        supplement.validate_archive(raw, inventory)


def test_expansion_bound_is_enforced(monkeypatch):
    raw, inventory = archive_fixture([("one", b"small")])
    monkeypatch.setattr(supplement, "MAX_TAR_BYTES", 100)
    with pytest.raises(ValueError, match="expansion"):
        supplement.validate_archive(raw, inventory)


def test_supplement_missing_or_corrupt_files_fail_without_writes(tmp_path):
    destination = tmp_path / supplement.SUPPLEMENT
    shutil.copytree(ROOT / supplement.SUPPLEMENT, destination)
    payload = destination / "e002b-validation-recovered.json"
    original = payload.read_bytes()
    payload.unlink()
    with pytest.raises(ValueError):
        supplement.verify(tmp_path)
    payload.write_bytes(original + b" ")
    before = payload.read_bytes()
    with pytest.raises(ValueError):
        supplement.verify(tmp_path)
    assert payload.read_bytes() == before


def frozen_publication_report():
    return {
        "passed": False,
        "new_opaque_files": 1,
        "new_opaque_files_preview": [publication.ARCHIVE_PATH],
        "secret_matches": 0,
        "secret_matches_preview": [],
        "provenance_privacy_scan": {
            "passed": True,
            "matches": 0,
            "matches_preview": [],
            "opaque_files": 1,
            "opaque_files_preview": [publication.ARCHIVE_PATH],
        },
    }


def test_only_pinned_archive_can_explain_frozen_opaque_finding():
    publication.validate_frozen_report(frozen_publication_report())
    for key, value in [
        ("new_opaque_files", 2),
        ("secret_matches", 1),
        ("passed", True),
        ("new_opaque_files_preview", ["unexpected-archive.tar.gz"]),
    ]:
        report = frozen_publication_report()
        report[key] = value
        with pytest.raises(ValueError):
            publication.validate_frozen_report(report)


def test_expanded_payload_scan_rejects_private_paths_and_credentials():
    for raw in [
        ("/" + "Users/someone/private").encode(),
        ("ghp_" + "a" * 30).encode(),
        ("file:" + "///private/path").encode(),
    ]:
        with pytest.raises(ValueError):
            publication.scan_text(raw)


def test_frozen_loader_does_not_import_a_workflow_or_runner(frozen):
    analysis, config, source = frozen
    assert analysis.__name__ == "_sal_reconciliation_frozen.analysis"
    assert config.primary_roots == 1068
    assert source["source_commit"] == reconciliation.SOURCE_COMMIT
    assert set(k for k in sys.modules if k.startswith("_sal_reconciliation_frozen")) == {
        "_sal_reconciliation_frozen",
        "_sal_reconciliation_frozen.config",
        "_sal_reconciliation_frozen.analysis",
    }


def test_readme_correction_and_old_scientific_docs_remain_distinct():
    readme = (ROOT / "README.md").read_text()
    assert "E005 correction, 9 September 2026" in readme
    assert "both configurations recorded zero physical adverse events; H2" not in readme
    assert (
        "physical adverse event"
        in (ROOT / "docs/experiment-005-confirmatory-closeout.md").read_text()
    )
    assert (ROOT / "docs/e005-corrigendum-2026-09-09.md").is_file()
