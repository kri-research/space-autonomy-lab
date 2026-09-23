"""Analytically selected development fixtures, not protected evaluation data."""

from fractions import Fraction as Q
from dataclasses import replace
from .information import Hypothesis, InformationSet


def point(state):
    return Hypothesis.point(state)


def box(center, error):
    center, error = tuple(map(Q, center)), tuple(map(Q, error))
    return Hypothesis(
        tuple(x - e for x, e in zip(center, error, strict=True)),
        tuple(x + e for x, e in zip(center, error, strict=True)),
    )


def fixtures():
    triple = (
        point((0, "-99.99905", 0, "-.001")),
        point(("7.99905", -80, ".001", 0)),
        point(("-7.99905", -80, "-.001", 0)),
    )
    pair = (point(("6.988", -70, ".02", 0)), point(("-6.988", -70, "-.02", 0)))
    compound = InformationSet(
        (box((0, "-27.033", 0, ".012"), (0, ".002", 0, ".001")),),
        age=1,
        delay=1,
        queue=((0, 0), (0, 0)),
        effectiveness=(Q(1, 2), Q(1)),
    )
    base = InformationSet((point((0, "-27.033", 0, ".012")),))
    cases = {
        "midpoint_known": InformationSet((point((0, "-97.5", 0, ".12")),)),
        "hold_bounded": InformationSet(
            (box((0, -30, 0, 0), (".01", ".01", ".001", ".001")),), disturbance=Q(1, 20000)
        ),
        "outward_boundary": InformationSet((point((0, -27, 0, ".12")),)),
        "opposed_radial": InformationSet(pair),
        "three_face_conflict": InformationSet(triple),
        "correlated_union": InformationSet(
            (point(("2.9", "-30.1", 0, 0)), point((0, "-27.1", 0, 0)))
        ),
        "outer_geometry_false_safe": InformationSet((point(("2.4", "-28.5", 0, 0)),)),
        "compound": compound,
        "single_age": replace(base, age=1, queue=((0, 0),)),
        "single_delay": replace(base, delay=1, queue=((0, 0),)),
        "single_error": replace(base, hypotheses=compound.hypotheses),
        "single_authority": replace(base, effectiveness=(Q(1, 2), Q(1))),
        "compound_without_age": replace(compound, age=0, queue=((0, 0),)),
        "compound_without_delay": replace(compound, delay=0, queue=((0, 0),)),
        "compound_without_error": replace(compound, hypotheses=base.hypotheses),
        "compound_without_authority_loss": replace(compound, effectiveness=(Q(1), Q(1))),
    }
    for i in range(3):
        cases["three_face_single_" + str(i)] = InformationSet((triple[i],))
    for i, j in ((0, 1), (0, 2), (1, 2)):
        cases["three_face_pair_" + str(i) + str(j)] = InformationSet((triple[i], triple[j]))
    for i in range(2):
        cases["opposed_single_" + str(i)] = InformationSet((pair[i],))
    return cases


PAIR_ACTIONS = {
    "three_face_pair_01": ("-.004", ".004"),
    "three_face_pair_02": (".004", ".004"),
    "three_face_pair_12": (0, "-.006"),
}
SINGLE_BRAKES = {
    "three_face_single_0": (0, ".015"),
    "three_face_single_1": ("-.015", 0),
    "three_face_single_2": (".015", 0),
    "opposed_single_0": ("-.02", 0),
    "opposed_single_1": (".02", 0),
}
