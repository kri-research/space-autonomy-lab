"""Version 2 commit-content binding, independent of caller-supplied digests.

The trusted entry point supplies the permitted full commit identity. Git object
IDs are computed over the literal working bytes, without filters or the index.
POSIX descriptor-relative, no-follow opens keep parent links out of the walk.
A stable checkout, trusted Python/Git implementation and collision resistance
remain assumptions; this is content verification, not scientific authentication.
"""

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

VERSION = "sal-git-content-binding/2"
MANIFEST_SCHEMA = "sal-scientific-publication-inputs/1"
CHUNK = 1024 * 1024


class BindingError(ValueError):
    """The requested content binding could not be established."""


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BindingError("Duplicate JSON field: " + repr(key))
            result[key] = value
        return result

    def bad(value):
        raise BindingError("Nonfinite JSON value: " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def _git(repository, *args, input_bytes=None):
    # A caller's GIT_DIR/index/alternate-object/config environment must not route
    # inspection to another repository. Repository-local object stores remain
    # subject to the trusted full commit and object content hashes.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_NO_LAZY_FETCH="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_OPTIONAL_LOCKS="0",
        LC_ALL="C",
    )
    try:
        run = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repository), *args],
            input=input_bytes,
            capture_output=True,
            env=env,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BindingError("Git inspection unavailable") from exc
    if run.returncode:
        raise BindingError("Git inspection failed: " + args[0])
    return run.stdout


