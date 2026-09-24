"""Verify the published reproduction receipt and immutable scientific figure bindings."""

from pathlib import Path, PurePosixPath
import argparse
import json
import subprocess
from .audit import ROOT, REPO, STUDY, digest, outcomes, load


def verify(directory=ROOT / "recorded"):
    directory = Path(directory)
    manifest = load(directory / "manifest.json")
    actual = {
        p.relative_to(directory).as_posix(): digest(p)
        for p in directory.rglob("*")
        if p.is_file() and p != directory / "manifest.json"
    }
    if actual != manifest["files"]:
        raise ValueError("Recorded output inventory differs")
    if manifest["scientific_source_commit"] != "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8":
        raise ValueError("Wrong scientific commit")
    report = load(directory / "verification.json")
    if report["outcomes"] != outcomes():
        raise ValueError("Recorded outcome interpretation differs")
    commit = manifest["reproduction_code_commit"]
    if report["reproduction_code_commit"] != commit:
        raise ValueError("Code identity differs")
    figures = load(directory / "figure_manifest.json")["figures"]
    if len(figures) != 7 or len({f["file"] for f in figures}) != 7:
        raise ValueError("Figure membership")
    for item in figures:
        path = PurePosixPath(item["file"])
        generator = PurePosixPath(item["generator"])
        if any(p.is_absolute() or ".." in p.parts for p in (path, generator)):
            raise ValueError("Invalid relative figure path")
        if (
            digest(directory / path) != item["sha256"]
            or digest(STUDY / generator) != item["generator_sha256"]
        ):
            raise ValueError("Figure or generator drift")
        raw = subprocess.check_output(
            [
                "git",
                "--no-replace-objects",
                "-C",
                str(REPO),
                "show",
                commit + ":studies/property-alignment-v1/" + generator.as_posix(),
            ]
        )
        from hashlib import sha256

        if sha256(raw).hexdigest() != item["generator_sha256"]:
            raise ValueError("Unbound generator source")
    return {
        "passed": True,
        "figures": len(figures),
        "scientific_source_commit": manifest["scientific_source_commit"],
        "reproduction_code_commit": commit,
        "physical_trials": 0,
        "external_human_reviews": 0,
        "scope": "Record and content identity, not authentication of independent scientific judgement",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, default=ROOT / "recorded")
    a = p.parse_args()
    print(json.dumps(verify(a.directory), indent=2))


if __name__ == "__main__":
    main()
