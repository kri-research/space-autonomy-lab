import hashlib
import json
import shutil

import pytest

from sa02.artifact import RECORD, read_json, verify


def test_recorded_identity():
    assert verify(RECORD)["cases"] == 10


@pytest.mark.parametrize(
    "mutation", ["data", "coedit", "missing", "extra", "symlink", "manifest_symlink", "duplicate"]
)
def test_mutations_fail(tmp_path, mutation):
    target = tmp_path / "copy"
    shutil.copytree(RECORD, target)
    p = target / "summary.json"
    if mutation in ("data", "coedit"):
        p.write_text(p.read_text() + " ")
        if mutation == "coedit":
            m = json.loads((target / "manifest.json").read_text())
            m["files"]["summary.json"] = {
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
            (target / "manifest.json").write_text(json.dumps(m))
    elif mutation == "missing":
        p.unlink()
    elif mutation == "extra":
        (target / "extra.json").write_text("{}")
    elif mutation == "symlink":
        p.unlink()
        p.symlink_to(RECORD / "summary.json")
    elif mutation == "manifest_symlink":
        (target / "manifest.json").unlink()
        (target / "manifest.json").symlink_to(RECORD / "manifest.json")
    else:
        (target / "manifest.json").write_text('{"schema":1,"schema":2}')
    with pytest.raises((ValueError, OSError)):
        verify(target)


def test_nonfinite_and_duplicate_json_fail(tmp_path):
    p = tmp_path / "bad.json"
    for raw in ('{"x":NaN}', '{"x":Infinity}', '{"x":0,"x":1}'):
        p.write_text(raw)
        with pytest.raises(ValueError):
            read_json(p)
