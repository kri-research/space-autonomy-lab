import hashlib
import json
import shutil

import pytest

from sa03.artifact import RECORD, verify


def test_current_artifact_and_source_identity():
    assert verify(RECORD)["comparisons"] == 52


@pytest.mark.parametrize(
    "mutation", ["data", "coedited_manifest", "missing", "extra", "symlink", "duplicate_key"]
)
def test_mutations_do_not_pass(tmp_path, mutation):
    target = tmp_path / "copy"
    shutil.copytree(RECORD, target)
    p = target / "summary.json"
    if mutation in ("data", "coedited_manifest"):
        p.write_text(p.read_text() + " ")
        if mutation == "coedited_manifest":
            m = json.loads((target / "manifest.json").read_text())
            m["files"][p.name] = dict(
                bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest()
            )
            (target / "manifest.json").write_text(json.dumps(m))
    elif mutation == "missing":
        p.unlink()
    elif mutation == "extra":
        (target / "unlisted.txt").write_text("unlisted")
    elif mutation == "symlink":
        p.unlink()
        p.symlink_to(RECORD / "summary.json")
    else:
        (target / "manifest.json").write_text('{"schema":1,"schema":2}')
    with pytest.raises((ValueError, OSError)):
        verify(target)
