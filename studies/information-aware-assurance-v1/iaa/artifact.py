"""Bounded fixture runner and strict source-bound deterministic artifact checks."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .fixtures import fixtures
from .runtime import run
from .types import encode, primitive

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def bad(value):
        raise ValueError("Nonfinite JSON constant")

    return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=bad)


def source_paths():
    return sorted(
        [p.relative_to(ROOT).as_posix() for d in ["iaa", "tests"] for p in (ROOT / d).rglob("*.py")]
        + [
            ".python-version",
            "pyproject.toml",
            "requirements-dev.txt",
            "engineering-protocol.json",
            "CONTRACT.md",
            "source-map.json",
        ]
    )


def source_state():
    commit = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        [
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain",
            "--",
            ROOT.relative_to(REPOSITORY).as_posix(),
        ],
        text=True,
    )
    if dirty:
        raise ValueError("Commit the new stage sources before recording an artifact")
    return {"commit": commit, "files": {name: sha(ROOT / name) for name in source_paths()}}


def expected_names():
    return {"summary.json", *[f.name + ".jsonl" for f in fixtures()]}


def run_set(output):
    output = output.expanduser().resolve()
    if output.is_relative_to(REPOSITORY):
        raise ValueError("Run outside the Git checkout; preserve existing evidence")
    source = source_state()
    if output.exists():
        raise FileExistsError("Never overwrite an existing fixture attempt")
    output.mkdir(parents=True)
    rows = []
    for fixture in fixtures():
        summary, records = run(fixture)
        (output / (fixture.name + ".jsonl")).write_text("".join(encode(r) + "\n" for r in records))
        rows.append(summary)
        print(
            fixture.name, summary["scheduled_decisions"], summary["protection_gap_ms"], flush=True
        )
    (output / "summary.json").write_text(encode(rows) + "\n")
    manifest = {
        "schema": "iaa-engineering-artifact/1",
        "source": source,
        "evidence_class": "engineering_fixtures_not_comparative_research",
        "python": sys.version.split()[0],
        "files": {
            name: {"sha256": sha(output / name), "bytes": (output / name).stat().st_size}
            for name in sorted(expected_names())
        },
    }
    (output / "manifest.json").write_text(encode(manifest) + "\n")
    return manifest


def verify(directory, replay=False):
    directory = directory.resolve()
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("Artifact manifest must be a regular file")
    # Trust the chosen checkout's committed record identity, not a co-edited manifest.
    anchor_path = (ROOT / "recorded/manifest.json").relative_to(REPOSITORY).as_posix()
    anchored = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(REPOSITORY), "show", "HEAD:" + anchor_path]
    )
    if hashlib.sha256(anchored).hexdigest() != sha(manifest_path):
        raise ValueError("Manifest differs from committed published fixture record")
    manifest = read_json(manifest_path)
    if manifest["schema"] != "iaa-engineering-artifact/1":
        raise ValueError("Wrong artifact schema")
    names = expected_names()
    if set(manifest["files"]) != names or {p.name for p in directory.iterdir()} != names | {
        "manifest.json"
    }:
        raise ValueError("Incomplete or extra artifact files")
    for name, spec in manifest["files"].items():
        p = directory / name
        if (
            p.is_symlink()
            or not p.is_file()
            or p.stat().st_size != spec["bytes"]
            or sha(p) != spec["sha256"]
        ):
            raise ValueError("Artifact content mismatch: " + name)
    source = manifest["source"]
    if set(source["files"]) != set(source_paths()):
        raise ValueError("Incomplete source binding")
    commit = source["commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Invalid source commit")
    for name, digest in source["files"].items():
        path = ROOT / name
        if path.is_symlink() or sha(path) != digest:
            raise ValueError("Current source differs: " + name)
        rel = path.relative_to(REPOSITORY).as_posix()
        raw = subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(REPOSITORY), "show", commit + ":" + rel]
        )
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Source not bound to actual Git blob: " + name)
    summary = read_json(directory / "summary.json")
    if [r["fixture"] for r in summary] != [f.name for f in fixtures()]:
        raise ValueError("Wrong fixture population/order")
    if replay:
        for fixture, expected in zip(fixtures(), summary, strict=True):
            row, events = run(fixture)
            if primitive(row) != expected:
                raise ValueError("Summary replay mismatch: " + fixture.name)
            actual = "".join(encode(r) + "\n" for r in events)
            if actual != (directory / (fixture.name + ".jsonl")).read_text():
                raise ValueError("Trace replay mismatch: " + fixture.name)
    return {
        "passed": True,
        "fixtures": len(summary),
        "replayed": replay,
        "source_commit": commit,
        "physical_validation": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    s = p.add_subparsers(dest="action", required=True)
    r = s.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    v = s.add_parser("verify")
    v.add_argument("directory", type=Path)
    v.add_argument("--replay", action="store_true")
    args = p.parse_args()
    try:
        result = (
            run_set(args.output) if args.action == "run" else verify(args.directory, args.replay)
        )
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    print(encode(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
