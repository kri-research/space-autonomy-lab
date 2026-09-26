"""Source-bound prospective recording with complete attempts and read-only replay."""

import argparse
import base64
import datetime
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from iaa.artifact import read_json
from iaa.types import encode, identity, primitive

from .analysis import host_summary, summarize
from .design import DEVELOPMENT_SEED, METHODS, population
from .plots import equal_rendering, generate

STUDY = Path(__file__).resolve().parents[1]
REPO = STUDY.parents[1]
PACKAGE = STUDY / "sa05"
PUBLIC = PACKAGE / "recorded"


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(REPO), *args])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths():
    paths = [
        p
        for d in ("iaa", "sa02", "sa03", "sa04", "sa05", "sa05_tests")
        for p in (STUDY / d).glob("*.py")
    ]
    paths += [REPO / "studies/property-alignment-v1/execution_validation_v1/protocol.py"]
    paths += [
        PACKAGE / name
        for name in (
            "requirements.txt",
            "requirements.lock",
            "protocol.json",
            "source-map.json",
            "MATHEMATICS.md",
        )
        if (PACKAGE / name).is_file()
    ]
    paths += [
        STUDY / name for name in ("pyproject.toml", ".python-version", "requirements-dev.txt")
    ]
    return sorted(p.relative_to(REPO).as_posix() for p in paths)


def sources():
    commit = git("rev-parse", "HEAD").decode().strip()
    files = {}
    for name in source_paths():
        p = REPO / name
        raw = git("show", commit + ":" + name)
        tree = git("ls-tree", commit, "--", name).decode().split()
        if p.is_symlink() or raw != p.read_bytes():
            raise ValueError("Uncommitted scientific source: " + name)
        files[name] = dict(sha256=digest(p), mode=tree[0], blob=tree[2])
    return dict(commit=commit, files=files)


def verify_sources(source):
    commit = source["commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Invalid source commit")
    if set(source["files"]) != set(source_paths()):
        raise ValueError("Scientific source membership changed")
    for name, spec in source["files"].items():
        p = REPO / name
        tree = git("ls-tree", commit, "--", name).decode().split()
        if (
            p.is_symlink()
            or digest(p) != spec["sha256"]
            or hashlib.sha256(git("show", commit + ":" + name)).hexdigest() != spec["sha256"]
            or tree[:3] != [spec["mode"], "blob", spec["blob"]]
            or bool(p.stat().st_mode & 0o111) != (spec["mode"] == "100755")
        ):
            raise ValueError("Scientific source Git binding: " + name)


def dependencies():
    return {
        d.metadata["Name"].lower().replace("_", "-"): d.version
        for d in importlib.metadata.distributions()
    }


