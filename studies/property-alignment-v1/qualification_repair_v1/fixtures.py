"""Fixed development inputs. No fresh protected namespace is generated here."""

from dataclasses import replace
from fractions import Fraction as Q
from candidate.information import Hypothesis, InformationSet
from candidate.fixtures import fixtures as named_fixtures
from evaluation.generator import STRATA, make_case
from evaluation.runner import _information
from evaluation.safety import canonical_hash
from runtime_diagnosis_v1.worker import validate_case

RETIRED = (136, 137, 179, 180, 181, 182)
ALLOWED = {"development", "calibration", "analytic", "retired_diagnosis"}


def envelope(key, namespace, info, source):
    if namespace not in ALLOWED:
        raise ValueError("Protected or undeclared validation namespace refused")
    return {
        "schema": "sal-repair-validation-input/1",
        "key": key,
        "namespace": namespace,
        "information": info.payload(),
        "source": source,
    }


def inputs():
    result = []
    for namespace, count in (("development", 24), ("calibration", 2)):
        for s in STRATA:
            for i in range(count):
                info, _ = make_case(namespace, s, i)
                result.append(
                    envelope(
                        f"{namespace}__{s}__{i:05d}",
                        namespace,
                        info,
                        {"generator_namespace": namespace, "stratum": s, "index": i},
                    )
                )
    for i in RETIRED:
        payload = validate_case(i)
        result.append(
            envelope(
                f"retired__{i:05d}",
                "retired_diagnosis",
                _information(payload),
                {
                    "retired_original_case_id": canonical_hash(payload),
                    "index": i,
                    "original_outcome_replaced": False,
                },
            )
        )
    for name, info in named_fixtures().items():
        result.append(
            envelope("named__" + name, "analytic", info, {"task06_development_fixture": name})
        )
    h = Hypothesis(
        (Q("-.01"), Q("-60.01"), Q("-.001"), Q("-.001")),
        (Q(".01"), Q("-59.99"), Q(".001"), Q(".001")),
    )
    base = InformationSet((h,), age=1, delay=1, queue=((0, 0), (0, 0)), disturbance=Q("0.00001"))
    additional = {
        "queued_departure": InformationSet(
            (Hypothesis.point((0, Q("-27.005"), 0, Q(".02"))),), age=1, queue=((0, 0),)
        ),
        "initial_unsafe": InformationSet((Hypothesis.point((0, 0, 0, 0)),)),
        "bounded_safe": base,
        "effectiveness_interval": replace(base, effectiveness=(Q(1, 2), Q(1))),
        "zero_authority": replace(base, authority=Q(0), disturbance=Q(0)),
        "nonzero_queue": replace(base, queue=((Q(".002"), Q("-.002")), (Q("-.002"), Q(".002")))),
        "zero_effectiveness": replace(base, effectiveness=(Q(0), Q(0))),
        "boundary_straddle": InformationSet(
            (Hypothesis((Q("4.999"), -50, 0, 0), (Q("5.001"), -50, 0, 0)),)
        ),
    }
    for name, info in additional.items():
        result.append(envelope("stress__" + name, "analytic", info, {"development_stress": name}))
    if len({r["key"] for r in result}) != len(result):
        raise AssertionError("Duplicate key")
    return result


def information(payload):
    if payload.get("namespace") not in ALLOWED:
        raise ValueError("Only declared development or retired diagnostic inputs permitted")
    return _information(payload)