def _object_id(data, kind, algorithm):
    return hashlib.new(algorithm, kind + b" " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _name(name):
    if type(name) is not str or not name or "\0" in name:
        raise BindingError("Invalid manifest path")
    parts = name.split("/")
    if any(p in ("", ".", "..") or p.casefold() == ".git" for p in parts):
        raise BindingError("Noncanonical or reserved path: " + repr(name))
    try:
        if os.fsdecode(os.fsencode(name)) != name:
            raise BindingError("Non-roundtrippable path")
    except UnicodeError as exc:
        raise BindingError("Unrepresentable path") from exc
    return parts


@dataclass(frozen=True)
class Entry:
    name: str
    mode: str
    oid: str
    size: int


def _trusted_tree(repository, expected_commit):
    algorithm = _git(repository, "rev-parse", "--show-object-format").strip().decode("ascii")
    if algorithm not in ("sha1", "sha256"):
        raise BindingError("Unsupported Git object format")
    length = hashlib.new(algorithm).digest_size * 2
    if type(expected_commit) is not str or not re.fullmatch(
        "[0-9a-f]{%d}" % length, expected_commit
    ):
        raise BindingError("A trusted full commit object ID is required")
    if _git(repository, "cat-file", "-t", expected_commit).strip() != b"commit":
        raise BindingError("Trusted anchor is not a commit object")
    commit_bytes = _git(repository, "cat-file", "commit", expected_commit)
    if _object_id(commit_bytes, b"commit", algorithm) != expected_commit:
        raise BindingError("Commit object content hash differs")
    tree = _git(repository, "ls-tree", "-r", "-z", "--full-tree", expected_commit)
    if not tree or not tree.endswith(b"\0"):
        raise BindingError("Empty or malformed trusted tree")
    rows = {}
    for raw in tree[:-1].split(b"\0"):
        try:
            metadata, raw_name = raw.split(b"\t", 1)
            mode, kind, oid = metadata.split()
            name = os.fsdecode(raw_name)
            _name(name)
            mode, oid = mode.decode("ascii"), oid.decode("ascii")
        except (ValueError, UnicodeError) as exc:
            raise BindingError("Malformed Git tree entry") from exc
        if name in rows:
            raise BindingError("Duplicate trusted path")
        if kind != b"blob" or mode not in ("100644", "100755", "120000"):
            raise BindingError("Unsupported Git object type/mode at " + repr(name))
        if not re.fullmatch("[0-9a-f]{%d}" % length, oid):
            raise BindingError("Malformed Git blob identity")
        rows[name] = (mode, oid)
    # Independently demand every blob be available, with its actual Git type
    # and size. Batch-check uses object IDs only, never names or manifest data.
    ids = sorted({oid for mode, oid in rows.values()})
    sizes = {}
    for start in range(0, len(ids), 256):
        group = ids[start : start + 256]
        response = _git(
            repository, "cat-file", "--batch-check", input_bytes=("\n".join(group) + "\n").encode()
        )
        lines = response.splitlines()
        if len(lines) != len(group):
            raise BindingError("Incomplete Git object inspection")
        for oid, line in zip(group, lines, strict=True):
            fields = line.split()
            if (
                len(fields) != 3
                or fields[0] != oid.encode()
                or fields[1] != b"blob"
                or not fields[2].isdigit()
            ):
                raise BindingError("Missing or invalid Git blob: " + oid)
            sizes[oid] = int(fields[2])
    return algorithm, [Entry(n, mode, oid, sizes[oid]) for n, (mode, oid) in rows.items()]


def _platform_check():
    if os.name != "posix" or not all(
        hasattr(os, n) for n in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK")
    ):
        raise BindingError("Full mode/no-follow verification requires a supported POSIX host")
    if not all(fn in os.supports_dir_fd for fn in (os.open, os.stat, os.readlink)):
        raise BindingError("Descriptor-relative file inspection unavailable")


@contextmanager
def _parent(root_fd, parts):
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _working_content(root_fd, entry, algorithm):
    parts = _name(entry.name)
    with _parent(root_fd, parts) as fd:
        name = parts[-1]
        before = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if entry.mode == "120000":
            if not stat.S_ISLNK(before.st_mode):
                raise BindingError("Expected literal symbolic link: " + repr(entry.name))
            data = os.readlink(os.fsencode(name), dir_fd=fd)
            after = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if (before.st_ino, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise BindingError("Link changed during inspection")
            return len(data), hashlib.sha256(data).hexdigest(), _object_id(data, b"blob", algorithm)
        if not stat.S_ISREG(before.st_mode):
            raise BindingError("Expected ordinary file: " + repr(entry.name))
        raw_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(raw_fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise BindingError("File type/identity changed during inspection")
            # Git records the owner-executable bit, not group/other permissions.
            if bool(opened.st_mode & stat.S_IXUSR) != (entry.mode == "100755"):
                raise BindingError("Git executable mode differs: " + repr(entry.name))
            if opened.st_size != entry.size:
                raise BindingError("Working size differs from Git blob: " + repr(entry.name))
            oid = hashlib.new(algorithm, b"blob " + str(entry.size).encode() + b"\0")
            sha = hashlib.sha256()
            count = 0
            while True:
                block = stream.read(CHUNK)
                if not block:
                    break
                count += len(block)
                if count > entry.size:
                    raise BindingError("File grew during inspection")
                oid.update(block)
                sha.update(block)
            after = os.fstat(stream.fileno())
            attributes = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
            if (
                any(getattr(opened, x) != getattr(after, x) for x in attributes)
                or count != entry.size
            ):
                raise BindingError("File changed during inspection")
            return count, sha.hexdigest(), oid.hexdigest()


def verify_commit_content(document, repository, *, expected_commit):
    """expected_commit is trusted caller configuration, never taken from document.

    Added post-snapshot repository paths are intentionally outside this inventory.
    Every entry of the anchored tree must occur exactly once in the manifest.
    """
    if type(document) is not dict or document.get("schema") != MANIFEST_SCHEMA:
        raise BindingError("Invalid scientific manifest schema")
    if document.get("scientific_source_commit") != expected_commit:
        raise BindingError("Wrong scientific source anchor")
    allowed = {
        "schema",
        "files",
        "scientific_source_commit",
        "historical_source_commit",
        "release_commit",
        "release_tag",
        "scope",
    }
    if set(document) - allowed:
        raise BindingError("Unsupported scientific manifest fields")
    files = document.get("files")
    if type(files) is not dict or not files:
        raise BindingError("Empty or invalid scientific inventory")
    for name, item in files.items():
        _name(name)
        if type(item) is not dict or set(item) != {"bytes", "sha256"}:
            raise BindingError("Malformed entry: " + repr(name))
        if type(item["bytes"]) is not int or item["bytes"] < 0:
            raise BindingError("Invalid byte count")
        if type(item["sha256"]) is not str or not re.fullmatch("[0-9a-f]{64}", item["sha256"]):
            raise BindingError("Invalid SHA-256 digest")
    _platform_check()
    repository = Path(repository).resolve(strict=True)
    top = os.fsdecode(_git(repository, "rev-parse", "--show-toplevel").rstrip(b"\n"))
    if Path(top).resolve(strict=True) != repository:
        raise BindingError("Repository root required")
    algorithm, entries = _trusted_tree(repository, expected_commit)
    if {x.name for x in entries} != set(files):
        raise BindingError("Prior-commit inventory is incomplete or has extra entries")
    total = 0
    modes = Counter()
    root_fd = os.open(repository, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for entry in entries:
            try:
                size, sha, oid = _working_content(root_fd, entry, algorithm)
            except OSError as exc:
                raise BindingError("Missing or unsafe working path: " + repr(entry.name)) from exc
            if size != entry.size or oid != entry.oid:
                raise BindingError("Working bytes differ from pinned Git blob: " + repr(entry.name))
            # These values now describe bytes independently bound to Git, not
            # merely agreement between two attacker-controlled representations.
            if files[entry.name] != {"bytes": size, "sha256": sha}:
                raise BindingError("Manifest differs from Git-bound content: " + repr(entry.name))
            total += size
            modes[entry.mode] += 1
    finally:
        os.close(root_fd)
    return {
        "verification_version": VERSION,
        "passed": True,
        "scientific_source_commit": expected_commit,
        "files": len(entries),
        "bytes": total,
        "git_object_format": algorithm,
        "git_modes": dict(sorted(modes.items())),
        "mismatches": 0,
        "access_failures": 0,
        "git_replacement_objects": "disabled",
        "scope": "Pinned tracked bytes, blob availability and Git modes; no scientific validity or custody claim",
        "platform_scope": "POSIX owner-executable bit and literal symlink bytes; no full permission audit",
        "extra_working_paths": "Outside the pinned inventory; not certified by this check",
    }
