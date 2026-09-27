"""Assemble a standalone source tree without changing frozen research modules.

Only import namespaces and the legacy protocol lookup are relocated. Every input
is checked against a real Git blob, every output is inventoried. No package index
or release service is contacted by this command.
"""

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
REPO = STUDY.parents[1]
BASE = "16744cd7e14ae1a6c569231539635346a10b5e5b"
MODULES = {
    "iaa": ("__init__", "types", "enclosure", "assurance"),
    "sa02": ("__init__", "model", "intervals", "estimator", "bridge"),
    "sa03": ("__init__", "model", "policy", "forecast"),
    "sa04": ("__init__", "compute", "wire", "gate"),
}
PREFIX = "kri_assurance_eval._vendor."
LEGACY = "studies/property-alignment-v1/execution_validation_v1/protocol.py"


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(REPO), *args])


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relocate(raw):
    text = raw.decode()
    text = re.sub(r"(?m)^(\s*from )(iaa|sa02|sa03|sa04)([. ])", rf"\1{PREFIX}\2\3", text)
    # Confirm there is no unresolved absolute import hidden in the selected closure.
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            if any(n.name.split(".")[0] in MODULES for n in node.names):
                raise ValueError("Unsupported absolute import transformation")
    return (
        "# KRI SA06 packaging adaptation: import namespace only; original source pinned.\n" + text
    ).encode()


def assemble(destination, source=None, *, development=False):
    destination = Path(destination).expanduser().resolve()
    if destination.exists() or any(
        (p / ".git").exists() for p in (destination, *destination.parents)
    ):
        raise ValueError("Use a new destination outside every Git checkout")
    if source is None:
        source = json.loads((HERE / "release.json").read_text())["source_commit"]
    if not re.fullmatch("[0-9a-f]{40}", source):
        raise ValueError("Exact source commit required")
    pinned = json.loads((HERE / "vendor-sources.json").read_text())
    if pinned["commit"] != BASE:
        raise ValueError("Unexpected inherited baseline")
    destination.mkdir(parents=True)
    package = destination / "src/kri_assurance_eval"
    package.mkdir(parents=True)
    sources = {}
    outputs = {}

    def read(path, commit, allow_dirty=False):
        rel = path.relative_to(REPO).as_posix()
        raw = path.read_bytes()
        entry = git("ls-tree", commit, "--", rel).decode().split()
        blob = git("show", commit + ":" + rel) if entry else None
        if path.is_symlink() or (not allow_dirty and (raw != blob or len(entry) < 3)):
            raise ValueError("Actual Git source mismatch: " + rel)
        if entry and bool(path.stat().st_mode & 0o111) != (entry[0] == "100755"):
            raise ValueError("Source mode mismatch: " + rel)
        sources[rel] = dict(
            commit=commit if raw == blob else None,
            sha256=sha(raw),
            blob=entry[2] if raw == blob else None,
        )
        return raw

    def put(name, raw):
        p = package / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        outputs[name] = sha(raw)

    for name in ("assemble.py", "vendor-sources.json", "requirements-build.lock"):
        read(HERE / name, source, development)

    actual_vendor = {}
    for directory, names in MODULES.items():
        for name in names:
            path = STUDY / directory / (name + ".py")
            raw = read(path, BASE)
            actual_vendor[path.relative_to(REPO).as_posix()] = sha(raw)
            put("_vendor/" + directory + "/" + name + ".py", relocate(raw))
    raw = read(REPO / LEGACY, BASE)
    actual_vendor[LEGACY] = sha(raw)
    if actual_vendor != pinned["files"]:
        raise ValueError("Inherited module membership or content mismatch")
    put("_vendor/sa04/legacy_protocol.py", raw)
    put(
        "_vendor/sa04/legacy.py",
        (
            b'"""SA06 relocation of the pinned legacy protocol; no checkout lookup."""\n'
            b"from . import legacy_protocol as protocol\n"
        ),
    )
    put(
        "_vendor/__init__.py",
        b'"""Private, source-pinned research modules. Not a supported public API."""\n',
    )
    for p in sorted((HERE / "src/kri_assurance_eval").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".json"):
            put(
                p.relative_to(HERE / "src/kri_assurance_eval").as_posix(),
                read(p, source, development),
            )
    for original, target in (
        (HERE / "packaging.toml", "pyproject.toml"),
        (HERE / "README.md", "README.md"),
        (REPO / "LICENSE", "LICENSE"),
    ):
        (destination / target).write_bytes(
            read(original, BASE if target == "LICENSE" else source, development)
        )
    for name in (
        "INTERFACE.md",
        "EXTERNAL_VALIDATION.md",
        "IMPLEMENTATION_NOTE.md",
        "related-work.md",
        "source-map.json",
        "external-evidence.json",
    ):
        (destination / name).write_bytes(read(HERE / name, source, development))
    for p in sorted((HERE / "examples").glob("*.py")):
        out = destination / "examples" / p.name
        out.parent.mkdir(exist_ok=True)
        out.write_bytes(read(p, source, development))
    manifest = dict(
        schema="kri-assurance-build/1",
        component_version="0.1.0",
        source_commit=source,
        inherited_commit=BASE,
        development_build=development,
        sources=sources,
        package_files=outputs,
        transformation="Namespace-only absolute imports; legacy lookup becomes relative import",
        physical_validation=False,
        external_replication=False,
    )
    (package / "_provenance.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    (destination / "MANIFEST.in").write_text(
        "include BUILD_EPOCH *.md *.json\nrecursive-include examples *.py\n"
    )
    epoch = int(git("show", "-s", "--format=%ct", source).strip())
    (destination / "BUILD_EPOCH").write_text(str(epoch) + "\n")
    print(
        json.dumps(
            dict(
                assembled=True,
                files=len(outputs),
                source_commit=source,
                development_build=development,
            )
        )
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source")
    args = parser.parse_args()
    assemble(args.output, args.source)
