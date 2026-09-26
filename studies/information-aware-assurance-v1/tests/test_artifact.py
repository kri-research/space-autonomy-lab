import hashlib
import json
import shutil
from pathlib import Path

import pytest

from iaa.artifact import read_json, verify

ROOT = Path(__file__).resolve().parents[1]


def test_recorded_source_and_file_integrity():
    assert verify(ROOT / "recorded")["fixtures"] == 9


@pytest.mark.parametrize(
    "mutation", ["content", "coedited_hash", "missing", "extra", "symlink", "duplicate_json"]
)
def test_artifact_integrity_mutations(tmp_path, mutation):
    dest = tmp_path / "artifact"
    shutil.copytree(ROOT / "recorded", dest)
    if mutation in ("content", "coedited_hash"):
        p = dest / "nominal.jsonl"
        p.write_text(p.read_text() + "\n")
        if mutation == "coedited_hash":
            m = json.loads((dest / "manifest.json").read_text())
            m["files"][p.name] = {
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            (dest / "manifest.json").write_text(json.dumps(m))
    elif mutation == "missing":
        (dest / "summary.json").unlink()
    elif mutation == "extra":
        (dest / "unlisted.json").write_text("{}")
    elif mutation == "symlink":
        (dest / "summary.json").unlink()
        (dest / "summary.json").symlink_to(ROOT / "recorded/summary.json")
    else:
        (dest / "manifest.json").write_text('{"schema":"x","schema":"y"}')
    with pytest.raises(ValueError):
        verify(dest)


def test_nonfinite_json_rejected(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text('{"value":NaN}')
    with pytest.raises(ValueError):
        read_json(p)
