"""Manifest and post-solve validation negative fixtures; no new campaign."""

import hashlib
import json
from types import SimpleNamespace
import numpy as np
import pytest
from protective.artifact import check_manifest, read, plan_residual
from protective.common import Tube, MODEL_COMPONENT, NUMERIC_COMPONENT
from protective.solver import solver_diagnostics


@pytest.mark.parametrize("mutation", ["extra", "missing", "changed", "nonfinite"])
def test_manifest_or_json_corruption_fails(tmp_path, mutation):
    p = tmp_path / "result.json"
    p.write_text('{"answer":1}')
    (tmp_path / "manifest.json").write_text(
        json.dumps({"result.json": hashlib.sha256(p.read_bytes()).hexdigest()})
    )
    assert check_manifest(tmp_path) == 1
    if mutation == "extra":
        (tmp_path / "extra.json").write_text("{}")
    if mutation == "missing":
        p.unlink()
    if mutation == "changed":
        p.write_text('{"answer":2}')
    if mutation == "nonfinite":
        p.write_text('{"answer":NaN}')
        with pytest.raises(ValueError):
            read(p)
    else:
        with pytest.raises(ValueError):
            check_manifest(tmp_path)


def test_missing_backend_is_not_optimal():
    r = solver_diagnostics(SimpleNamespace(_solver_cache={}))
    assert not r["optimality_residual_check"]


def test_excessive_duality_gap_is_not_optimal():
    value = SimpleNamespace(r_prim=0.0, r_dual=0.0, obj_val=2.0, obj_val_dual=0.0, status="Solved")
    r = solver_diagnostics(
        SimpleNamespace(_solver_cache={"CLARABEL": SimpleNamespace(get_solution=lambda: value)})
    )
    assert not r["optimality_residual_check"]


def test_bad_plan_is_not_repaired_to_pass():
    tube = Tube(np.zeros(4), MODEL_COMPONENT + NUMERIC_COMPONENT)
    p = {
        "u": [[1.0, 0.0], [1.0, 0.0]],
        "switch": 1,
        "r0": 0.0,
        "initial_estimate": [0.0, -30.0, 0.0, 0.0],
        "terminal_z": [0.0, 0.0, 0.0, 0.0],
    }
    with pytest.raises(ValueError):
        plan_residual(p, tube)
