"""Read-only accounting of the protocol-invalid qualification attempt.

No policy, qualification, trajectory or protected endpoint is recomputed.
"""

from collections import Counter
from fractions import Fraction as Q
from pathlib import Path, PurePosixPath
import argparse
import csv
import hashlib
import json
import math

from evaluation.execute import verify_freeze
from evaluation.generator import STRATA, case_payload
from evaluation.safety import canonical_hash

STUDY = Path(__file__).resolve().parents[1]
FREEZE = STUDY / "evaluation/frozen/freeze.json"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_tree(value):
    if isinstance(value, float):
        require(math.isfinite(value), "Nonfinite field")
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)
    elif isinstance(value, dict):
        for item in value.values():
            finite_tree(item)


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def bad(value):
        raise ValueError("Invalid numeric constant: " + value)

    value = json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=bad)
    finite_tree(value)
    return value


def member(base, name):
    p = PurePosixPath(name)
    require(not p.is_absolute() and ".." not in p.parts and p.as_posix() == name, "Unsafe member")
    result = Path(base) / p
    require(not any(q.is_symlink() for q in (result, *result.parents)), "Symlink in artifact")
    return result


def validate_qualification(receipt, payload):
    require(receipt["case_id"] == canonical_hash(payload), "Wrong input identity")
    for key in ("namespace", "stratum", "index"):
        require(receipt[key] == payload[key], "Wrong input metadata")
    q = receipt["qualification"]
    require(type(q["eligible"]) is bool, "Non-Boolean eligibility")
    require(q.get("full_recovery_claim") is False, "Prefix relabelled as recovery")
    require(len(q["hypotheses"]) == len(payload["information"]["hypotheses"]), "Omitted hypothesis")
    authority = Q(payload["information"]["authority"])
    for i, h in enumerate(q["hypotheses"]):
        require(type(h["hypothesis"]) is int and h["hypothesis"] == i, "Wrong hypothesis order")
        require(type(h["qualified"]) is bool, "Non-Boolean hypothesis outcome")
        for a in h["attempts"]:
            action = a["action"]
            require(isinstance(action, list) and len(action) == 2, "Wrong action dimension")
            require(all(type(v) in (str, int, float) for v in action), "Invalid action type")
            require(sum(Q(v) ** 2 for v in action) <= authority**2, "Action exceeds physical bound")
        if h["qualified"]:
            require(
                any(
                    a["status"] == "certified_common_prefix" and a["action"] == h["witness_action"]
                    for a in h["attempts"]
                ),
                "Missing qualifying action record",
            )
        else:
            require(h["witness_action"] is None, "Failed qualification has a witness")
    require(
        q["eligible"] == all(h["qualified"] for h in q["hypotheses"]), "Contradictory eligibility"
    )
    return q["eligible"]


