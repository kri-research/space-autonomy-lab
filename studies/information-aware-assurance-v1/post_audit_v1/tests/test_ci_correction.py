"""Regression for a YAML-invalid unquoted pip command and retained evidence."""

from pathlib import Path

from post_audit_v1.assemble import HERE, REPO, git

FIRST = "eb0d1b3bce712cd2631970c3ba13689b723c832a"


def test_pip_installation_uses_a_yaml_literal_block():
    text = (REPO / ".github/workflows/post-audit-corrections.yml").read_text()
    lines = text.splitlines()
    positions = [i for i, line in enumerate(lines) if "--only-binary=:all:" in line]
    assert len(positions) == 1
    i = positions[0]
    assert lines[i - 1].strip() == "run: |"
    assert lines[i].startswith("          python -m pip install ")
    assert "--require-hashes" in lines[i]
    assert "sa06/requirements-build.lock" in lines[i]
    historical = git("show", FIRST + ":.github/workflows/post-audit-corrections.yml").decode()
    assert "run: python -m pip install" in historical
    assert "run: python -m pip install" not in text


def test_first_correction_evidence_retains_actual_git_bytes():
    history = HERE / "history/pre-ci-fix"
    expected = [Path("release.json")] + [
        Path("recorded") / name
        for name in ("manifest.json", "probes.json", "integration.json", "package-inventory.json")
    ]
    for rel in expected:
        original = (HERE / rel).relative_to(REPO).as_posix()
        assert (history / rel).read_bytes() == git("show", FIRST + ":" + original)
