"""Validate saved qualification claims against exact inputs and unmodified code."""

from dataclasses import replace
from fractions import Fraction as Q
from candidate.certify import certify_action
from evaluation.qualification import QUALIFICATION_ACTIONS
from .core import recheck_queue_witness


def recheck(info, result):
    if result.get("information_sha256") != info.identity():
        raise ValueError("Qualification information binding changed")
    eligible = result.get("eligible")
    status = result.get("status")
    if eligible is None:
        return {"passed": False, "reason": "qualification_unknown"}
    if type(eligible) is not bool or result.get("full_recovery_claim") is not False:
        raise ValueError("Malformed eligibility or recovery claim")
    if eligible:
        if status != "qualified" or result.get("physical_impossibility_claim") is not False:
            raise ValueError("Inconsistent positive qualification")
        rows = result.get("hypotheses", [])
        if len(rows) != len(info.hypotheses) or [r.get("hypothesis") for r in rows] != list(
            range(len(info.hypotheses))
        ):
            raise ValueError("Missing or duplicated qualified hypothesis")
        library = {tuple(Q(str(x)) for x in values) for values in QUALIFICATION_ACTIONS}
        for row in rows:
            if row.get("qualified") is not True:
                raise ValueError("False qualified hypothesis")
            action = tuple(Q(x) for x in row["witness_action"])
            if action not in library or sum(x * x for x in action) > info.authority**2:
                raise ValueError("Action outside fixed library or authority")
            single = replace(info, hypotheses=(info.hypotheses[row["hypothesis"]],))
            old = certify_action(single, action)
            if old["status"] != "certified_common_prefix":
                return {
                    "passed": False,
                    "reason": "original_full_schedule_recheck_unresolved",
                    "hypothesis": row["hypothesis"],
                    "status": old["status"],
                }
        return {
            "passed": True,
            "kind": "all_original_full_schedule_rechecks",
            "hypotheses": len(rows),
        }
    if status == "proved_precommand_violation":
        if result.get("physical_impossibility_claim") is not True:
            raise ValueError("Missing negative claim declaration")
        return {
            "passed": recheck_queue_witness(info, result["queue_witness"]),
            "kind": "attainable_precommand_violation",
        }
    if (
        status != "not_certified_by_library"
        or result.get("physical_impossibility_claim") is not False
    ):
        raise ValueError("Unknown or unjustified negative label")
    return {
        "passed": True,
        "kind": "explicitly_noncertifying_abstention",
        "physical_impossibility_checked": False,
    }
