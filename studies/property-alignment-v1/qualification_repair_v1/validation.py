"""Recorded developmental validation, with no protected execution interface."""

from pathlib import Path
from collections import Counter
from dataclasses import replace
from fractions import Fraction as Q
import argparse
import hashlib
import json
import platform
import subprocess
from evaluation.safety import atomic_json, strict_json, canonical_hash, safe_path
from candidate.certify import certify_action
from .core import recheck_queue_witness
from .fixtures import inputs, information
from .jobs import run_jobs, _validate
from .recheck import recheck

PACKAGE = Path(__file__).resolve().parent
STUDY = PACKAGE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signatures(directory, payloads):
    result = []
    for p in payloads:
        row = strict_json(directory / "cases" / (p["key"] + ".json"))
        _validate(row, p)
        q = dict(row["qualification"])
        q.pop("wall_s", None)
        result.append(q)
    return result


def _original_pilot_agreement(rows):
    by_key = {r["key"]: r for r in rows}
    checks = []
    for path in sorted((STUDY / "evaluation/recorded_pilot/cases").glob("*.json")):
        old = strict_json(path)
        key = f"development__{old['stratum']}__{old['index']:05d}"
        new = by_key[key]["qualification"]
        checks.append(
            {
                "key": key,
                "old_receipt_sha256": sha(path),
                "old_eligible": old["qualification"]["eligible"],
                "new_eligible": new["eligible"],
                "agree": old["qualification"]["eligible"] is new["eligible"],
            }
        )
    if len(checks) != 48:
        raise ValueError("Expected 48 original pilot qualification receipts")
    return checks


def summarize(directory, payloads):
    batches = {
        name: strict_json(directory / (name + "-batch.json")) for name in ("serial", "parallel")
    }
    rows = [strict_json(directory / "serial/cases" / (p["key"] + ".json")) for p in payloads]
    for row, p in zip(rows, payloads, strict=True):
        _validate(row, p)
    agreement = signatures(directory / "serial", payloads) == signatures(
        directory / "parallel", payloads
    )
    status = Counter(r["qualification"]["status"] for r in rows)
    categories = {}
    for namespace in sorted({p["namespace"] for p in payloads}):
        selected = [r for r in rows if r["namespace"] == namespace]
        categories[namespace] = {
            "cases": len(selected),
            "statuses": dict(Counter(r["qualification"]["status"] for r in selected)),
        }
    proof_rows = strict_json(directory / "fixed_action_rechecks.json")
    rechecks_pass = all(r["passed"] for r in proof_rows)
    pilot = _original_pilot_agreement(rows)
    slow = []
    for batch in ("serial", "parallel"):
        r = strict_json(directory / batch / "cases/retired__00137.json")["qualification"]
        slow.append(
            {
                "batch": batch,
                "status": r["status"],
                "qualification_wall_s": r["wall_s"],
                "continuation_propagations": r["counters"]["continuation_propagations"],
            }
        )
    timing = {}
    for batch in ("serial", "parallel"):
        rr = [strict_json(directory / batch / "cases" / (p["key"] + ".json")) for p in payloads]
        timing[batch] = {
            "batch_wall_s": batches[batch]["wall_s"],
            "maximum_qualification_wall_s": max(r["qualification"]["wall_s"] for r in rr),
            "maximum_worker_wall_s": max(r["worker_wall_s"] for r in rr),
        }
    repeats = [strict_json(directory / ("repeat-" + str(i) + "-batch.json")) for i in range(3)]
    stress = [p for p in payloads if p["namespace"] in ("retired_diagnosis", "analytic")]
    repeat_agreement = all(
        signatures(directory / ("repeat-" + str(i)), stress)
        == signatures(directory / "serial", stress)
        for i in range(3)
    )
    return {
        "schema": "sal-qualification-repair-validation/1",
        "evidence_class": "development_only_repair_validation",
        "unique_inputs": len(payloads),
        "serial_parallel_attempts": 2 * len(payloads),
        "additional_repeated_stress_attempts": 3 * len(stress),
        "groups": categories,
        "serial_statuses": dict(status),
        "serial_parallel_numerical_equivalence": agreement,
        "repeat_stress_equivalence": repeat_agreement,
        "timing": timing,
        "diagnosed_case": slow,
        "fixed_rechecks": len(proof_rows),
        "fixed_rechecks_passed": sum(r["passed"] for r in proof_rows),
        "pilot_qualification_agreement": pilot,
        "original_qualified_pilot_cases_preserved": all(r["agree"] for r in pilot),
        "job_watchdog_s": 15,
        "candidate_policy_budget_changed": False,
        "qualification_unknowns": sum(b["blockers"] for b in [*batches.values(), *repeats]),
        "all_batches_complete": all(b["complete"] for b in [*batches.values(), *repeats]),
        "new_freeze_created": False,
        "protected_candidate_evaluations": 0,
        "timings_are_worst_case_guarantee": False,
        "physical_validation": False,
        "passed": agreement
        and repeat_agreement
        and rechecks_pass
        and all(r["agree"] for r in pilot)
        and all(b["complete"] and b["blockers"] == 0 for b in [*batches.values(), *repeats]),
    }