def verify_deposit(commit):
    """A public immutable commit must contain the exact local freeze before outcomes."""
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("Exact deposited commit required")
    name = (PACKAGE / "freeze.json").relative_to(REPO).as_posix()
    url = (
        f"https://api.github.com/repos/kri-research/space-autonomy-lab/contents/{name}?ref={commit}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "KRI-SA05-prospective-check"})
    with urllib.request.urlopen(req, timeout=30) as response:
        remote = json.load(response)
    if base64.b64decode(remote["content"]) != (PACKAGE / "freeze.json").read_bytes():
        raise ValueError("Public deposit differs from local freeze")
    meta_url = f"https://api.github.com/repos/kri-research/space-autonomy-lab/commits/{commit}"
    with urllib.request.urlopen(
        urllib.request.Request(meta_url, headers={"User-Agent": "KRI-SA05-prospective-check"}),
        timeout=30,
    ) as response:
        meta = json.load(response)
    return dict(
        commit=commit,
        freeze_sha256=digest(PACKAGE / "freeze.json"),
        github_commit_date=meta["commit"]["committer"]["date"],
        checked_before_execution_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        public_source_deposit=True,
        external_preregistration=False,
    )


def write(path, value):
    path.write_text(encode(value) + "\n")


def record(output, split, deposit=None):
    if sys.version.split()[0] != "3.13.5":
        raise ValueError("Pinned CPython 3.13.5 required")
    output = output.expanduser().resolve()
    if output.exists() or any((p / ".git").exists() for p in (output, *output.parents)):
        raise ValueError("A new directory outside every checkout is required")
    protocol = read_json(PACKAGE / "protocol.json")
    if split == "development":
        cases = population(DEVELOPMENT_SEED, split, protocol["pilot_counts"])
        source = sources()
        deposited = dict(public_source_deposit=False, development_only=True)
    elif split == "held_out":
        if not deposit:
            raise ValueError("Held-out execution requires public source deposit")
        freeze = read_json(PACKAGE / "freeze.json")
        verify_sources(freeze["source"])
        if (
            digest(PACKAGE / "protocol.json") != freeze["protocol_sha256"]
            or digest(PACKAGE / "held-inputs.json") != freeze["held_inputs_sha256"]
        ):
            raise ValueError("Frozen design or input population changed")
        if dependencies() != freeze["dependencies"]:
            raise ValueError("Installed distribution versions differ from freeze")
        deposited = verify_deposit(deposit)
        cases = read_json(PACKAGE / "held-inputs.json")
        if any(c["split"] != "held_out" for c in cases):
            raise ValueError("Development inputs cannot be labelled held-out")
        source = freeze["source"]
    else:
        raise ValueError("Unknown split")
    output.mkdir(parents=True)
    public = output / "public"
    public.mkdir()
    raw = output / "private-process-logs"
    raw.mkdir()
    (public / "cases").mkdir()
    write(public / "inputs.json", cases)
    write(public / "deposit.json", deposited)
    write(
        public / "environment.json",
        dict(
            python=sys.version.split()[0],
            os=platform.system(),
            architecture=platform.machine(),
            distributions=dependencies(),
            energy_measured=False,
            physical_validation=False,
        ),
    )
    rows = []
    timings = []
    ledger = []
    started = time.monotonic()
    limit = (
        protocol["pilot_wall_seconds"] if split == "development" else protocol["held_wall_seconds"]
    )
    for case in cases:
        for method in case["method_order"]:
            stem = case["unit"] + "--" + method
            job = raw / (stem + "-input.json")
            answer = raw / (stem + "-output.json")
            write(job, dict(case=case, method=method))
            event = dict(
                unit=case["unit"],
                method=method,
                started_offset_ns=int((time.monotonic() - started) * 1e9),
            )
            result = None
            status = "not_started_budget_exhausted"
            remaining = limit - (time.monotonic() - started)
            if remaining > 0:
                with (raw / (stem + ".log")).open("wb") as log:
                    try:
                        proc = subprocess.run(
                            [sys.executable, "-m", "sa05.single", str(job), str(answer)],
                            cwd=STUDY,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            timeout=min(protocol["cell_timeout_seconds"], remaining),
                            env={
                                **os.environ,
                                "PYTHONDONTWRITEBYTECODE": "1",
                                "OPENBLAS_NUM_THREADS": "1",
                            },
                        )
                        event["exit_code"] = proc.returncode
                        if proc.returncode == 0 and answer.is_file():
                            result = read_json(answer)
                            status = "completed"
                        else:
                            status = "infrastructure_failure"
                    except subprocess.TimeoutExpired:
                        status = "infrastructure_timeout"
                        event["exit_code"] = None
            if result is None:
                row = dict(
                    schema="iaa-sa05-result/1",
                    unit=case["unit"],
                    method=method,
                    stratum=case["stratum"],
                    input_sha256=identity(case),
                    status=status,
                )
                evidence = None
                timing = dict(unit=case["unit"], method=method, status=status)
            else:
                row, evidence, timing = result["row"], result["evidence"], result["timing"]
            rows.append(row)
            timings.append(timing)
            event.update(status=status, finished_offset_ns=int((time.monotonic() - started) * 1e9))
            ledger.append(event)
            write(public / "cases" / (stem + ".json"), dict(row=row, evidence=evidence))
            # Persist full accounting after every attempted cell. No selective retries.
            write(public / "ledger.json", ledger)
            write(public / "measurements.json", timings)
            write(public / "results.json", rows)
            print(
                stem, status, row.get("acquired_goal"), row.get("observation_requests"), flush=True
            )
    analysis = summarize(cases, rows)
    write(public / "analysis.json", analysis)
    write(public / "host-summary.json", host_summary(timings))
    generate(analysis, public / "plots")
    files = {
        p.relative_to(public).as_posix(): dict(sha256=digest(p), bytes=p.stat().st_size)
        for p in sorted(public.rglob("*"))
        if p.is_file()
    }
    manifest = dict(
        schema="iaa-sa05-artifact/1",
        split=split,
        source=source,
        files=files,
        scheduled=len(cases) * len(METHODS),
        completed=analysis["completed"],
        physical_validation=False,
        external_replication=False,
    )
    write(public / "manifest.json", manifest)
    return dict(
        output=str(public),
        units=len(cases),
        scheduled=len(rows),
        completed=analysis["completed"],
        source_commit=source["commit"],
    )


def verify_files(directory, manifest):
    actual = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() or p.is_symlink()
    }
    if actual != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("Artifact membership mismatch")
    for name, spec in manifest["files"].items():
        p = directory / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or p.is_symlink()
            or not p.is_file()
            or p.stat().st_size != spec["bytes"]
            or digest(p) != spec["sha256"]
        ):
            raise ValueError("Artifact data binding: " + name)


