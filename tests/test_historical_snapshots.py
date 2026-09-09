from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "historical_snapshot_verifier", ROOT / "tools/verify_historical_snapshots.py"
)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def commit(root: Path, message: str) -> str:
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        message,
    )
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def snapshots(tmp_path: Path):
    git(tmp_path, "init", "-q")
    file = tmp_path / "docs/input.txt"
    file.parent.mkdir()
    file.write_bytes(b"historical input\n")
    old = commit(tmp_path, "Historical fixture")
    manifest = {
        "source_file_hashes": {"docs/input.txt": hashlib.sha256(file.read_bytes()).hexdigest()}
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest) + "\n")
    file.write_bytes(b"published input\n")
    release = commit(tmp_path, "Published fixture")
    file.write_bytes(b"maintained input\n")
    maintenance = commit(tmp_path, "Maintenance fixture")
    return tmp_path, old, release, maintenance


def inspect(snapshots, item=None):
    root, old, release, maintenance = snapshots
    item = item or verifier.Identity("manifest.json", "docs/input.txt", old)
    return verifier.verify(root, catalogue=(item,), release=release, maintenance=maintenance)


def test_real_catalogue_matches_eleven_snapshots_and_one_recovered_supplement():
    report = verifier.verify(ROOT)
    assert report["catalogued_items"] == 12
    assert report["matched_historical_snapshots"] == 11
    assert report["matched_recovered_supplements"] == 1
    assert report["phase_differences"] == 11
    assert report["unresolved_items"] == 0
    assert report["verification_errors"] == 0
    assert report["catalogue_complete"] is True
    assert report["experimental_provenance_verified"] is False
    assert verifier.exit_code(report) == 0
    row = next(r for r in report["results"] if r["status"] == verifier.RECOVERED)
    assert row["expected_sha256"] == row["supplemental_sha256"] == verifier.E002B_EXPECTED
    assert row["current_sha256"] == verifier.E002B_OBSERVED
    assert row["historical_commit"] is None
    assert row["expected_bytes_in_original_git_snapshot"] is False
    assert row["supplemental_content_matched"] is True
    assert row["external_record_matched"] is False


def test_exact_phase_snapshot_is_identified_without_writes(snapshots):
    root, _, _, maintained = snapshots
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    report = inspect(snapshots)
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after
    assert verifier.exit_code(report) == 0
    row = report["results"][0]
    assert row["status"] == verifier.PHASE
    assert row["current_snapshot_commit"] == maintained
    assert row["historical_sha256"] == row["expected_sha256"]


def test_current_bytes_can_match_the_specific_historical_snapshot(snapshots):
    root, old, _, _ = snapshots
    (root / "docs/input.txt").write_bytes(b"historical input\n")
    row = inspect(snapshots)["results"][0]
    assert row["status"] == verifier.MATCHED
    assert row["current_snapshot_commit"] == old


@pytest.mark.parametrize("change", ["unknown", "missing", "symlink", "directory_symlink"])
def test_unrecognised_current_state_is_not_excused_by_history(snapshots, change):
    root, _, _, _ = snapshots
    file = root / "docs/input.txt"
    if change == "unknown":
        file.write_bytes(b"unreviewed alteration\n")
    elif change == "missing":
        file.unlink()
    elif change == "symlink":
        file.unlink()
        file.symlink_to(root / "manifest.json")
    else:
        (root / "docs").rename(root / "saved-docs")
        (root / "docs").symlink_to(root / "saved-docs", target_is_directory=True)
    report = inspect(snapshots)
    assert verifier.exit_code(report) == 2
    assert report["results"][0]["status"] == verifier.ERROR
    assert report["phase_differences"] == 0


def test_manifest_rewrite_is_rejected_instead_of_re_freezing(snapshots):
    root, _, _, _ = snapshots
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"source_file_hashes": {"docs/input.txt": "0" * 64}}))
    report = inspect(snapshots)
    assert report["results"][0]["reason"] == "frozen_manifest_modified_in_checkout"
    assert verifier.exit_code(report) == 2


