import hashlib
import json
import shutil
from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest

from post_audit_v1.assemble import REVIEWED, STUDY, source_bindings
from post_audit_v1.verify import RECORD, verify


def test_inherited_example_results_unchanged_except_new_identity(component):
    from kri_assurance_eval.examples import examples

    original = json.loads((STUDY / "sa06/recorded/host.json").read_text())
    old = {r["name"]: r["result"] for r in original["samples"]}

    def semantic(result):
        return {
            k: v
            for k, v in result.items()
            if k not in {"component_version", "source_commit", "request_sha256"}
        }

    for case in examples():
        assert semantic(component.assess(case["request"])) == semantic(old[case["name"]])


def test_installation_mutation_detected(component):
    integrity = import_module("kri_assurance_eval.integrity")
    path = Path(integrity.__file__).parent / "_numeric.py"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n# changed\n")
        with pytest.raises(ValueError):
            integrity.verify_installation()
    finally:
        path.write_bytes(original)
    assert integrity.verify_installation()["component_version"] == "0.1.1"


def test_new_sources_cannot_be_attributed_to_reviewed_baseline():
    with pytest.raises(ValueError):
        source_bindings(REVIEWED)


def test_published_probes(component):
    from post_audit_v1.probes import evaluate

    out = evaluate()
    assert len(out["numeric"]) == 4
    assert all(r["fractional_constructions"] == 0 for r in out["numeric"])
    assert out["observer"]["future_cells_equal"]
    assert len(out["examples"]) == 10
    assert out["physical_validation"] is False


@pytest.mark.skipif(
    not (RECORD / "manifest.json").is_file(), reason="Source frozen before new evidence recording"
)
def test_current_record_reproduces():
    result = verify()
    assert result["posthoc_in_model_cases"] == 96
    assert result["component_version"] == "0.1.1"


@pytest.mark.skipif(
    not (RECORD / "manifest.json").is_file(), reason="Source frozen before new evidence recording"
)
@pytest.mark.parametrize("mutation", ["data", "coedited_manifest", "extra", "missing", "symlink"])
def test_changed_record_fails(tmp_path, mutation):
    directory = tmp_path / "copy"
    shutil.copytree(RECORD, directory)
    path = directory / "probes.json"
    if mutation in ("data", "coedited_manifest"):
        path.write_bytes(path.read_bytes() + b" ")
        if mutation == "coedited_manifest":
            manifest = directory / "manifest.json"
            value = json.loads(manifest.read_text())
            value["files"]["probes.json"] = dict(
                bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            )
            manifest.write_text(json.dumps(value))
    elif mutation == "extra":
        (directory / "unexpected.txt").write_text("unexpected")
    elif mutation == "missing":
        path.unlink()
    else:
        path.unlink()
        path.symlink_to(RECORD / "probes.json")
    with pytest.raises(ValueError):
        verify(directory)


def test_changed_contract_is_rejected(component, request_data):
    for part, value in [("component_version", "0.1.0"), ("mode", "physical")]:
        request = deepcopy(request_data)
        request["contract"][part] = value
        assert component.assess(request)["status"] == "unsupported_input"
