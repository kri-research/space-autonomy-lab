"""Navigation maintenance must preserve cited scientific text and source identities."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "0cbc55c7e9f176cc0d20c33c3b7416079acc7313"
SCIENTIFIC = "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8"


def previous(path: str) -> str:
    return subprocess.check_output(
        ["git", "--no-replace-objects", "show", f"{PREVIOUS}:{path}"],
        cwd=ROOT,
        text=True,
        timeout=30,
    )


def test_root_exposes_research_and_reproduction_without_replacing_history():
    readme = (ROOT / "README.md").read_text()
    assert "](studies/README.md)" in readme
    assert "](docs/research-reproduction.md)" in readme
    assert "](studies/property-alignment-v1/publication_v1/README.md)" in readme
    before, section = readme.split("## Research and reproduction\n", 1)
    _, after = section.split("## Current status\n", 1)
    assert before + "## Current status\n" + after == previous("README.md")


def test_research_index_adds_reproduction_navigation_without_revising_outcomes():
    index = (ROOT / "studies/README.md").read_text()
    assert "](../docs/research-reproduction.md)" in index
    assert "](property-alignment-v1/publication_v1/README.md)" in index
    before, section = index.split("For installation profiles and recorded-result checks,", 1)
    _, after = section.split("## Evidence phases\n", 1)
    assert before + "## Evidence phases\n" + after == previous("studies/README.md")


@pytest.mark.parametrize(
    "relative", ["README.md", "studies/README.md", "docs/research-reproduction.md"]
)
def test_navigation_pages_have_existing_local_link_targets(relative: str):
    page = ROOT / relative
    text = re.sub(r"```.*?```", "", page.read_text(), flags=re.S)
    links = re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", text)
    assert links
    for target in links:
        parsed = urlsplit(target)
        if parsed.scheme or not parsed.path:
            continue
        destination = (page.parent / unquote(parsed.path)).resolve()
        assert destination.is_relative_to(ROOT)
        assert destination.exists(), f"Missing target in {relative}: {target}"


def test_environment_guide_keeps_distinct_versions_and_evidence_boundaries():
    guide = " ".join((ROOT / "docs/research-reproduction.md").read_text().split())
    for required in (
        "CPython 3.11.16",
        "CPython 3.13.5",
        "original component 0.1.0",
        "corrected 0.1.1",
        "full-history",
        "separate scientific checkout",
        "does not mean every historical test or manifest passes",
    ):
        assert required in guide


@pytest.mark.parametrize("relative", ["CITATION.cff", "release/v0.1.0.json"])
def test_original_citation_and_release_metadata_remain_unchanged(relative: str):
    assert (ROOT / relative).read_text() == previous(relative)


def test_reproduction_ci_adds_only_the_checker_to_the_pinned_scientific_snapshot():
    workflow = (ROOT / ".github/workflows/publication-reproduction.yml").read_text()
    assert f"git diff --exit-code --diff-filter=CDMRTUXB {SCIENTIFIC}" in workflow
    assert f"checkout --detach {SCIENTIFIC}" in workflow
    assert 'test ! -e "$RUNNER_TEMP/sal-scientific/studies/' in workflow
    assert "cp -R studies/property-alignment-v1/publication_v1 " in workflow
    assert "working-directory: ${{ runner.temp }}/sal-scientific/studies/" in workflow
    assert "python -m publication_v1.audit" in workflow
    assert "python -m publication_v1.verify_recorded" in workflow
    assert "python -m publication_v1.reproduce" in workflow
    assert 'git -C "$GITHUB_WORKSPACE" diff --exit-code' in workflow
    assert "contents: read" in workflow
    # The added checker must not overwrite any member of the bound scientific inventory.
    assert not subprocess.check_output(
        ["git", "ls-tree", SCIENTIFIC, "studies/property-alignment-v1/publication_v1"],
        cwd=ROOT,
        timeout=30,
    )


def test_reproduction_ci_covers_navigation_changes_before_and_after_merge():
    workflow = (ROOT / ".github/workflows/publication-reproduction.yml").read_text()
    assert "  pull_request:" in workflow and "  push:" in workflow
    for target in ("README.md", "studies/README.md", "docs/research-reproduction.md"):
        assert workflow.count(f"      - '{target}'") == 2
