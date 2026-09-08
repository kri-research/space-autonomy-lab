from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


preservation = _load("check_release_preservation")
release_check = _load("verify_published_release")


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def snapshot(tmp_path: Path) -> tuple[Path, str]:
    _git(tmp_path, "init", "-q")
    for name, content in {
        "src/controller.py": "value = 1\n",
        "results/study/outcome.json": '{"decision": "inconclusive"}\n',
        "docs/experiment-005.md": "Historical design\n",
        "README.md": "Maintained entry point\n",
        ".gitignore": "results/**/*.jsonl\n*.pyc\n",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    _git(tmp_path, "add", ".")
    _git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Fixture snapshot",
    )
    commit = _git(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "tag", "v0.1.0")
    return tmp_path, commit


def _check(snapshot: tuple[Path, str]) -> dict:
    return preservation.check_preservation(snapshot[0], release_commit=snapshot[1])


def test_release_scientific_bytes_are_preserved() -> None:
    report = preservation.check_preservation(ROOT)
    assert report["passed"], report
    assert report["scientific_validity_assessed"] is False
    assert report["protected_files_checked"] == 574


def test_preservation_is_read_only_and_allows_maintained_text(snapshot) -> None:
    root, _ = snapshot
    (root / "README.md").write_text("New navigation text\n")
    before = _git(root, "status", "--porcelain")
    report = _check(snapshot)
    assert report["passed"], report
    assert _git(root, "status", "--porcelain") == before
    assert (root / "README.md").read_text() == "New navigation text\n"


@pytest.mark.parametrize("change", ["modify", "delete", "mode", "symlink"])
def test_protected_file_changes_fail_closed(snapshot, change) -> None:
    root, _ = snapshot
    path = root / "src/controller.py"
    if change == "modify":
        path.write_text("value = 2\n")
    elif change == "delete":
        path.unlink()
    elif change == "mode":
        path.chmod(0o755)
    else:
        path.unlink()
        path.symlink_to(root / "README.md")
    assert _check(snapshot)["passed"] is False


@pytest.mark.parametrize(
    "name",
    [
        "results/new/campaign.jsonl",
        "experiments/006/config.json",
        "docs/experiment-006.md",
        "tests/test_experiment_006.py",
        "src/new.py",
    ],
)
def test_new_scientific_paths_including_ignored_outputs_fail(snapshot, name) -> None:
    root, _ = snapshot
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("new\n")
    report = _check(snapshot)
    assert report["passed"] is False
    assert f"new_scientific_path:{name}" in report["errors"]


def test_installed_build_metadata_and_bytecode_do_not_count_as_scientific_data(snapshot) -> None:
    root, _ = snapshot
    for name in ("src/kri_space_autonomy_lab.egg-info/PKG-INFO", "src/__pycache__/x.pyc"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"temporary installation product")
    assert _check(snapshot)["passed"] is True


def test_symlinked_scientific_directory_fails_without_rewriting(snapshot) -> None:
    root, _ = snapshot
    original = root / "src"
    original.rename(root / "saved-src")
    original.symlink_to(root / "saved-src", target_is_directory=True)
    assert _check(snapshot)["passed"] is False
    assert original.is_symlink()


def test_missing_release_tag_fails_without_creating_one(snapshot) -> None:
    root, _ = snapshot
    _git(root, "tag", "-d", "v0.1.0")
    assert _check(snapshot)["passed"] is False
    assert _git(root, "tag", "--list") == ""


def test_moved_release_tag_fails(snapshot) -> None:
    root, _ = snapshot
    (root / "README.md").write_text("Later commit\n")
    _git(root, "add", "README.md")
    _git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-qm",
        "Fixture maintenance",
    )
    _git(root, "tag", "-f", "v0.1.0")
    assert "release_tag_target_mismatch" in _check(snapshot)["errors"]


def _published_records() -> tuple[dict, dict]:
    return (
        {
            "ref": "refs/tags/v0.1.0",
            "object": {"type": "commit", "sha": release_check.RELEASE_COMMIT},
        },
        {
            "tag_name": "v0.1.0",
            "target_commitish": release_check.RELEASE_COMMIT,
            "draft": False,
            "prerelease": False,
        },
    )


def test_published_release_validation_accepts_exact_record() -> None:
    assert release_check.validate_records(*_published_records()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("tag_name", "v0.2.0"),
        ("target_commitish", "main"),
        ("draft", True),
        ("prerelease", True),
        ("draft", None),
    ],
)
def test_release_identity_or_status_drift_is_rejected(field, value) -> None:
    tag, release = _published_records()
    release[field] = value
    assert release_check.validate_records(tag, release)


def test_remote_verifier_uses_only_two_read_endpoints(monkeypatch, capsys) -> None:
    tag, release = _published_records()
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command, 0, json.dumps(tag if len(commands) == 1 else release)
        )

    monkeypatch.setattr(release_check.subprocess, "run", fake_run)
    assert release_check.main() == 0
    assert json.loads(capsys.readouterr().out)["read_only"] is True
    assert commands == [
        ["gh", "api", "repos/kri-research/space-autonomy-lab/git/ref/tags/v0.1.0"],
        ["gh", "api", "repos/kri-research/space-autonomy-lab/releases/tags/v0.1.0"],
    ]


def test_remote_error_has_no_release_creation_fallback(monkeypatch, capsys) -> None:
    calls = []

    def fail(endpoint):
        calls.append(endpoint)
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(release_check, "_read_record", fail)
    assert release_check.main() == 1
    assert len(calls) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False


def test_malformed_remote_record_is_rejected() -> None:
    assert release_check.validate_records([], {}) == ["invalid_metadata_shape"]


def test_maintained_check_runner_never_dispatches_a_historical_campaign(monkeypatch) -> None:
    runner = _load("run_post_release_checks")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    assert runner.main() == 0
    forbidden = {"execute", "freeze", "run", "analyze", "materialize-seeds"}
    assert all(not forbidden.intersection(command) for command in commands)
    test_command = next(c for c in commands if "pytest" in c)
    assert "tests/test_fault_suite.py" in test_command
    assert "tests/test_navigation_profiles.py" in test_command
    assert commands[0][1] == commands[-1][1] == "tools/check_release_preservation.py"


def test_maintained_check_runner_stops_on_failed_preservation(monkeypatch) -> None:
    runner = _load("run_post_release_checks")
    commands = []

    def fail(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(runner.subprocess, "run", fail)
    assert runner.main() == 1
    assert len(commands) == 1
