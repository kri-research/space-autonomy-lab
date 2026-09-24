"""Readable host evidence archive and fixed-output checks without hidden reruns."""

from pathlib import Path
import argparse
import hashlib
import json
import tempfile
from .harness import ROOT, write_new, verify_freeze
from .analysis import summarize_directory
from .adapters import verify_fixed


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(run, output):
    run, output = Path(run), Path(output)
    if output.exists():
        raise ValueError("Artifact output already exists")
    frozen = verify_freeze(ROOT / "host_freeze.json")
    done = json.loads((run / "completion.json").read_text())
    for name, h in done["files"].items():
        if sha(run / name) != h:
            raise ValueError("Raw measurement changed")
    summary = summarize_directory(run, frozen)
    if summary != json.loads((run / "summary.json").read_text()):
        raise ValueError("Saved analysis differs")
    checks = []
    for file in sorted(run.glob("session*/samples/*.json")):
        row = json.loads(file.read_text())
        good = verify_fixed(row["request"], row["response"]["result"]["prediction"])
        checks.append(
            {
                "id": row["request"]["id"],
                "phase": row["phase"],
                "domain": row["request"]["domain"],
                "method": row["request"]["method"],
                "checked": good is not None,
                "passed": good,
            }
        )
    output.mkdir()
    with (output / "raw_records.jsonl").open("x") as stream:
        for file in sorted(run.rglob("*.json")):
            raw = file.read_text()
            if any(
                x in raw for x in ("/" + "Users/", "/" + "home/", "access_token", "PRIVATE KEY")
            ):
                raise ValueError("Private host data in public record")
            stream.write(
                json.dumps(
                    {"path": file.relative_to(run).as_posix(), "raw_utf8": raw},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    write_new(output / "summary.json", summary)
    write_new(
        output / "fixed_output_checks.json",
        {
            "checks": checks,
            "definite_checks": sum(x["checked"] for x in checks),
            "failed_checks": sum(x["passed"] is False for x in checks),
            "scope": "After-timing calibration fixed-output rechecks; no protected re-evaluation or independent human validation",
        },
    )
    evidence = [
        {
            "level": "host_computer_timing",
            "status": "measured",
            "quantity": summary["measured_samples"],
            "limitation": "one host, three process sessions, correlated samples",
        },
        {
            "level": "simulated_interface",
            "status": "tested",
            "limitation": "virtual command scheduling and uncertainty checks; no equipment interfaces",
        },
        {
            "level": "processor_in_the_loop",
            "status": "not_performed",
            "missing": "identified target processor and independently driven simulated-plant interface",
        },
        {
            "level": "hardware_in_the_loop",
            "status": "not_performed",
            "missing": "real sensor/actuator interfaces and timestamp metrology",
        },
        {
            "level": "physical_system_trials",
            "status": "not_performed",
            "missing": "rig, independent metrology, operator, safety supervisor and trial-specific approval",
        },
        {
            "level": "independent_external_replication",
            "status": "not_performed",
            "missing": "actual independent reviewer or laboratory reports",
        },
    ]
    write_new(output / "evidence_levels.json", evidence)
    write_new(
        output / "manifest.json",
        {
            "files": {f.name: sha(f) for f in output.iterdir() if f.is_file()},
            "host_freeze_sha256": sha(ROOT / "host_freeze.json"),
            "raw_measurement_files": len(list(run.rglob("*.json"))),
            "original_measurements_unchanged": True,
            "private_worker_stderr_not_published": True,
        },
    )
    return verify(output)


def verify(output):
    output = Path(output)
    m = json.loads((output / "manifest.json").read_text())
    actual = {f.name: sha(f) for f in output.iterdir() if f.is_file() and f.name != "manifest.json"}
    if actual != m["files"] or sha(ROOT / "host_freeze.json") != m["host_freeze_sha256"]:
        raise ValueError("Host artifact differs")
    frozen = verify_freeze(ROOT / "host_freeze.json")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        seen = set()
        for line in (output / "raw_records.jsonl").read_text().splitlines():
            entry = json.loads(line)
            rel = Path(entry["path"])
            if rel.is_absolute() or ".." in rel.parts or str(rel) in seen:
                raise ValueError("Unsafe/duplicate archive name")
            seen.add(str(rel))
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(entry["raw_utf8"])
        summary = summarize_directory(root, frozen)
    if summary != json.loads((output / "summary.json").read_text()):
        raise ValueError("Host summary mismatch")
    checks = json.loads((output / "fixed_output_checks.json").read_text())
    if len(checks["checks"]) != summary["measured_samples"] + summary["warmup_samples"] or len(
        {x["id"] for x in checks["checks"]}
    ) != len(checks["checks"]):
        raise ValueError("Missing fixed-output check")
    return {
        "passed": True,
        "samples": summary["measured_samples"],
        "warmup": summary["warmup_samples"],
        "fixed_output_checks": checks["definite_checks"],
        "failed_fixed_output_checks": checks["failed_checks"],
        "physical_trials": 0,
        "independent_reviews": 0,
        "status": "ready_for_external_execution",
        "measurement_rerun": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = verify(args.output) if args.verify else build(args.run, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