def run(output):
    output = safe_path(output)
    if output.exists() or output.is_relative_to(STUDY.parents[1]):
        raise ValueError("New private output required")
    seal = strict_json(PACKAGE / "validation_seal.json")
    for name, digest in seal["source_sha256"].items():
        if sha(STUDY / name) != digest:
            raise ValueError("Development source changed before validation")
    output.mkdir(parents=True)
    payloads = inputs()
    if [canonical_hash(p) for p in payloads] != seal["input_sha256"]:
        raise ValueError("Validation inputs changed")
    atomic_json(output / "inputs.json", payloads)
    atomic_json(output / "source_binding.json", seal)
    atomic_json(
        output / "runtime.json",
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip(),
            "scope": "local development measurements, no hardware reliability inference",
        },
    )
    for name, workers in (("serial", 1), ("parallel", 4)):
        batch = run_jobs(payloads, output / name, workers=workers)
        atomic_json(output / (name + "-batch.json"), batch)
        if not batch["complete"] or batch["blockers"]:
            raise AssertionError("Validation batch failed; preserve attempt")
    # Replay saved accepted actions and queue witnesses, never regenerate policies.
    rechecked = []
    for p in payloads:
        q = strict_json(output / "serial/cases" / (p["key"] + ".json"))["qualification"]
        info = information(p)
        if q["eligible"]:
            for row in q["hypotheses"]:
                single = replace(info, hypotheses=(info.hypotheses[row["hypothesis"]],))
                answer = certify_action(single, tuple(Q(v) for v in row["witness_action"]))
                rechecked.append(
                    {
                        "key": p["key"],
                        "kind": "original_full_schedule_positive_replay",
                        "hypothesis": row["hypothesis"],
                        "status": answer["status"],
                        "passed": answer["status"] == "certified_common_prefix",
                    }
                )
        elif q["physical_impossibility_claim"]:
            valid = recheck_queue_witness(info, q["queue_witness"])
            rechecked.append(
                {"key": p["key"], "kind": "attainable_queue_witness_recheck", "passed": valid}
            )
    atomic_json(output / "fixed_action_rechecks.json", rechecked)
    stress = [p for p in payloads if p["namespace"] in ("retired_diagnosis", "analytic")]
    for i in range(3):
        batch = run_jobs(stress, output / ("repeat-" + str(i)), workers=4)
        atomic_json(output / ("repeat-" + str(i) + "-batch.json"), batch)
    summary = summarize(output, payloads)
    atomic_json(output / "summary.json", summary)
    manifest = {str(p.relative_to(output)): sha(p) for p in output.rglob("*") if p.is_file()}
    atomic_json(output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "passed",
                    "unique_inputs",
                    "serial_statuses",
                    "diagnosed_case",
                    "timing",
                    "fixed_rechecks",
                )
            },
            indent=2,
        )
    )
    if not summary["passed"]:
        raise AssertionError("Development validity gate failed")


def verify(directory):
    directory = Path(directory)
    manifest = strict_json(directory / "manifest.json")
    actual = {
        str(p.relative_to(directory)): sha(p)
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if actual != manifest:
        raise ValueError("Development artifact changed")
    payloads = strict_json(directory / "inputs.json")
    if payloads != inputs():
        raise ValueError("Development inputs differ")
    seal = strict_json(directory / "source_binding.json")
    for name, digest in seal["source_sha256"].items():
        if sha(STUDY / name) != digest:
            raise ValueError("Bound source changed")
    summary = summarize(directory, payloads)
    if summary != strict_json(directory / "summary.json") or not summary["passed"]:
        raise ValueError("Stored validation result differs or failed")
    # Independent of stored pass flags: replay every accepted fixed action through
    # the unmodified full-schedule adjudicator, never a policy or timed trial.
    for payload in payloads:
        row = strict_json(directory / "serial/cases" / (payload["key"] + ".json"))
        if not recheck(information(payload), row["qualification"])["passed"]:
            raise ValueError("Recorded qualification failed original-code recheck")
    return {
        "passed": True,
        "files": len(actual),
        "unique_inputs": len(payloads),
        "verification_scope": "recorded identities, accounting and original-code fixed-input proof rechecks; no policy/qualification trials rerun",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if (args.output is None) == (args.verify is None):
        raise ValueError("Choose execution or verification, never both")
    if args.verify:
        print(json.dumps(verify(args.verify), indent=2))
    else:
        run(args.output)


if __name__ == "__main__":
    main()
