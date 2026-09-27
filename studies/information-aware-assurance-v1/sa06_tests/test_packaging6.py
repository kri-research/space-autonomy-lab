import hashlib
import json
from pathlib import Path

import pytest

from sa06.assemble import BASE, LEGACY, MODULES, REPO, STUDY, relocate


def test_original_dependency_closure(component):
    from kri_assurance_eval.integrity import verify_installation

    m = verify_installation()
    for directory, names in MODULES.items():
        for name in names:
            rel = f"_vendor/{directory}/{name}.py"
            expected = relocate((STUDY / directory / (name + ".py")).read_bytes())
            assert hashlib.sha256(expected).hexdigest() == m["package_files"][rel]
    assert m["inherited_commit"] == BASE
    original = (REPO / LEGACY).read_bytes()
    assert (
        hashlib.sha256(original).hexdigest()
        == m["package_files"]["_vendor/sa04/legacy_protocol.py"]
    )


@pytest.mark.parametrize("mutation", ["content", "extra", "missing", "symlink"])
def test_installation_tampering_fails(component, mutation):
    from kri_assurance_eval.integrity import verify_installation

    root = Path(component.__file__).parent
    path = root / "examples.json"
    old = path.read_bytes()
    extra = root / "unknown.py"
    try:
        if mutation == "content":
            path.write_bytes(old + b" ")
        elif mutation == "extra":
            extra.write_text("hidden = True\n")
        elif mutation == "missing":
            path.unlink()
        else:
            path.unlink()
            path.symlink_to(root / "__init__.py")
        with pytest.raises(ValueError):
            verify_installation()
    finally:
        if path.is_symlink():
            path.unlink()
        path.write_bytes(old)
        if extra.exists():
            extra.unlink()
    assert verify_installation()


def test_packaging_source_is_original_and_explicitly_versioned():
    pins = json.loads((STUDY / "sa06/vendor-sources.json").read_text())
    assert pins["commit"] == BASE
    for path, value in pins["files"].items():
        assert hashlib.sha256((REPO / path).read_bytes()).hexdigest() == value
    config = (STUDY / "sa06/packaging.toml").read_text()
    assert "dependencies = []" in config and 'version = "0.1.0"' in config
