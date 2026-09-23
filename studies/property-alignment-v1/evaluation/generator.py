"""Prospective benchmark population generator for Task 07/08.

Generation never evaluates the candidate or a comparator. Namespace, stratum
and index determine the complete input. Probability statements in the frozen
analysis refer only to this declared synthetic generator, not operations.
"""

from fractions import Fraction as Q
import hashlib
import random

from candidate.information import Hypothesis, InformationSet

STRATA = (
    "interior_pair",
    "radial_boundary",
    "three_face_boundary",
    "timing_bounded_pair",
)
NAMESPACES = {
    "development": "sal-eval-v1-development",
    "calibration": "sal-eval-v1-calibration",
    "protected": "sal-eval-v1-protected",
    "stress": "sal-eval-v1-stress",
}


def _rng(namespace, stratum, index):
    if namespace not in NAMESPACES or stratum not in STRATA:
        raise ValueError("Unknown population namespace or stratum")
    if type(index) is not int or index < 0:
        raise ValueError("Nonnegative integer case index required")
    payload = f"{NAMESPACES[namespace]}|{stratum}|{index}".encode()
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:16], "big")
    return random.Random(seed), seed


def _point(values):
    return Hypothesis.point(tuple(Q(str(value)) for value in values))


def _box(center, error):
    center = tuple(Q(str(value)) for value in center)
    error = tuple(Q(str(value)) for value in error)
    return Hypothesis(
        tuple(value - radius for value, radius in zip(center, error, strict=True)),
        tuple(value + radius for value, radius in zip(center, error, strict=True)),
    )


def case_payload(namespace, stratum, index):
    info, seed = make_case(namespace, stratum, index)
    return {
        "schema": "sal-protected-case/1",
        "namespace": namespace,
        "stratum": stratum,
        "index": index,
        "generator_seed": str(seed),
        "information": info.payload(),
    }


def make_case(namespace, stratum, index):
    r, seed = _rng(namespace, stratum, index)
    if stratum == "interior_pair":
        y = Q(r.randint(-900, -500), 10)
        width = -y / 10
        clearance = Q(r.randint(500, 8000), 10000)
        radial_speed = Q(r.randint(0, 150), 10000)
        along_speed = Q(r.randint(-100, 100), 10000)
        hypotheses = (
            _point((width - clearance, y, radial_speed, along_speed)),
            _point((-(width - clearance), y, -radial_speed, along_speed)),
        )
        info = InformationSet(hypotheses)

    elif stratum == "radial_boundary":
        y = Q(r.randint(-900, -500), 10)
        width = -y / 10
        clearance = Q(r.randint(5, 50), 10000)
        radial_speed = Q(r.randint(5, 20), 10000)
        hypotheses = (
            _point((width - clearance, y, radial_speed, 0)),
            _point((-(width - clearance), y, -radial_speed, 0)),
        )
        info = InformationSet(hypotheses)

    elif stratum == "three_face_boundary":
        y = Q(r.randint(-900, -600), 10)
        width = -y / 10
        side_clearance = Q(r.randint(5, 50), 10000)
        radial_speed = Q(r.randint(5, 20), 10000)
        lower_clearance = Q(r.randint(5, 50), 10000)
        along_speed = -Q(r.randint(5, 20), 10000)
        x_lower = Q(r.randint(-20, 20), 100)
        hypotheses = (
            _point((width - side_clearance, y, radial_speed, 0)),
            _point((-(width - side_clearance), y, -radial_speed, 0)),
            _point((x_lower, -100 + lower_clearance, 0, along_speed)),
        )
        info = InformationSet(hypotheses)

    elif stratum == "timing_bounded_pair":
        y = Q(r.randint(-800, -500), 10)
        width = -y / 10
        clearance = Q(r.randint(50, 250), 10000)
        radial_speed = Q(r.randint(0, 15), 10000)
        error = ("0.002", "0.002", "0.0002", "0.0002")
        hypotheses = (
            _box((width - clearance, y, radial_speed, 0), error),
            _box((-(width - clearance), y, -radial_speed, 0), error),
        )
        info = InformationSet(
            hypotheses,
            age=1,
            delay=1,
            queue=((0, 0), (0, 0)),
            disturbance=Q(1, 100000),
        )
    else:
        raise AssertionError("Unhandled stratum")
    return info, seed


def stress_cases():
    """Fixed non-prevalence cases for defensive assumption handling."""
    base, _ = make_case("stress", "interior_pair", 0)
    covariance = InformationSet(
        base.hypotheses,
        kind="covariance_only",
    )
    reduced = InformationSet(
        base.hypotheses,
        effectiveness=(Q(1, 2), Q(1)),
    )
    outer = InformationSet(
        (base.hull(),),
        kind="outer_enclosure_only",
    )
    return {
        "covariance_only": covariance,
        "reduced_effectiveness": reduced,
        "outer_enclosure_only": outer,
    }
