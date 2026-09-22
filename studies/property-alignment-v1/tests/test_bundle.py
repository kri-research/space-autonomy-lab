"""Synthetic integrity fixtures, not spacecraft evidence or independent validation."""

import json
import pytest
import bundle


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root = tmp_path / "repository/studies/property-alignment-v1"
    base = root / "baseline"
    (base / "logs").mkdir(parents=True)
    monkeypatch.setattr(bundle, "ROOT", root)
    monkeypatch.setattr(bundle, "BASE", base)
    monkeypatch.setattr(bundle, "source_inventory", lambda: {"source.py": "checked"})
    record = {"status": "passed", "source_sha256": {"source.py": "checked"}, "output_sha256": {}}
    for name in bundle.GROUPS["audit"]:
        path = base / "data" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic fixture\n")
        record["output_sha256"][name] = bundle.digest(path.read_bytes())
    (base / "logs/audit-receipt.json").write_text(json.dumps(record))
    return base, record, tmp_path / "export"


def test_valid_output_import(prepared):
    base, record, destination = prepared
    assert bundle.export_group("audit", destination) == record
    assert all(
        (destination / n).read_bytes() == (base / "data" / n).read_bytes()
        for n in bundle.GROUPS["audit"]
    )


@pytest.mark.parametrize(
    "fault", ["tampered", "missing", "source_changed", "running", "extra_member", "symlink"]
)
def test_invalid_output_rejected(prepared, monkeypatch, fault):
    base, record, destination = prepared
    first = base / "data" / bundle.GROUPS["audit"][0]
    if fault == "tampered":
        first.write_bytes(b"changed")
    elif fault == "missing":
        first.unlink()
    elif fault == "source_changed":
        monkeypatch.setattr(bundle, "source_inventory", lambda: {"source.py": "changed"})
    elif fault == "running":
        record["status"] = "running"
    elif fault == "extra_member":
        record["output_sha256"]["../private.txt"] = "forbidden"
    elif fault == "symlink":
        saved = first.with_name("other.csv")
        first.rename(saved)
        first.symlink_to(saved)
    (base / "logs/audit-receipt.json").write_text(json.dumps(record))
    with pytest.raises(ValueError):
        bundle.export_group("audit", destination)
    assert not destination.exists()


def test_exports_cannot_modify_research_repository(prepared):
    with pytest.raises(ValueError):
        bundle.export_group("audit", bundle.ROOT / "accidental-output")


def test_exports_cannot_modify_pinned_evidence(prepared, monkeypatch):
    base, record, destination = prepared
    historical = destination.parent / "pinned-evidence"
    historical.mkdir()
    monkeypatch.setenv("SAL_EVIDENCE_ROOT", str(historical))
    with pytest.raises(ValueError, match="historical evidence"):
        bundle.export_group("audit", historical / "data")
    assert not (historical / "data").exists()


def test_export_root_symlink_is_rejected(prepared):
    base, record, destination = prepared
    target = destination.parent / "real-destination"
    target.mkdir()
    destination.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        bundle.export_group("audit", destination)
    assert not list(target.iterdir())
