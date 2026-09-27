"""Read-only verification of the separately versioned SA06 software evidence.

The recorded host measurements are checked for identity/accounting. Semantic
reproduction recomputes results, never requires identical new host timings.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from iaa.artifact import read_json

from .assemble import BASE, HERE, REPO, assemble, git

RECORD = HERE / "recorded"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_names():
    paths = []
    for directory in (HERE, HERE.parent / "sa06_tests"):
        for p in directory.rglob("*"):
            if (
                p.is_file()
                and "__pycache__" not in p.parts
                and "recorded" not in p.parts
                and p.suffix in (".py", ".md", ".json", ".toml", ".txt", ".lock")
                and p.name not in ("release.json", "RESULTS.md")
            ):
                paths.append(p.relative_to(REPO).as_posix())
    return sorted(paths)


def verify(directory=RECORD):
    directory = Path(directory).resolve()
    release_path = HERE / "release.json"
    if release_path.read_bytes() != git(
        "show", "HEAD:" + release_path.relative_to(REPO).as_posix()
    ):
        raise ValueError("Release metadata differs from committed identity")
    release = read_json(release_path)
    if release["schema"] != "kri-sa06-release/1" or release["inherited_commit"] != BASE:
        raise ValueError("Release scope or predecessor mismatch")
    if release["component_version"] != "0.1.0" or set(release["sources"]) != set(source_names()):
        raise ValueError("Release source membership mismatch")
    source = release["source_commit"]
    for name, spec in release["sources"].items():
        path = REPO / name
        tree = git("ls-tree", source, "--", name).decode().split()
        if (
            path.is_symlink()
            or sha(path) != spec["sha256"]
            or hashlib.sha256(git("show", source + ":" + name)).hexdigest() != spec["sha256"]
            or tree[:3] != [spec["mode"], "blob", spec["blob"]]
            or bool(path.stat().st_mode & 0o111) != (spec["mode"] == "100755")
        ):
            raise ValueError("Release source/Git binding mismatch")
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.read_bytes() != git(
        "show", "HEAD:" + (RECORD / "manifest.json").relative_to(REPO).as_posix()
    ):
        raise ValueError("Evidence manifest differs from committed anchor")
    manifest = read_json(manifest_path)
    expected_files = {"host.json", "integration.json", "package-inventory.json"}
    if (
        manifest["schema"] != "kri-sa06-record/1"
        or manifest["source_commit"] != source
        or set(manifest["files"]) != expected_files
        or {p.name for p in directory.iterdir()} != expected_files | {"manifest.json"}
    ):
        raise ValueError("Evidence membership/scope mismatch")
    for name, spec in manifest["files"].items():
        p = directory / name
        if (
            p.is_symlink()
            or not p.is_file()
            or sha(p) != spec["sha256"]
            or p.stat().st_size != spec["bytes"]
        ):
            raise ValueError("Evidence content mismatch")
    measured = read_json(directory / "host.json")
    if (
        measured["source_commit"] != source
        or measured["development_build"] is not False
        or measured["complete"] is not True
        or any(
            measured[k] is not False
            for k in (
                "physical_validation",
                "target_validation",
                "external_replication",
                "timings_are_WCET",
            )
        )
    ):
        raise ValueError("Host evidence scope mismatch")
    examples = read_json(HERE / "src/kri_assurance_eval/examples.json")
    expected_order = [(r, x["name"]) for r in (-1, 0, 1) for x in examples]
    if [(x["repetition"], x["name"]) for x in measured["samples"]] != expected_order:
        raise ValueError("Incomplete host sample accounting")
    for row in measured["samples"]:
        if (
            row["warmup"] is not (row["repetition"] == -1)
            or row["expected_status_matched"] is not True
            or any(
                type(row[k]) is not int or row[k] < 0
                for k in ("elapsed_ns", "cpu_ns", "process_peak_rss_bytes")
            )
        ):
            raise ValueError("Invalid host sample")
    integration = read_json(directory / "integration.json")
    if (
        integration["source_commit"] != source
        or integration["external_replication"] is not False
        or integration["installed_outside_checkout"] is not True
        or integration["adapter"]["status"] != "supported_prefix"
    ):
        raise ValueError("Integration evidence scope mismatch")
    with tempfile.TemporaryDirectory() as tmp:
        staged = assemble(Path(tmp) / "source", source)
        provenance = read_json(staged / "src/kri_assurance_eval/_provenance.json")
        inventory = read_json(directory / "package-inventory.json")
        if provenance != inventory:
            raise ValueError("Packaged module inventory differs")
        # Separate interpreter, no prior imports, no target or physical execution.
        code = (
            "import sys,json; sys.path.insert(0,sys.argv[1]); "
            "from kri_assurance_eval.api import assess; "
            "from kri_assurance_eval.examples import examples; "
            "print(json.dumps({x['name']:assess(x['request']) for x in examples()},sort_keys=True))"
        )
        actual = json.loads(
            subprocess.check_output(
                [sys.executable, "-I", "-c", code, str(staged / "src")],
                cwd=tmp,
                text=True,
                timeout=60,
            )
        )
        if any(row["result"] != actual[row["name"]] for row in measured["samples"]):
            raise ValueError("Internal semantic reproduction mismatch")
    return dict(
        passed=True,
        source_commit=source,
        semantic_cases=len(examples),
        original_host_samples=len(expected_order),
        host_measurements_repeated=False,
        external_replication=False,
        physical_validation=False,
    )


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), sort_keys=True))
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        ArithmeticError,
        subprocess.CalledProcessError,
    ) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