def audit(directory, freeze_path=FREEZE):
    directory = Path(directory)
    f = load(freeze_path)
    verify_freeze(freeze_path, f["evaluation_id"])
    header = load(directory / "run_header.json")
    require(header["evaluation_id"] == f["evaluation_id"], "Run identity differs")
    require(header["freeze_sha256"] == sha(freeze_path), "Run freeze bytes differ")
    require(header["source_commit"] == f["source_commit"], "Run source differs")
    require(header["workers"] == f["resources"]["workers"], "Worker regime differs")
    require(header["physical_validation"] is False, "Unexpected physical label")
    require(
        not any(
            (directory / n).exists() for n in ("selection.json", "analysis.json", "completion.json")
        ),
        "Attempt contains final selection or inference",
    )
    require(not list((directory / "cases").glob("*.json")), "Unexpected candidate execution")
    receipt = load(directory / "execution_receipt.json")
    require(
        receipt["exit_code"] == 1
        and receipt["observed_exception"]
        == "RuntimeError: Qualification failure blocks selection: worker_wall_timeout",
        "Execution failure evidence differs",
    )
    require(receipt["evaluation_id"] == f["evaluation_id"], "Receipt evaluation differs")
    require(receipt["frozen_analysis_executed"] is False, "Unexpected analysis claim")
    reserve = load(Path(freeze_path).parent / "protected_reserve.json")
    names, entries = set(), []
    totals, by_stratum = Counter(), {s: Counter() for s in STRATA}
    for e in reserve["cases"]:
        name = f"{e['stratum']}__{e['index']:05d}.json"
        require(name not in names, "Duplicate planned reserve")
        names.add(name)
        payload = case_payload("protected", e["stratum"], e["index"])
        require(canonical_hash(payload) == e["payload_sha256"], "Reserve input drift")
        raw, marker = directory / "qualification" / name, directory / "qualification/started" / name
        if raw.exists():
            require(marker.exists(), "Receipt has no start marker")
            eligible = validate_qualification(load(raw), payload)
            status = "completed_eligible" if eligible else "completed_ineligible"
        elif marker.exists():
            status = "started_without_receipt"
        else:
            status = "not_started"
        if marker.exists():
            m = load(marker)
            require(
                m["case_id"] == e["payload_sha256"] and m["kind"] == "qualification",
                "Invalid start marker",
            )
        totals[status] += 1
        by_stratum[e["stratum"]][status] += 1
        entries.append(
            {
                "stratum": e["stratum"],
                "index": e["index"],
                "case_id": e["payload_sha256"],
                "status": status,
                "receipt_sha256": sha(raw) if raw.exists() else "",
                "marker_sha256": sha(marker) if marker.exists() else "",
            }
        )
    for folder in (directory / "qualification", directory / "qualification/started"):
        require({p.name for p in folder.glob("*.json")} <= names, "Unexpected reserve receipt")
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        manifest = load(manifest_path)
        files = {
            p.relative_to(directory).as_posix()
            for p in directory.rglob("*")
            if p.is_file() and p != manifest_path
        }
        require(set(manifest) == files, "Artifact membership differs")
        for name, expected in manifest.items():
            require(sha(member(directory, name)) == expected, "Artifact bytes changed")
    summary = {
        "schema": "sal-frozen-attempt-audit/1",
        "passed": True,
        "audit_pass_means": "Preservation and accounting checks passed; campaign remains protocol-invalid",
        "evaluation_id": f["evaluation_id"],
        "campaign_valid": False,
        "reason": "Qualification worker reached frozen 15-second watchdog before selection",
        "planned_reserve": len(entries),
        "planned_candidate_target": f["design"]["target_total"],
        "qualification_counts": dict(totals),
        "per_stratum": {s: dict(c) for s, c in by_stratum.items()},
        "selected_population_formed": False,
        "candidate_evaluations": 0,
        "primary_estimate": None,
        "confidence_interval": None,
        "inference_status": "not_estimable_no_selected_population_or_candidate_outcomes",
        "frozen_analysis_executed": False,
        "historical_endpoints_reopened": False,
        "physical_validation": False,
        "failure_attribution": "The driver records one worker timeout. Four missing receipts are not all labelled timeouts; the exception omits the triggering case ID.",
        "underlying_timeout_cause": "Not established without further separately identified development",
        "resume_scope": "The frozen runner blocks interrupted qualification. Do not retry or relabel missing cases under this identity.",
        "evidence_scope": "Qualification receipts and start markers only. No protected common-set coverage, collision, hold, abort, utility or controller-superiority result.",
    }
    return summary, entries


def export(directory, output):
    summary, entries = audit(directory)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "summary.json").open("x") as f:
        json.dump(summary, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    with (output / "attempt_ledger.csv").open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(entries[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(entries)
    statuses = (
        "completed_eligible",
        "completed_ineligible",
        "started_without_receipt",
        "not_started",
    )
    with (output / "qualification_counts.csv").open("x", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["stratum", *statuses], lineterminator="\n")
        w.writeheader()
        for s in STRATA:
            w.writerow({"stratum": s, **{k: summary["per_stratum"][s].get(k, 0) for k in statuses}})
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    summary = export(args.directory, args.output) if args.output else audit(args.directory)[0]
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
