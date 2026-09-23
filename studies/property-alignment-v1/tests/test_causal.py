"""Unit checks; these do not execute a selected new closed-loop study case."""

from fractions import Fraction as Q
import json
import numpy as np
import pytest
from adjudication.interval import Box, Interval
from adjudication.polynomial import PolynomialArc
from specification.contract import Verdict as V
from causal.screen import predicted_box, ControlledGate, screen, inspect_arcs
from causal.native import components
from causal.experiment import ideal_snapshot, archival_call, innovations, packet_update, ARM_NAMES
from causal.qualification import reference
from causal.execute import matrix
from causal.io import PACKAGE, source_hashes


@pytest.mark.parametrize(
    "state,old,aligned",
    [
        ([0, -70, 0, 0], V.SATISFIED, V.SATISFIED),
        ([0, -25, 0, 0], V.SATISFIED, V.VIOLATED),
        ([0, -105, 0, 0], V.SATISFIED, V.VIOLATED),
        ([0, -27, 0, 0], V.SATISFIED, V.SATISFIED),
        ([0, -28, 0, 0], V.SATISFIED, V.SATISFIED),
        ([12, -70, 0, 0], V.VIOLATED, V.VIOLATED),
        ([10, -100, 0, 0], V.SATISFIED, V.SATISFIED),
        ([3, -30, 0, 0], V.SATISFIED, V.SATISFIED),
    ],
)
def test_online_semantics(state, old, aligned):
    assert predicted_box(Box.point(state), "in_band", 10.0)["predicate"] == old
    assert predicted_box(Box.point(state), "closed_union", 10.0)["predicate"] == aligned


@pytest.mark.parametrize("predicate", ["in_band", "closed_union"])
def test_closed_keepout(predicate):
    assert predicted_box(Box.point([0, 10, 0, 0]), predicate, 10.0)["keep_out"] == V.VIOLATED
    assert predicted_box(Box.point([0, 10.001, 0, 0]), predicate, 10.0)["keep_out"] == V.SATISFIED


@pytest.mark.parametrize("predicate", ["in_band", "closed_union"])
def test_missing_and_exhausted_prediction(predicate):
    assert inspect_arcs([], predicate, 10.0)["status"] == "unresolved"
    arc = PolynomialArc(Q(0), Q(1), tuple((Q(v),) for v in [0, -70, 0, 0]))
    assert inspect_arcs([arc, arc], predicate, 10.0, max_cells=1)["status"] == "unresolved"


def test_inband_discontinuity():
    b = Box(
        (Interval(12.0, 12.0), Interval(-100.001, -99.999), Interval(0.0, 0.0), Interval(0.0, 0.0))
    )
    assert predicted_box(b, "in_band", 10.0)["predicate"] == V.UNRESOLVED


def test_same_kernel_except_predicate(monkeypatch):
    cfg, ctrl, *_ = components()
    controller = ctrl.DeterministicHoldController(cfg)
    calls = []

    def stub(mean, command, predicate, radius):
        calls.append((mean.copy(), command.copy(), predicate, radius))
        return {"status": "violated"}

    monkeypatch.setattr("causal.screen.screen", stub)
    snap = ideal_snapshot([0, -70, 0, 0.12], 0)
    proposal = controller.decide(ctrl.observation_from_snapshot(snap))
    out = [ControlledGate(controller, p).gate(snap, proposal) for p in ("in_band", "closed_union")]
    for j in (0, 1):
        np.testing.assert_array_equal(calls[0][j], calls[1][j])
    assert calls[0][3] == calls[1][3] and calls[0][2] != calls[1][2]
    for r, meta in out:
        np.testing.assert_array_equal(r.executed_acceleration_mps2, proposal.acceleration_mps2)
        assert r.overridden and meta["geometry_evaluated"]


@pytest.mark.parametrize(
    "health,reason", [("DEGRADED", "ESTIMATOR_QUALITY"), ("DIVERGED", "ESTIMATOR_DIVERGED")]
)
def test_quality_short_circuit(monkeypatch, health, reason):
    cfg, ctrl, *_ = components()
    controller = ctrl.DeterministicHoldController(cfg)
    snap = ideal_snapshot([0, -70, 0, 0.12], 0)
    snap.health = getattr(ctrl.FilterHealth, health)
    proposal = controller.decide(ctrl.observation_from_snapshot(snap))

    def forbidden(*args):
        raise AssertionError("Unexpected geometry")

    monkeypatch.setattr("causal.screen.screen", forbidden)
    for p in ("in_band", "closed_union"):
        r, meta = ControlledGate(controller, p).gate(snap, proposal)
        assert r.reason == reason and not meta["geometry_evaluated"]


