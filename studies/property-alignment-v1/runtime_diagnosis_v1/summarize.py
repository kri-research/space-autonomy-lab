"""Recompute diagnostic timing/accounting from saved post-failure records only."""

from pathlib import Path
from collections import Counter
import argparse
import hashlib
import json
from .worker import atomic_new


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def summarize(directory):
    directory = Path(directory)
    complete = read(directory / "complete.json")
    header = read(directory / "run.json")
    receipts = complete["receipts"]
    if len(receipts) != 13 or len({r["label"] for r in receipts}) != 13:
        raise ValueError("Incomplete or duplicate diagnosis attempts")
    for r in receipts:
        if read(directory / (r["label"] + ".receipt.json")) != r:
            raise ValueError("Supervisor receipt mismatch")
        result = directory / r["label"] / "result.json"
        if "result_sha256" in r and sha(result) != r["result_sha256"]:
            raise ValueError("Diagnostic result bytes differ")
    trace_path = directory / "serial_trace__00137"
    trace = read(trace_path / "result.json")
    events = [json.loads(line) for line in (trace_path / "events.jsonl").read_text().splitlines()]
    actions = [x for x in events if x["event"] == "action_ended"]
    adjudications = [x for x in events if x["event"] == "adjudication_ended"]
    propagation = [x for x in events if x["event"] == "propagation_ended"]
    wall = trace["qualification_wall_s"]
    checked = sum(x["elapsed_s"] for x in adjudications)
    controls = [x for x in receipts if x["stage"] == "serial_plain" and x["index"] != 137]
    profile = directory / "serial_profile__00137/profile_summary.json"
    rows = read(profile) if profile.exists() else []
    result = {
        "schema": "sal-task08A-diagnosis-summary/1",
        "evidence_class": "post_failure_development_diagnosis",
        "unique_retired_inputs": 6,
        "diagnostic_attempts": len(receipts),
        "completed_attempts": sum(x["exit_code"] == 0 for x in receipts),
        "censored_attempts": sum(x["diagnostic_watchdog"] for x in receipts),
        "trace_case": 137,
        "trace_final_library_eligibility": trace["qualification"]["eligible"],
        "trace_qualification_wall_s": wall,
        "trace_qualification_cpu_s": trace["qualification_cpu_s"],
        "trace_adjudication_wall_s": checked,
        "trace_adjudication_fraction": checked / wall,
        "trace_propagation_wall_s": sum(x["elapsed_s"] for x in propagation),
        "trace_action_attempts": len(actions),
        "trace_action_statuses": dict(Counter(x["status"] for x in actions)),
        "trace_range_nodes": sum(x["result"]["range_evaluations"] for x in adjudications),
        "trace_ambiguous_leaves": sum(x["result"]["ambiguous_intervals"] for x in adjudications),
        "control_qualification_wall_range_s": [
            min(x["qualification_wall_s"] for x in controls),
            max(x["qualification_wall_s"] for x in controls),
        ],
        "control_parent_wall_range_s": [
            min(x["parent_wall_s"] for x in controls),
            max(x["parent_wall_s"] for x in controls),
        ],
        "profile_completed": profile.exists(),
        "profile_top_cumulative": rows[:12],
        "parallel_results": [x for x in receipts if x["stage"] == "parallel_plain"],
        "plain_slow_results": [x for x in receipts if x["index"] == 137 and x["mode"] == "plain"],
        "source_header_sha256": sha(directory / "run.json"),
        "original_campaign_complete": False,
        "protected_candidate_outcomes_computed": 0,
        "repair_implemented": False,
        "new_freeze_created": False,
        "same_run_restarted": False,
        "interpretation": "Execution diagnosis only; repeated inputs and profiler overhead do not estimate campaign coverage or platform reliability.",
    }
    if header["candidate_outcomes"] != 0 or header["original_attempt_retried"]:
        raise ValueError("Incorrect evidence scope")
    return result


def verify_recorded(directory):
    directory = Path(directory)
    manifest = read(directory / "manifest.json")
    actual = {
        str(p.relative_to(directory)): sha(p)
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    if manifest != actual:
        raise ValueError("Recorded diagnosis manifest differs")
    result = summarize(directory / "runs")
    if result != read(directory / "summary.json"):
        raise ValueError("Recorded summary differs")
    import ast

    package = Path(__file__).resolve().parent
    formatting = read(package / "executed_source/formatting.json")
    for name, record_name in (
        ("queue_probe.py", "queue-probe.json"),
        ("profile_one.py", "single-action-profile.json"),
    ):
        metadata = formatting["files"][name]
        original = package / metadata["preserved_path"]
        formatted = package / name
        if (
            sha(original) != metadata["executed_sha256"]
            or sha(formatted) != metadata["formatted_sha256"]
        ):
            raise ValueError("Executed/formatted source identity differs")
        if ast.dump(ast.parse(original.read_text()), include_attributes=False) != ast.dump(
            ast.parse(formatted.read_text()), include_attributes=False
        ):
            raise ValueError("Formatting changed executable syntax")
        if read(directory / record_name)["source_sha256"] != sha(original):
            raise ValueError("Diagnostic output has wrong execution source")
    probe = read(directory / "queue-probe.json")
    if probe["original_record_replaced"] or probe["candidate_command_computed"]:
        raise ValueError("Unexpected proof scope")
    for r in probe["rows"]:
        from fractions import Fraction

        if r["endpoint_containment"] != "violated" or Fraction(r["side_residual_m"][0]) <= 0:
            raise ValueError("Queue violation not demonstrated")
        if not 0 < r["adjudication"]["first_exit_bracket_s"][1] < 2:
            raise ValueError("Violation not before new command")
    return {
        "passed": True,
        "files": len(manifest),
        "diagnostic_attempts": len(read(directory / "runs/complete.json")["receipts"]),
        "queue_witnesses": len(probe["rows"]),
        "original_campaign_valid": False,
        "repair_implemented": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--verify", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    result = verify_recorded(a.directory) if a.verify else summarize(a.directory)
    if a.output:
        atomic_new(a.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
