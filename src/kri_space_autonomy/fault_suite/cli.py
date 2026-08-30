from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from kri_space_autonomy.controller_adapter import ControllerAdapterError

from .errors import FaultSuiteError
from .manifest import validate_fault_suite
from .runner import replay_fault_suite, run_fault_suite


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kri_space_autonomy.fault_suite",
        description="Validate and run deterministic fault suites on the simplified RPO harness.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="Validate a versioned fault-suite JSON file")
    validate.add_argument("suite", type=Path)

    run = commands.add_parser("run-suite", help="Run every suite case with one controller")
    run.add_argument("controller", help="Import spec in module.path:attribute form")
    run.add_argument("suite", type=Path)
    run.add_argument("--output", type=Path, help="Also write the JSON result document")

    replay = commands.add_parser(
        "replay-suite", help="Run the complete suite twice and compare exact results"
    )
    replay.add_argument("controller", help="Import spec in module.path:attribute form")
    replay.add_argument("suite", type=Path)
    replay.add_argument("--output", type=Path, help="Also write the JSON replay document")
    return parser


def _render(result: dict[str, object]) -> str:
    return json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_fault_suite(args.suite)
        elif args.command == "run-suite":
            result = run_fault_suite(args.controller, args.suite).to_dict()
        else:
            result = replay_fault_suite(args.controller, args.suite)
        rendered = _render(result)
        output = getattr(args, "output", None)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered, encoding="utf-8")
    except (FaultSuiteError, ControllerAdapterError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(rendered, end="")
    return 0
