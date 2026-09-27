"""File/stdout interface only. No network, serial port or actuator command."""

import argparse
import json
import sys
from pathlib import Path

from .api import assess, contract, record, replay
from .examples import examples
from .integrity import verify_installation


def read(path):
    from ._vendor.sa04.wire import MAX_BYTES, loads

    with Path(path).open("rb") as f:
        return loads(f.read(MAX_BYTES + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("contract")
    sub.add_parser("example")
    for name in ("assess", "replay"):
        sub.add_parser(name).add_argument("--input", type=Path, required=True)
    sub.add_parser("benchmark").add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "contract":
            verify_installation()
            result, code = contract(), 0
        elif args.command == "example":
            result = [
                dict(name=x["name"], expected=x["expected_status"], receipt=record(x["request"]))
                for x in examples()
            ]
            code = (
                0 if all(x["receipt"]["result"]["status"] == x["expected"] for x in result) else 1
            )
        elif args.command == "assess":
            result = assess(read(args.input))
            code = (
                0
                if result["status"] == "supported_prefix"
                else 2
                if result["status"] == "unsupported_input"
                else 3
            )
        elif args.command == "replay":
            good = replay(read(args.input))
            result, code = dict(reproduces=good, external_replication=False), 0 if good else 2
        else:
            from .benchmark import run

            result = run(args.output)
            code = 0 if result["complete"] else 1
            result = dict(
                complete=result["complete"],
                samples=len(result["samples"]),
                target_validation=False,
                physical_validation=False,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return code
    except (ValueError, TypeError, KeyError, ArithmeticError, OSError, RecursionError) as exc:
        print(json.dumps(dict(error=type(exc).__name__, physical_actuation=False)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
