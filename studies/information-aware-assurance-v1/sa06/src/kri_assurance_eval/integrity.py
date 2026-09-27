"""Installed-byte diagnostics, not authentication or a defence against hostile Python."""

import hashlib
import json
from pathlib import Path


def verify_installation():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "_provenance.json").read_text())
    expected = set(manifest["package_files"])
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.suffix in (".py", ".json") and "__pycache__" not in p.parts
    }
    if actual != expected | {"_provenance.json"}:
        raise ValueError("Installed source membership differs")
    for name, digest in manifest["package_files"].items():
        path = root / name
        if Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink():
            raise ValueError("Invalid installed source path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Installed source content differs")
    return manifest