def test_known_rejection_identical_fallback():
    cfg, ctrl, *_ = components()
    controller = ctrl.DeterministicHoldController(cfg)
    snap = ideal_snapshot([0, -25, 0, 0], 0)
    proposal = controller.decide(ctrl.observation_from_snapshot(snap))
    old, _ = ControlledGate(controller, "in_band").gate(snap, proposal)
    new, _ = ControlledGate(controller, "closed_union").gate(snap, proposal)
    assert not old.overridden and new.overridden
    np.testing.assert_array_equal(old.executed_acceleration_mps2, new.executed_acceleration_mps2)


@pytest.mark.parametrize("state", [[0, -70, 0, 0], [0, -25, 0, 0], [0, -30, 0, 0]])
def test_archival_observation_does_not_change_values(state):
    cfg, ctrl, *_ = components()
    controller = ctrl.DeterministicHoldController(cfg)
    snap = ideal_snapshot(state, 0)
    proposal = controller.decide(ctrl.observation_from_snapshot(snap))
    a = ctrl.EstimatedGeometryMonitor(cfg, controller, controller.controller_identity)
    b = ctrl.EstimatedGeometryMonitor(cfg, controller, controller.controller_identity)
    plain = a.gate(snap, proposal)
    observed, meta = archival_call(b, snap, proposal)
    assert meta["geometry_evaluated"]
    assert plain.reason == observed.reason and plain.overridden == observed.overridden
    np.testing.assert_array_equal(
        plain.executed_acceleration_mps2, observed.executed_acceleration_mps2
    )


def test_matrix_and_control_labels():
    p = json.loads((PACKAGE / "protocol.json").read_text())
    runs = matrix(p)
    assert len(runs) == len({(c["id"], m, a) for c, m, a in runs}) == 56
    assert tuple(p["arms"]) == ARM_NAMES
    assert sum(c["role"] == "ideal_main" for c in p["cases"]) == 3
    c = next(c for c in p["cases"] if c["role"] == "unrecoverable_control")
    assert c["initial"][1] == -27 and c["initial"][3] > 0


def test_stream_pairing():
    p = json.loads((PACKAGE / "protocol.json").read_text())
    a, b = innovations(p), innovations(p)
    for k in a:
        np.testing.assert_array_equal(a[k], b[k])
    assert not np.array_equal(a["primary_noise"], a["monitor_noise"])
    assert np.max(np.abs(a["process_acceleration"])) <= 0.0015


def test_observations_follow_own_state():
    cfg, _, _, _, est, _ = components()
    p = json.loads((PACKAGE / "protocol.json").read_text())
    noise = innovations(p)
    case = next(c for c in p["cases"] if c["id"] == "estimated_nominal")
    f1 = [est.PlanarNavigationFilter(cfg) for _ in range(2)]
    f2 = [est.PlanarNavigationFilter(cfg) for _ in range(2)]
    _, a = packet_update(f1, case, np.array([0.0, -97.5, 0.0, 0.12]), 0, noise, p)
    _, b = packet_update(f2, case, np.array([1.0, -95.5, 0.0, 0.12]), 0, noise, p)
    assert a[0]["noise_innovation"] == b[0]["noise_innovation"] and a[0]["packet"] != b[0]["packet"]
    assert not a[0]["fault_window_active"]


@pytest.mark.parametrize("initial", [[0, -97.5, 0, 0.12], [1, -70, 0, 0.08], [0, -30, 0, 0]])
def test_qualification_reference_endpoints(initial):
    q, v, a = reference(initial, 0)
    np.testing.assert_array_equal(q, initial[:2])
    np.testing.assert_array_equal(v, initial[2:])
    q, v, a = reference(initial, 180)
    np.testing.assert_array_equal(q, [0, -30])
    np.testing.assert_array_equal(v, [0, 0])


def test_inventory_includes_scientific_dependencies():
    hashes = source_hashes()
    assert "causal/protocol.json" in hashes and "adjudication/engine.py" in hashes
    assert not any("recorded" in k for k in hashes)


def test_failed_prediction_not_safe():
    assert screen([0, float("nan"), 0, 0], [0, 0], "closed_union", 10.0)["status"] == "unresolved"


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra"])
def test_execution_manifest_rejects_corruption(tmp_path, mutation):
    from causal.io import save_json, manifest
    from causal.verify_records import verify_manifest

    save_json(tmp_path / "data.json", {"value": 1})
    manifest(tmp_path)
    assert verify_manifest(tmp_path) == 1
    if mutation == "changed":
        (tmp_path / "data.json").write_text("{}")
    elif mutation == "missing":
        (tmp_path / "data.json").unlink()
    else:
        (tmp_path / "extra.txt").write_text("extra")
    with pytest.raises(ValueError):
        verify_manifest(tmp_path)


def test_strict_execution_json_rejects_nonfinite(tmp_path):
    from causal.verify_records import strict_json

    path = tmp_path / "bad.json"
    path.write_text('{"v":NaN}')
    with pytest.raises(ValueError):
        strict_json(path)
