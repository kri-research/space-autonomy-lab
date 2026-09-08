import json
from pathlib import Path


def test_v010_release_metadata_is_consistent() -> None:
    manifest = json.loads(Path("release/v0.1.0.json").read_text(encoding="utf-8"))
    citation = Path("CITATION.cff").read_text(encoding="utf-8")
    project = Path("pyproject.toml").read_text(encoding="utf-8")
    package = Path("src/kri_space_autonomy/__init__.py").read_text(encoding="utf-8")

    assert manifest["version"] == "0.1.0"
    assert manifest["tag"] == "v0.1.0"
    assert manifest["release_date"] == "2026-09-08"
    assert manifest["status"] == "stable_citable_research_release"
    assert manifest["scientific_rerun_required"] is False
    assert "version: 0.1.0" in citation
    assert "date-released: 2026-09-08" in citation
    assert 'version = "0.1.0"' in project
    assert '__version__ = "0.1.0"' in package
    assert Path(manifest["release_notes"]).is_file()


def test_retired_release_workflow_is_manual_and_read_only() -> None:
    workflow = Path(".github/workflows/release-v0.1.0.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "contents: write" not in workflow
    assert "  push:" not in workflow
    assert "gh release create" not in workflow
    assert "tools/verify_published_release.py" in workflow


def test_referenced_report_has_a_corporate_author() -> None:
    citation = Path("CITATION.cff").read_text(encoding="utf-8")
    reference = citation.split("references:", 1)[1]
    assert "    authors:\n      - name: KRI" in reference
