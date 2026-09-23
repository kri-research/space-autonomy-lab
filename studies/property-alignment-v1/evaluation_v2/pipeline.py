"""Two-phase orchestration shared by calibration and the replacement campaign."""

from pathlib import Path
import hashlib
from evaluation.analysis import analyze_rows
from evaluation.safety import atomic_json, strict_json, canonical_hash, utc_now
from .generator import STRATA
from .jobs import run_batch
from .receipts import key


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def publish_or_match(path, doc):
    if Path(path).exists():
        if strict_json(path) != doc:
            raise ValueError("Previously recorded object changed")
    else:
        atomic_json(path, doc)


def file_inventory(output):
    return {
        p.relative_to(output).as_posix(): sha(p)
        for p in sorted(Path(output).rglob("*"))
        if p.is_file() and p != Path(output) / "completion.json" and not p.name.endswith(".lock")
    }


def pipeline(payloads, output, *, identity, resources, target_per_stratum, protected=False):
    output = Path(output)
    payloads = list(payloads)
    if protected and target_per_stratum != 192:
        raise ValueError("Protected denominator changed")
    if any((p["namespace"] == "protected") != protected for p in payloads):
        raise PermissionError("Population and execution class disagree")
    if (output / "completion.json").exists():
        done = strict_json(output / "completion.json")
        if done["identity"] != identity or done["files"] != file_inventory(output):
            raise ValueError("Completed attempt changed")
        return strict_json(output / "analysis.json")
    common = {
        "context_id": identity,
        "workers": resources["workers"],
        "case_limit_s": resources["case_wall_limit_s"],
        "phase_limit_s": resources["phase_wall_limit_s"],
        "authorize_task08d": protected,
    }
    qbatch = run_batch(payloads, output / "qualification", kind="qualification", **common)
    if not qbatch["complete"] or qbatch["blockers"]:
        return {
            "campaign_complete": False,
            "status": "qualification_blocked" if qbatch["blockers"] else "qualification_incomplete",
            "work": qbatch,
            "candidate_evaluations": 0,
            "validity_claim_gate_passed": False,
        }
    qrows = {
        canonical_hash(p): strict_json(output / "qualification/cases" / (key(p) + ".json"))
        for p in payloads
    }
    selected = {}
    selected_payloads = []
    for s in STRATA:
        eligible = [
            p
            for p in payloads
            if p["stratum"] == s and qrows[canonical_hash(p)]["qualification"]["eligible"] is True
        ]
        if len(eligible) < target_per_stratum:
            return {
                "campaign_complete": False,
                "status": "reserve_exhausted",
                "stratum": s,
                "eligible": len(eligible),
                "target": target_per_stratum,
                "candidate_evaluations": 0,
                "validity_claim_gate_passed": False,
            }
        chosen = eligible[:target_per_stratum]
        selected[s] = [p["index"] for p in chosen]
        selected_payloads.extend(chosen)
    selection = {
        "schema": "sal-replacement-selection/1",
        "identity": identity,
        "selected": selected,
        "selection_rule": "first eligible in frozen stratum/index order before any full-set method call",
        "qualification_sha256": {
            p.name: sha(p) for p in sorted((output / "qualification/cases").glob("*.json"))
        },
    }
    publish_or_match(output / "selection.json", selection)
    qualified = {
        canonical_hash(p): qrows[canonical_hash(p)]["qualification"] for p in selected_payloads
    }
    work = run_batch(
        selected_payloads, output / "episodes", kind="episode", qualifications=qualified, **common
    )
    if not work["complete"]:
        return {
            "campaign_complete": False,
            "status": "selected_execution_incomplete",
            "work": work,
            "started_failures_retained": True,
            "validity_claim_gate_passed": False,
        }
    rows = [strict_json(output / "episodes/cases" / (key(p) + ".json")) for p in selected_payloads]
    expected = [(p["stratum"], p["index"]) for p in selected_payloads]
    analysis = analyze_rows(
        rows, protected=protected, expected_keys=expected if protected else None
    )
    analysis["replacement_evaluation_id"] = identity
    analysis["qualification_statuses"] = {
        status: sum(r["qualification"]["status"] == status for r in qrows.values())
        for status in sorted({r["qualification"]["status"] for r in qrows.values()})
    }
    analysis["evaluation_class"] = "protected_replacement" if protected else "calibration_only"
    publish_or_match(output / "analysis.json", analysis)
    atomic_json(
        output / "completion.json",
        {
            "identity": identity,
            "completed_at_utc": utc_now(),
            "files": file_inventory(output),
            "campaign_complete": analysis["campaign_complete"],
            "validity_claim_gate_passed": analysis["validity_claim_gate_passed"],
        },
    )
    return analysis
