"""One offline audit job. Inputs and old timing outcomes are never changed."""

from fractions import Fraction as Q
from .schema import read_info, InvalidEvidence, UnsupportedAssumption
from .reader import read_pair
from .certificates import audit_claim, check_prefix


def execute(job, settings):
    try:
        if job.get("kind") == "recorded_episode":
            info, candidate, actions = read_pair(
                job["payload"], job["episode"], job["qualification"]
            )
        elif job.get("kind") == "development_certificate":
            info = read_info(job["information"])
            candidate = job["candidate"]
            actions = []
        else:
            raise InvalidEvidence("Unknown job kind")
        result = audit_claim(
            info,
            candidate,
            max_cells=settings["max_cells_per_prefix"],
            min_width=Q(settings["minimum_time_width_s"]),
        )
        qualification = []
        for i, u in enumerate(actions):
            checked = check_prefix(
                info.singleton(i),
                u,
                max_cells=settings["max_cells_per_prefix"],
                min_width=Q(settings["minimum_time_width_s"]),
            )
            qualification.append(
                {"hypothesis": i, "saved_command": list(map(str, u)), "audit": checked}
            )
        return {
            "schema": "sal-independent-hcw-case-audit/1",
            "key": job["key"],
            "original_status": candidate["status"],
            "information_sha256": info.identity(),
            "claim": result,
            "qualification_witnesses": qualification,
            "qualification_all_verified": all(
                x["audit"]["status"] == "verified_prefix" for x in qualification
            )
            if actions
            else None,
            "original_policy_rerun": False,
            "original_timing_changed": False,
        }
    except UnsupportedAssumption as exc:
        return {
            "schema": "sal-independent-hcw-case-audit/1",
            "key": job.get("key"),
            "claim": {"status": "unsupported_assumptions", "reason": str(exc)},
        }
    except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
        return {
            "schema": "sal-independent-hcw-case-audit/1",
            "key": job.get("key"),
            "claim": {"status": "binding_invalid_evidence", "reason": str(exc)},
        }
