"""Write-once evaluation freeze from retained development evidence only."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
from .generator import STRATA, case_payload
from .statistics import PER_STRATUM, PRIMARY_N, hoeffding_half_width
from .analysis import analyze_rows
from .safety import atomic_json, canonical_hash, strict_json, safe_path, check_receipt

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
RETIRED_INPUT_COUNT = 32


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_inventory():
    paths = []
    for directory in (
        "evaluation",
        "candidate",
        "protective",
        "adjudication",
        "specification",
        "baseline/validation",
    ):
        paths.extend((ROOT / directory).rglob("*.py"))
    paths.extend(
        ROOT / p
        for p in (
            "specification/property_contract.json",
            "candidate/claim_limits.json",
            "candidate/protocol.json",
            "candidate/seal.json",
            "protective/protocol.json",
            "protective/requirements.txt",
            "evaluation/pilot_protocol.json",
        )
    )
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(paths)) if p.is_file()}


def identity_fields(doc):
    return {k: v for k, v in doc.items() if k not in ("evaluation_id", "task08_execution_command")}


def exact_command(evaluation_id):
    root = '"$HOME/LaTeX/spacecraft-runtime-assurance-paper'
    return (
        "cd " + root + '/development/space-autonomy-lab/studies/property-alignment-v1" && '
        "export SAL_EVIDENCE_ROOT=" + root + '/evidence/space-autonomy-lab" '
        "OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 && "
        + root
        + '/.venv-baselines/bin/python" -m evaluation.execute protected '
        "--authorize-task08 --freeze evaluation/frozen/freeze.json "
        "--evaluation-id "
        + evaluation_id
        + " --output "
        + root
        + '/.research/tasks/08/protected-v1" --workers 4'
    )


def reserve_count(analysis):
    minimum = min(analysis["per_stratum"][s]["eligible"] / 12 for s in STRATA)
    if minimum >= 0.90:
        return 288
    if minimum >= 0.60:
        return 384
    raise RuntimeError("Original pilot eligibility gate blocks freezing")


def freeze(pilot, output, calibration):
    pilot, output = safe_path(pilot), safe_path(output)
    if output.exists():
        raise ValueError("Freeze is write-once; use a separately amended identity")
    manifest = strict_json(pilot / "manifest.json")
    for name, digest in manifest.items():
        p = pilot / name
        if not p.is_relative_to(pilot) or sha(p) != digest:
            raise ValueError("Retained pilot hash mismatch")
    rows = [strict_json(p) for p in sorted((pilot / "cases").glob("*.json"))]
    if len(rows) != 48 or any(r["namespace"] != "development" for r in rows):
        raise ValueError("Expected original 48 development pilot cases")
    for r in rows:
        check_receipt(r, case_payload("development", r["stratum"], r["index"]))
    analysis = analyze_rows(rows)
    if analysis["invalid_definite_certificates"]:
        raise ValueError("Unverified candidate certificates block the freeze")
    summary = strict_json(pilot / "summary.json")
    if summary["on_time_decisive_valid"] != analysis["on_time_decisive_valid"]:
        raise ValueError("Pilot primary counts changed")
    reserve = reserve_count(analysis)
    sources = source_inventory()
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    for name, digest in sources.items():
        raw = subprocess.check_output(
            ["git", "-C", str(REPO), "show", commit + ":studies/property-alignment-v1/" + name]
        )
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Commit all frozen code before depositing the freeze: " + name)
    runtime = {
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "packages": {},
    }
    if platform.system() == "Darwin":
        runtime["macos_version"] = platform.mac_ver()[0]
        runtime["hardware_model"] = subprocess.check_output(
            ["sysctl", "-n", "hw.model"], text=True
        ).strip()
        runtime["processor"] = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip()
    for line in (ROOT / "protective/requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, expected = line.split("==")
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise ValueError("Installed dependency differs from existing lock: " + name)
        runtime["packages"][name] = actual
    cal = strict_json(calibration)
    if not cal["passed"] or cal["namespace"] != "calibration":
        raise ValueError("Fresh-process calibration/restart checks required")
    protocol = {
        "schema": "sal-frozen-evaluation-protocol/2",
        "evidence_class": "prospective_synthetic_evaluation",
        "primary_question": "On-time checked common-prefix or HCW obstruction coverage among individually prefix-qualified synthetic information sets",
        "strata": list(STRATA),
        "weights": [0.25] * 4,
        "target_per_stratum": PER_STRATUM,
        "target_total": PRIMARY_N,
        "qualification": "All hypotheses admit the known queue plus next one-second HCW prefix under the fixed 13-action qualification library; not full recovery",
        "selection": "All reserve qualification precedes any full-set candidate evaluation. Select first 192 qualified IDs per stratum, never using candidate outcomes.",
        "retired_indices": [0, RETIRED_INPUT_COUNT - 1],
        "retirement_reason": "Early tests inspected initial membership of these inputs; conservatively exclude all 32 per stratum even though no candidate or qualification outcome was computed",
        "failure_semantics": "Unresolved, budget miss, invalid/unverified proof or started-case execution failure are zero primary successes. Incomplete unstarted selection withholds final inference.",
        "primary_inference": {
            "alpha": 0.05,
            "sample_size": PRIMARY_N,
            "sampling_half_width_bound": hoeffding_half_width(PRIMARY_N),
            "target": "average conditional success probability in frozen stratum/index reveal order",
            "dependence": "Conditional Hoeffding derivation permits dependent hardware timing; a fixed generator success-probability interpretation additionally requires independent execution outcomes",
            "no_hardware_reliability_inference": True,
            "one_confirmatory_estimate": True,
        },
        "secondary": "Descriptive only: status composition, genuine false-safe witnesses versus unresolved shortcuts, native baseline outputs, paired discordance and timing. Different continuation obligations preclude superiority claims.",
        "meaningful_difference": "Five percentage points is an estimation-resolution target, not powered effect detection, equivalence, operational safety or a journal-driven success threshold.",
        "historical_data_in_denominator": False,
        "held_out_transfer_family_used": False,
        "plant": "HCW for protected diagnostic; no negative-certificate transfer to nonlinear dynamics",
        "task_phases": "measurement-time exact information set, fixed age/queue, decision, held-input prefix; no mission completion or abort controller is evaluated",
        "fault_model": "Exact synthetic ambiguous information sets and quarter-second bounded actuation disturbances; no Gaussian-tail or sensor-calibration claim",
        "outside_assumption_checks": "fixed covariance-only, outer-only and reduced-effectiveness stress fixtures excluded from primary denominator",
    }
    analysis_plan = {
        "schema": "sal-frozen-analysis-plan/2",
        "primary_endpoint": "on_time_decisive_valid",
        "valid": "Candidate returns a definite result within its one-second policy budget and fixed certificate replay passes",
        "qualification_denominator": "192 selected per stratum; no post-candidate exclusion",
        "numerical_unknown": "No certificate counted verified or safe solely because computation failed",
        "mean_shortcut": "Failed sufficient check is unresolved. Confirmed false-safe requires a validated violation or a checked full-set impossibility certificate.",
        "multiplicity": "One alpha=.05 conditional-mean estimate; all additional quantities descriptive without confirmatory p-values",
        "inferential_proof": "For X_i in [0,1], p_i=E[X_i|F_(i-1)], conditional MGF <= exp(lambda^2/8). Iteration and optimization at lambda=4*epsilon give two-sided bound 2*exp(-2*N*epsilon^2).",
        "independence_limit": "One Mac and one session do not demonstrate independent timing or platform variation. The unconditional fixed-generator interpretation is not asserted.",
        "stopping": "No efficacy/futility stopping. Pause for resource budget, source mismatch, corruption or user interruption; resume only the same identity. Started unfinished candidate cases become failures without re-execution. Qualification interruption blocks selection.",
        "reserve_exhaustion": "No candidate execution and no denominator replacement; preserve the attempt and amend prospectively",
        "incomplete": "No balanced interval until complete equal stratum counts. Missing selected receipts remain visible.",
        "validity_gate": "Any definite certificate failing revalidation blocks a validity claim; distinguishes a failed check from an actual contrary witness",
    }
    protected = {
        "schema": "sal-protected-reserve/2",
        "namespace": "protected",
        "reserve_per_stratum": reserve,
        "first_index": RETIRED_INPUT_COUNT,
        "outcomes_computed": False,
        "cases": [
            {
                "stratum": s,
                "index": i,
                "payload_sha256": canonical_hash(case_payload("protected", s, i)),
            }
            for s in STRATA
            for i in range(RETIRED_INPUT_COUNT, RETIRED_INPUT_COUNT + reserve)
        ],
    }
    recording = {
        "schema": "sal-evaluation-recording/2",
        "case_schema": "evaluation/safety.py check_receipt",
        "source": "evaluation/episode.py",
        "selection_bound_before_candidate": True,
        "atomicity": "fsync temporary then exclusive hard-link publish; never overwrite; per-case start marker and bounded subprocess",
        "preservation": "All qualification attempts and started-case failures retained. Final case hashes and analysis hash recorded.",
        "full_inputs": "Deterministic generator plus frozen seed-key/payload identities; exact set, queue, timing, authority and bounds reconstruct every selected case",
    }
    output.mkdir(parents=True)
    documents = {
        "protocol.json": protocol,
        "analysis_plan.json": analysis_plan,
        "protected_reserve.json": protected,
        "recording_schema.json": recording,
        "pilot_review.json": analysis,
        "calibration_receipt.json": cal,
        "pre_freeze_review.json": strict_json(PACKAGE / "pre_freeze_review.json"),
        "exposure_history.json": strict_json(PACKAGE / "exposure_history.json"),
        "retained_manifest.json": strict_json(PACKAGE / "retained_manifest.json"),
        "method_sources.json": strict_json(PACKAGE / "method_sources.json"),
    }
    for name, document in documents.items():
        atomic_json(output / name, document)
    (output / "amendments.jsonl").open("x").close()
    components = {name: sha(output / name) for name in [*documents, "amendments.jsonl"]}
    rough = cal["parallel_wall_s"] / cal["cases"] * PRIMARY_N
    doc = {
        "schema": "sal-evaluation-freeze/2",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit,
        "source_sha256": sources,
        "component_sha256": components,
        "historical_commit": "5539de5753092b09fd78351095292e7627047794",
        "design": {
            "target_eligible_per_stratum": PER_STRATUM,
            "target_total": PRIMARY_N,
            "reserve_per_stratum": reserve,
            "first_index": RETIRED_INPUT_COUNT,
            "strata": list(STRATA),
        },
        "runtime": runtime,
        "resources": {
            "workers": 4,
            "blas_threads": 1,
            "case_wall_limit_s": 15.0,
            "phase_wall_limit_s": 1800.0,
            "minimum_free_disk_bytes": 2 * 1024**3,
            "receipt_directory_limit_bytes": 512 * 1024**2,
            "process_model": "fresh spawn per case; qualification phase separate",
            "measured_calibration_scaled_candidate_wall_s": rough,
            "rough_total_workload_projection_s": cal["parallel_wall_s"]
            / cal["cases"]
            * (PRIMARY_N + reserve * 4),
            "projection_assumption": "Conservatively assigns a complete calibration-case cost also to each qualification reserve item; startup/load and rare difficult cases may differ",
            "suggested_memory_reserve_bytes": 2 * 1024**3,
            "memory_reserve_is_hard_limit": False,
            "qualification_reserve_max": reserve * 4,
            "estimate_includes_host_variability": False,
            "paid_cloud_required": False,
        },
        "protected_campaign_executed": False,
        "external_preregistration_claimed": False,
        "identity_statement": "Immutable byte identity and before-execution Git deposit; no independent absence-of-access certification",
    }
    doc["evaluation_id"] = canonical_hash(identity_fields(doc))
    doc["task08_execution_command"] = exact_command(doc["evaluation_id"])
    atomic_json(output / "freeze.json", doc)
    return doc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pilot", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--calibration", type=Path, required=True)
    a = p.parse_args()
    result = freeze(a.pilot, a.output, a.calibration)
    print(
        json.dumps(
            {
                "evaluation_id": result["evaluation_id"],
                "design": result["design"],
                "resources": result["resources"],
                "task08_execution_command": result["task08_execution_command"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
