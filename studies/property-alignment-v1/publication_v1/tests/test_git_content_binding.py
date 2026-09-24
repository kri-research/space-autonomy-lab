"""Real Git mutation regressions for the active publication verifier."""

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest
from publication_v1 import audit
from publication_v1.git_binding import (
    BindingError,
    MANIFEST_SCHEMA,
    strict_json,
    verify_commit_content,
)


def git(repo, *args, input_bytes=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.check_output(
        [
            "git",
            "-c",
            "user.name=Binding fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repo),
            *args,
        ],
        input=input_bytes,
        env=env,
        stderr=subprocess.DEVNULL,
    )


def commit(repo):
    git(repo, "add", "--all")
    git(repo, "commit", "-qm", "Fixture content")
    return git(repo, "rev-parse", "HEAD").decode().strip()


def manifest(repo, anchor):
    files = {}
    for row in git(repo, "ls-tree", "-r", "-z", anchor).split(b"\0"):
        if not row:
            continue
        metadata, raw = row.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        if kind == b"blob":
            content = git(repo, "cat-file", "blob", oid.decode())
            files[os.fsdecode(raw)] = {
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        else:
            files[os.fsdecode(raw)] = {"bytes": 0, "sha256": "0" * 64}
    return {"schema": MANIFEST_SCHEMA, "scientific_source_commit": anchor, "files": files}


@pytest.fixture
def tree(tmp_path, monkeypatch):
    repo = tmp_path / "repository"
    repo.mkdir()
    git(repo, "init", "-q")
    (repo / "file.txt").write_bytes(b"original\n")
    (repo / "nested").mkdir()
    (repo / "nested/data.bin").write_bytes(b"\0\xff\t\n")
    anchor = commit(repo)
    # Test-only trusted configuration. A manifest never controls this value.
    monkeypatch.setattr(audit, "SCIENTIFIC_SOURCE_COMMIT", anchor)
    return repo, anchor, manifest(repo, anchor)


def active(tree, doc=None):
    repo, anchor, original = tree
    return audit.verify_manifest(original if doc is None else doc, repository=repo)


def update_digest(doc, name, data):
    doc["files"][name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_unchanged_active_path_checks_bytes_and_modes(tree):
    result = active(tree)
    assert result["passed"] and result["files"] == 2 and result["bytes"] == 13
    assert result["verification_version"] == "sal-git-content-binding/2"
    assert result["git_modes"] == {"100644": 2}


@pytest.mark.parametrize("same_length", [False, True])
@pytest.mark.parametrize("edit_manifest", [False, True])
def test_file_edits_including_coordinated_manifest_edits_fail(tree, same_length, edit_manifest):
    repo, anchor, doc = tree
    data = b"tampered\n" if same_length else b"changed length\n"
    (repo / "file.txt").write_bytes(data)
    if edit_manifest:
        update_digest(doc, "file.txt", data)
    with pytest.raises(BindingError, match="Git blob"):
        active(tree, doc)


def test_coordinated_edit_staged_into_current_index_still_fails(tree):
    repo, anchor, doc = tree
    data = b"tampered\n"
    (repo / "file.txt").write_bytes(data)
    git(repo, "add", "file.txt")
    update_digest(doc, "file.txt", data)
    with pytest.raises(BindingError):
        active(tree)


@pytest.mark.parametrize(
    "damage",
    ["missing_file", "missing_entry", "extra_entry", "missing_parent", "directory_instead"],
)
def test_membership_failures(tree, damage):
    repo, anchor, doc = tree
    if damage == "missing_file":
        (repo / "file.txt").unlink()
    elif damage == "missing_entry":
        del doc["files"]["file.txt"]
    elif damage == "extra_entry":
        doc["files"]["extra"] = {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    elif damage == "missing_parent":
        shutil.rmtree(repo / "nested")
    else:
        (repo / "file.txt").unlink()
        (repo / "file.txt").mkdir()
    with pytest.raises(BindingError):
        active(tree)


@pytest.mark.parametrize(
    "value", [{}, [], False, 0, "bad", {"schema": MANIFEST_SCHEMA}, {"files": {}}]
)
def test_explicit_empty_or_malformed_document_never_loads_default(tree, value):
    with pytest.raises(BindingError):
        active(tree, value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("bytes", True),
        ("bytes", -1),
        ("bytes", 9.0),
        ("bytes", "9"),
        ("sha256", None),
        ("sha256", "g" * 64),
        ("sha256", "0" * 63),
    ],
)
def test_malformed_entry_metadata(tree, field, value):
    doc = tree[2]
    doc["files"]["file.txt"][field] = value
    with pytest.raises(BindingError):
        active(tree)


@pytest.mark.parametrize(
    "value", [[], None, False, {"bytes": 9}, {"bytes": 9, "sha256": "0" * 64, "mode": "100644"}]
)
def test_malformed_entry_shapes(tree, value):
    tree[2]["files"]["file.txt"] = value
    with pytest.raises(BindingError):
        active(tree)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "/absolute",
        "../escape",
        "a/../b",
        "./file.txt",
        "nested//data.bin",
        "trailing/",
        "bad\0name",
        ".git/config",
        "a/.GIT/b",
    ],
)
def test_noncanonical_names_rejected(tree, name):
    doc = tree[2]
    doc["files"][name] = doc["files"].pop("file.txt")
    with pytest.raises(BindingError):
        active(tree)


@pytest.mark.parametrize("anchor", ["0" * 40, "HEAD", "main", "b2ff0cc", "f" * 64, None, True])
def test_manifest_cannot_select_its_own_trust_anchor(tree, anchor):
    tree[2]["scientific_source_commit"] = anchor
    with pytest.raises(BindingError, match="anchor"):
        active(tree)


def test_missing_commit_fails(tree):
    repo, anchor, doc = tree
    doc["scientific_source_commit"] = "0" * 40
    with pytest.raises(BindingError):
        verify_commit_content(doc, repo, expected_commit="0" * 40)


def test_manifest_hash_or_size_must_match_git_content(tree):
    doc = tree[2]
    doc["files"]["file.txt"]["sha256"] = "0" * 64
    with pytest.raises(BindingError, match="Manifest differs"):
        active(tree)


def test_mode_change_detected_even_when_git_core_filemode_is_false(tree):
    repo, anchor, doc = tree
    git(repo, "config", "core.filemode", "false")
    (repo / "file.txt").chmod(0o755)
    with pytest.raises(BindingError, match="mode"):
        active(tree)


def test_owner_executable_mapping_and_group_permissions(tree, monkeypatch):
    repo, anchor, doc = tree
    (repo / "file.txt").chmod(0o755)
    anchor = commit(repo)
    monkeypatch.setattr(audit, "SCIENTIFIC_SOURCE_COMMIT", anchor)
    doc = manifest(repo, anchor)
    assert audit.verify_manifest(doc, repo)["git_modes"]["100755"] == 1
    (repo / "file.txt").chmod(0o655)
    with pytest.raises(BindingError, match="mode"):
        audit.verify_manifest(doc, repo)
    (repo / "file.txt").chmod(0o700)
    assert audit.verify_manifest(doc, repo)["passed"]


def test_expected_symlink_compares_literal_target_not_target_contents(tree, monkeypatch):
    repo, anchor, doc = tree
    (repo / "link").symlink_to("../absent-target")
    anchor = commit(repo)
    monkeypatch.setattr(audit, "SCIENTIFIC_SOURCE_COMMIT", anchor)
    doc = manifest(repo, anchor)
    assert audit.verify_manifest(doc, repo)["git_modes"]["120000"] == 1
    (repo / "link").unlink()
    (repo / "link").symlink_to("../different")
    update_digest(doc, "link", b"../different")
    with pytest.raises(BindingError, match="Git blob"):
        audit.verify_manifest(doc, repo)


def test_expected_symlink_replaced_with_same_bytes_regular_file_fails(tree, monkeypatch):
    repo, anchor, doc = tree
    (repo / "link").symlink_to("file.txt")
    anchor = commit(repo)
    monkeypatch.setattr(audit, "SCIENTIFIC_SOURCE_COMMIT", anchor)
    doc = manifest(repo, anchor)
    (repo / "link").unlink()
    (repo / "link").write_bytes(b"file.txt")
    with pytest.raises(BindingError, match="symbolic link"):
        audit.verify_manifest(doc, repo)


def test_unexpected_leaf_symlink_rejected_despite_identical_target_bytes(tree):
    repo, anchor, doc = tree
    outside = repo.parent / "same.bin"
    outside.write_bytes((repo / "file.txt").read_bytes())
    (repo / "file.txt").unlink()
    (repo / "file.txt").symlink_to(outside)
    with pytest.raises(BindingError):
        active(tree)


def test_parent_symlink_cannot_escape_checkout(tree):
    repo, anchor, doc = tree
    outside = repo.parent / "outside"
    (repo / "nested").rename(outside)
    (repo / "nested").symlink_to(outside, target_is_directory=True)
    with pytest.raises(BindingError, match="unsafe"):
        active(tree)


def test_fifo_is_not_opened_as_a_regular_file(tree):
    repo, anchor, doc = tree
    (repo / "file.txt").unlink()
    os.mkfifo(repo / "file.txt")
    with pytest.raises(BindingError, match="ordinary file"):
        active(tree)


def test_submodule_gitlink_is_explicitly_unsupported(tree, monkeypatch):
    repo, anchor, doc = tree
    git(repo, "update-index", "--add", "--cacheinfo", "160000," + anchor + ",submodule")
    git(repo, "commit", "-qm", "Gitlink fixture")
    anchor = git(repo, "rev-parse", "HEAD").decode().strip()
    monkeypatch.setattr(audit, "SCIENTIFIC_SOURCE_COMMIT", anchor)
    with pytest.raises(BindingError, match="Unsupported Git object"):
        audit.verify_manifest(manifest(repo, anchor), repo)


@pytest.mark.parametrize(
    "name",
    [
        "with space",
        "tab\tname",
        "new\nline",
        'quote"name',
        "-option",
        "back\\slash",
        "colon:name",
        "accent-é",
    ],
)
def test_nul_tree_handles_unusual_legal_names(tree, name, monkeypatch):
    repo, anchor, doc = tree
    (repo / name).write_bytes(b"unusual\0bytes")
    anchor = commit(repo)
    monkeypatch.setattr(audit, "SCIENTIFIC_SOURCE_COMMIT", anchor)
    assert audit.verify_manifest(manifest(repo, anchor), repo)["files"] == 3


def test_missing_blob_does_not_pass_from_tree_id_alone(tree):
    repo, anchor, doc = tree
    oid = git(repo, "rev-parse", anchor + ":file.txt").decode().strip()
    (repo / ".git/objects" / oid[:2] / oid[2:]).unlink()
    with pytest.raises(BindingError, match="blob"):
        active(tree)


@pytest.mark.parametrize("kind", ["blob", "commit"])
def test_replacement_objects_cannot_redefine_scientific_content(tree, kind):
    repo, anchor, doc = tree
    old = git(repo, "rev-parse", anchor + ":file.txt").decode().strip()
    changed = b"tampered\n"
    new = git(repo, "hash-object", "-w", "--stdin", input_bytes=changed).decode().strip()
    if kind == "blob":
        git(repo, "replace", old, new)
    else:
        (repo / "file.txt").write_bytes(changed)
        replacement = commit(repo)
        git(repo, "replace", anchor, replacement)
        (repo / "file.txt").write_bytes(b"original\n")
    assert active(tree)["passed"]
    (repo / "file.txt").write_bytes(changed)
    update_digest(doc, "file.txt", changed)
    with pytest.raises(BindingError, match="Git blob"):
        active(tree)


def test_ambient_git_dir_and_index_cannot_redirect_verification(tree, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/nonexistent-fixture-git")
    monkeypatch.setenv("GIT_WORK_TREE", "/nonexistent-fixture-worktree")
    monkeypatch.setenv("GIT_INDEX_FILE", "/nonexistent-fixture-index")
    assert active(tree)["passed"]


def test_untracked_additions_are_explicitly_outside_historical_inventory(tree):
    (tree[0] / "new-research.txt").write_bytes(b"not certified")
    assert active(tree)["extra_working_paths"].startswith("Outside")


def test_sha256_git_objects(tmp_path):
    repo = tmp_path / "sha256-repository"
    repo.mkdir()
    git(repo, "init", "-q", "--object-format=sha256")
    (repo / "sample").write_bytes(b"sha256 Git fixture\n")
    anchor = commit(repo)
    result = verify_commit_content(manifest(repo, anchor), repo, expected_commit=anchor)
    assert result["git_object_format"] == "sha256" and result["passed"]


@pytest.mark.parametrize("raw", ['{"files":{},"files":{}}', '{"x":NaN}', '{"x":Infinity}', '{"x":'])
def test_strict_manifest_json(raw):
    with pytest.raises(ValueError):
        strict_json(raw)


def test_actual_public_cli_rejects_coordinated_mutation(tmp_path):
    repo = tmp_path / "real-anchor"
    git(audit.REPO, "clone", "--shared", "--no-checkout", str(audit.REPO), str(repo))
    git(repo, "checkout", "--detach", "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8")
    package = repo / "studies/property-alignment-v1/publication_v1"
    shutil.copytree(audit.ROOT, package, ignore=shutil.ignore_patterns("__pycache__"))
    doc = json.loads((package / "evidence_manifest.json").read_text())
    data = (repo / "README.md").read_bytes()
    changed = bytes([data[0] ^ 1]) + data[1:]
    (repo / "README.md").write_bytes(changed)
    update_digest(doc, "README.md", changed)
    (package / "evidence_manifest.json").write_text(json.dumps(doc))
    env = {**os.environ, "PYTHONPATH": str(package.parent), "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run(
        [sys.executable, "-m", "publication_v1.audit"],
        cwd=package.parent,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert run.returncode == 2
    reply = json.loads(run.stdout)
    assert reply["passed"] is False and "Git blob" in reply["error"]
