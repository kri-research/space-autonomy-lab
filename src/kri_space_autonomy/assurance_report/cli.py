from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from kri_space_autonomy.controller_adapter import ControllerAdapterError
from kri_space_autonomy.fault_suite import (
    FaultApplicationError,
    FaultSpecError,
    FaultSuiteLoadError,
)
from kri_space_autonomy.navigation_profiles import (
    NavigationFaultPlanError,
    NavigationProfileError,
)

from .errors import (
    AssessmentCompatibilityError,
    AssessmentPolicyLoadError,
    AssessmentPolicySpecError,
    AssessmentResultLoadError,
    AssessmentResultSpecError,
    AssuranceReportError,
)
from .policy import validate_assessment_policy
from .report import (
    ERROR_SCHEMA_VERSION,
    AssuranceReport,
    assess_controller,
    assess_fault_suite_result,
    render_report_json,
    render_report_markdown,
    write_assurance_report,
)


class _CliUsageError(ValueError):
    pass


class _MachineReadableArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _CliUsageError(message)


def _output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json-output", type=Path, help="Write stable JSON to this path")
    parser.add_argument(
        "--markdown-output", type=Path, help="Write concise Markdown to this path"
    )
    parser.add_argument(
        "--stdout",
        choices=("json", "markdown", "none"),
        default="json",
        help="Select stdout format (default: json)",
    )


def _parser() -> argparse.ArgumentParser:
    parser = _MachineReadableArgumentParser(
        prog="python -m kri_space_autonomy.assurance_report",
        description=(
            "Run or assess deterministic external-controller fault-suite evidence from the "
            "simplified RPO test harness."
        ),
    )
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        parser_class=_MachineReadableArgumentParser,
    )

    validate = commands.add_parser(
        "validate-policy", help="Validate a versioned assessment-policy JSON file"
    )
    validate.add_argument("policy", type=Path)

    assess = commands.add_parser(
        "assess",
        help="Replay a controller on a suite and produce JSON/Markdown assessment evidence",
    )
    assess.add_argument("controller", help="Import spec in module.path:attribute form")
    assess.add_argument("suite", type=Path)
    assess.add_argument("policy", type=Path)
    assess.add_argument(
        "--navigation-profile",
        choices=("direct", "estimated"),
        default="direct",
        help="Controller navigation source (default: direct)",
    )
    assess.add_argument(
        "--navigation-fault-plan",
        type=Path,
        help="Optional estimated-profile stale/covariance packet-fault plan",
    )
    _output_arguments(assess)

    report = commands.add_parser(
        "report",
        help="Assess an existing fault-suite result without rerunning the controller",
    )
    report.add_argument("result", type=Path)
    report.add_argument("suite", type=Path)
    report.add_argument("policy", type=Path)
    _output_arguments(report)
    return parser


def _error_type(exc: Exception) -> str:
    if isinstance(exc, _CliUsageError):
        return "invalid_cli_arguments"
    if isinstance(exc, ControllerAdapterError):
        return "invalid_controller"
    if isinstance(exc, (FaultSuiteLoadError, FaultSpecError)):
        return "invalid_fault_suite"
    if isinstance(exc, FaultApplicationError):
        return "execution"
    if isinstance(exc, (NavigationFaultPlanError, NavigationProfileError)):
        return "invalid_navigation_profile"
    if isinstance(exc, (AssessmentPolicyLoadError, AssessmentPolicySpecError)):
        return "invalid_assessment_policy"
    if isinstance(exc, (AssessmentResultLoadError, AssessmentResultSpecError)):
        return "invalid_fault_suite_result"
    if isinstance(exc, AssessmentCompatibilityError):
        return "incompatible_inputs"
    if isinstance(exc, OSError):
        return "infrastructure"
    if isinstance(exc, AssuranceReportError):
        return "invalid_assessment"
    return "infrastructure"


def _error_payload(exc: Exception) -> dict[str, object]:
    return {
        "schema_version": ERROR_SCHEMA_VERSION,
        "assessment_status": "INVALID",
        "error_type": _error_type(exc),
        "message": str(exc),
    }


def _emit_report(args: argparse.Namespace, report: object) -> int:
    if type(report) is not AssuranceReport:
        raise AssessmentResultSpecError("generated report has an invalid type")
    if args.json_output is not None or args.markdown_output is not None:
        write_assurance_report(
            report,
            json_path=args.json_output,
            markdown_path=args.markdown_output,
        )
    if args.stdout == "json":
        print(render_report_json(report), end="")
    elif args.stdout == "markdown":
        print(render_report_markdown(report), end="")
    return 0 if report.decision == "PASS" else 1


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "validate-policy":
            print(
                json.dumps(
                    validate_assessment_policy(args.policy),
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
            return 0
        if args.command == "assess":
            report = assess_controller(
                args.controller,
                args.suite,
                args.policy,
                navigation_profile=args.navigation_profile,
                navigation_fault_plan=args.navigation_fault_plan,
            )
        else:
            report = assess_fault_suite_result(args.result, args.suite, args.policy)
        return _emit_report(args, report)
    except Exception as exc:
        print(
            json.dumps(
                _error_payload(exc),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ),
            file=sys.stderr,
        )
        return 2
