"""CLI for development/calibration runs and the separately authorized protected run."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import argparse
import hashlib
import json

from .analysis import analyze_directory
from .episode import run_case
from .generator import STRATA, case_payload
from .runner import (
    qualification_receipt,
    read_json,
    run_fixed_namespace,
    sha,
    write_json,
)


def payload_sha(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def verify_freeze(path, evaluation_id):
    doc = read_json(path)
    if doc.get("evaluation_id") != evaluation_id:
        raise ValueError("Evaluation identity does not match frozen protocol")
    for name, expected in doc["component_sha256"].items():
        actual = sha(Path(path).parent / name)
        if actual != expected:
            raise ValueError("Frozen component drift: " + name)
    if doc.get("protected_campaign_executed") is not False:
        raise ValueError("Invalid pre-execution freeze state")
    return doc


def _missing_episode(payload, reason):
    return {
        "schema": "sal-evaluation-episode/1",
        "case_id": payload_sha(payload),
        "namespace": payload["namespace"],
        "stratum": payload["stratum"],
        "index": payload["index"],
        "generator_seed": payload["generator_seed"],
        "qualification": {"eligible": True, "reason": "selected_before_candidate_execution"},
        "candidate": {
            "status": "infrastructure_missing",
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


def run_protected(freeze_path, evaluation_id, output, workers):
    freeze = verify_freeze(freeze_path, evaluation_id)
    output = Path(output).expanduser().resolve()
    study = Path(__file__).resolve().parents[1]
    if output.is_relative_to(study) or output.is_relative_to(study.parents[1]):
        raise ValueError("Protected output must be outside both public repositories")
    if output.exists():
        header = output / "run_header.json"
        if not header.exists() or read_json(header).get("evaluation_id") != evaluation_id:
            raise ValueError("Existing output is not the same protected run")
    else:
        output.mkdir(parents=True)
        write_json(
            output / "run_header.json",
            {
                "schema": "sal-protected-run/1",
                "evaluation_id": evaluation_id,
                "freeze_sha256": sha(freeze_path),
                "source_commit": freeze["source_commit"],
                "protected_results_observed_before_start": False,
                "physical_validation": False,
            },
        )

    reserve = read_json(Path(freeze_path).parent / "protected_reserve.json")
    qual_dir = output / "qualification"
    qual_dir.mkdir(exist_ok=True)
    selected = {}
    for stratum in STRATA:
        entries = [row for row in reserve["cases"] if row["stratum"] == stratum]
        eligible = []
        for entry in entries:
            payload = case_payload("protected", stratum, entry["index"])
            if payload_sha(payload) != entry["payload_sha256"]:
                raise ValueError("Protected generator payload drift")
            receipt = qual_dir / f"{stratum}__{entry['index']:05d}.json"
            if receipt.exists():
                row = read_json(receipt)
            else:
                row = qualification_receipt(payload)
                write_json(receipt, row)
            if row["qualification"]["eligible"]:
                eligible.append(entry["index"])
            if len(eligible) == freeze["design"]["target_eligible_per_stratum"]:
                break
        if len(eligible) != freeze["design"]["target_eligible_per_stratum"]:
            raise RuntimeError("Protected reserve exhausted before fixed eligible target")
        selected[stratum] = eligible

    selection_path = output / "selection.json"
    selection = {
        "schema": "sal-protected-selection/1",
        "evaluation_id": evaluation_id,
        "selection_rule": "first eligible cases in frozen reserve order; candidate not called during selection",
        "selected": selected,
    }
    if selection_path.exists():
        if read_json(selection_path) != selection:
            raise ValueError("Protected selection changed")
    else:
        write_json(selection_path, selection)

    cases_dir = output / "cases"
    starts_dir = output / "started"
    cases_dir.mkdir(exist_ok=True)
    starts_dir.mkdir(exist_ok=True)
    payloads = [
        case_payload("protected", stratum, index)
        for stratum in STRATA
        for index in selected[stratum]
    ]
    pending = []
    for payload in payloads:
        stem = f"{payload['stratum']}__{payload['index']:05d}"
        result_path = cases_dir / (stem + ".json")
        marker = starts_dir / (stem + ".json")
        if result_path.exists():
            continue
        if marker.exists():
            write_json(
                result_path,
                _missing_episode(
                    payload, "previous process ended after start marker and before atomic receipt"
                ),
            )
            continue
        write_json(
            marker,
            {
                "case_id": payload_sha(payload),
                "evaluation_id": evaluation_id,
                "started_marker_only": True,
            },
        )
        pending.append(payload)

    def save_result(payload, result):
        stem = f"{payload['stratum']}__{payload['index']:05d}"
        write_json(cases_dir / (stem + ".json"), result)

    if workers == 1:
        for payload in pending:
            save_result(payload, run_case(payload, include_native_baselines=True))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(run_case, payload, include_native_baselines=True): payload
                for payload in pending
            }
            for future in as_completed(futures):
                payload = futures[future]
                try:
                    save_result(payload, future.result())
                except Exception as exc:
                    save_result(
                        payload,
                        _missing_episode(payload, "worker_exception:" + type(exc).__name__),
                    )

    analysis = analyze_directory(output, output / "analysis.json", protected=True)
    write_json(
        output / "completion.json",
        {
            "evaluation_id": evaluation_id,
            "selected_total": sum(map(len, selected.values())),
            "analysis_sha256": sha(output / "analysis.json"),
            "invalid_definite_certificates": analysis["invalid_definite_certificates"],
            "campaign_complete": True,
        },
    )
    return analysis


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

    args = parser.parse_args()
    if args.mode in {"pilot", "calibration"}:
        namespace = "development" if args.mode == "pilot" else "calibration"
        if args.count_per_stratum < 1 or args.workers not in range(1, 9):
            raise SystemExit("Invalid bounded run size or workers")
        result = run_fixed_namespace(
            namespace,
            args.count_per_stratum,
            args.output,
            workers=args.workers,
            include_native=not args.no_native_baselines,
        )
    else:
        if args.workers not in range(1, 9):
            raise SystemExit("Workers must be between 1 and 8")
        result = run_protected(
            args.freeze,
            args.evaluation_id,
            args.output,
            args.workers,
        )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
