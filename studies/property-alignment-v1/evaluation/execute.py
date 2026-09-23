"""Pilot and protected CLI. Protected execution requires explicit Task 08 opt-in."""

from pathlib import Path
import argparse
import fcntl
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
from .analysis import analyze_directory
from .generator import STRATA, case_payload
from .runner import run_fixed_namespace, sha
from .safety import (
    atomic_json as write_json,
    strict_json as read_json,
    canonical_hash,
    safe_path,
    utc_now,
)

payload_sha = canonical_hash


def verify_freeze(path, evaluation_id):
    from .freeze import source_inventory, identity_fields

    path = safe_path(path)
    doc = read_json(path)
    if (
        doc.get("evaluation_id") != evaluation_id
        or canonical_hash(identity_fields(doc)) != evaluation_id
    ):
        raise ValueError("Evaluation identity is not the hash of its frozen design")
    if doc.get("protected_campaign_executed") is not False:
        raise ValueError("Invalid pre-execution freeze statement")
    for name, expected in doc["component_sha256"].items():
        if Path(name).name != name or sha(path.parent / name) != expected:
            raise ValueError("Frozen component drift or unsafe path")
    if source_inventory() != doc["source_sha256"]:
        raise ValueError("Frozen executable source inventory changed")
    return doc


def check_runtime(freeze):
    env = freeze["runtime"]
    if platform.python_version() != env["python"]:
        raise ValueError("Python version differs from freeze")
    for name, expected in env["packages"].items():
        if importlib.metadata.version(name) != expected:
            raise ValueError("Dependency differs: " + name)
    if platform.system() != env["system"] or platform.machine() != env["machine"]:
        raise ValueError("Protected timing platform differs; amend before execution")
    if platform.system() == "Darwin":
        actual = {
            "macos_version": platform.mac_ver()[0],
            "hardware_model": subprocess.check_output(
                ["sysctl", "-n", "hw.model"], text=True
            ).strip(),
            "processor": subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip(),
        }
        if any(env.get(k) != v for k, v in actual.items()):
            raise ValueError("Protected timing hardware or OS version differs from frozen runtime")
    if os.environ.get("OPENBLAS_NUM_THREADS") != "1":
        raise ValueError("One BLAS thread required")
    evidence = safe_path(os.environ["SAL_EVIDENCE_ROOT"])

    def git(*args):
        return subprocess.check_output(["git", "-C", str(evidence), *args], text=True).strip()

    if git("rev-parse", "HEAD") != freeze["historical_commit"] or git(
        "status", "--porcelain", "--untracked-files=no"
    ):
        raise ValueError("Historical evidence is not pinned and unchanged")
    return evidence


def _missing_episode(payload, reason):
    status = (
        "execution_timeout"
        if "timeout" in reason
        else "execution_failure_unclassified"
        if "worker_failed" in reason
        else "infrastructure_missing"
    )
    return {
        "schema": "sal-evaluation-episode/1",
        "case_id": payload_sha(payload),
        "namespace": payload["namespace"],
        "stratum": payload["stratum"],
        "index": payload["index"],
        "generator_seed": payload["generator_seed"],
        "qualification": {"eligible": True, "reason": "selected_before_candidate_execution"},
        "candidate": {
            "status": status,
            "action": None,
            "wall_s": None,
            "deadline_exceeded": None,
            "reason": reason,
        },
        "certificate_recheck": {"checked": False, "valid": None, "kind": None},
        "primary": {
            "eligible": True,
            "decisive": False,
            "on_time": False,
            "valid_certificate": False,
            "on_time_decisive_valid": False,
        },
        "pairwise_shortcut": {"applicable": False, "declares_compatible": None, "pairs": []},
        "mean_shortcut": {"declares_safe": False, "false_safe_for_full_set": False},
        "native_baselines": {"status": "not_run_due_infrastructure_missing"},
        "episode_wall_s": None,
        "physical_validation": False,
    }


