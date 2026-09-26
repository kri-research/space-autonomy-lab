"""Complete source-bound SA04 record; host samples are never replay expectations."""

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

from iaa.artifact import read_json
from iaa.types import encode

from .fixtures import FAULTS, METHODS, run
from .host import record as host_record
from .host import summarize
from .trace import audit

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
RECORD = ROOT / "sa04/recorded"


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(REPO), *args])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths():
    files = [
        p for d in ("iaa", "sa02", "sa03", "sa04", "sa04_tests") for p in (ROOT / d).glob("*.py")
    ]
    files += [
        ROOT / p
        for p in (
            ".python-version",
            "pyproject.toml",
            "requirements-dev.txt",
            "sa04/host-protocol.json",
            "sa04/MATHEMATICS.md",
            "sa04/source-map.json",
        )
    ]
    files += [REPO / "studies/property-alignment-v1/execution_validation_v1/protocol.py"]
    return sorted(p.relative_to(REPO).as_posix() for p in files)


def sources():
    if git("status", "--porcelain", "--", ROOT.relative_to(REPO).as_posix()).strip():
        raise ValueError("Commit source before any recorded execution")
    commit = git("rev-parse", "HEAD").decode().strip()
    files = {}
    for name in source_paths():
        p = REPO / name
        tree = git("ls-tree", commit, "--", name).decode().split()
        if p.is_symlink() or p.read_bytes() != git("show", commit + ":" + name):
            raise ValueError("Source/Git mismatch")
        files[name] = dict(sha256=sha(p), mode=tree[0], blob=tree[2])
    return dict(commit=commit, files=files)


def names():
    return {
        "inputs.json",
        "summary.json",
        "host.json",
        "host-summary.json",
        "host-logging.jsonl",
    } | {fault + "--" + method + ".json" for fault in FAULTS for method in METHODS}


def record(output):
    output = output.expanduser().resolve()
    if output.exists() or any((p / ".git").exists() for p in (output, *output.parents)):
        raise ValueError("Use a new output directory outside all Git checkouts")
    if sys.version.split()[0] != "3.13.5":
        raise ValueError("Pinned CPython 3.13.5 required")
    source = sources()
    output.mkdir(parents=True)
    (output / "inputs.json").write_text(encode(dict(faults=FAULTS, methods=METHODS)) + "\n")
    rows = []
    try:
        for fault in FAULTS:
            for method in METHODS:
                summary, trace = run(fault, method)
                rows.append(summary)
                (output / (fault + "--" + method + ".json")).write_text(encode(trace) + "\n")
                print(
                    fault,
                    method,
                    summary["candidate_admitted"],
                    summary["applied_times"],
                    flush=True,
                )
        (output / "summary.json").write_text(encode(rows) + "\n")
        host_summary = host_record(output)
        (output / "host-summary.json").write_text(encode(host_summary) + "\n")
    except Exception as exc:
        (output / "failed-attempt.json").write_text(
            encode(
                dict(
                    source=source,
                    completed_fixtures=len(rows),
                    error=type(exc).__name__ + ":" + str(exc),
                )
            )
            + "\n"
        )
        raise
    manifest = dict(
        schema="iaa-sa04-record/1",
        source=source,
        files={
            n: dict(sha256=sha(output / n), bytes=(output / n).stat().st_size)
            for n in sorted(names())
        },
        evidence="deterministic_simulation_and_separate_actual_host_measurement",
        physical_validation=False,
    )
    (output / "manifest.json").write_text(encode(manifest) + "\n")
    return dict(
        recorded=True, fixtures=len(rows), host=host_summary, source_commit=source["commit"]
    )


