"""Strict bounded JSON transport; identity checks are not authentication."""

import math
import re
from copy import deepcopy
from dataclasses import fields
from fractions import Fraction

from iaa.types import ObservationPacket, StateBox, encode, identity
from sa02.intervals import Interval
from sa02.model import FaultHypothesis, HistorySegment, SensorContract
from sa03.model import Timing

from .legacy import protocol

MAX_BYTES = protocol.MAX_PACKET_BYTES
MODEL = {
    "id": "sa04-HCW-window/1",
    "mean_motion_rad_s": "11/10000",
    "effectiveness": ["4/5", "1"],
    "disturbance_mps2": "1/100000",
    "authority_mps2": "1/50",
    "frame": "chief-centred-radial-alongtrack/1",
    "obligation": "continuous_prefix_hold_and_finite_coast",
    "application_window_ms": [700, 710],
    "command_end_ms": 1200,
    "expires_ms": 4200,
    "clock": "single_host_monotonic_relative_epoch",
    "physical_io": False,
}


def exact(obj, keys):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise ValueError("Unexpected schema fields")
    return obj


def bounded(obj, depth=0):
    if depth > 24:
        raise ValueError("Object nesting limit")
    if obj is None or type(obj) is bool:
        return
    if type(obj) is str:
        if len(obj) > 512:
            raise ValueError("String limit")
    elif type(obj) is int:
        if obj.bit_length() > 256:
            raise ValueError("Integer limit")
    elif type(obj) is float:
        if not math.isfinite(obj):
            raise ValueError("Nonfinite numeric value")
    elif type(obj) in (list, dict):
        if len(obj) > 1024:
            raise ValueError("Collection limit")
        for x in obj.values() if isinstance(obj, dict) else obj:
            bounded(x, depth + 1)
    else:
        raise ValueError("Unsupported wire value")


def loads(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Byte framing limit")
    obj = protocol.strict_load(raw)
    bounded(obj)
    return obj


def dumps(obj):
    raw = encode(obj).encode()
    loads(raw)
    return raw


def request(operation, sequence, payload, session="deterministic-fixture"):
    if operation not in ("plan", "check"):
        raise ValueError("Operation")
    protocol.integer(sequence)
    return dict(
        schema="iaa-execution-request/4",
        mode="simulation_only",
        operation=operation,
        sequence=sequence,
        session=session,
        payload=payload,
        payload_sha256=identity(payload),
        model=deepcopy(MODEL),
    )


def validate_request(obj):
    exact(
        obj,
        (
            "schema",
            "mode",
            "operation",
            "sequence",
            "session",
            "payload",
            "payload_sha256",
            "model",
        ),
    )
    if obj["schema"] != "iaa-execution-request/4" or obj["mode"] != "simulation_only":
        raise ValueError("Execution scope")
    if obj["model"] != MODEL or obj["operation"] not in ("plan", "check"):
        raise ValueError("Model or operation mismatch")
    protocol.integer(obj["sequence"])
    if not isinstance(obj["session"], str) or not 1 <= len(obj["session"]) <= 64:
        raise ValueError("Session identity")
    if obj["payload_sha256"] != identity(obj["payload"]):
        raise ValueError("Corrupted payload")
    return obj


def decode_dataclass(cls, raw, **changes):
    exact(raw, (f.name for f in fields(cls)))
    return cls(**(raw | changes))


def number(value):
    if type(value) is str and not re.fullmatch(
        r"[+-]?[0-9]{1,80}(?:/[0-9]{1,80}|\.[0-9]{1,30})?", value
    ):
        raise ValueError("Unsupported rational spelling or size")
    if type(value) not in (int, float, str):
        raise ValueError("Finite numeric field required")
    if type(value) is float and (not math.isfinite(value) or abs(value) > 1e9):
        raise ValueError("Numeric magnitude limit")
    result = Fraction(str(value))
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 512:
        raise ValueError("Rational bit-size limit")
    return result


def initial(raw):
    return decode_dataclass(
        StateBox,
        raw,
        lower=tuple(number(v) for v in raw["lower"]),
        upper=tuple(number(v) for v in raw["upper"]),
        units=tuple(raw["units"]),
    )


def sensors(raw):
    hypotheses = []
    for h in raw["hypotheses"]:
        biases = tuple(
            Interval(number(exact(b, ("lo", "hi"))["lo"]), number(b["hi"])) for b in h["biases"]
        )
        hypotheses.append(decode_dataclass(FaultHypothesis, h, biases=biases))
    return decode_dataclass(
        SensorContract,
        raw,
        hypotheses=tuple(hypotheses),
        range_error_m=number(raw["range_error_m"]),
        bearing_error_rad=number(raw["bearing_error_rad"]),
    )


def packets(raw):
    if not isinstance(raw, list) or len(raw) > 128:
        raise ValueError("Packet count limit")
    return tuple(decode_dataclass(ObservationPacket, p) for p in raw)


def history(raw):
    if not isinstance(raw, list) or len(raw) > 256:
        raise ValueError("History count limit")
    return tuple(
        decode_dataclass(HistorySegment, s, action=tuple(number(v) for v in s["action"]))
        for s in raw
    )


def timing(raw):
    t = decode_dataclass(Timing, raw)
    if (t.now_ms, t.first_apply_ms, t.acquire_ms, t.apply_ms, t.end_ms) != (
        100,
        200,
        250,
        700,
        4200,
    ):
        raise ValueError("SA04 does not shift the inherited timeline")
    return t
