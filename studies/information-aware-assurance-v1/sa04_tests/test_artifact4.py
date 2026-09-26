import hashlib
import json
import shutil

import pytest

from sa04.artifact import RECORD, verify


def test_complete_committed_artifact():
    assert verify(RECORD)["fixtures"] == 32


@pytest.mark.parametrize(
    "fault", ["data", "coedit", "missing", "extra", "symlink", "manifest_symlink", "duplicate"]
)
def test_integrity_adversaries(tmp_path, fault):
    target = tmp_path / "copy"
    shutil.copytree(RECORD, target)
    p = target / "host.json"
    if fault in ("data", "coedit"):
        p.write_text(p.read_text() + " ")
        if fault == "coedit":
            m = json.loads((target / "manifest.json").read_text())
            m["files"][p.name] = dict(
                bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()
            )
            (target / "manifest.json").write_text(json.dumps(m))
    elif fault == "missing":
        p.unlink()
    elif fault == "extra":
        (target / "unlisted").write_text("x")
    elif fault == "symlink":
        p.unlink()
        p.symlink_to(RECORD / "host.json")
    elif fault == "manifest_symlink":
        (target / "manifest.json").unlink()
        (target / "manifest.json").symlink_to(RECORD / "manifest.json")
    else:
        (target / "manifest.json").write_text('{"schema":1,"schema":2}')
    with pytest.raises((ValueError, OSError)):
        verify(target)
