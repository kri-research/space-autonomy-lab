"""Build the corrected 0.1.1 component without editing frozen SA06 sources."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from sa06.assemble import assemble as original_assemble

from .patches import apply, once

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
REPO = STUDY.parents[1]
OLD_SOURCE = "50003cb0511265afbe7c2f368d9fb19100ee4d44"
REVIEWED = "cc93a5ce725f7a736d4837b1178b5725962ff28f"


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(REPO), *args])


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def correction_sources():
    paths = list(HERE.glob("*.py")) + list(HERE.glob("*.md"))
    paths += list((HERE / "tests").glob("*.py"))
    paths += list((STUDY / "sa05/posthoc_attainability_v1").glob("*.py"))
    paths += list((STUDY / "sa05/posthoc_attainability_v1").glob("*.md"))
    paths += [REPO / ".github/workflows/post-audit-corrections.yml"]
    return sorted(p for p in paths if p.is_file() and p.name != "RESULTS.md")


def source_bindings(source, development=False):
    bindings = {}
    for path in correction_sources():
        name = path.relative_to(REPO).as_posix()
        entry = git("ls-tree", source, "--", name).decode().split()
        actual = path.read_bytes()
        expected = git("show", source + ":" + name) if entry else None
        if path.is_symlink() or (not development and (actual != expected or not entry)):
            raise ValueError("Correction source/Git mismatch: " + name)
        if entry and bool(path.stat().st_mode & 0o111) != (entry[0] == "100755"):
            raise ValueError("Correction source mode mismatch")
        bindings[name] = dict(
            commit=source if actual == expected else None,
            blob=entry[2] if actual == expected else None,
            sha256=sha(actual),
            mode=entry[0] if actual == expected else "100644",
        )
    return bindings


def assemble(destination, source=None, *, development=False):
    if source is None:
        source = json.loads((HERE / "release.json").read_text())["source_commit"]
    if not re.fullmatch("[0-9a-f]{40}", source):
        raise ValueError("Exact source commit required")
    bindings = source_bindings(source, development)
    # All older files must still match the original source pins.
    destination = original_assemble(destination, OLD_SOURCE)
    package = destination / "src/kri_assurance_eval"
    provenance = json.loads((package / "_provenance.json").read_text())
    before = dict(provenance["package_files"])
    apply(package)
    (package / "_numeric.py").write_bytes((HERE / "numeric.py").read_bytes())
    project = destination / "pyproject.toml"
    project.write_text(once(project.read_text(), 'version = "0.1.0"', 'version = "0.1.1"'))
    (destination / "README.md").write_bytes((HERE / "README.md").read_bytes())
    (destination / "CORRECTIONS.md").write_bytes((HERE / "CORRECTIONS.md").read_bytes())
    interface = destination / "INTERFACE.md"
    interface.write_text(
        interface.read_text().replace("Version 0.1.0", "Version 0.1.1")
        + "\n## Post-audit input correction\n\n"
        + "Read CORRECTIONS.md for the bounded observation scalar grammar, "
        + "future-packet fix and retained limits. Version 0.1.0 is historical.\n"
    )
    after = {
        p.relative_to(package).as_posix(): sha(p.read_bytes())
        for p in sorted(package.rglob("*"))
        if p.is_file() and p.name != "_provenance.json"
    }
    changes = {
        name: dict(before=before.get(name), after=digest)
        for name, digest in after.items()
        if before.get(name) != digest
    }
    if set(changes) != {
        "__init__.py",
        "api.py",
        "_numeric.py",
        "examples.json",
        "_vendor/iaa/types.py",
        "_vendor/sa02/estimator.py",
    }:
        raise ValueError("Unexpected runtime transformation")
    provenance.update(
        component_version="0.1.1",
        source_commit=source,
        inherited_component_source=OLD_SOURCE,
        reviewed_revision=REVIEWED,
        development_build=development,
        correction_sources=bindings,
        package_files=after,
        corrections=changes,
        transformation="Original namespace relocation plus A1/C1 corrections and version change",
        new_scientific_campaign=False,
    )
    (package / "_provenance.json").write_text(
        json.dumps(provenance, sort_keys=True, indent=2) + "\n"
    )
    epoch = int(git("show", "-s", "--format=%ct", source).strip())
    (destination / "BUILD_EPOCH").write_text(str(epoch) + "\n")
    print(
        json.dumps(dict(corrected_version="0.1.1", source_commit=source, development=development))
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source")
    args = parser.parse_args()
    assemble(args.output, args.source)
