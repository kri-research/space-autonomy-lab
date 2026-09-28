"""Read-only source, correction, derived-data and internal replay verification."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from sa05.posthoc_attainability_v1.audit import INPUT_COMMIT, analyze

from .assemble import HERE, REPO, STUDY, assemble, git, sha, source_bindings

RECORD = HERE / "recorded"
DERIVED = STUDY / "sa05/posthoc_attainability_v1/recorded.json"
EXPECTED_FILES = {"probes.json", "package-inventory.json", "integration.json"}


def anchored(path, relative):
    if path.is_symlink() or path.read_bytes() != git("show", "HEAD:" + relative):
        raise ValueError("Record differs from committed anchor")


def verify(directory=RECORD):
    directory = Path(directory).resolve()
    release_path = HERE / "release.json"
    anchored(release_path, release_path.relative_to(REPO).as_posix())
    release = json.loads(release_path.read_text())
    if release["schema"] != "kri-post-audit-release/1" or release["component_version"] != "0.1.1":
        raise ValueError("Correction release scope")
    source = release["source_commit"]
    if source_bindings(source) != release["sources"]:
        raise ValueError("Correction source identities")
    path = directory / "manifest.json"
    anchored(path, (RECORD / "manifest.json").relative_to(REPO).as_posix())
    manifest = json.loads(path.read_text())
    if (
        manifest["schema"] != "kri-post-audit-evidence/1"
        or manifest["source_commit"] != source
        or set(manifest["files"]) != EXPECTED_FILES
        or {p.name for p in directory.iterdir()} != EXPECTED_FILES | {"manifest.json"}
    ):
        raise ValueError("Correction evidence membership/scope")
    for name, spec in manifest["files"].items():
        p = directory / name
        if (
            p.is_symlink()
            or not p.is_file()
            or p.stat().st_size != spec["bytes"]
            or sha(p.read_bytes()) != spec["sha256"]
        ):
            raise ValueError("Changed correction evidence")
    anchored(DERIVED, DERIVED.relative_to(REPO).as_posix())
    if sha(DERIVED.read_bytes()) != manifest["derived_sha256"]:
        raise ValueError("Derived evidence identity")
    if json.loads(DERIVED.read_text()) != analyze(STUDY / "sa05/held-inputs.json"):
        raise ValueError("Post-hoc analysis does not reproduce")
    inputs = (STUDY / "sa05/held-inputs.json").relative_to(REPO).as_posix()
    if git("show", INPUT_COMMIT + ":" + inputs) != (REPO / inputs).read_bytes():
        raise ValueError("Frozen population Git mismatch")
    integration = json.loads((directory / "integration.json").read_text())
    if (
        integration["source_commit"] != source
        or integration["component_version"] != "0.1.1"
        or integration["external_replication"] is not False
        or integration["physical_validation"] is not False
        or integration["installed_outside_checkout"] is not True
    ):
        raise ValueError("Internal integration scope mismatch")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        assembled = assemble(tmp / "source", source)
        inventory = json.loads((assembled / "src/kri_assurance_eval/_provenance.json").read_text())
        if inventory != json.loads((directory / "package-inventory.json").read_text()):
            raise ValueError("Corrected runtime inventory mismatch")
        output = tmp / "probes.json"
        code = (
            "import sys,runpy; sys.path.insert(0,sys.argv[1]); "
            "sys.argv=sys.argv[2:];runpy.run_path(sys.argv[0],run_name='__main__')"
        )
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                code,
                str(assembled / "src"),
                str(HERE / "probes.py"),
                "--output",
                str(output),
            ],
            cwd=tmp,
            check=True,
            timeout=60,
            capture_output=True,
        )
        if json.loads(output.read_text()) != json.loads((directory / "probes.json").read_text()):
            raise ValueError("Correction probes do not reproduce")
    return dict(
        passed=True,
        component_version="0.1.1",
        source_commit=source,
        early_rejection_routes=4,
        causal_observer_cases=5,
        inherited_examples=10,
        posthoc_in_model_cases=96,
        physical_validation=False,
        new_scientific_campaign=False,
        host_measurements_repeated=False,
    )


if __name__ == "__main__":
    try:
        print(json.dumps(verify(), sort_keys=True))
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        ArithmeticError,
        subprocess.SubprocessError,
    ) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None
