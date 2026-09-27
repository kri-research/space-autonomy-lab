import hashlib
import json
import shutil

import pytest

from sa06.verify import RECORD, verify

pytestmark = pytest.mark.skipif(
    not (RECORD / "manifest.json").exists(), reason="pre-record source preparation"
)


def test_source_and_record_bindings():
    result = verify()
    assert result["semantic_cases"] == 10
    assert result["original_host_samples"] == 30
    assert not result["host_measurements_repeated"]


@pytest.mark.parametrize("mutation", ["bytes", "coedited_manifest", "extra", "missing", "symlink"])
def test_record_mutations_fail(tmp_path, mutation):
    directory = tmp_path / "record"
    shutil.copytree(RECORD, directory)
    path = directory / "host.json"
    if mutation in ("bytes", "coedited_manifest"):
        path.write_text(path.read_text() + " ")
        if mutation == "coedited_manifest":
            mp = directory / "manifest.json"
            m = json.loads(mp.read_text())
            m["files"]["host.json"] = dict(
                bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            )
            mp.write_text(json.dumps(m))
    elif mutation == "extra":
        (directory / "unexpected.txt").write_text("extra")
    elif mutation == "missing":
        path.unlink()
    else:
        path.unlink()
        path.symlink_to(RECORD / "host.json")
    with pytest.raises((ValueError, OSError)):
        verify(directory)