def _run_protected(freeze_path, evaluation_id, output, workers):
    from .jobs import run_jobs

    freeze = verify_freeze(freeze_path, evaluation_id)
    evidence = check_runtime(freeze)
    if workers != freeze["resources"]["workers"]:
        raise ValueError("Protected worker count differs from frozen timing regime")
    output = safe_path(output)
    repo = Path(__file__).resolve().parents[3]
    if output.is_relative_to(repo) or output.is_relative_to(evidence):
        raise ValueError("Protected output cannot enter either scientific repository")
    parent = output
    while not parent.exists():
        parent = parent.parent
    if shutil.disk_usage(parent).free < 2 * 1024**3:
        raise RuntimeError("At least 2 GiB free disk is required")
    from .safety import bind_run

    bind_run(
        repo.parents[1] / ".research/evaluation-identities", evaluation_id, output, sha(freeze_path)
    )
    expected_header = {
        "schema": "sal-protected-run/2",
        "evaluation_id": evaluation_id,
        "freeze_sha256": sha(freeze_path),
        "source_commit": freeze["source_commit"],
        "workers": workers,
        "physical_validation": False,
    }
    if output.exists():
        if not (output / "run_header.json").exists():
            raise ValueError("Unowned existing output directory")
        header = read_json(output / "run_header.json")
        if any(header.get(k) != v for k, v in expected_header.items()):
            raise ValueError("Existing output belongs to another frozen run")
    else:
        output.mkdir(parents=True)
        write_json(output / "run_header.json", dict(expected_header, started_at_utc=utc_now()))
    # Exclusive advisory lock avoids simultaneous resume writers; only our run is locked.
    with (output / "execution.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (output / "completion.json").exists():
            completed = read_json(output / "completion.json")
            if completed["evaluation_id"] != evaluation_id or completed["analysis_sha256"] != sha(
                output / "analysis.json"
            ):
                raise ValueError("Completion identity changed")
            if completed["selection_sha256"] != sha(output / "selection.json"):
                raise ValueError("Completed selection changed")
            for name, digest in completed["case_sha256"].items():
                if sha(output / "cases" / name) != digest:
                    raise ValueError("Completed receipt changed")
            return read_json(output / "analysis.json")
        reserve = read_json(Path(freeze_path).parent / "protected_reserve.json")
        payloads = []
        for entry in reserve["cases"]:
            payload = case_payload("protected", entry["stratum"], entry["index"])
            if payload_sha(payload) != entry["payload_sha256"]:
                raise ValueError("Protected reserve input changed")
            payloads.append(payload)
        # All eligibility work precedes every protected full-set method call.
        work = run_jobs(
            payloads,
            output / "qualification",
            kind="qualification",
            workers=workers,
            case_limit_s=freeze["resources"]["case_wall_limit_s"],
            wall_limit_s=freeze["resources"]["phase_wall_limit_s"],
        )
        if not work["complete"]:
            return {
                "status": "qualification_incomplete",
                "work": work,
                "protected_candidate_called": False,
            }
        selected = {}
        qualified = {}
        selected_payloads = []
        for stratum in STRATA:
            eligible = []
            for p in [p for p in payloads if p["stratum"] == stratum]:
                receipt = read_json(output / "qualification" / f"{stratum}__{p['index']:05d}.json")
                if receipt["qualification"]["eligible"]:
                    eligible.append(p)
            target = freeze["design"]["target_eligible_per_stratum"]
            if len(eligible) < target:
                raise RuntimeError(
                    "Protected reserve exhausted; no candidate run or denominator substitution"
                )
            chosen = eligible[:target]
            selected[stratum] = [p["index"] for p in chosen]
            selected_payloads.extend(chosen)
            for p in chosen:
                receipt = read_json(output / "qualification" / f"{stratum}__{p['index']:05d}.json")
                qualified[payload_sha(p)] = receipt["qualification"]
        selection = {
            "schema": "sal-protected-selection/2",
            "evaluation_id": evaluation_id,
            "selection_rule": "first eligible in frozen stratum/index order before full-set outcomes",
            "selected": selected,
            "qualification_sha256": {
                p.name: sha(p) for p in sorted((output / "qualification").glob("*.json"))
            },
        }
        sp = output / "selection.json"
        if sp.exists():
            if read_json(sp) != selection:
                raise ValueError("Selected inputs or eligibility receipts changed")
        else:
            write_json(sp, selection)
        work = run_jobs(
            selected_payloads,
            output / "cases",
            kind="episode",
            workers=workers,
            qualification_records=qualified,
            case_limit_s=freeze["resources"]["case_wall_limit_s"],
            wall_limit_s=freeze["resources"]["phase_wall_limit_s"],
        )
        if not work["complete"]:
            return {
                "status": "selected_execution_incomplete",
                "work": work,
                "completed_attempts_preserved": True,
                "retry_started_cases": False,
            }
        analysis = analyze_directory(output, protected=True)
        if (output / "analysis.json").exists():
            if read_json(output / "analysis.json") != analysis:
                raise ValueError("Stored analysis differs from records")
        else:
            write_json(output / "analysis.json", analysis)
        write_json(
            output / "completion.json",
            {
                "evaluation_id": evaluation_id,
                "completed_at_utc": utc_now(),
                "analysis_sha256": sha(output / "analysis.json"),
                "selection_sha256": sha(output / "selection.json"),
                "case_sha256": {p.name: sha(p) for p in sorted((output / "cases").glob("*.json"))},
                "campaign_complete": analysis["campaign_complete"],
                "validity_claim_gate_passed": analysis["validity_claim_gate_passed"],
            },
        )
        return analysis


def run_protected(freeze_path, evaluation_id, output, workers, *, authorize_task08=False):
    if authorize_task08 is not True:
        raise PermissionError("Task 08 must be explicitly invoked before protected execution")
    return _run_protected(freeze_path, evaluation_id, output, workers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for mode in ("pilot", "calibration"):
        item = sub.add_parser(mode)
        item.add_argument("--output", type=Path, required=True)
        item.add_argument("--count-per-stratum", type=int, required=True)
        item.add_argument("--workers", type=int, default=1)
        item.add_argument("--no-native-baselines", action="store_true")
    protected = sub.add_parser("protected")
    protected.add_argument("--freeze", type=Path, required=True)
    protected.add_argument("--evaluation-id", required=True)
    protected.add_argument("--output", type=Path, required=True)
    protected.add_argument("--workers", type=int, default=4)
    protected.add_argument("--authorize-task08", action="store_true")
    args = parser.parse_args()
    if args.mode in ("pilot", "calibration"):
        if not 1 <= args.count_per_stratum <= 12 or not 1 <= args.workers <= 4:
            raise ValueError("Declared development budget exceeded")
        namespace = "development" if args.mode == "pilot" else "calibration"
        result = run_fixed_namespace(
            namespace,
            args.count_per_stratum,
            args.output,
            workers=args.workers,
            include_native=not args.no_native_baselines,
        )
    else:
        result = run_protected(
            args.freeze,
            args.evaluation_id,
            args.output,
            args.workers,
            authorize_task08=args.authorize_task08,
        )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
