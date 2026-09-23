"""Production-path integration on eight already exposed calibration inputs only."""

from pathlib import Path
import argparse
import json
import time
from evaluation.generator import case_payload as original_payload, STRATA
from evaluation.safety import atomic_json, strict_json, safe_path, canonical_hash
from .pipeline import pipeline, file_inventory, sha
from .jobs import run_batch
from .identity import inventory, REPO
from .receipts import key


def calibrate(output):
    output = safe_path(output)
    if output.exists() or output.is_relative_to(REPO):
        raise ValueError("New private calibration directory required")
    output.mkdir(parents=True)
    payloads = [original_payload("calibration", s, i) for s in STRATA for i in range(2)]
    atomic_json(output / "inputs.json", payloads)
    source = inventory()
    atomic_json(output / "sources.json", source)
    executions = {}
    started = time.perf_counter()
    for label, workers in (("serial", 1), ("parallel", 4)):
        resources = {"workers": workers, "case_wall_limit_s": 15.0, "phase_wall_limit_s": 1800.0}
        begin = time.perf_counter()
        result = pipeline(
            payloads,
            output / label,
            identity="replacement-integration-" + label,
            resources=resources,
            target_per_stratum=2,
        )
        if not result.get("campaign_complete") or not result.get("validity_claim_gate_passed"):
            raise AssertionError("Integration did not complete with checked evidence")
        executions[label] = {
            "wall_s": time.perf_counter() - begin,
            "on_time_valid": result["on_time_decisive_valid"],
            "candidate_statuses": result["candidate_statuses"],
            "qualification_statuses": result["qualification_statuses"],
        }
    qualification_agreement = True
    for p in payloads:
        a = strict_json(output / "serial/qualification/cases" / (key(p) + ".json"))["qualification"]
        b = strict_json(output / "parallel/qualification/cases" / (key(p) + ".json"))[
            "qualification"
        ]
        qualification_agreement &= (
            a["status"],
            a["eligible"],
            [r["witness_action"] for r in a["hypotheses"]],
        ) == (b["status"], b["eligible"], [r["witness_action"] for r in b["hypotheses"]])
    if not qualification_agreement:
        raise AssertionError("Numerical qualification changed with concurrency")
    completed = file_inventory(output / "parallel")
    pipeline(
        payloads,
        output / "parallel",
        identity="replacement-integration-parallel",
        resources={"workers": 4, "case_wall_limit_s": 15.0, "phase_wall_limit_s": 1800.0},
        target_per_stratum=2,
    )
    if completed != file_inventory(output / "parallel"):
        raise AssertionError("Completed pipeline replay changed bytes")
    directory = output / "checkpoint"
    context = "replacement-qualification-checkpoint"
    first = run_batch(
        payloads, directory, kind="qualification", context_id=context, workers=4, max_new=3
    )
    kept = {p.name: sha(p) for p in (directory / "cases").glob("*.json")}
    second = run_batch(payloads, directory, kind="qualification", context_id=context, workers=4)
    if first["complete"] or not second["complete"] or second["blockers"]:
        raise AssertionError("Checkpoint execution did not complete")
    if any(sha(directory / "cases" / name) != digest for name, digest in kept.items()):
        raise AssertionError("Checkpoint overwrote a receipt")
    if source != inventory():
        raise ValueError("Sources changed during calibration")
    result = {
        "schema": "sal-replacement-integration/1",
        "passed": True,
        "namespace": "calibration",
        "unique_inputs": 8,
        "full_pipelines": 2,
        "qualification_attempts": 24,
        "candidate_attempts": 16,
        "serial_parallel_qualification_equivalent": True,
        "completed_pipeline_read_only": True,
        "checkpoint_receipts_preserved": True,
        "executions": executions,
        "total_wall_s": time.perf_counter() - started,
        "input_sha256": sha(output / "inputs.json"),
        "source_sha256": canonical_hash(source),
        "protected_evaluations": 0,
        "physical_validation": False,
        "timing_scope": "Observed real-clock execution of eight reused calibration fixtures. Deadline-sensitive outputs need not be identical across hosts or repetitions; no worst-case bound or independent replication claim.",
    }
    atomic_json(output / "result.json", result)
    atomic_json(output / "manifest.json", file_inventory(output))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    print(json.dumps(calibrate(p.parse_args().output), indent=2))


if __name__ == "__main__":
    main()
