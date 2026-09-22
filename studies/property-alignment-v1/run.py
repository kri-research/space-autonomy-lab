"""Run only the supplied baseline or check/export its outputs; no new campaign."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from bundle import BASE, ROOT, GROUPS, digest, source_inventory, verified_group, export_group


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["audit", "diagnostics", "test", "verify", "export"])
    parser.add_argument("--group", choices=list(GROUPS))
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--junitxml", type=Path)
    args = parser.parse_args()
    if args.action in ["verify", "export"]:
        if args.group is None:
            parser.error("--group is required")
        if args.action == "export" and args.destination is None:
            parser.error("--destination is required")
        result = (
            export_group(args.group, args.destination)
            if args.action == "export"
            else verified_group(args.group)[0]
        )
        print(
            json.dumps(
                {"status": "verified", "group": args.group, "files": len(result["output_sha256"])}
            )
        )
        return 0
    logs = BASE / "logs"
    logs.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run = logs / "runs" / stamp
    run.mkdir(parents=True, exist_ok=False)
    before = source_inventory()
    shutil.copytree(BASE / "data", run / "prior_data")
    receipts = list(logs.glob("*-receipt.json"))
    for path in receipts:
        shutil.copy2(path, run / path.name)
    python = sys.executable
    xml = args.junitxml or logs / "tests.xml"
    xml = xml.resolve()
    xml.parent.mkdir(parents=True, exist_ok=True)
    commands = {
        "audit": [[python, str(BASE / "scripts/verify_historical.py")]],
        "diagnostics": [
            [python, str(BASE / "scripts/record_extrema_fixtures.py")],
            [
                python,
                str(BASE / "scripts/check_statistics.py"),
                "--output",
                str(BASE / "data/statistical_design_check.json"),
            ],
            [python, str(BASE / "scripts/run_diagnostics.py")],
        ],
        "test": [
            [
                python,
                "-m",
                "pytest",
                "-c",
                str(ROOT / "pyproject.toml"),
                "--confcutdir=" + str(ROOT),
                str(BASE / "tests"),
                "--junitxml=" + str(xml),
            ]
        ],
    }
    env = dict(
        os.environ,
        OPENBLAS_NUM_THREADS="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTEST_ADDOPTS="-p no:cacheprovider",
    )
    record = dict(
        status="running",
        action=args.action,
        source_sha256=before,
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        commands=[],
    )
    receipt_path = logs / (args.action + "-receipt.json")
    receipt_path.write_text(json.dumps(record, indent=2) + "\n")
    for index, argv in enumerate(commands[args.action]):
        with (run / f"{index}.log").open("w") as output:
            completed = subprocess.run(
                argv, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=600
            )
        record["commands"].append(dict(argv=argv, exit_code=completed.returncode))
        if completed.returncode:
            record["status"] = "failed"
            receipt_path.write_text(json.dumps(record, indent=2) + "\n")
            print("Baseline action failed; its log and prior outputs are retained.")
            return completed.returncode
    if source_inventory() != before:
        raise RuntimeError("Source changed during execution")
    if args.action in GROUPS:
        record["output_sha256"] = {
            n: digest((BASE / "data" / n).read_bytes()) for n in GROUPS[args.action]
        }
    else:
        suites = list(ET.parse(xml).iter("testsuite"))
        if any(
            int(s.get("errors", 0)) + int(s.get("failures", 0)) + int(s.get("skipped", 0))
            for s in suites
        ):
            raise RuntimeError("Baseline tests did not all execute successfully")
        record["tests"] = sum(int(s.get("tests", 0)) for s in suites)
        record["junitxml_sha256"] = digest(xml.read_bytes())
    record["status"] = "passed"
    receipt_path.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"action": args.action, "status": "passed", "tests": record.get("tests")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
