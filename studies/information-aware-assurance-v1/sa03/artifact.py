"""Immutable-source record and replay of bounded SA03 development only."""

import argparse
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

from iaa.artifact import read_json
from iaa.types import encode, primitive

from .development import cases, run
from .policy import METHODS
from .scalar import examples

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RECORD = ROOT / "sa03/recorded_causal"


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(REPO), *args])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths():
    return sorted(
        [
            p.relative_to(ROOT).as_posix()
            for directory in ("iaa", "sa02", "sa03", "sa03_tests")
            for p in (ROOT / directory).glob("*.py")
        ]
        + [
            ".python-version",
            "pyproject.toml",
            "requirements-dev.txt",
            "sa03/MATHEMATICS.md",
            "sa03/protocol.json",
            "sa03/source-map.json",
        ]
    )


def source_state():
    if git("status", "--porcelain", "--", ROOT.relative_to(REPO).as_posix()).strip():
        raise ValueError("Commit stage sources before recording")
    commit = git("rev-parse", "HEAD").decode().strip()
    result = {}
    for name in source_paths():
        path = ROOT / name
        rel = path.relative_to(REPO).as_posix()
        raw = git("show", commit + ":" + rel)
        tree = git("ls-tree", commit, "--", rel).decode().split()
        if path.is_symlink() or raw != path.read_bytes():
            raise ValueError("Source differs from actual Git blob")
        result[name] = dict(sha256=sha(path), mode=tree[0], blob=tree[2])
    return dict(commit=commit, files=result)


def names():
    return {"inputs.json", "summary.json", "analytical.json", "host-timings.json"} | {
        c.name + "--" + method + ".json" for c in cases() for method in METHODS
    }


def record(output):
    output = output.expanduser().resolve()
    if output.exists() or output.is_relative_to(REPO):
        raise ValueError("New external output directory required")
    if sys.version.split()[0] != "3.13.5":
        raise ValueError("CPython 3.13.5 required for the declared record")
    source = source_state()
    output.mkdir(parents=True)
    (output / "inputs.json").write_text(encode(dict(cases=cases(), methods=METHODS)) + "\n")
    rows = []
    timings = []
    try:
        for case in cases():
            for method in METHODS:
                result, evidence, timing = run(case, method)
                (output / (case.name + "--" + method + ".json")).write_text(encode(evidence) + "\n")
                rows.append(result)
                timings.append(timing)
                print(
                    case.name,
                    method,
                    result["policy_status"],
                    result["requested_channel"],
                    result["all_reading_useful"],
                    flush=True,
                )
    except Exception as exc:
        (output / "failed-attempt.json").write_text(
            encode(
                dict(completed=len(rows), error=type(exc).__name__ + ":" + str(exc), source=source)
            )
            + "\n"
        )
        raise
    (output / "summary.json").write_text(encode(rows) + "\n")
    (output / "analytical.json").write_text(encode(examples()) + "\n")
    (output / "host-timings.json").write_text(
        encode(
            dict(
                os=platform.system(),
                architecture=platform.machine(),
                python=sys.version.split()[0],
                samples=timings,
                energy_measured=False,
                timing_scope="planner and complete selected-tree recheck on one host",
            )
        )
        + "\n"
    )
    manifest = dict(
        schema="iaa-sa03-record/1",
        source=source,
        files={
            n: dict(bytes=(output / n).stat().st_size, sha256=sha(output / n))
            for n in sorted(names())
        },
        evidence_class="bounded_development_not_protected_evaluation",
        hardware_validated=False,
    )
    (output / "manifest.json").write_text(encode(manifest) + "\n")
    return dict(cases=len(cases()), comparisons=len(rows), source_commit=source["commit"])


def verify(directory, replay=False):
    directory = directory.resolve()
    mp = directory / "manifest.json"
    anchor = (RECORD / "manifest.json").relative_to(REPO).as_posix()
    if mp.is_symlink() or mp.read_bytes() != git("show", "HEAD:" + anchor):
        raise ValueError("Manifest differs from committed record")
    manifest = read_json(mp)
    if manifest["schema"] != "iaa-sa03-record/1" or set(manifest["files"]) != names():
        raise ValueError("Wrong record schema or population")
    if {p.name for p in directory.iterdir()} != names() | {"manifest.json"}:
        raise ValueError("Missing or extra artifact files")
    for name, spec in manifest["files"].items():
        p = directory / name
        if (
            p.is_symlink()
            or not p.is_file()
            or p.stat().st_size != spec["bytes"]
            or sha(p) != spec["sha256"]
        ):
            raise ValueError("Changed record " + name)
    source = manifest["source"]
    commit = source["commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Malformed source identity")
    if set(source["files"]) != set(source_paths()):
        raise ValueError("Source membership mismatch")
    for name, spec in source["files"].items():
        p = ROOT / name
        rel = p.relative_to(REPO).as_posix()
        tree = git("ls-tree", commit, "--", rel).decode().split()
        if (
            p.is_symlink()
            or sha(p) != spec["sha256"]
            or hashlib.sha256(git("show", commit + ":" + rel)).hexdigest() != spec["sha256"]
            or tree[:3] != [spec["mode"], "blob", spec["blob"]]
            or bool(p.stat().st_mode & 0o111) != (spec["mode"] == "100755")
        ):
            raise ValueError("Actual source/mode Git binding failed: " + name)
    if (directory / "inputs.json").read_text() != encode(
        dict(cases=cases(), methods=METHODS)
    ) + "\n":
        raise ValueError("Inputs differ")
    expected = read_json(directory / "summary.json")
    order = [(c.name, m) for c in cases() for m in METHODS]
    if [(r["case"], r["method"]) for r in expected] != order:
        raise ValueError("Incomplete comparison accounting")
    timing = read_json(directory / "host-timings.json")["samples"]
    if [(r["case"], r["method"]) for r in timing] != order or any(
        type(r[k]) is not int or r[k] < 0
        for r in timing
        for k in ("planner_ns", "selected_tree_recheck_ns")
    ):
        raise ValueError("Timing accounting mismatch")
    if (directory / "analytical.json").read_text() != encode(examples()) + "\n":
        raise ValueError("Analytical examples differ")
    if replay:
        for (case, method), row in zip(
            ((c, m) for c in cases() for m in METHODS), expected, strict=True
        ):
            actual, evidence, _ = run(case, method)
            if (
                primitive(actual) != row
                or (directory / (case.name + "--" + method + ".json")).read_text()
                != encode(evidence) + "\n"
            ):
                raise ValueError("Deterministic replay mismatch " + case.name + " " + method)
    return dict(
        passed=True,
        cases=len(cases()),
        comparisons=len(order),
        replayed=replay,
        source_commit=commit,
        real_time_feasibility=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("directory", type=Path)
    v.add_argument("--replay", action="store_true")
    args = p.parse_args()
    try:
        result = (
            record(args.output) if args.action == "run" else verify(args.directory, args.replay)
        )
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        ArithmeticError,
        subprocess.CalledProcessError,
    ) as exc:
        print(type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        return 1
    print(encode(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