def verify(directory, replay=False):
    directory = directory.resolve()
    mp = directory / "manifest.json"
    anchor = (RECORD / "manifest.json").relative_to(REPO).as_posix()
    if mp.is_symlink() or mp.read_bytes() != git("show", "HEAD:" + anchor):
        raise ValueError("Record manifest is not the committed anchor")
    m = read_json(mp)
    if (
        m["schema"] != "iaa-sa04-record/1"
        or set(m["files"]) != names()
        or {p.name for p in directory.iterdir()} != names() | {"manifest.json"}
    ):
        raise ValueError("File/schema membership mismatch")
    for name, spec in m["files"].items():
        p = directory / name
        if (
            p.is_symlink()
            or not p.is_file()
            or p.stat().st_size != spec["bytes"]
            or sha(p) != spec["sha256"]
        ):
            raise ValueError("Artifact content mismatch: " + name)
    source = m["source"]
    commit = source["commit"]
    if (
        len(commit) != 40
        or any(c not in "0123456789abcdef" for c in commit)
        or set(source["files"]) != set(source_paths())
    ):
        raise ValueError("Source identity/membership")
    for name, spec in source["files"].items():
        p = REPO / name
        tree = git("ls-tree", commit, "--", name).decode().split()
        if (
            p.is_symlink()
            or sha(p) != spec["sha256"]
            or hashlib.sha256(git("show", commit + ":" + name)).hexdigest() != spec["sha256"]
            or tree[:3] != [spec["mode"], "blob", spec["blob"]]
            or bool(p.stat().st_mode & 0o111) != (spec["mode"] == "100755")
        ):
            raise ValueError("Source bytes/mode do not match actual Git blob: " + name)
    expected = read_json(directory / "summary.json")
    order = [(f, method) for f in FAULTS for method in METHODS]
    if [(r["fault"], r["method"]) for r in expected] != order:
        raise ValueError("Engineering population changed")
    if (directory / "inputs.json").read_text() != encode(
        dict(faults=FAULTS, methods=METHODS)
    ) + "\n":
        raise ValueError("Input identities differ")
    host = read_json(directory / "host.json")
    design = read_json(ROOT / "sa04/host-protocol.json")
    if (
        host["design"] != design
        or len(host["diagnostic_sessions"]) != design["sessions"]
        or len(host["enforced_runs"]) != 12
    ):
        raise ValueError("Host protocol/population mismatch")
    for session in host["diagnostic_sessions"]:
        expected_calls = [
            (rep, k, method)
            for rep in range(design["repetitions"])
            for k in design["contexts"]
            for method in METHODS
        ]
        if [
            (r["repeat"], r["kind"], r["method"]) for r in session["samples"]
        ] != expected_calls or len(session["warmups"]) != 2:
            raise ValueError("Incomplete host samples")
    enforced_order = [
        (rep, kind, method)
        for rep in range(design["enforced_repetitions"])
        for kind in ("ambiguity", "adequate")
        for method in METHODS
    ]
    if [(r["repeat"], r["kind"], r["method"]) for r in host["enforced_runs"]] != enforced_order:
        raise ValueError("Enforced population/order mismatch")
    if [s["session"] for s in host["diagnostic_sessions"]] != list(range(design["sessions"])):
        raise ValueError("Process-session accounting")
    for session in host["diagnostic_sessions"]:
        if [(r["kind"], r["method"]) for r in session["warmups"]] != [
            ("adequate", m) for m in METHODS
        ]:
            raise ValueError("Warmup identities")
        for row in (*session["warmups"], *session["samples"]):
            if (
                row["compute_path_ns"]
                != row["summed_components_ns"] + row["unattributed_python_overhead_ns"]
            ):
                raise ValueError("Incomplete elapsed-time accounting")
            if row["unattributed_python_overhead_ns"] < 0:
                raise ValueError("Overlapping timing scopes")
    for row in host["enforced_runs"]:
        if row["physical_signal_emitted"] is not False or row["target_validation"] is not False:
            raise ValueError("Unsupported physical scope")
        if row["candidate_signal_emitted"] and not (
            row["planner_on_time"]
            and row["admission"]["scheduled"]
            and row["plan_ready_offset_ns"] <= 150_000_000
            and row["admission_complete_offset_ns"] <= 700_000_000
        ):
            raise ValueError("Signal lacked completed on-time permission")
    log_rows = (directory / "host-logging.jsonl").read_text().splitlines()
    if len(log_rows) != 2 * (36 + 6 + 12):
        raise ValueError("Logging completion accounting")
    if read_json(directory / "host-summary.json") != summarize(host):
        raise ValueError("Host summary mismatch")
    if not summarize(host)["no_out_of_window_emission"]:
        raise ValueError("Host emitted outside its verified window")
    for (fault, method), row in zip(order, expected, strict=True):
        path = directory / (fault + "--" + method + ".json")
        trace = read_json(path)
        if audit(trace):
            raise ValueError("Semantic trace replay failed")
        if trace["terminal"] != row["trace_terminal"]:
            raise ValueError("Trace/summary identity mismatch")
        if replay:
            actual, again = run(fault, method)
            if encode(actual) != encode(row) or encode(again) + "\n" != path.read_text():
                raise ValueError("Deterministic full replay mismatch: " + fault + " " + method)
    return dict(
        passed=True,
        fixtures=len(order),
        replayed=replay,
        source_commit=commit,
        host_measurements_repeated=False,
        physical_validation=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("directory", type=Path)
    v.add_argument("--replay", action="store_true")
    a = p.parse_args()
    try:
        result = record(a.output) if a.action == "run" else verify(a.directory, a.replay)
    except (
        ValueError,
        OSError,
        TypeError,
        KeyError,
        ArithmeticError,
        subprocess.CalledProcessError,
    ) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    print(encode(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
