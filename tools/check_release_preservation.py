"""Check preservation against the published snapshot without running scientific code."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
from pathlib import Path

RELEASE_COMMIT = "f0e9e5d8c140ca3d5eea71cee97fd29f23bffe12"
RELEASE_TAG = "v0.1.0"
# These maintained surfaces are reviewed separately from scientific snapshot bytes.
MAINTAINED_PATHS = frozenset(
    {
        "README.md",
        "CONTRIBUTING.md",
        "CITATION.cff",
        ".github/workflows/ci.yml",
        ".github/workflows/release-v0.1.0.yml",
        "tests/test_release_metadata.py",
    }
)
SCIENTIFIC_DIRECTORIES = (
    "src",
    "experiments",
    "results",
    "artifacts",
    "demo",
    "scenarios",
    "assessment-policies",
    "fault-suites",
    "navigation-fault-plans",
    "release",
)


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, timeout=30
    ).stdout


def _has_symlink(root: Path, relative: str) -> bool:
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            return True
    return False


def _scientific_addition(relative: str) -> bool:
    path = Path(relative)
    if relative.startswith("src/kri_space_autonomy_lab.egg-info/") and path.name in {
        "PKG-INFO",
        "SOURCES.txt",
        "dependency_links.txt",
        "entry_points.txt",
        "requires.txt",
        "top_level.txt",
    }:
        return False
    if path.parts[0] in SCIENTIFIC_DIRECTORIES:
        return "__pycache__" not in path.parts and path.suffix != ".pyc"
    return relative.startswith("docs/experiment-") or relative.startswith("tests/test_experiment_")


def check_preservation(
    root: Path, *, release_commit: str = RELEASE_COMMIT, tag: str = RELEASE_TAG
) -> dict[str, object]:
    """Return byte-preservation findings, not a historical validity or safety verdict."""
    root = root.resolve()
    errors: list[str] = []
    try:
        actual_tag = _git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
        if actual_tag.decode().strip() != release_commit:
            errors.append("release_tag_target_mismatch")
        entries = _git(root, "ls-tree", "-r", "-z", release_commit).split(b"\0")
        baseline: dict[str, tuple[str, str]] = {}
        for entry in entries:
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            relative = raw_path.decode("utf-8")
            if kind != "blob":
                errors.append(f"unsupported_baseline_object:{relative}")
            baseline[relative] = (mode, blob)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {
            "passed": False,
            "errors": [f"release_snapshot_unavailable:{type(exc).__name__}"],
            "scientific_validity_assessed": False,
        }

    protected = {p: identity for p, identity in baseline.items() if p not in MAINTAINED_PATHS}
    for relative, (mode, expected) in sorted(protected.items()):
        path = root / relative
        if _has_symlink(root, relative):
            errors.append(f"symlink_in_protected_path:{relative}")
            continue
        if not path.is_file():
            errors.append(f"missing_protected_file:{relative}")
            continue
        data = path.read_bytes()
        observed = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if observed != expected:
            errors.append(f"modified_protected_file:{relative}")
        executable = bool(path.stat().st_mode & stat.S_IXUSR)
        if mode not in {"100644", "100755"} or executable != (mode == "100755"):
            errors.append(f"modified_protected_mode:{relative}")

    # Include ignored new evidence, since blanket JSONL ignores can conceal it from git status.
    candidates: set[str] = set()
    for directory in SCIENTIFIC_DIRECTORIES:
        base = root / directory
        if base.exists():
            for path in base.rglob("*"):
                if path.is_file() or path.is_symlink():
                    candidates.add(path.relative_to(root).as_posix())
    for directory, pattern in (("docs", "experiment-*"), ("tests", "test_experiment_*")):
        candidates.update(p.relative_to(root).as_posix() for p in (root / directory).glob(pattern))
    for relative in sorted(candidates - baseline.keys()):
        if _scientific_addition(relative):
            errors.append(f"new_scientific_path:{relative}")
    return {
        "passed": not errors,
        "release_commit": release_commit,
        "release_tag": tag,
        "protected_files_checked": len(protected),
        "maintained_paths": sorted(MAINTAINED_PATHS),
        "errors": errors,
        "scientific_validity_assessed": False,
        "scope": "release byte and mode preservation only; no campaign or replay execution",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report = check_preservation(args.root)
    except (OSError, ValueError) as exc:
        report = {
            "passed": False,
            "errors": [f"inspection_failed:{type(exc).__name__}"],
            "scientific_validity_assessed": False,
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
