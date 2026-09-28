from copy import deepcopy
from fractions import Fraction as Q
from importlib import import_module

import pytest

INVALID = [
    "1e10000",
    "1e-10000",
    "1E1000000",
    "1_000",
    " 45",
    "45 ",
    "1/0",
    "1/-2",
    "+",
    ".5",
    "9" * 1000,
    "0/" + "9" * 1000,
    True,
    False,
    float("nan"),
    float("inf"),
    -float("inf"),
    10**9 + 1,
    10**2000,
    1e10,
    "1000000001",
    [],
    {},
    None,
    "０",
]


@pytest.mark.parametrize("route", ["helper", "assess", "estimate", "decoder"])
@pytest.mark.parametrize("value", INVALID, ids=lambda v: str(type(v).__name__))
def test_invalid_observation_rejected_before_fraction(
    component, request_data, monkeypatch, route, value
):
    numeric = import_module("kri_assurance_eval._numeric")
    wire = import_module("kri_assurance_eval._vendor.sa04.wire")
    packet = component.observation_packet("bounded", 0, "range", 45.0, 0, 40)
    packet["value"] = value
    req = deepcopy(request_data)
    req["current_input"]["packets"] = [packet]
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("Unvalidated scalar reached Fraction")

    monkeypatch.setattr(numeric, "Fraction", forbidden)
    if route == "assess":
        assert component.assess(req)["status"] == "unsupported_input"
    else:
        with pytest.raises(ValueError):
            if route == "helper":
                component.observation_packet("bad", 0, "range", value, 0, 40)
            elif route == "estimate":
                component.estimate_snapshot(req["current_input"])
            else:
                wire.packets([packet])
    assert calls == []


@pytest.mark.parametrize("value", [45, 45.0, "45", "45.0", "90/2", "+45", Q(45)])
def test_supported_encodings_construct_decode_and_assess(component, request_data, value):
    packet = component.observation_packet("valid", 0, "range", value, 250, 290)
    req = deepcopy(request_data)
    req["current_input"]["packets"] = [packet]
    assert component.assess(req)["status"] == "supported_prefix"
    estimated = component.estimate_snapshot(req["current_input"])
    assert estimated["status"] == "updated"
    assert Q(str(packet["value"])) == 45


@pytest.mark.parametrize(
    "value", [0, -0.0, 10**9, 1e9, "1000000000", "1/" + "9" * 80, "0." + "0" * 29 + "1", 1e-100]
)
def test_numeric_boundary_valid(component, value):
    f = import_module("kri_assurance_eval._numeric").observation_value
    assert Q(str(f(value))) == Q(str(value))


@pytest.mark.parametrize("value", [Q(1, 10**1000), Q(10**1000), 5e-324, "1/" + "9" * 81])
def test_excess_rational_scale_fails(component, value):
    with pytest.raises(ValueError):
        component.observation_packet("scale", 0, "range", value, 0, 40)


@pytest.mark.parametrize("channel,value", [("range", -1), ("bearing", 4), ("bearing", "-4")])
def test_geometry_checks_remain(component, channel, value):
    with pytest.raises(ValueError):
        component.observation_packet("geometry", 0, channel, value, 0, 40)


def test_rational_normalization_is_exact(component):
    packet = component.observation_packet("exact", 0, "bearing", "1/3", 0, 40)
    assert packet["value"] == "1/3"
    wire = import_module("kri_assurance_eval._vendor.sa04.wire")
    assert wire.packets([packet])[0].value == Q(1, 3)


def test_float_identity_not_changed(component):
    packet = component.observation_packet("float", 0, "range", 45.125, 0, 40)
    assert type(packet["value"]) is float and packet["value"] == 45.125


def test_prior_snapshot_also_preflighted(component, request_data):
    packet = component.observation_packet("bad", 0, "range", 45.0, 0, 40)
    packet["value"] = "1e1000000"
    request_data["initial_input"]["packets"] = [packet]
    assert component.assess(request_data)["status"] == "unsupported_input"
