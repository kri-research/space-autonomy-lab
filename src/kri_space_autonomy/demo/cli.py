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

from .bundle import DEFAULT_CONTROLLER, DEFAULT_OUTPUT, DemoBuildError, build_demo_bundle


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
        default=DEFAULT_OUTPUT,
        help=f"Bundle directory (default: {DEFAULT_OUTPUT.as_posix()})",
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
        manifest = build_demo_bundle(args.output, controller_spec=args.controller)
        if args.open:
            webbrowser.open((args.output / "index.html").resolve().as_uri())
        print(
            json.dumps(
                {
                    "status": "built",
                    "output": args.output.as_posix(),
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