def verify(directory, replay=False, sample=False):
    directory = directory.resolve()
    anchor = (PUBLIC / "manifest.json").relative_to(REPO).as_posix()
    if (directory / "manifest.json").is_symlink() or (
        directory / "manifest.json"
    ).read_bytes() != git("show", "HEAD:" + anchor):
        raise ValueError("Manifest differs from committed record")
    m = read_json(directory / "manifest.json")
    verify_files(directory, m)
    verify_sources(m["source"])
    if m["schema"] != "iaa-sa05-artifact/1" or m["split"] != "held_out":
        raise ValueError("Only frozen held-out record at this entry point")
    frozen = read_json(PACKAGE / "freeze.json")
    if (
        m["source"] != frozen["source"]
        or digest(directory / "inputs.json") != frozen["held_inputs_sha256"]
    ):
        raise ValueError("Frozen source/population mismatch")
    cases = read_json(directory / "inputs.json")
    rows = read_json(directory / "results.json")
    if summarize(cases, rows) != read_json(directory / "analysis.json"):
        raise ValueError("Frozen analysis does not reproduce")
    if host_summary(read_json(directory / "measurements.json")) != read_json(
        directory / "host-summary.json"
    ):
        raise ValueError("Host accounting does not reproduce")
    ledger = read_json(directory / "ledger.json")
    order = [(c["unit"], method) for c in cases for method in c["method_order"]]
    if [(r["unit"], r["method"]) for r in ledger] != order or [
        (r["unit"], r["method"]) for r in rows
    ] != order:
        raise ValueError("Attempt order/accounting mismatch")
    measured = read_json(directory / "measurements.json")
    if [(r["unit"], r["method"]) for r in measured] != order:
        raise ValueError("Missing or reordered host measurements")
    lookup = {c["unit"]: c for c in cases}
    for row, event, timing in zip(rows, ledger, measured, strict=True):
        if row["input_sha256"] != identity(lookup[row["unit"]]) or event["status"] != row["status"]:
            raise ValueError("Unit identity or completion accounting mismatch")
        if row["status"] == "completed":
            for key in (
                "planner_ns",
                "checker_ns",
                "complete_offline_trial_ns",
                "process_cpu_ns",
                "peak_rss_bytes",
            ):
                if type(timing[key]) is not int or timing[key] < 0:
                    raise ValueError("Invalid host measurement")
        if not 0 <= event["started_offset_ns"] <= event["finished_offset_ns"]:
            raise ValueError("Invalid attempt timeline")
    deposited = read_json(directory / "deposit.json")
    freeze_path = (PACKAGE / "freeze.json").relative_to(REPO).as_posix()
    if (
        not deposited["public_source_deposit"]
        or deposited["external_preregistration"]
        or deposited["freeze_sha256"] != digest(PACKAGE / "freeze.json")
        or git("show", deposited["commit"] + ":" + freeze_path)
        != (PACKAGE / "freeze.json").read_bytes()
    ):
        raise ValueError("Prospective deposit identity mismatch")
    if digest(PACKAGE / "protocol.json") != frozen["protocol_sha256"]:
        raise ValueError("Frozen analysis protocol changed")
    for row in rows:
        if (
            read_json(directory / "cases" / (row["unit"] + "--" + row["method"] + ".json"))["row"]
            != row
        ):
            raise ValueError("Per-case summary differs")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        generate(read_json(directory / "analysis.json"), Path(tmp))
        for p in Path(tmp).iterdir():
            if not equal_rendering(p, directory / "plots" / p.name):
                raise ValueError("Plot/table regeneration mismatch: " + p.name)
    count = 0
    if replay or sample:
        from .experiment import run

        selected = {c["unit"]: c for c in cases if replay or c["index"] in (0, 1)}
        for expected in rows:
            if expected["unit"] not in selected or expected["status"] != "completed":
                continue
            actual, _, _ = run(selected[expected["unit"]], expected["method"])
            for key in expected:
                if key in (
                    "task_potential_change_m2",
                    "initial_task_potential_m2",
                    "final_task_potential_m2",
                ):
                    if abs(actual[key] - expected[key]) > 5e-5:
                        raise ValueError("Numerical replay tolerance: " + key)
                elif primitive(actual[key]) != expected[key]:
                    raise ValueError("Semantic replay mismatch: " + expected["unit"] + "/" + key)
            count += 1
    return dict(
        passed=True,
        units=len(cases),
        scheduled=len(rows),
        replayed_cells=count,
        source_commit=m["source"]["commit"],
        host_timings_repeated=False,
        physical_validation=False,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--split", choices=("development", "held_out"), required=True)
    r.add_argument("--deposit")
    v = sub.add_parser("verify")
    v.add_argument("directory", type=Path)
    v.add_argument("--replay", action="store_true")
    v.add_argument("--sample", action="store_true")
    a = p.parse_args()
    try:
        out = (
            record(a.output, a.split, a.deposit)
            if a.cmd == "run"
            else verify(a.directory, a.replay, a.sample)
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
    print(encode(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
