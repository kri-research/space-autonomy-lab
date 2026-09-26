import hashlib
import json
import shutil

import pytest

from iaa.types import encode
from sa05 import artifact
from sa05.analysis import summarize
from sa05.design import METHODS, STRATA


def test_held_execution_requires_a_public_deposit(tmp_path):
    with pytest.raises(ValueError, match="deposit"):
        artifact.record(tmp_path / "fresh", "held_out")
    assert not (tmp_path / "fresh").exists()


def test_no_existing_output_or_checkout_can_be_overwritten(tmp_path):
    for output in (tmp_path, artifact.PACKAGE / "forbidden"):
        with pytest.raises(ValueError, match="directory"):
            artifact.record(output, "development")


@pytest.mark.parametrize("mutation", ["bytes", "missing", "extra", "symlink"])
def test_data_membership_and_identity_fail_closed(tmp_path, mutation):
    p = tmp_path / "data.json"
    p.write_text("{}\n")
    (tmp_path / "manifest.json").write_text("{}")
    m = {
        "files": {
            "data.json": {
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
        }
    }
    artifact.verify_files(tmp_path, m)
    if mutation == "bytes":
        p.write_text('{"x":1}')
    elif mutation == "missing":
        p.unlink()
    elif mutation == "extra":
        (tmp_path / "unexpected").write_text("x")
    else:
        target = tmp_path.parent / (tmp_path.name + "-outside")
        target.write_text("{}\n")
        p.unlink()
        p.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        artifact.verify_files(tmp_path, m)


def test_all_missing_outcomes_are_accounted_without_physical_failure_claim():
    cases = [dict(unit=s, stratum=s) for s in STRATA]
    rows = [
        dict(unit=s, method=m, stratum=s, status="infrastructure_timeout")
        for s in STRATA
        for m in METHODS
    ]
    result = summarize(cases, rows)
    assert result["scheduled"] == 12 and result["completed"] == 0
    assert all(r["exact_p"] is None for r in result["primary"])
    assert all(r["constraints"] == {} and r["missing"] == 1 for r in result["absolute"])


def test_declared_measurement_dimensions_cannot_silently_use_other_units():
    from sa05.design import DEVELOPMENT_SEED, make_case
    from sa05.experiment import packet

    case = make_case(DEVELOPMENT_SEED, "development", "nominal", 998)
    r = packet(case, (0, -45, 0, 0), "range", 250)[0]
    b = packet(case, (0, -45, 0, 0), "bearing", 250)[0]
    assert r.unit == "m" and b.unit == "rad"
    assert 44 < r.value < 46 and -1.58 < b.value < -1.56


def test_positive_artifact_when_record_exists():
    if not artifact.PUBLIC.exists():
        pytest.skip("Prospective source deposit contains no held-out outcomes")
    assert artifact.verify(artifact.PUBLIC)["passed"]


@pytest.mark.parametrize("mutation", ["coedited_manifest", "manifest_symlink", "duplicate_key"])
def test_committed_record_mutations_fail(tmp_path, mutation):
    if not artifact.PUBLIC.exists():
        pytest.skip("Prospective source deposit contains no held-out outcomes")
    target = tmp_path / "copy"
    shutil.copytree(artifact.PUBLIC, target)
    m = target / "manifest.json"
    if mutation == "coedited_manifest":
        p = target / "analysis.json"
        p.write_text(p.read_text() + " ")
        value = json.loads(m.read_text())
        value["files"]["analysis.json"] = {
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
        m.write_text(encode(value))
    elif mutation == "manifest_symlink":
        m.unlink()
        m.symlink_to(artifact.PUBLIC / "manifest.json")
    else:
        m.write_text('{"schema":1,"schema":2}')
    with pytest.raises((ValueError, OSError)):
        artifact.verify(target)
