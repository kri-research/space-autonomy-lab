"""One evaluation episode with explicit proof checks and comparator semantics."""

from fractions import Fraction as Q
import hashlib
import json
import time
import numpy as np

from candidate.affine import recheck_certificate
from candidate.certify import certify_action, decide
from candidate.comparators import compare
from candidate.information import Hypothesis, InformationSet

from .qualification import pairwise_shortcut, qualification


def identity(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def mean_shortcut(info):
    points = []
    for hypothesis in info.hypotheses:
        points.append(
            [float((a + b) / 2) for a, b in zip(hypothesis.lower, hypothesis.upper, strict=True)]
        )
    mean = tuple(map(float, np.mean(points, axis=0)))
    fictional = InformationSet(
        (Hypothesis.point(mean),),
        age=info.age,
        delay=info.delay,
        queue=info.queue,
        authority=info.authority,
        effectiveness=info.effectiveness,
        disturbance=info.disturbance,
    )
    result = decide(fictional, budget_s=1.0)
    full = None
    if result.get("action") is not None:
        full = certify_action(info, tuple(Q(value) for value in result["action"]))
    return {
        "fictional_mean_status": result["status"],
        "full_set_recheck": None if full is None else full["status"],
        "declares_safe": result["status"] == "certified_common_prefix",
        "false_safe_for_full_set": bool(
            result["status"] == "certified_common_prefix"
            and full is not None
            and full["status"] != "certified_common_prefix"
        ),
        "shortcut_is_valid": False,
    }


def run_case(payload, *, include_native_baselines=True):
    info = InformationSet(
        tuple(
            Hypothesis(tuple(item["lower"]), tuple(item["upper"]))
            for item in payload["information"]["hypotheses"]
        ),
        age=payload["information"]["age"],
        delay=payload["information"]["delay"],
        queue=tuple(tuple(v for v in row) for row in payload["information"]["queue"]),
        authority=Q(payload["information"]["authority"]),
        effectiveness=tuple(Q(v) for v in payload["information"]["effectiveness"]),
        disturbance=Q(payload["information"]["disturbance"]),
        kind=payload["information"]["kind"],
        units=tuple(payload["information"]["units"]),
    )
    qual = qualification(info)
    started = time.perf_counter()
    candidate = (
        decide(info, budget_s=1.0)
        if qual["eligible"]
        else {
            "status": "ineligible_individual_prefix",
            "action": None,
            "wall_s": 0.0,
            "deadline_exceeded": False,
        }
    )
    elapsed = time.perf_counter() - started

    proof = {"checked": False, "valid": None, "kind": None}
    if candidate["status"] == "proved_no_common_held_command":
        checked = recheck_certificate(info, candidate["negative"])
        proof = {"checked": True, "valid": bool(checked["proved"]), "kind": "negative_dual"}
    elif candidate["status"] == "certified_common_prefix":
        checked = certify_action(info, tuple(Q(value) for value in candidate["action"]))
        proof = {
            "checked": True,
            "valid": checked["status"] == "certified_common_prefix",
            "kind": "positive_fixed_action",
        }

    pairwise = pairwise_shortcut(info)
    mean = mean_shortcut(info)
    native = compare(info) if include_native_baselines else {"status": "not_run"}
    decisive = candidate["status"] in {
        "certified_common_prefix",
        "proved_no_common_held_command",
    }
    on_time = (
        not candidate.get("deadline_exceeded", False) and candidate.get("wall_s", elapsed) <= 1.0
    )
    integrity = bool(proof["valid"]) if proof["checked"] else not decisive
    result = {
        "schema": "sal-evaluation-episode/1",
        "case_id": identity(payload),
        "namespace": payload["namespace"],
        "stratum": payload["stratum"],
        "index": payload["index"],
        "generator_seed": payload["generator_seed"],
        "qualification": qual,
        "candidate": candidate,
        "certificate_recheck": proof,
        "primary": {
            "eligible": qual["eligible"],
            "decisive": decisive,
            "on_time": on_time,
            "valid_certificate": integrity,
            "on_time_decisive_valid": bool(qual["eligible"] and decisive and on_time and integrity),
        },
        "pairwise_shortcut": pairwise,
        "mean_shortcut": mean,
        "native_baselines": native,
        "episode_wall_s": time.perf_counter() - started,
        "timing_scope": "local developmental processor timing; not WCET or target hardware",
        "physical_validation": False,
    }
    return result


def scientific_signature(row):
    """Fields expected to match across serial/parallel/checkpoint execution."""
    return {
        "case_id": row["case_id"],
        "namespace": row["namespace"],
        "stratum": row["stratum"],
        "index": row["index"],
        "qualification": row["qualification"],
        "candidate_status": row["candidate"]["status"],
        "candidate_action": row["candidate"].get("action"),
        "certificate_recheck": row["certificate_recheck"],
        "primary": row["primary"],
        "pairwise_shortcut": row["pairwise_shortcut"],
        "mean_shortcut": row["mean_shortcut"],
        "native_baselines": {
            "status": row["native_baselines"].get("status"),
            "methods": {
                key: {
                    "status": value.get("status"),
                    "protected": value.get("protected"),
                    "command": value.get("command"),
                    "prefix": value.get("separate_prefix_check", {}).get("status"),
                }
                for key, value in row["native_baselines"].get("methods", {}).items()
            },
        },
    }
