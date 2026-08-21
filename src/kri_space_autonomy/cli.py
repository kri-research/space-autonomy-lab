from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import run_benchmark
from .evidence import EvidenceLogger
from .scenario import load_scenario
from .simulation import run_episode
from .verification import bounded_gate_check


def _json_print(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(prog="kri-space-lab")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run one scenario")
    run_parser.add_argument("scenario", type=Path)
    run_parser.add_argument(
        "--controller",
        choices=("deterministic", "learned", "protected"),
        default="protected",
    )
    run_parser.add_argument("--evidence", type=Path)

    bench_parser = sub.add_parser("benchmark", help="Run all supplied scenarios")
    bench_parser.add_argument("scenarios", nargs="+", type=Path)
    bench_parser.add_argument("--output", type=Path)

    sub.add_parser("verify-gate", help="Run bounded safety-envelope property check")

    evidence_parser = sub.add_parser("verify-evidence", help="Verify a hash-chained JSONL log")
    evidence_parser.add_argument("path", type=Path)

    args = parser.parse_args()

    if args.command == "run":
        scenario = load_scenario(args.scenario)
        result = run_episode(scenario, args.controller, args.evidence)
        _json_print(result.to_dict())
        return

    if args.command == "benchmark":
        result = run_benchmark(args.scenarios)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        _json_print(result["summary"])
        return

    if args.command == "verify-gate":
        _json_print(bounded_gate_check())
        return

    if args.command == "verify-evidence":
        _json_print({"valid": EvidenceLogger.verify_jsonl(args.path), "path": str(args.path)})
        return


if __name__ == "__main__":
    main()
