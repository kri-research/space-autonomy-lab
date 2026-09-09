"""Run the maintained public checks without invoking historical campaign entry points."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TEST_FILES = (
    "tests/test_environment.py",
    "tests/test_evidence.py",
    "tests/test_controller_adapter.py",
    "tests/test_demo.py",
    "tests/test_assurance_report.py",
    "tests/test_benchmark_documentation.py",
    "tests/test_release_metadata.py",
    "tests/test_experiment_005_confirmatory_analysis.py",
    "tests/test_experiment_005_confirmatory_closeout.py",
    "tests/test_fault_suite.py",
    "tests/test_navigation_profiles.py",
    "tests/test_faults.py",
    "tests/test_safety.py",
    "tests/test_simulation.py",
    "tests/test_verification.py",
    "tests/test_post_release_hardening.py",
    "tests/test_historical_snapshots.py",
    "tests/test_evidence_reconciliation.py",
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    commands = (
        (sys.executable, "tools/check_release_preservation.py"),
        (sys.executable, "-m", "ruff", "check", "."),
        (sys.executable, "-m", "pytest", *TEST_FILES),
        (sys.executable, "-m", "kri_space_autonomy.cli", "verify-gate"),
        (sys.executable, "-m", "kri_space_autonomy.experiment_004_closeout", "verify"),
        (sys.executable, "-B", "tools/verify_historical_snapshots.py"),
        (sys.executable, "-B", "tools/verify_evidence_supplement.py"),
        (sys.executable, "-B", "tools/reconcile_e005_records.py"),
        (sys.executable, "-B", "tools/check_reconciliation_publication.py"),
        ("git", "diff", "--check"),
        (sys.executable, "tools/check_release_preservation.py"),
    )
    for command in commands:
        print("Running " + " ".join(command[1:]), flush=True)
        try:
            completed = subprocess.run(command, cwd=root, check=False, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Check could not complete: {type(exc).__name__}", file=sys.stderr)
            return 1
        if completed.returncode:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
