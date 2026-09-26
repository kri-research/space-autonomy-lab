"""Source-bound SA02 development recording and exact deterministic replay."""

import argparse
import hashlib
import platform
import subprocess
import sys
from pathlib import Path

from iaa.artifact import read_json
from iaa.types import encode, primitive

from .development import cases, evaluate, reference_cases
from .packet_fixtures import evaluate as packet_cases

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
RECORD = ROOT / "sa02/recorded"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(REPOSITORY), *args])


def source_paths():
    paths = [
        p.relative_to(ROOT).as_posix()
        for directory in ("iaa", "sa02", "sa02_tests")
        for p in (ROOT / directory).glob("*.py")
    ]
    return sorted(
        paths
        + [
            ".python-version",
            "requirements-dev.txt",
            "pyproject.toml",
            "sa02/protocol.json",
            "sa02/MATHEMATICS.md",
            "sa02/source-map.json",
        ]
    )


def source_state():
    if git("status", "--porcelain", "--", ROOT.relative_to(REPOSITORY).as_posix()).strip():
        raise ValueError("Commit stage sources before recording")
    commit = git("rev-parse", "HEAD").decode().strip()
    files = {}
    for name in source_paths():
        path = ROOT / name
        rel = path.relative_to(REPOSITORY).as_posix()
        raw = git("show", commit + ":" + rel)
        if path.is_symlink() or raw != path.read_bytes():
            raise ValueError("Source not at its claimed Git identity")
        tree = git("ls-tree", commit, "--", rel).decode().split()
        files[name] = {"sha256": sha(path), "blob": tree[2], "mode": tree[0]}
    return {"commit": commit, "files": files}


def names():
    return {
        "inputs.json",
        "summary.json",
        "comparisons.json",
        "small-reference.json",
        "packet-fixtures.json",
        "host-timings.json",
        *[f.name + ".jsonl" for f, c in cases()],
    }


def record(output):
    if sys.version.split()[0] != "3.13.5":
        raise ValueError("This evidence run requires CPython 3.13.5")
    output = output.expanduser().resolve()
    if output.exists() or output.is_relative_to(REPOSITORY):
        raise ValueError("Use a new output directory outside the checkout")
    source = source_state()
    output.mkdir(parents=True)
    (output / "inputs.json").write_text(encode(cases()) + "\n")
    summaries = []
    comparisons = []
    timings = []
    for f, c in cases():
        result, events, comparison, timing = evaluate(f, c)
        (output / (f.name + ".jsonl")).write_text("".join(encode(e) + "\n" for e in events))
        summaries.append(result)
        comparisons.append({"fixture": f.name, "decisions": comparison})
        timings.append(timing)
        print(
            f.name,
            result["update_status_counts"],
            result["nonempty_outer_exclusions_observed"],
            flush=True,
        )
    for name, data in [
        ("summary.json", summaries),
        ("comparisons.json", comparisons),
        ("small-reference.json", reference_cases()),
        ("packet-fixtures.json", packet_cases()),
    ]:
        (output / name).write_text(encode(data) + "\n")
    host = {
        "python": sys.version.split()[0],
        "os": platform.system(),
        "architecture": platform.machine(),
        "invocations": 1,
        "cases": timings,
        "hardware_energy_measured": False,
        "target_processor": False,
    }
    (output / "host-timings.json").write_text(encode(host) + "\n")
    manifest = {
        "schema": "iaa-sa02-artifact/1",
        "source": source,
        "files": {
            n: {"sha256": sha(output / n), "bytes": (output / n).stat().st_size}
            for n in sorted(names())
        },
        "timing_replay": (
            "Measured samples retained; only deterministic outputs must replay identically."
        ),
        "physical_validation": False,
    }
    (output / "manifest.json").write_text(encode(manifest) + "\n")
    return {"recorded": True, "cases": len(summaries), "source_commit": source["commit"]}


def verify(directory, replay=False):
    directory = directory.resolve()
    mp = directory / "manifest.json"
    anchor = (RECORD / "manifest.json").relative_to(REPOSITORY).as_posix()
    if mp.is_symlink() or mp.read_bytes() != git("show", "HEAD:" + anchor):
        raise ValueError("Manifest does not match selected committed record")
    manifest = read_json(mp)
    if manifest["schema"] != "iaa-sa02-artifact/1" or set(manifest["files"]) != names():
        raise ValueError("Artifact schema/membership")
    if {p.name for p in directory.iterdir()} != names() | {"manifest.json"}:
        raise ValueError("Unlisted or missing file")
    for name, spec in manifest["files"].items():
        p = directory / name
        if (
            p.is_symlink()
            or not p.is_file()
            or p.stat().st_size != spec["bytes"]
            or sha(p) != spec["sha256"]
        ):
            raise ValueError("Content mismatch: " + name)
    source = manifest["source"]
    commit = source["commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Invalid source commit")
    if set(source["files"]) != set(source_paths()):
        raise ValueError("Source membership mismatch")
    for name, spec in source["files"].items():
        p = ROOT / name
        rel = p.relative_to(REPOSITORY).as_posix()
        tree = git("ls-tree", commit, "--", rel).decode().split()
        if (
            p.is_symlink()
            or not p.is_file()
            or sha(p) != spec["sha256"]
            or hashlib.sha256(git("show", commit + ":" + rel)).hexdigest() != spec["sha256"]
            or tree[:3] != [spec["mode"], "blob", spec["blob"]]
        ):
            raise ValueError("Actual source Git binding failed: " + name)
        if bool(p.stat().st_mode & 0o111) != (spec["mode"] == "100755"):
            raise ValueError("Source executable mode mismatch")
    summaries = read_json(directory / "summary.json")
    if [r["fixture"] for r in summaries] != [f.name for f, c in cases()]:
        raise ValueError("Wrong development population")
    host = read_json(directory / "host-timings.json")
    if len(host["cases"]) != len(summaries):
        raise ValueError("Incomplete timing accounting")
    for measured, result in zip(host["cases"], summaries, strict=True):
        times = measured["observer_update_ns"]
        if (
            measured["fixture"] != result["fixture"]
            or len(times) != result["observation_updates"]
            or any(type(t) is not int or t < 0 for t in times)
        ):
            raise ValueError("Invalid timing receipt")
    if (directory / "inputs.json").read_text() != encode(cases()) + "\n":
        raise ValueError("Input binding mismatch")
    if replay:
        comparisons = []
        for (f, c), expected in zip(cases(), summaries, strict=True):
            row, events, comparison, _ = evaluate(f, c)
            if primitive(row) != expected or (
                directory / (f.name + ".jsonl")
            ).read_text() != "".join(encode(e) + "\n" for e in events):
                raise ValueError("Deterministic replay mismatch: " + f.name)
            comparisons.append({"fixture": f.name, "decisions": comparison})
        for name, data in [
            ("comparisons.json", comparisons),
            ("small-reference.json", reference_cases()),
            ("packet-fixtures.json", packet_cases()),
        ]:
            if (directory / name).read_text() != encode(data) + "\n":
                raise ValueError("Independent reference/packet replay mismatch: " + name)
    return {
        "passed": True,
        "replayed": replay,
        "cases": len(summaries),
        "source_commit": commit,
        "physical_validation": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("run")
    p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("verify")
    p.add_argument("directory", type=Path)
    p.add_argument("--replay", action="store_true")
    args = parser.parse_args()
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
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    print(encode(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
