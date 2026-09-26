from copy import deepcopy

import pytest

from sa04 import wire
from sa04.compute import check_action
from sa04.fixtures import at_time, initial_input
from sa04.service import answer


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{",
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e9999}',
        b'{"x":1,"x":2}',
        b"[" * 30 + b"0" + b"]" * 30,
        b" " * (wire.MAX_BYTES + 1),
    ],
)
def test_invalid_framing(raw):
    with pytest.raises((ValueError, RecursionError)):
        wire.loads(raw)


@pytest.mark.parametrize(
    "value", [True, "1e99999999", "9" * 1000, "1/0", float("nan"), float("inf")]
)
def test_bounded_numbers(value):
    with pytest.raises((ValueError, ZeroDivisionError)):
        wire.number(value)


def test_canonical_binding_and_mismatch():
    raw, _ = initial_input()
    req = wire.request("check", 0, dict(input=at_time(raw, 650, ()), action=["0", "0"]))
    assert wire.validate_request(wire.loads(wire.dumps(req))) == req
    for field, value in (
        ("schema", "old"),
        ("mode", "physical"),
        ("sequence", True),
        ("model", {}),
        ("payload_sha256", "x"),
    ):
        bad = deepcopy(req)
        bad[field] = value
        with pytest.raises(ValueError):
            wire.validate_request(bad)
    with pytest.raises(ValueError):
        answer(req, "plan")


@pytest.mark.parametrize("field", ["initial", "sensors", "timing"])
def test_unknown_nested_fields_fail(field):
    raw, _ = initial_input()
    raw = at_time(raw, 650, ())
    raw[field]["surprise"] = True
    with pytest.raises(ValueError):
        check_action(dict(input=raw, action=["0", "0"]))


def test_nonfinite_cannot_hide_in_json_string():
    raw, _ = initial_input()
    raw["initial"]["lower"][0] = "1e99999999"
    with pytest.raises(ValueError):
        check_action(dict(input=raw, action=["0", "0"]))


def test_request_cannot_mutate_shared_model_definition():
    before = deepcopy(wire.MODEL)
    try:
        req = wire.request("plan", 0, {})
        req["model"]["application_window_ms"][1] = 9999
        assert wire.MODEL == before
    finally:
        wire.MODEL.clear()
        wire.MODEL.update(before)
