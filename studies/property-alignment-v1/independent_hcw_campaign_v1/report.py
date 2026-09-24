"""All-case audit accounting; no numerical policy or certificate search is executed."""

from pathlib import Path
from collections import Counter
import math
from independent_hcw_audit_v1.schema import strict_json, identity, require
from independent_hcw_audit_v1.runner import validate_worker_result, worker_artifacts
from independent_hcw_audit_v1.reader import read_pair, STRATA
from .population import AUDIT_ID, EXPECTED_ORIGINAL

EXECUTION_FAILURES = {"audit_timeout", "audit_interrupted", "audit_execution_failure"}


def job_for(row):
    return {
        "kind": "recorded_episode",
        "key": row["key"],
        "payload": row["payload"],
        "episode": row["episode"],
        "qualification": row["qualification"],
    }


def json_bytes(value):
    import json

    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def category(original, result):
    status = result.get("status")
    if original in ("unresolved", "unresolved_budget"):
        require(
            status
            in ({"no_on_time_certificate"} | EXECUTION_FAILURES | {"binding_invalid_evidence"}),
            "Original nondelivery cannot be credited",
        )
    else:
        require(status != "no_on_time_certificate", "Definite certificate silently omitted")
    if status in ("verified_prefix", "verified_obstruction"):
        require(
            (original, status)
            in (
                ("certified_common_prefix", "verified_prefix"),
                ("proved_no_common_held_command", "verified_obstruction"),
            ),
            "Wrong verified certificate kind",
        )
        return "verified_original_certificate"
    if status == "contradicted_prefix":
        require(
            original == "certified_common_prefix"
            and result.get("witness", {}).get("proved") is True,
            "Contradiction lacks verified contrary witness",
        )
        return "verified_contrary_witness"
    if status == "numerically_unresolved":
        return "independent_numerical_nonresolution"
    if status == "binding_invalid_evidence":
        return "malformed_or_binding_invalid_evidence"
    if status == "unsupported_assumptions":
        return "unsupported_assumptions"
    if status == "no_on_time_certificate":
        return "original_no_on_time_certificate"
    if status in EXECUTION_FAILURES:
        return status
    raise ValueError("Unknown independent classification")


def verify_attempt(folder, records, frozen):
    folder = Path(folder)
    settings = frozen["protocol"]
    jobs = [job_for(x) for x in records]
    require(len(jobs) == 768 and len({j["key"] for j in jobs}) == 768, "All selected jobs required")
    expected = {
        "audit_id": AUDIT_ID,
        "jobs": {j["key"]: identity(j) for j in jobs},
        "settings": settings["numerical"],
        "job_timeout_s": settings["job_timeout_s"],
        "phase_timeout_s": settings["phase_timeout_s"],
    }
    require(
        strict_json((folder / "header.json").read_bytes()) == expected,
        "Frozen audit header differs",
    )
    names = {j["key"] + ".json" for j in jobs}
    for sub in ("receipts", "started", "jobs"):
        require({f.name for f in (folder / sub).iterdir()} == names, "Incomplete/extra " + sub)
    receipts = []
    for j in jobs:
        key = j["key"]
        f = folder / "receipts" / (key + ".json")
        require(not any(x.is_symlink() for x in (f, *f.parents)), "Unsafe audit path")
        row = strict_json(f.read_bytes())
        binding = {"audit_id": AUDIT_ID, "job_sha256": identity(j), "key": key}
        require(
            row.get("binding") == binding
            and row.get("receipt_sha256")
            == identity({k: v for k, v in row.items() if k != "receipt_sha256"}),
            "Audit receipt binding",
        )
        require(
            strict_json((folder / "started" / (key + ".json")).read_bytes()).get("binding")
            == binding,
            "Audit start binding",
        )
        require(
            (folder / "jobs" / (key + ".json")).read_bytes()
            == json_bytes({"job": j, "settings": settings["numerical"]}),
            "Raw audit job mismatch",
        )
        require(
            row.get("worker_artifacts") == worker_artifacts(folder, key),
            "Changed worker raw output",
        )
        result = row["result"]
        status = result["claim"]["status"]
        if status not in EXECUTION_FAILURES:
            validate_worker_result(result, j)
            require(
                strict_json((folder / "worker-output" / (key + ".json")).read_bytes()) == result,
                "Receipt/worker result mismatch",
            )
            require(
                result.get("original_status") == j["episode"]["candidate"]["status"],
                "Original status binding",
            )
        require(row.get("original_policy_executed") is False, "Original policy executed")
        elapsed = row.get("cold_process_elapsed_s")
        require(
            elapsed is None
            or (type(elapsed) in (float, int) and math.isfinite(elapsed) and elapsed >= 0),
            "Audit cost invalid",
        )
        receipts.append(row)
    completion = {
        "audit_id": AUDIT_ID,
        "expected": 768,
        "completed": len(receipts),
        "complete": True,
        "statuses": dict(Counter(r["result"]["claim"]["status"] for r in receipts)),
        "qualification_witnesses": sum(
            len(r["result"].get("qualification_witnesses", [])) for r in receipts
        ),
        "no_original_results_changed": True,
        "no_original_policy_executed": True,
    }
    require(
        strict_json((folder / "completion.json").read_bytes()) == completion,
        "Audit completion ledger mismatch",
    )
    return receipts


