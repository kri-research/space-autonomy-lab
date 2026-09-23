"""Design tests that must pass before the Task 07 pilot is executed."""

from pathlib import Path
import hashlib
import json

from adjudication.geometry import bounds
from specification.contract import Verdict, load_property

from evaluation.generator import STRATA, case_payload, make_case, stress_cases
from evaluation.statistics import (
    PER_STRATUM,
    PRIMARY_N,
    hoeffding_half_width,
    required_total,
)


def test_namespace_separation_and_reproducibility():
    seen = set()
    for namespace in ("development", "calibration", "protected"):
        for stratum in STRATA:
            first = case_payload(namespace, stratum, 0)
            second = case_payload(namespace, stratum, 0)
            assert first == second
            digest = hashlib.sha256(
                json.dumps(first, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            assert digest not in seen
            seen.add(digest)


def test_generated_initial_boxes_are_inside_declared_union():
    prop = load_property()
    for namespace in ("development", "calibration"):
        for stratum in STRATA:
            for index in range(32):
                info, _ = make_case(namespace, stratum, index)
                for hypothesis in info.hypotheses:
                    judged = bounds(hypothesis.enclosure(), prop)
                    assert judged["containment"] == Verdict.SATISFIED


def test_primary_precision_and_balancing():
    assert required_total() == 738
    assert PER_STRATUM == 192
    assert PRIMARY_N == 768
    assert hoeffding_half_width(PRIMARY_N) < 0.05


def test_stress_cases_are_not_primary_population():
    cases = stress_cases()
    assert cases["covariance_only"].kind == "covariance_only"
    assert cases["outer_enclosure_only"].kind == "outer_enclosure_only"
    assert cases["reduced_effectiveness"].effectiveness[0] < 1


def test_pilot_protocol_never_authorizes_protected_execution():
    path = Path(__file__).resolve().parents[1] / "pilot_protocol.json"
    doc = json.loads(path.read_text())
    assert doc["protected_campaign_executed_in_task07"] is False
    assert doc["development_pilot_cases_per_stratum"] == 12
    assert doc["primary_inference"]["balanced_total"] == 768
