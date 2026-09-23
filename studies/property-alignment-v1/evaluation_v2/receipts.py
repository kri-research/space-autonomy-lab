"""Strict metadata and digest checks for replacement execution receipts."""

from fractions import Fraction as Q
import math
from evaluation.safety import canonical_hash, check_receipt
from evaluation.runner import _information
from qualification_repair_v1.jobs import _last_event
from .generator import STRATA


def key(payload):
    if (
        payload.get("stratum") not in STRATA
        or type(payload.get("index")) is not int
        or payload["index"] < 0
    ):
        raise ValueError("Invalid stratum/index")
    if payload.get("namespace") not in ("calibration", "development", "protected"):
        raise ValueError("Invalid namespace")
    _information(payload)
    return f"{payload['stratum']}__{payload['index']:05d}"


def seal(row):
    if "receipt_sha256" in row:
        raise ValueError("Already sealed")
    return {**row, "receipt_sha256": canonical_hash(row)}


def validate(row, payload, kind, qualification=None):
    if row.get("receipt_sha256") != canonical_hash(
        {k: v for k, v in row.items() if k != "receipt_sha256"}
    ):
        raise ValueError("Receipt digest differs")
    if row.get("case_id") != canonical_hash(payload):
        raise ValueError("Input binding differs")
    for field in ("namespace", "stratum", "index", "generator_seed"):
        if row.get(field) != payload[field]:
            raise ValueError("Receipt metadata differs")
    q = row["qualification"]
    e, status = q.get("eligible"), q.get("status")
    if e is not None and type(e) is not bool:
        raise ValueError("Invalid typed eligibility")
    if kind == "qualification":
        if (status == "qualified") != (e is True):
            raise ValueError("Qualification status differs")
        if e is False and status not in ("not_certified_by_library", "proved_precommand_violation"):
            raise ValueError("Unknown computation cannot become exclusion")
        if e is not None:
            if q.get("information_sha256") != _information(payload).identity():
                raise ValueError("Information binding differs")
            if row.get("qualification_recheck", {}).get("passed") is not True:
                raise ValueError("Unverified qualification outcome")
        if (
            q.get("physical_impossibility_claim") is True
            and status != "proved_precommand_violation"
        ):
            raise ValueError("Unjustified physical impossibility label")
    elif kind == "episode":
        if qualification is None or qualification.get("eligible") is not True or q != qualification:
            raise ValueError("Selected qualification changed")
        check_receipt(row, payload)
        c = row["candidate"]
        if row["primary"]["decisive"]:
            wall = c.get("wall_s")
            if (
                isinstance(wall, bool)
                or not isinstance(wall, (int, float))
                or not math.isfinite(wall)
                or wall < 0
            ):
                raise ValueError("Invalid policy timing")
            expected = not c.get("deadline_exceeded", False) and wall <= 1.0
            if row["primary"]["on_time"] is not expected:
                raise ValueError("Deadline interpretation changed")
        if c.get("action") is not None:
            action = tuple(Q(v) for v in c["action"])
            if (
                len(action) != 2
                or sum(v * v for v in action) > _information(payload).authority ** 2
            ):
                raise ValueError("Action outside authority")
    else:
        raise ValueError("Unknown phase")
    return row


def missing(payload, kind, reason, event_file, qualification=None, elapsed=None, exitcode=None):
    from evaluation.execute import _missing_episode

    if kind == "episode":
        row = _missing_episode(payload, reason)
        row["qualification"] = qualification
    else:
        row = {
            "schema": "sal-replacement-qualification/1",
            "case_id": canonical_hash(payload),
            **{k: payload[k] for k in ("namespace", "stratum", "index", "generator_seed")},
            "qualification": {
                "status": reason,
                "eligible": None,
                "physical_impossibility_claim": False,
            },
            "qualification_recheck": {"passed": False, "reason": reason},
        }
    row["failure"] = {
        "case_key": key(payload),
        "kind": kind,
        "reason": reason,
        "last_event": _last_event(event_file),
        "parent_wall_s": elapsed,
        "exit_code": exitcode,
        "retried": False,
    }
    return seal(row)
