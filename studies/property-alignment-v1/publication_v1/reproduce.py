"""Bounded public reproduction entry point. Never starts a frozen campaign."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import subprocess
import sys
import time
from .audit import STUDY, REPO, verify_manifest, outcomes, digest


def run(output, replay=False):
    output = Path(output).expanduser().absolute()
    if (
        output.exists()
        or output.is_relative_to(REPO)
        or any(p.is_symlink() for p in (output, *output.parents))
    ):
        raise ValueError("Use a new output directory outside the source repository")
    evidence = Path(os.environ["SAL_EVIDENCE_ROOT"]).resolve()
    if output.is_relative_to(evidence):
        raise ValueError("Output overlaps historical evidence")
    verify_manifest()
    output.mkdir(parents=True)
    env = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "MPLCONFIGDIR": str(output / "matplotlib"),
    }
    record = {
        "scientific_source_commit": "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "commands": [],
        "replay": replay,
        "new_protected_or_historical_campaign": False,
        "physical_validation": False,
    }
    python = sys.executable
    commands = [
        ("causal-inputs", [python, "-m", "causal.execute", "verify"]),
        (
            "causal-records",
            [python, "-m", "causal.verify_records", "--execution", "causal/recorded_execution"],
        ),
        (
            "candidate-records",
            [python, "-m", "candidate.artifact", "candidate/recorded_development"],
        ),
        (
            "replacement-freeze",
            [python, "-m", "evaluation_v2.verify", "--freeze", "evaluation_v2/frozen/freeze.json"],
        ),
        (
            "frozen-raw-analysis",
            [python, "-m", "campaign_v2.artifact", "--verify", "--output", "campaign_v2/recorded"],
        ),
        (
            "cart-records",
            [
                python,
                "-m",
                "transfer_cart_v1.audit",
                "--verify",
                "--output",
                "transfer_cart_v1/recorded",
            ],
        ),
        (
            "host-records",
            [
                python,
                "-m",
                "execution_validation_v1.artifact",
                "--verify",
                "--output",
                "execution_validation_v1/recorded",
            ],
        ),
        (
            "audit-fixtures",
            [
                python,
                "-m",
                "pytest",
                "publication_v1/tests",
                "--junitxml=" + str(output / "tests.xml"),
            ],
        ),
        (
            "spacecraft-figures",
            [
                python,
                "campaign_v2/plot.py",
                "--data",
                "campaign_v2/recorded",
                "--output",
                str(output / "spacecraft-figures"),
                "--pdf",
            ],
        ),
        (
            "cart-figures",
            [
                python,
                "transfer_cart_v1/plot.py",
                "--data",
                "transfer_cart_v1/recorded",
                "--output",
                str(output / "cart-figures"),
                "--local-pdf",
            ],
        ),
    ]
    if replay:
        commands += [
            (
                "saved-prefixes-and-recoveries",
                [
                    python,
                    "-m",
                    "candidate.verification.replay",
                    "candidate/recorded_development",
                    "--output",
                    str(output / "fixed-replay"),
                ],
            ),
            (
                "cart-separate-referee",
                [
                    python,
                    "-m",
                    "transfer_cart_v1.cleanroom",
                    "--data",
                    "transfer_cart_v1/recorded",
                    "--output",
                    str(output / "referee.json"),
                ],
            ),
            (
                "fixed-event-validation",
                [
                    python,
                    "-m",
                    "adjudication.validate",
                    "--output",
                    str(output / "event-validation"),
                ],
            ),
        ]
    for name, argv in commands:
        started = time.monotonic()
        with (output / (name + ".log")).open("x") as stream:
            try:
                code = subprocess.run(
                    argv, cwd=STUDY, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=600
                ).returncode
            except subprocess.TimeoutExpired:
                code = -9
        record["commands"].append(
            {"name": name, "argv": argv, "exit_code": code, "elapsed_s": time.monotonic() - started}
        )
        (output / "execution.json").write_text(json.dumps(record, indent=2) + "\n")
        if code:
            raise RuntimeError("Reproduction failed; complete attempt retained: " + name)
    verify_manifest()
    record["passed"] = True
    record["outcomes"] = outcomes()
    record["files"] = {
        str(p.relative_to(output)): digest(p)
        for p in output.rglob("*")
        if p.is_file() and p.name != "execution.json"
    }
    (output / "execution.json").write_text(json.dumps(record, indent=2) + "\n")
    print(
        json.dumps(
            {"passed": True, "commands": len(commands), "new_campaigns": 0, "replay": replay},
            indent=2,
        )
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--replay", action="store_true")
    args = p.parse_args()
    run(args.output, args.replay)


if __name__ == "__main__":
    main()
