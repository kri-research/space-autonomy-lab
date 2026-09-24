"""Publish/verify the complete post hoc audit and deterministic proof transcripts.

Build only into a new directory. Verification recomputes each recorded continuous
leaf enclosure and saved negative margin, never a policy or command-library search.
"""

from pathlib import Path
from fractions import Fraction as Q
from collections import Counter
import argparse
import csv
import hashlib
import io
import json
import subprocess
import tempfile
import time
from independent_hcw_audit_v1.schema import strict_json, require
from independent_hcw_audit_v1.reader import STRATA, read_pair, safe_name
from independent_hcw_audit_v1.certificates import check_obstruction
from .population import ROOT, STUDY, SCIENCE, AUDIT_ID, load_original
from .report import job_for, json_bytes, verify_attempt, summarize
from .trace import trace_prefix, verify_trace


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(json_bytes(doc))


def line(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def table(summary):
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\n")
    w.writerow(
        [
            "stratum",
            "selected",
            "original_prefixes",
            "original_obstructions",
            "original_unresolved",
            "original_late",
            "independent_prefixes",
            "independent_obstructions",
            "original_nondeliveries_retained",
            "other_audit_outcomes",
            "qualification_witnesses",
            "verified_qualification_witnesses",
        ]
    )
    for g in summary["groups"]:
        o, a = g["original_statuses"], g["independent_statuses"]
        w.writerow(
            [
                g["stratum"],
                g["selected"],
                *[
                    o.get(k, 0)
                    for k in (
                        "certified_common_prefix",
                        "proved_no_common_held_command",
                        "unresolved",
                        "unresolved_budget",
                    )
                ],
                *[
                    a.get(k, 0)
                    for k in ("verified_prefix", "verified_obstruction", "no_on_time_certificate")
                ],
                sum(
                    v
                    for k, v in a.items()
                    if k
                    not in ("verified_prefix", "verified_obstruction", "no_on_time_certificate")
                ),
                g["qualification_witnesses"],
                g["qualification_outcomes"].get("verified_prefix", 0),
            ]
        )
    return out.getvalue()


def trace_one(source, receipt, settings):
    info, candidate, actions = read_pair(
        source["payload"], source["episode"], source["qualification"]
    )
    result = receipt["result"]
    trace = {"key": source["key"], "primary": None, "qualification": []}
    if candidate["status"] == "certified_common_prefix" and result["claim"]["status"] not in (
        "audit_timeout",
        "audit_execution_failure",
        "audit_interrupted",
        "binding_invalid_evidence",
    ):
        trace["primary"] = trace_prefix(
            info, tuple(map(Q, candidate["action"])), result["claim"], settings
        )
    for q in result.get("qualification_witnesses", []):
        i = q["hypothesis"]
        trace["qualification"].append(
            {
                "hypothesis": i,
                "trace": trace_prefix(info.singleton(i), actions[i], q["audit"], settings),
            }
        )
    return trace


def check_trace_one(source, receipt, settings, trace):
    require(trace.get("key") == source["key"], "Swapped transcript")
    info, candidate, actions = read_pair(
        source["payload"], source["episode"], source["qualification"]
    )
    result = receipt["result"]
    checks = Counter()
    primary = trace.get("primary")
    expected_primary = candidate["status"] == "certified_common_prefix" and result["claim"][
        "status"
    ] not in (
        "audit_timeout",
        "audit_execution_failure",
        "audit_interrupted",
        "binding_invalid_evidence",
    )
    require((primary is not None) is expected_primary, "Missing or extra primary transcript")
    if primary is not None:
        check = verify_trace(
            info, tuple(map(Q, candidate["action"])), result["claim"], settings, primary
        )
        checks["primary_prefix_transcripts"] += 1
        checks["continuous_leaves"] += check["leaves"]
    if result["claim"]["status"] == "verified_obstruction":
        require(
            check_obstruction(info, candidate["negative"]) == result["claim"],
            "Rebuilt original-weight negative certificate differs",
        )
        checks["negative_margin_rechecks"] += 1
    q = trace.get("qualification")
    expected = result.get("qualification_witnesses", [])
    require(type(q) is list and len(q) == len(expected), "Missing qualification transcript")
    for row, old in zip(q, expected, strict=True):
        i = old["hypothesis"]
        require(row["hypothesis"] == i, "Swapped singleton transcript")
        check = verify_trace(info.singleton(i), actions[i], old["audit"], settings, row["trace"])
        checks["qualification_transcripts"] += 1
        checks["continuous_leaves"] += check["leaves"]
    return checks


def build(attempt, output, execution_receipt):
    attempt, output = Path(attempt).resolve(), Path(output).absolute()
    require(
        not output.exists() and not any(x.is_symlink() for x in (output, *output.parents)),
        "New safe artifact output required",
    )
    frozen, records, reserve, population = load_original()
    receipts = verify_attempt(attempt, records, frozen)
    rows, discrepancies, summary = summarize(records, receipts, population)
    repository = STUDY.parents[1]
    commit = strict_json((ROOT / "source_binding.json").read_bytes())["source_commit"]
    source_files = {x.relative_to(ROOT).as_posix(): digest(x) for x in ROOT.glob("*.py")}
    for name, h in source_files.items():
        raw = subprocess.check_output(
            [
                "git",
                "--no-replace-objects",
                "-C",
                str(repository),
                "show",
                commit + ":studies/property-alignment-v1/independent_hcw_campaign_v1/" + name,
            ]
        )
        require(
            hashlib.sha256(raw).hexdigest() == h,
            "Report source must be committed before trace expansion",
        )
    output.mkdir(parents=True)
    start = time.monotonic()
    write_new(output / "population.json", population)
    write_new(output / "reserve_ledger.json", reserve)
    write_new(output / "summary.json", summary)
    write_new(output / "discrepancies.json", discrepancies)
    (output / "group_summary.csv").write_text(table(summary))
    with (output / "cases.jsonl").open("x") as stream:
        for row in rows:
            stream.write(line(row))
    all_files = {
        f.relative_to(attempt).as_posix(): digest(f)
        for f in sorted(attempt.rglob("*"))
        if f.is_file()
    }
    with (output / "audit_records.jsonl").open("x") as stream:
        for rel, h in all_files.items():
            if rel.startswith("jobs/"):
                continue
            stream.write(line({"path": rel, "raw_utf8": (attempt / rel).read_text()}))
    write_new(
        output / "original_attempt_manifest.json",
        {
            "files": all_files,
            "omitted_job_files": "Exact bytes reconstructed from bound original records and frozen settings; hashes remain in this inventory",
        },
    )
    trace_counts = Counter()
    settings = frozen["protocol"]["numerical"]
    for st in STRATA:
        path = output / "traces" / (st + ".jsonl")
        path.parent.mkdir(exist_ok=True)
        with path.open("x") as stream:
            for source, receipt in zip(records, receipts, strict=True):
                if source["payload"]["stratum"] != st:
                    continue
                require(time.monotonic() - start < 1800, "Supplemental trace phase budget exceeded")
                traced = trace_one(source, receipt, settings)
                trace_counts.update(check_trace_one(source, receipt, settings, traced))
                stream.write(line(traced))
                stream.flush()
    execution = strict_json(Path(execution_receipt).read_bytes())
    write_new(
        output / "execution.json",
        {
            "audit_id": AUDIT_ID,
            "started_at_utc": execution["started_at_utc"],
            "ended_at_utc": execution["ended_at_utc"],
            "exit_code": execution["exit_code"],
            "audit_wall_s": execution["elapsed_s"],
            "exact_R02_command_sha256": execution["command_sha256"],
            "trace_expansion_wall_s": time.monotonic() - start,
            "trace_checks": dict(trace_counts),
            "trace_code_commit": commit,
            "trace_class": "supplemental deterministic fixed-output replay under unchanged R02 settings; never changes first audit classifications",
            "original_policy_executed": False,
            "new_probability_inference": False,
        },
    )
    write_new(
        output / "manifest.json",
        {
            "schema": "sal-independent-hcw-campaign-artifact/1",
            "audit_id": AUDIT_ID,
            "scientific_source_commit": SCIENCE,
            "numerical_source_commit": frozen["implementation_commit"],
            "report_source_commit": commit,
            "auditor_freeze_sha256": digest(
                STUDY / "independent_hcw_audit_v1/frozen/protocol.json"
            ),
            "report_source_sha256": source_files,
            "files": {
                f.relative_to(output).as_posix(): digest(f)
                for f in sorted(output.rglob("*"))
                if f.is_file()
            },
            "original_counts_or_timing_rewritten": False,
            "physical_or_human_validation": False,
        },
    )
    return verify(output)


def verify(directory=ROOT / "recorded"):
    directory = Path(directory)
    manifest = strict_json((directory / "manifest.json").read_bytes())
    require(
        manifest.get("schema") == "sal-independent-hcw-campaign-artifact/1"
        and manifest.get("audit_id") == AUDIT_ID,
        "Artifact identity",
    )
    require(manifest.get("scientific_source_commit") == SCIENCE, "Scientific anchor")
    files = {
        f.relative_to(directory).as_posix(): digest(f)
        for f in directory.rglob("*")
        if f.is_file() and f != directory / "manifest.json"
    }
    require(files == manifest["files"], "Artifact file inventory changed")
    anchor = strict_json((ROOT / "source_binding.json").read_bytes())
    generation = anchor["accepted_generators"].get(manifest["report_source_commit"])
    require(
        generation == manifest["report_source_sha256"],
        "Generating source differs from trusted installed binding",
    )
    repository = STUDY.parents[1]
    for commit, sources in (
        (manifest["report_source_commit"], generation),
        (anchor["source_commit"], anchor["files"]),
    ):
        for name, h in sources.items():
            safe_name(name)
            blob = subprocess.check_output(
                [
                    "git",
                    "--no-replace-objects",
                    "-C",
                    str(repository),
                    "show",
                    commit + ":studies/property-alignment-v1/independent_hcw_campaign_v1/" + name,
                ]
            )
            require(
                hashlib.sha256(blob).hexdigest() == h,
                "Reporter content differs from actual Git blob",
            )
    require(
        {x.name for x in ROOT.glob("*.py")} == set(anchor["files"]),
        "Incomplete current reader source inventory",
    )
    for name, h in anchor["files"].items():
        require(digest(ROOT / name) == h, "Current verification source drift")
    require(
        digest(STUDY / "independent_hcw_audit_v1/frozen/protocol.json")
        == manifest["auditor_freeze_sha256"],
        "Auditor freeze drift",
    )
    frozen, records, reserve, population = load_original()
    require(
        manifest["numerical_source_commit"] == frozen["implementation_commit"],
        "Numerical source identity",
    )
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp).resolve()
        seen = set()
        for row in (
            strict_json(x) for x in (directory / "audit_records.jsonl").read_text().splitlines()
        ):
            rel = safe_name(row["path"])
            require(rel not in seen and not rel.startswith("jobs/"), "Duplicate raw audit member")
            seen.add(rel)
            dest = output / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(row["raw_utf8"])
        for record in records:
            write_new(
                output / "jobs" / (record["key"] + ".json"),
                {"job": job_for(record), "settings": frozen["protocol"]["numerical"]},
            )
        rebuilt = {
            f.relative_to(output).as_posix(): digest(f) for f in output.rglob("*") if f.is_file()
        }
        require(
            rebuilt
            == strict_json((directory / "original_attempt_manifest.json").read_bytes())["files"],
            "Raw attempt reconstruction differs",
        )
        receipts = verify_attempt(output, records, frozen)
    rows, discrepancies, summary = summarize(records, receipts, population)
    for name, value in (
        ("population.json", population),
        ("reserve_ledger.json", reserve),
        ("summary.json", summary),
        ("discrepancies.json", discrepancies),
    ):
        require(
            strict_json((directory / name).read_bytes()) == value, "Derived report differs " + name
        )
    require(
        (directory / "cases.jsonl").read_text() == "".join(map(line, rows)),
        "All-case ledger differs",
    )
    require((directory / "group_summary.csv").read_text() == table(summary), "Group table differs")
    trace_rows = []
    for st in STRATA:
        trace_rows.extend(
            strict_json(x)
            for x in (directory / "traces" / (st + ".jsonl")).read_text().splitlines()
        )
    require([x["key"] for x in trace_rows] == [x["key"] for x in records], "Trace membership/order")
    counts = Counter()
    for source, receipt, traced in zip(records, receipts, trace_rows, strict=True):
        counts.update(check_trace_one(source, receipt, frozen["protocol"]["numerical"], traced))
    require(
        dict(counts) == strict_json((directory / "execution.json").read_bytes())["trace_checks"],
        "Transcript accounting differs",
    )
    return {
        "passed": True,
        "artifact_reader_version": 2,
        "audit_id": AUDIT_ID,
        "selected": 768,
        "independent_statuses": summary["independent_statuses"],
        "qualification_outcomes": summary["qualification_outcomes"],
        "discrepancies": len(discrepancies),
        "trace_checks": dict(counts),
        "original_policy_executed": False,
        "independent_human_review_asserted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["build", "verify"])
    p.add_argument("--directory", type=Path, default=ROOT / "recorded")
    p.add_argument("--attempt", type=Path)
    p.add_argument("--execution-receipt", type=Path)
    a = p.parse_args()
    result = (
        verify(a.directory)
        if a.mode == "verify"
        else build(a.attempt, a.directory, a.execution_receipt)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