def summarize(records, receipts, population):
    require(len(records) == len(receipts) == 768, "Selected denominator")
    require(
        len({r["key"] for r in records}) == 768
        and len({r["binding"]["key"] for r in receipts}) == 768,
        "Duplicate selected record",
    )
    rows = []
    discrepancies = []
    for source, receipt in zip(records, receipts, strict=True):
        key = source["key"]
        require(receipt["binding"]["key"] == key, "Swapped audit receipt")
        info, candidate, commands = read_pair(
            source["payload"], source["episode"], source["qualification"]
        )
        result = receipt["result"]
        classified = category(candidate["status"], result["claim"])
        require(
            receipt["binding"]["job_sha256"] == identity(job_for(source)),
            "Input/receipt correspondence",
        )
        q = result.get("qualification_witnesses", [])
        if (
            result["claim"]["status"] not in EXECUTION_FAILURES
            and result["claim"]["status"] != "binding_invalid_evidence"
        ):
            require(len(q) == len(commands), "Missing selected qualification witness")
            for i, (row, command) in enumerate(zip(q, commands, strict=True)):
                require(
                    row["hypothesis"] == i and row["saved_command"] == list(map(str, command)),
                    "Swapped/changed qualification witness",
                )
                require(
                    row["audit"]["status"]
                    in (
                        "verified_prefix",
                        "numerically_unresolved",
                        "contradicted_prefix",
                        "unsupported_assumptions",
                    ),
                    "Invalid singleton audit category",
                )
        item = {
            "key": key,
            "stratum": source["payload"]["stratum"],
            "index": source["payload"]["index"],
            **source["bindings"],
            "information_sha256": info.identity(),
            "queue_sha256": identity(info.payload()["queue"]),
            "information": info.payload(),
            "original_candidate": candidate,
            "original_primary": source["episode"]["primary"],
            "original_qualification_actions": [list(map(str, u)) for u in commands],
            "audit_receipt_sha256": receipt["receipt_sha256"],
            "independent_result": result["claim"],
            "comparison_category": classified,
            "qualification_checks": q,
            "audit_cost_s": receipt["cold_process_elapsed_s"],
        }
        rows.append(item)
        if classified not in ("verified_original_certificate", "original_no_on_time_certificate"):
            discrepancies.append(
                {
                    "key": key,
                    "scope": "original_candidate_certificate",
                    "category": classified,
                    "failure_path": "independent_hcw_audit_v1.certificates.audit_claim",
                    "result": result["claim"],
                    "input_sha256": source["bindings"]["input_sha256"],
                    "affected_claim": "validity of this original finite held-command certificate",
                }
            )
        for i, row in enumerate(q):
            if row["audit"]["status"] != "verified_prefix":
                discrepancies.append(
                    {
                        "key": key,
                        "scope": "selected_singleton_qualification",
                        "hypothesis": i,
                        "failure_path": "independent_hcw_audit_v1.certificates.check_prefix",
                        "result": row["audit"],
                        "affected_claim": "selected hypothesis admits its saved library-command prefix",
                    }
                )
        if len(q) != len(commands):
            discrepancies.append(
                {
                    "key": key,
                    "scope": "qualification_execution",
                    "expected": len(commands),
                    "checked": len(q),
                    "affected_claim": "independent singleton validation incomplete",
                }
            )
    original = dict(Counter(r["original_candidate"]["status"] for r in rows))
    require(original == EXPECTED_ORIGINAL, "Original count changed")
    groups = []
    for s in STRATA:
        g = [r for r in rows if r["stratum"] == s]
        groups.append(
            {
                "stratum": s,
                "selected": len(g),
                "original_statuses": dict(Counter(r["original_candidate"]["status"] for r in g)),
                "independent_statuses": dict(Counter(r["independent_result"]["status"] for r in g)),
                "qualification_witnesses": sum(len(r["qualification_checks"]) for r in g),
                "qualification_outcomes": dict(
                    Counter(q["audit"]["status"] for r in g for q in r["qualification_checks"])
                ),
            }
        )
    verified = sum(r["comparison_category"] == "verified_original_certificate" for r in rows)
    summary = {
        "schema": "sal-independent-hcw-campaign-results/1",
        "audit_id": AUDIT_ID,
        "selected": 768,
        "original_delivered_certificates": 756,
        "original_statuses": original,
        "independent_statuses": dict(Counter(r["independent_result"]["status"] for r in rows)),
        "comparison_categories": dict(Counter(r["comparison_category"] for r in rows)),
        "independently_verified_original_certificates": verified,
        "original_descriptive_coverage": {
            "numerator": 756,
            "denominator": 768,
            "fraction": 756 / 768,
        },
        "post_hoc_verified_fraction_of_all_selected": {
            "numerator": verified,
            "denominator": 768,
            "fraction": verified / 768,
        },
        "post_hoc_certificate_agreement": {"numerator": verified, "denominator": 756},
        "qualification_witnesses_expected": population["selected_singleton_witnesses"],
        "qualification_witnesses_checked": sum(len(r["qualification_checks"]) for r in rows),
        "qualification_outcomes": dict(
            Counter(q["audit"]["status"] for r in rows for q in r["qualification_checks"])
        ),
        "discrepancies": len(discrepancies),
        "groups": groups,
        "all_selected_accounted_for": True,
        "original_timing_changed": False,
        "new_probability_interval": None,
        "full_recovery_or_physical_validation": False,
        "interpretation": "Deterministic post hoc certificate validation under the declared HCW model and information/input class; not an operational safety probability, original timing measurement, physical validation or independent human review",
    }
    return rows, discrepancies, summary
