import math
from dataclasses import replace
from fractions import Fraction as Q

import pytest

from iaa.controller import Baseline
from iaa.plant import SensorFaults, flow, observe
from iaa.types import Command, ObservationPacket, StateBox, Uncertainty, rational


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, None, [], "NaN"])
def test_reject_nonfinite_or_nonreal(bad):
    with pytest.raises((ValueError, ZeroDivisionError)):
        rational(bad)


@pytest.mark.parametrize(
    "kw",
    [
        {"unit": "degrees"},
        {"frame": "inertial"},
        {"schema": "old"},
        {"acquired_ms": 100, "available_ms": 50},
        {"value": -1},
        {"sequence": True},
        {"timestamp_uncertainty_ms": -1},
        {"packet_id": ""},
    ],
)
def test_packet_contract(kw):
    values = dict(
        packet_id="p", sequence=0, channel="range", value=40.0, acquired_ms=0, available_ms=70
    )
    values.update(kw)
    with pytest.raises(ValueError):
        ObservationPacket(**values)


@pytest.mark.parametrize(
    "kw",
    [
        {"acceleration": (0.02, 0.02)},
        {"acceleration": (0.02001, 0)},
        {"unit": "m"},
        {"frame": "body"},
        {"apply_ms": True},
        {"end_ms": 0},
        {"schema": "old"},
    ],
)
def test_command_contract(kw):
    values = dict(acceleration=(0, 0), apply_ms=0, end_ms=500, request_id="r")
    values.update(kw)
    with pytest.raises(ValueError):
        Command(**values)


def test_state_units_membership_and_uncertainty_scope():
    box = StateBox.around((0, -45, 0, 0), (1, 1, 0.1, 0.1))
    assert box.contains((1, -46, 0.1, -0.1))
    assert not box.contains((2, -45, 0, 0))
    with pytest.raises(ValueError):
        replace(box, units=("km", "km", "km/s", "km/s"))
    with pytest.raises(ValueError):
        StateBox((0, 0, 0, 0), (-1, 1, 1, 1))
    with pytest.raises(ValueError):
        Uncertainty(box, 0, kind="covariance_only")


def test_range_bearing_convention_round_trip():
    for state in [(1, -45, 0, 0), (-2, -35, 0, 0), (3, 4, 0, 0)]:
        pair, _ = observe(state, 0, 0, SensorFaults())
        r, b = pair
        assert math.isclose(r.value * math.cos(b.value), state[0], abs_tol=1e-12)
        assert math.isclose(r.value * math.sin(b.value), state[1], abs_tol=1e-12)
        assert r.unit == "m" and b.unit == "rad"


def test_shared_error_is_cartesian_before_both_measurements():
    state = (1, -45, 0, 0)
    fault = SensorFaults(start_ms=0, common_position_bias_m=(2, 3))
    pair, _ = observe(state, 0, 0, fault)
    r, b = pair
    assert math.isclose(r.value * math.cos(b.value), 3, abs_tol=1e-12)
    assert math.isclose(r.value * math.sin(b.value), -42, abs_tol=1e-12)
    assert not hasattr(r, "truth") and not hasattr(r, "fault")


def test_fault_window_and_channel_dropout():
    f = SensorFaults(start_ms=500, end_ms=1000, dropout_range=True)
    assert len(observe((1, -45, 0, 0), 490, 0, f)[0]) == 2
    packets, lost = observe((1, -45, 0, 0), 500, 1, f)
    assert len(packets) == 1 and packets[0].channel == "bearing"
    assert lost[0]["reason"] == "simulated_dropout"
    assert len(observe((1, -45, 0, 0), 1000, 2, f)[0]) == 2


def test_bad_timestamp_and_nonfinite_do_not_reach_controller():
    f = SensorFaults(start_ms=0, invalid_range=True, stamp_offset_ms=1000)
    packets, lost = observe((1, -45, 0, 0), 0, 0, f)
    assert packets == () and len(lost) == 2


def test_future_and_stale_packets_are_not_used():
    pair, _ = observe((1, -45, 0, 0), 0, 0, SensorFaults())
    for now in [0, 60, 700]:
        p = Baseline().propose(pair, now, now + 100, now + 600)
        assert p.choice == "protect" and not p.packet_ids
    p = Baseline().propose(pair, 100, 200, 700)
    assert p.choice == "execute" and len(p.packet_ids) == 2
    assert sum(x * x for x in p.command.acceleration) <= Q(1, 50) ** 2


def test_controller_uses_matching_epochs_and_is_replayable():
    pair, _ = observe((1, -45, 0, 0), 0, 0, SensorFaults())
    mixed = (pair[0], replace(pair[1], sequence=1))
    assert Baseline().propose(mixed, 100, 200, 700).choice == "protect"
    assert Baseline().propose(pair, 100, 200, 700) == Baseline().propose(pair, 100, 200, 700)


def test_stationary_alongtrack_point_and_zero_gravity_specialization():
    assert flow((0, -45, 0, 0), (0, 0), 50) == (0, -45, 0, 0)
    assert flow((1, 2, 3, 4), (0.1, -0.2), 2, n=0) == pytest.approx((7.2, 9.6, 3.2, 3.6))
