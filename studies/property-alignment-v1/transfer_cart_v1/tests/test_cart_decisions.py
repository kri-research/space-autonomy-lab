"""Decision semantics and independent proof checks on analytic fixtures."""

from fractions import Fraction as Q
from pathlib import Path
import ast
import pytest
from transfer_cart_v1.policies import METHODS, decide, check_dual
from transfer_cart_v1.reference import action_check, dual_check
from transfer_cart_v1.schema import NORMALS, digest
from transfer_cart_v1.arithmetic import Interval


def simple():
    return {
        "schema": "sal-lag-cart-case/1",
        "namespace": "calibration",
        "stratum": "analytic",
        "index": 0,
        "generator_seed": "0",
        "tau": "0.3",
        "eta": "1",
        "authority": "0.4",
        "duration": "1",
        "delay": "0.25",
        "disturbance": "0",
        "boxes": [{"lower": ["0"] * 6, "upper": ["0"] * 6}],
        "packet_code": "analytic",
        "measurement_time_s": "0",
    }


@pytest.mark.parametrize("method", METHODS)
def test_origin_admissions_are_rechecked(method):
    c = simple()
    r = decide(c, method, budget_s=60)
    assert "exception" not in r["details"]
    assert r["status"] == "prefix"
    assert action_check(c, r["action"])["status"] == "contained"


def test_mean_and_real_information_are_separate():
    c = simple()
    c["delay"] = "0"
    c["tau"] = "0.1"
    c["boxes"] = []
    for n in NORMALS:
        x = [str(s * v) for s in (Q(".95"), Q(".1"), Q(0)) for v in n]
        c["boxes"].append({"lower": x, "upper": x})
    candidate = decide(c, budget_s=60)
    assert candidate["status"] == "obstruction"
    assert dual_check(c, candidate["details"]["obstruction"]["weights"])["proved"]
    mean = decide(c, "mean_only_prefix", budget_s=60)
    assert mean["status"] == "prefix"
    assert action_check(c, mean["action"])["status"] == "violation"


def test_late_answer_is_never_delivered():
    c = simple()
    r = decide(c, budget_s=1e-8)
    assert r["status"] == "budget_miss" and r["action"] is None and not r["on_time"]


@pytest.mark.parametrize("weights", [[], [-1, 1], [0, 0]])
def test_invalid_dual(weights):
    assert not check_dual(
        [(Interval.of(1), Interval.of(0)), (Interval.of(-1), Interval.of(0))],
        [Interval.of(-1), Interval.of(-1)],
        weights,
        Q(".4"),
    )["proved"]


def test_exact_dual_with_rounding_residual():
    rows = [(Interval.of(1), Interval.of(0)), (Interval.of(-1), Interval.of(0))]
    assert check_dual(rows, [Interval.of(-1), Interval.of(-1)], [Q(1, 2)] * 2, Q(".4"))["proved"]
    assert not check_dual(rows, [Interval.of(1), Interval.of(1)], [Q(1, 2)] * 2, Q(".4"))["proved"]


def test_source_does_not_use_original_orbital_code():
    root = Path(__file__).resolve().parents[1]
    forbidden = ("candidate", "protective", "adjudication", "evaluation", "qualification_repair")
    for name in ("lag.py", "policies.py", "reference.py", "schema.py"):
        tree = ast.parse((root / name).read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                assert not (n.module or "").startswith(forbidden)
            if isinstance(n, ast.Import):
                assert not any(a.name.startswith(forbidden) for a in n.names)


def test_recorded_input_metadata_rejects_boolean():
    from transfer_cart_v1.audit import verify_row

    c = simple()
    row = {
        "case_id": digest(c),
        "namespace": c["namespace"],
        "stratum": c["stratum"],
        "index": False,
        "execution_failure": {"retry": False},
    }
    with pytest.raises(ValueError):
        verify_row(c, row)


def test_reference_negative_actual_lag_rejected():
    with pytest.raises(ValueError):
        action_check(simple(), (0, 0), actual_tau=-1)


def test_atomic_result_cannot_overwrite(tmp_path):
    from transfer_cart_v1.experiment import atomic

    p = tmp_path / "result.json"
    atomic(p, {"x": 1})
    before = p.read_bytes()
    with pytest.raises(FileExistsError):
        atomic(p, {"x": 2})
    assert p.read_bytes() == before
