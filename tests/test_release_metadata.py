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


def test_release_workflow_is_one_shot_and_main_only() -> None:
    workflow = Path(".github/workflows/release-v0.1.0.yml").read_text(encoding="utf-8")

    assert "branches: [main]" in workflow
    assert "release/v0.1.0.json" in workflow
    assert "permissions:\n  contents: write" in workflow
    assert "gh release create v0.1.0" in workflow
