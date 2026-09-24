"""Strict data-only parser for exact information and stored certificate bindings."""

from dataclasses import dataclass, replace
from fractions import Fraction as Q
from itertools import product
import hashlib
import json
import math
import re
from .arithmetic import rational, Interval

PATTERN = "no new distinguishing observation before this held command ends"
FIELDS = {
    "schema",
    "hypotheses",
    "age",
    "delay",
    "queue",
    "authority",
    "effectiveness",
    "disturbance",
    "kind",
    "units",
    "command_period_s",
    "observation_pattern",
}


class InvalidEvidence(ValueError):
    pass


class UnsupportedAssumption(ValueError):
    pass


def require(test, message):
    if not test:
        raise InvalidEvidence(message)


def strict_json(raw):
    require(
        isinstance(raw, (str, bytes)) and len(raw) <= 32 * 1024 * 1024, "JSON packet limit/type"
    )

    def pairs(rows):
        result = {}
        for k, v in rows:
            require(k not in result, "Duplicate JSON key")
            result[k] = v
        return result

    def bad(v):
        raise InvalidEvidence("Nonfinite JSON")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    except (ValueError, RecursionError) as exc:
        raise InvalidEvidence("Malformed JSON") from exc

    def walk(x, depth=0):
        require(depth <= 64, "JSON nesting limit")
        if isinstance(x, float):
            require(math.isfinite(x), "Nonfinite number")
        if isinstance(x, dict):
            for v in x.values():
                walk(v, depth + 1)
        if isinstance(x, list):
            for v in x:
                walk(v, depth + 1)

    walk(value)
    return value


def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(doc):
    return hashlib.sha256(canonical(doc)).hexdigest()


def exact(value):
    require(
        type(value) is str
        and len(value) <= 4096
        and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?", value) is not None,
        "Expected canonical rational string without exponential expansion",
    )
    try:
        q = rational(value)
    except ValueError as exc:
        raise InvalidEvidence("Malformed rational") from exc
    require(str(q) == value, "Noncanonical rational representation")
    require(abs(q) <= 10**12, "Numeric resource domain")
    return q


def vector(value, n):
    require(type(value) is list and len(value) == n, "Vector dimension/type")
    return tuple(exact(x) for x in value)


def action(values, authority):
    u = vector(values, 2)
    require(sum(v * v for v in u) <= authority**2, "Exact command authority exceeded")
    return u


@dataclass(frozen=True)
class Box:
    lower: tuple
    upper: tuple

    def contains(self, x):
        return len(x) == 4 and all(
            a <= v <= b for a, v, b in zip(self.lower, x, self.upper, strict=True)
        )

    def intervals(self):
        return tuple(Interval.bounds(a, b) for a, b in zip(self.lower, self.upper, strict=True))

    def vertices(self):
        return tuple(
            sorted(
                set(
                    product(
                        *[
                            tuple(sorted({a, b}))
                            for a, b in zip(self.lower, self.upper, strict=True)
                        ]
                    )
                )
            )
        )

    def payload(self):
        return {"lower": list(map(str, self.lower)), "upper": list(map(str, self.upper))}


@dataclass(frozen=True)
class Info:
    hypotheses: tuple
    age: int
    delay: int
    queue: tuple
    authority: Q
    effectiveness: tuple
    disturbance: Q
    kind: str

    @property
    def D(self):
        return self.age + self.delay

    def payload(self):
        return {
            "schema": "sal-common-information/1",
            "hypotheses": [b.payload() for b in self.hypotheses],
            "age": self.age,
            "delay": self.delay,
            "queue": [list(map(str, u)) for u in self.queue],
            "authority": str(self.authority),
            "effectiveness": list(map(str, self.effectiveness)),
            "disturbance": str(self.disturbance),
            "kind": self.kind,
            "units": ["m", "m", "m/s", "m/s"],
            "command_period_s": 1,
            "observation_pattern": PATTERN,
        }

    def identity(self):
        return identity(self.payload())

    def singleton(self, i):
        return replace(self, hypotheses=(self.hypotheses[i],))


def read_info(doc):
    require(type(doc) is dict and set(doc) == FIELDS, "Information fields")
    require(doc["schema"] == "sal-common-information/1", "Information schema")
    require(
        doc["units"] == ["m", "m", "m/s", "m/s"]
        and type(doc["command_period_s"]) is int
        and doc["command_period_s"] == 1,
        "Units/order/command period",
    )
    require(doc["observation_pattern"] == PATTERN, "Observation schedule")
    require(
        type(doc["hypotheses"]) is list and 1 <= len(doc["hypotheses"]) <= 16, "Hypothesis count"
    )
    boxes = []
    for h in doc["hypotheses"]:
        require(type(h) is dict and set(h) == {"lower", "upper"}, "Box fields")
        lo, hi = vector(h["lower"], 4), vector(h["upper"], 4)
        require(all(a <= b for a, b in zip(lo, hi, strict=True)), "Reversed box")
        boxes.append(Box(lo, hi))
    for key in ("age", "delay"):
        require(type(doc[key]) is int and doc[key] in (0, 1), "Unsupported " + key)
    U, W = exact(doc["authority"]), exact(doc["disturbance"])
    eta = vector(doc["effectiveness"], 2)
    require(
        0 <= U <= Q(1, 50) and W >= 0 and 0 <= eta[0] <= eta[1] <= 1,
        "Authority/effectiveness/disturbance",
    )
    require(
        type(doc["queue"]) is list and len(doc["queue"]) == doc["age"] + doc["delay"],
        "Queue does not cover measurement to application",
    )
    queue = tuple(action(u, U) for u in doc["queue"])
    require(
        doc["kind"]
        in ("declared_exact_information_set", "covariance_only", "outer_enclosure_only"),
        "Unknown information kind",
    )
    result = Info(tuple(boxes), doc["age"], doc["delay"], queue, U, eta, W, doc["kind"])
    require(result.payload() == doc, "Information serialization binding")
    return result


def positive_binding(info, certificate, delivered):
    require(type(certificate) is dict, "Missing positive certificate")
    require(certificate.get("status") == "certified_common_prefix", "Positive certificate kind")
    require(certificate.get("information_sha256") == info.identity(), "Wrong information binding")
    if certificate.get("model") != "hcw":
        raise UnsupportedAssumption("Only HCW is audited")
    require(
        exact(certificate.get("end_after_measurement_s")) == info.D + 1, "Certificate time window"
    )
    u = action(delivered, info.authority)
    require(
        action(certificate.get("action"), info.authority) == u,
        "Delivered command differs from certificate",
    )
    return u
