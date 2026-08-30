from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .adapter import validate_controller
from .benchmark import replay_external_controller, run_external_controller
from .errors import ControllerAdapterError

_NAVIGATION_PROFILES = ("direct", "estimated")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m kri_space_autonomy.controller_adapter",
        description="Load and exercise an external controller on the simplified RPO testbed.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser(
        "validate", help="Check import, contract, degraded inputs, bounds, and reset replay"
    )
    validate.add_argument("controller", help="Import spec in module.path:attribute form")

    run = commands.add_parser("run", help="Run one scenario")
    run.add_argument("controller", help="Import spec in module.path:attribute form")
    run.add_argument("scenario", type=Path)
    run.add_argument(
        "--navigation-profile",
        choices=_NAVIGATION_PROFILES,
        default="direct",
        help="Controller navigation source (default: direct)",
    )

    replay = commands.add_parser("replay", help="Run a scenario twice and compare exact results")
    replay.add_argument("controller", help="Import spec in module.path:attribute form")
    replay.add_argument("scenario", type=Path)
    replay.add_argument(
        "--navigation-profile",
        choices=_NAVIGATION_PROFILES,
        default="direct",
        help="Controller navigation source (default: direct)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_controller(args.controller)
        elif args.command == "run":
            result = run_external_controller(
                args.controller,
                args.scenario,
                navigation_profile=args.navigation_profile,
            ).to_dict()
        else:
            result = replay_external_controller(
                args.controller,
                args.scenario,
                navigation_profile=args.navigation_profile,
            )
    except (ControllerAdapterError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0
