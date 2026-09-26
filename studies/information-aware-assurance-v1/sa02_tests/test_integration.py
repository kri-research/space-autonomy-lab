import ast
from dataclasses import replace
from fractions import Fraction as Q
from pathlib import Path

import pytest

from iaa.fixtures import Fixture
from iaa.plant import SensorFaults, flow, observe
from iaa.types import ObservationPacket, StateBox, encode
from sa02.estimator import Observer
from sa02.model import HistorySegment, SensorContract
from sa02.runtime import run


def test_integrated_loop_and_replay_are_causal():
    f = Fixture("sa02-wiring", horizon_ms=2000, additional_request_ms=())
    a, events, timings = run(f)
    b, again, _ = run(f)
    assert a == b and encode(events) == encode(again)
    assert a["observation_updates"] == 4 and len(timings) == 4
    assert all(type(t) is int and t > 0 for t in timings)
    assert a["observed_true_state_exclusions"] == 0
    assert a["model_containment_via_continuous_tubes"]
    arrivals = {}
    for r in events:
        if r.event == "observation_available":
            arrivals[r.details["packet"]["packet_id"]] = r.at_ms
        elif r.event == "decision_snapshot":
            assert r.details["measurement_set_update"] == "updated"
            assert all(arrivals[p] <= r.at_ms for p in r.details["proposal"]["packet_ids"])
            assert r.details["observation_set"]["at_ms"] == r.at_ms
    assert a["physical_execution"] is False


@pytest.mark.parametrize("j", range(24))
def test_supported_moving_trajectory_and_bias_remain_in_outer_union(j):
    # Exposed deterministic numerical corroboration, not sensor calibration.
    x = (0.2 * (j % 3 - 1), -44.0, 0.01 * (j % 2), -0.01 * (j % 3))
    u = (Q((j % 3) - 1, 100), Q((j % 2), 100))
    eta = 0.8 if j % 2 else 1.0
    exact = flow(x, u, 0.501, eta)
    faults = SensorFaults(
        start_ms=0,
        end_ms=10000,
        common_position_bias_m=(0.3, -0.2),
        range_bias_m=0.25,
        bearing_bias_rad=0.01,
    )
    packets, _ = observe(exact, 500, 0, faults)
    packets = tuple(replace(p, available_ms=550 if p.channel == "range" else 570) for p in packets)
    box = StateBox.around(x, (0.01, 0.01, 0.002, 0.002))
    e = Observer(box).update(packets, (HistorySegment(0, 600, u),), 600)
    assert e.status == "updated" and e.contains_state(flow(x, u, 0.6, eta))


def test_replayed_bias_window_onset_and_end():
    x = (0, -45, 0, 0)
    o = Observer(StateBox.around(x, (0.05, 0.05, 0.002, 0.002)))
    faults = SensorFaults(
        common_position_bias_m=(0.3, 0.2), range_bias_m=0.3, bearing_bias_rad=0.01
    )
    for k, t in enumerate((4998, 5000, 5002, 9998, 10000, 10002)):
        packets, _ = observe(x, t, k, faults)
        e = o.update(packets, (HistorySegment(0, t + 100, (0, 0)),), t + 100)
        assert e.cells and e.contains_state(x)
        assert "window_shared_and_channels" in e.diagnostics["hypotheses"]


def test_exact_sensor_error_bound_keeps_boundary_state():
    x = (0, -45, 0, 0)
    box = StateBox.around(x, (0, 0, 0, 0))
    from sa02.intervals import interval
    from sa02.model import FaultHypothesis

    con = SensorContract(
        hypotheses=(FaultHypothesis("no_bias", (interval(0),) * 4),), initial_splits=0
    )
    for value in (44.99, 45.01):
        p = ObservationPacket("range", 0, "range", value, 0, 0, timestamp_uncertainty_ms=0)
        e = Observer(box, con).update((p,), (), 0)
        assert e.status == "updated" and e.contains_state(x)


def test_reference_modules_cannot_be_seen_by_online_estimator():
    root = Path(__file__).resolve().parents[1] / "sa02"
    for name in ("estimator.py", "model.py", "intervals.py", "bridge.py"):
        tree = ast.parse((root / name).read_text())
        modules = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(
            any(s in m for s in ("plant", "oracle", "runtime", "fixtures")) for m in modules
        )


def test_new_horizon_is_explicit_not_a_changed_original_fixture():
    f = Fixture("nominal")
    assert f.horizon_ms == 30000 and f.additional_request_ms == (7250,)
    e = Observer(f.initial_box()).update((), (), 30001)
    assert e.status == "unsupported_time" and not e.cells
