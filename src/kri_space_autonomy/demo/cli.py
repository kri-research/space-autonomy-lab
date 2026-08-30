from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from collections.abc import Sequence
from pathlib import Path

from kri_space_autonomy.assurance_report import AssuranceReportError
from kri_space_autonomy.controller_adapter import ControllerAdapterError
from kri_space_autonomy.fault_suite import FaultSuiteError

from .bundle import (
    DEFAULT_CONTROLLER,
    DEFAULT_ESTIMATED_FAULT_PLAN,
    DEFAULT_ESTIMATED_OUTPUT,
    DEFAULT_ESTIMATED_POLICY,
    DEFAULT_ESTIMATED_SUITE,
    DEFAULT_OUTPUT,
    DEFAULT_POLICY,
    DEFAULT_SUITE,
    DemoBuildError,
    build_demo_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kri_space_autonomy.demo",
        description=(
            "Build the deterministic public RPO controller demo from the existing adapter, "
            "fault-suite, report, and frozen aggregate-evidence APIs."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build stable JSON, Markdown, and standalone HTML")
    build.add_argument(
        "--controller",
        default=DEFAULT_CONTROLLER,
        help="Controller import spec in module.path:attribute form",
    )
    build.add_argument(
        "--output",
        type=Path,
        help=(
            f"Bundle directory (defaults: {DEFAULT_OUTPUT.as_posix()} for direct; "
            f"{DEFAULT_ESTIMATED_OUTPUT.as_posix()} for estimated)"
        ),
    )
    build.add_argument(
        "--navigation-profile",
        choices=("direct", "estimated"),
        default="direct",
        help="Controller navigation source (default: direct)",
    )
    build.add_argument(
        "--open",
        action="store_true",
        help="Open the generated standalone HTML page in the default browser",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        estimated = args.navigation_profile == "estimated"
        output = args.output or (
            DEFAULT_ESTIMATED_OUTPUT if estimated else DEFAULT_OUTPUT
        )
        manifest = build_demo_bundle(
            output,
            controller_spec=args.controller,
            suite_path=DEFAULT_ESTIMATED_SUITE if estimated else DEFAULT_SUITE,
            policy_path=DEFAULT_ESTIMATED_POLICY if estimated else DEFAULT_POLICY,
            navigation_profile=args.navigation_profile,
            navigation_fault_plan=(DEFAULT_ESTIMATED_FAULT_PLAN if estimated else None),
        )
        if args.open:
            webbrowser.open((output / "index.html").resolve().as_uri())
        print(
            json.dumps(
                {
                    "status": "built",
                    "output": output.as_posix(),
                    "demo_fingerprint_sha256": manifest["demo_fingerprint_sha256"],
                    "input_fingerprint_sha256": manifest["input_fingerprint_sha256"],
                    "files": [item["path"] for item in manifest["files"]],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (
        AssuranceReportError,
        ControllerAdapterError,
        DemoBuildError,
        FaultSuiteError,
        OSError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
