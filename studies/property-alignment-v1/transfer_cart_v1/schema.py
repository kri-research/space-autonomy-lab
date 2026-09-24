"""Explicit synthetic cart parameters and aliased observation packets."""

from fractions import Fraction as Q
from pathlib import Path
import hashlib
import json
import random

ROOT = Path(__file__).resolve().parent
NORMALS = ((Q(1), Q(0)), (Q("-0.6"), Q("0.8")), (Q("-0.6"), Q("-0.8")))
STRATA = ("interior", "single_face", "aliased_pair", "aliased_triple")


def rational(x):
    if isinstance(x, bool):
        raise ValueError("Boolean physical quantity")
    return Q(str(x))


def digest(obj):
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def read(path):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError("Duplicate JSON key")
            d[k] = v
        return d

    def bad(x):
        raise ValueError("Nonfinite JSON token " + x)

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=bad)


def validate(case):
    if case.get("schema") != "sal-lag-cart-case/1":
        raise ValueError("Wrong cart input schema")
    for key in ("tau", "eta", "authority", "duration", "delay", "disturbance"):
        rational(case[key])
    if not Q(0) < rational(case["tau"]) <= 3 or not Q(0) < rational(case["eta"]) <= 1:
        raise ValueError("Unsupported lag/effectiveness")
    if not 0 < rational(case["authority"]) <= 1 or not 0 < rational(case["duration"]) <= 1:
        raise ValueError("Unsupported command domain")
    if not 0 <= rational(case["delay"]) <= Q(1, 2) or not 0 <= rational(case["disturbance"]) <= Q(
        1, 10
    ):
        raise ValueError("Unsupported delay/disturbance")
    if not case.get("boxes"):
        raise ValueError("Empty observation set")
    for b in case["boxes"]:
        if set(b) != {"lower", "upper"} or len(b["lower"]) != 6 or len(b["upper"]) != 6:
            raise ValueError("Six dimensional box required")
        if any(rational(a) > rational(z) for a, z in zip(b["lower"], b["upper"], strict=True)):
            raise ValueError("Reversed box")
    return case


def make_case(namespace, stratum, index):
    if (
        namespace not in ("protected", "calibration")
        or stratum not in STRATA
        or type(index) is not int
        or index < 0
    ):
        raise ValueError("Invalid population identity")
    salt = "sal-cart-lag-transfer-v1-" + namespace
    seed = int.from_bytes(hashlib.sha256(f"{salt}|{stratum}|{index}".encode()).digest()[:16], "big")
    r = random.Random(seed)
    tau = r.choice(("0.1", "0.3", "0.6"))
    eta = r.choice(("0.8", "1"))
    delay = r.choice(("0", "0.25"))
    error = tuple(map(Q, ("0.001", "0.001", "0.001", "0.001", "0.002", "0.002")))
    if stratum == "interior":
        centers = [tuple(Q(r.randint(-n, n), 100) for n in (20, 20, 3, 3, 2, 2))]
    else:
        count = {"single_face": 1, "aliased_pair": 2, "aliased_triple": 3}[stratum]
        clearance = Q(r.randint(20, 140), 1000)
        speed = Q(r.randint(40, 180), 1000)
        accel = Q(r.randint(0, 100), 1000)
        centers = []
        for j in range(count):
            n = NORMALS[(index + j) % 3]
            centers.append(tuple(c * x for c in (1 - clearance, speed, accel) for x in n))
    boxes = [
        {
            "lower": list(map(str, (x - e for x, e in zip(c, error, strict=True)))),
            "upper": list(map(str, (x + e for x, e in zip(c, error, strict=True)))),
        }
        for c in centers
    ]
    return validate(
        {
            "schema": "sal-lag-cart-case/1",
            "namespace": namespace,
            "stratum": stratum,
            "index": index,
            "generator_seed": str(seed),
            "tau": tau,
            "eta": eta,
            "authority": "0.4",
            "duration": "1",
            "delay": delay,
            "disturbance": "0.003",
            "boxes": boxes,
            "packet_code": f"{salt}/{stratum}/{index}",
            "measurement_time_s": "0",
        }
    )


def observe(case, state):
    validate(case)
    x = tuple(map(rational, state))
    if len(x) != 6:
        raise ValueError("Incomplete physical state")
    match = any(
        all(
            rational(lo) <= v <= rational(hi)
            for lo, v, hi in zip(b["lower"], x, b["upper"], strict=True)
        )
        for b in case["boxes"]
    )
    return (
        {"time": case["measurement_time_s"], "code": case["packet_code"]}
        if match
        else {"time": case["measurement_time_s"], "code": "inconsistent"}
    )


def support(box, normal, block, upper=True):
    values = []
    for j, c in enumerate(normal):
        lo, hi = map(rational, (box["lower"][2 * block + j], box["upper"][2 * block + j]))
        values.append(c * (hi if (c >= 0) == upper else lo))
    return sum(values, Q(0))


def subset(case, indices):
    return {**case, "boxes": [case["boxes"][i] for i in indices]}


def mean_case(case):
    center = [
        sum((rational(b["lower"][j]) + rational(b["upper"][j])) / 2 for b in case["boxes"])
        / len(case["boxes"])
        for j in range(6)
    ]
    return {**case, "boxes": [{"lower": list(map(str, center)), "upper": list(map(str, center))}]}