def test_other_historical_matches_cannot_rescue_the_wrong_designated_snapshot(snapshots):
    _, _, release, _ = snapshots
    item = verifier.Identity("manifest.json", "docs/input.txt", release)
    report = inspect(snapshots, item)
    assert report["results"][0]["reason"] == "designated_historical_snapshot_digest_mismatch"
    assert verifier.exit_code(report) == 2


@pytest.mark.parametrize("snapshot", ["f" * 40, "HEAD", "main", "12345"])
def test_missing_or_mutable_snapshot_is_a_verification_error(snapshots, snapshot):
    item = verifier.Identity("manifest.json", "docs/input.txt", snapshot)
    report = inspect(snapshots, item)
    assert verifier.exit_code(report) == 2
    assert report["matched_historical_snapshots"] == 0


def test_missing_anchor_cannot_be_replaced_with_checkout_data(snapshots):
    root, old, _, maintenance = snapshots
    report = verifier.verify(
        root,
        catalogue=(verifier.Identity("manifest.json", "docs/input.txt", old),),
        release="0" * 40,
        maintenance=maintenance,
    )
    assert verifier.exit_code(report) == 2


def test_git_replace_refs_do_not_change_the_pinned_object_read(snapshots):
    root, old, release, _ = snapshots
    git(root, "replace", old, release)
    report = inspect(snapshots)
    assert verifier.exit_code(report) == 0
    assert (
        report["results"][0]["historical_sha256"]
        == hashlib.sha256(b"historical input\n").hexdigest()
    )


def test_only_read_only_git_plumbing_is_dispatched(snapshots, monkeypatch):
    calls = []
    real_run = verifier.subprocess.run

    def observe(command, **kwargs):
        calls.append(command)
        assert command[0:2] == ["git", "--no-replace-objects"]
        assert command[4] == "cat-file"
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert kwargs["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
        assert "shell" not in kwargs
        return real_run(command, **kwargs)

    monkeypatch.setattr(verifier.subprocess, "run", observe)
    assert verifier.exit_code(inspect(snapshots)) == 0
    assert calls


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "../input.txt", "docs/../input.txt", "docs//input.txt"]
)
def test_catalogue_paths_cannot_escape_the_repository(snapshots, path):
    _, old, _, _ = snapshots
    report = inspect(snapshots, verifier.Identity("manifest.json", path, old))
    assert verifier.exit_code(report) == 2


def test_artifact_lookup_requires_one_unambiguous_identity():
    item = verifier.Identity("manifest.json", "input", "a" * 40, "artifact")
    digest = "b" * 64
    good = json.dumps({"artifacts": [{"path": "input", "sha256": digest}]}).encode()
    assert verifier._expected(good, item) == digest
    for body in [
        b"{}",
        b"null",
        b"{",
        json.dumps(
            {
                "artifacts": [
                    {"path": "input", "sha256": digest},
                    {"path": "input", "sha256": digest},
                ]
            }
        ).encode(),
    ]:
        with pytest.raises(verifier.InspectionError):
            verifier._expected(body, item)


def test_unknown_unresolved_entry_is_not_whitelisted(snapshots):
    _, old, _, _ = snapshots
    item = replace(verifier.Identity("manifest.json", "docs/input.txt", old), snapshot=None)
    report = inspect(snapshots, item)
    assert verifier.exit_code(report) == 2
    assert report["unresolved_items"] == 0


def test_known_gap_cannot_be_hidden_by_modifying_current_bytes(monkeypatch):
    original = verifier._working_bytes

    def changed(root, relative):
        if relative == "experiments/002b/validation-evidence.json":
            return b"replacement validation evidence"
        return original(root, relative)

    monkeypatch.setattr(verifier, "_working_bytes", changed)
    report = verifier.verify(ROOT)
    assert verifier.exit_code(report) == 2
    assert report["unresolved_items"] == 0
    assert report["verification_errors"] == 1


