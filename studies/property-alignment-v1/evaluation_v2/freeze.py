"""Deposit a new immutable freeze after repaired-interface calibration passes."""

from pathlib import Path
import argparse
import importlib.metadata
import json
import platform
import subprocess
from evaluation.safety import atomic_json, strict_json, canonical_hash, utc_now, safe_path
from .identity import ROOT, PACKAGE, REPO, PARENT_ID, inventory, identity_fields, sha
from .pipeline import file_inventory
from .reserve import build_reserve

PRESERVED = (
    "evaluation/frozen/freeze.json",
    "evaluation/frozen/protocol.json",
    "evaluation/frozen/analysis_plan.json",
    "evaluation/frozen/protected_reserve.json",
    "evaluation/recorded_pilot/manifest.json",
    "campaign_v1/recorded_attempt/manifest.json",
    "campaign_v1/recorded_summary/summary.json",
    "runtime_diagnosis_v1/recorded/manifest.json",
    "qualification_repair_v1/recorded/manifest.json",
    "qualification_repair_v1/recorded/summary.json",
    "qualification_repair_v1/recorded/inputs.json",
    "candidate/recorded_development/fixture_inputs.json",
    "candidate/recorded_development/grid.json",
)


def command(evaluation_id):
    root = '"$HOME/LaTeX/spacecraft-runtime-assurance-paper'
    return (
        "cd " + root + '/development/space-autonomy-lab/studies/property-alignment-v1" && '
        "export SAL_EVIDENCE_ROOT="
        + root
        + '/evidence/space-autonomy-lab" OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 && '
        + root
        + '/.venv-baselines/bin/python" -m evaluation_v2.execute --authorize-task08d '
        "--freeze evaluation_v2/frozen/freeze.json --evaluation-id "
        + evaluation_id
        + " --output "
        + root
        + '/.research/tasks/08D/protected-v2" --workers 4'
    )


def runtime():
    env = {
        "python": platform.python_version(),
        "system": platform.system(),
        "machine": platform.machine(),
        "packages": {},
    }
    if env["system"] == "Darwin":
        env.update(
            macos_version=platform.mac_ver()[0],
            hardware_model=subprocess.check_output(["sysctl", "-n", "hw.model"], text=True).strip(),
            processor=subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip(),
        )
    for line in (ROOT / "protective/requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, expected = line.split("==")
            actual = importlib.metadata.version(name)
            if actual != expected:
                raise ValueError("Locked dependency changed: " + name)
            env["packages"][name] = actual
    return env


def check_calibration(directory):
    directory = Path(directory)
    manifest = strict_json(directory / "manifest.json")
    observed = {
        p.relative_to(directory).as_posix(): sha(p)
        for p in directory.rglob("*")
        if p.is_file() and p.name != "manifest.json" and not p.name.endswith(".lock")
    }
    # Nested completion receipts are themselves evidence and are included by the package manifest.
    if manifest != observed:
        raise ValueError("Integration calibration artifact differs")
    result = strict_json(directory / "result.json")
    if (
        result.get("passed") is not True
        or result.get("protected_evaluations") != 0
        or result.get("unique_inputs") != 8
    ):
        raise ValueError("Completed calibration-only interface validation required")
    then = strict_json(directory / "sources.json")
    now = inventory()
    # Test/report-only edits after the measured calibration cannot affect production semantics.
    if then != now:
        raise ValueError("Source identity changed since measured integration calibration")
    for name in ("serial", "parallel"):
        completed = strict_json(directory / name / "completion.json")
        if completed["files"] != file_inventory(directory / name):
            raise ValueError("Completed pipeline bytes differ")
    return result


def create(calibration, output):
    output = safe_path(output)
    if output.exists():
        raise ValueError("Freeze is write-once; preserve prior identity before amendment")
    cal = check_calibration(calibration)
    design = strict_json(PACKAGE / "design.json")
    sources = inventory()
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    for name, digest in sources.items():
        raw = subprocess.check_output(
            ["git", "-C", str(REPO), "show", commit + ":studies/property-alignment-v1/" + name]
        )
        import hashlib

        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Commit source before freezing: " + name)
    env = runtime()
    preserved = {name: sha(ROOT / name) for name in PRESERVED}
    reserve = build_reserve()
    original_plan = strict_json(ROOT / "evaluation/frozen/analysis_plan.json")
    original_plan = {
        **original_plan,
        "replacement_note": "Same frozen analysis implementation, binary endpoint, N=768 and conditional-mean interval. Eligibility now uses the explicitly versioned repaired qualifier and definite-claim recheck.",
    }
    amendment = {
        "schema": "sal-prospective-amendment/1",
        "recorded_at_utc": utc_now(),
        "parent_evaluation_id": PARENT_ID,
        "old_attempt_status": "protocol_invalid_preserved",
        "old_candidate_outcomes": 0,
        "reason": "Qualification runtime defect diagnosed in08A and validated additive repair in08B; integrate before new evaluation.",
        "changes": design["changes"] + [design["freshness_rule"]],
        "unchanged": design["unchanged"],
        "no_old_outcome_replaced": True,
        "protected_replacement_executed": False,
    }
    exposure = {
        "schema": "sal-replacement-exposure/1",
        "old_namespace_retired_entirely": True,
        "prior_work": "All historical studies, Tasks04-06, original pilot/calibration, failed reserve, 08A retired-case diagnosis and08B repair development are prior knowledge.",
        "integration": "Eight previously exposed original calibration cases; synthetic failure fixtures; no new protected outcome.",
        "freshness": "Exact-information identity retirement before science; all rejected identities retained in reserve.json.",
        "new_protected_outcomes_seen": False,
        "external_preregistration_claimed": False,
    }
    components = {
        "protocol.json": design,
        "analysis_plan.json": original_plan,
        "reserve.json": reserve,
        "amendment.json": amendment,
        "exposure.json": exposure,
        "integration_receipt.json": cal,
    }
    output.mkdir(parents=True)
    for name, doc in components.items():
        atomic_json(output / name, doc)
    resources = design["resources"]
    # Scale measured full-pipeline calibration conservatively by the reserve/selection work count.
    projection = cal["executions"]["parallel"]["wall_s"] / 16 * (1152 + 768)
    doc = {
        "schema": "sal-replacement-freeze/1",
        "created_at_utc": utc_now(),
        "parent_evaluation_id": PARENT_ID,
        "source_commit": commit,
        "source_sha256": sources,
        "component_sha256": {k: sha(output / k) for k in components},
        "preserved_artifact_sha256": preserved,
        "historical_commit": "5539de5753092b09fd78351095292e7627047794",
        "design": design,
        "resources": resources,
        "runtime": env,
        "integration_manifest_sha256": sha(Path(calibration) / "manifest.json"),
        "rough_workload_projection_s": projection,
        "resource_estimate_scope": "Scaled real-clock eight-case calibration, not a worst-case bound; allow host and difficult-case variation. No paid compute.",
        "protected_campaign_executed": False,
        "external_preregistration_claimed": False,
        "identity_statement": "Before-execution Git deposit and byte bindings; no independent proof of absent access.",
    }
    doc["evaluation_id"] = canonical_hash(identity_fields(doc))
    doc["task08d_execution_command"] = command(doc["evaluation_id"])
    atomic_json(output / "freeze.json", doc)
    return doc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--calibration", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    doc = create(a.calibration, a.output)
    print(
        json.dumps(
            {
                "evaluation_id": doc["evaluation_id"],
                "rough_workload_projection_s": doc["rough_workload_projection_s"],
                "task08d_execution_command": doc["task08d_execution_command"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