def test_cli_returns_zero_for_complete_content_catalogue_with_no_runtime_imports():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "tools/verify_historical_snapshots.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["status"] == "MATCHED"
    assert report["scientific_calculations_executed"] is False
    assert report["checkout_modified"] is False


def test_cli_missing_repository_returns_structured_error(tmp_path, capsys):
    assert verifier.main(["--root", str(tmp_path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["verification_errors"] == 12
    assert report["matched_historical_snapshots"] == 0


def test_existing_external_record_is_only_read(tmp_path):
    file = tmp_path / "archival-payload.json"
    raw = b"exact archived bytes"
    file.write_bytes(raw)
    expected = hashlib.sha256(raw).hexdigest()
    before = file.stat().st_mtime_ns
    assert verifier._external_record_hash(file, expected) == expected
    assert file.read_bytes() == raw and file.stat().st_mtime_ns == before


@pytest.mark.parametrize("kind", ["wrong", "missing", "symlink"])
def test_invalid_external_record_cannot_close_the_gap(tmp_path, kind):
    file = tmp_path / "archival-payload.json"
    if kind == "wrong":
        file.write_bytes(b"wrong record")
    elif kind == "symlink":
        file.symlink_to(ROOT / "README.md")
    with pytest.raises(verifier.InspectionError):
        verifier._external_record_hash(file, "0" * 64)


def test_wrong_supplied_record_is_an_error_not_a_known_gap(tmp_path):
    file = tmp_path / "archival-payload.json"
    file.write_bytes(b"wrong record")
    report = verifier.verify(ROOT, e002b_record=file)
    assert verifier.exit_code(report) == 2
    assert report["verification_errors"] == 1


def test_matched_external_payload_does_not_waive_missing_public_supplement(monkeypatch):
    original = verifier._working_bytes

    def missing(root, relative):
        if relative == verifier.E002B_SUPPLEMENT_PATH:
            raise verifier.InspectionError("working_file_unavailable:" + relative)
        return original(root, relative)

    monkeypatch.setattr(verifier, "_working_bytes", missing)
    monkeypatch.setattr(verifier, "_external_record_hash", lambda path, expected: expected)
    report = verifier.verify(ROOT, e002b_record=Path("existing-payload.json"))
    assert verifier.exit_code(report) == 1
    assert report["unresolved_items"] == 1
    assert report["verification_errors"] == 0
    row = next(r for r in report["results"] if r["status"] == verifier.GAP)
    assert row["external_record_matched"] is True
    assert row["external_record_sha256"] == verifier.E002B_EXPECTED
    assert row["supplemental_content_matched"] is False


def test_corrupt_public_supplement_is_a_verification_error(monkeypatch):
    original = verifier._working_bytes

    def corrupted(root, relative):
        if relative == verifier.E002B_SUPPLEMENT_PATH:
            return b"corrupt replacement"
        return original(root, relative)

    monkeypatch.setattr(verifier, "_working_bytes", corrupted)
    report = verifier.verify(ROOT)
    assert verifier.exit_code(report) == 2
    assert report["matched_recovered_supplements"] == 0
    assert report["verification_errors"] == 1


def test_readme_correction_has_an_exact_path_specific_content_binding():
    report = verifier.verify(ROOT)
    row = next(r for r in report["results"] if r["path"] == "README.md")
    assert row["current_content_binding"]["sha256"] == verifier.APPROVED_CURRENT_SHA256["README.md"]
    assert row["current_snapshot_commit"] is None
    assert set(verifier.APPROVED_CURRENT_SHA256) == {"README.md"}


def test_future_readme_drift_is_not_covered_by_the_correction_binding(monkeypatch):
    original = verifier._working_bytes

    def changed(root, relative):
        if relative == "README.md":
            return b"Unreviewed future README bytes"
        return original(root, relative)

    monkeypatch.setattr(verifier, "_working_bytes", changed)
    report = verifier.verify(ROOT)
    assert verifier.exit_code(report) == 2
    row = next(r for r in report["results"] if r["path"] == "README.md")
    assert row["reason"] == "unexpected_current_file_digest"
