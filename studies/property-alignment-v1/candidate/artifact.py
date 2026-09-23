"""Read-only scientific record and dual-certificate verification."""

from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
from collections import Counter
from .information import Hypothesis, InformationSet
from .affine import recheck_certificate
from .scalar import ScalarBox, action_is_safe, common_inputs
from .develop import inventory


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict(path):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("Nonfinite JSON number: " + value)

    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def load_information(payload):
    if payload["schema"] != "sal-common-information/1" or payload["command_period_s"] != 1:
        raise ValueError("Unexpected information schema")
    return InformationSet(
        tuple(Hypothesis(tuple(h["lower"]), tuple(h["upper"])) for h in payload["hypotheses"]),
        age=payload["age"],
        delay=payload["delay"],
        queue=tuple(tuple(u) for u in payload["queue"]),
        authority=payload["authority"],
        effectiveness=tuple(payload["effectiveness"]),
        disturbance=payload["disturbance"],
        kind=payload["kind"],
        units=tuple(payload["units"]),
    )


def verify(directory):
    directory = Path(directory)
    manifest = strict(directory / "manifest.json")
    names = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() and p != directory / "manifest.json"
    }
    if names != set(manifest):
        raise ValueError("Unexpected artifact membership")
    for name, expected in manifest.items():
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or p.as_posix() != name:
            raise ValueError("Unsafe artifact path")
        path = directory / name
        if any(q.is_symlink() for q in (path, *path.parents)) or sha(path) != expected:
            raise ValueError("Artifact hash or symlink mismatch")
    inputs = strict(directory / "inputs.json")
    summary = strict(directory / "summary.json")
    if inputs["seal"]["source_sha256"] != inventory() or summary["source_sha256"] != inventory():
        raise ValueError("Recorded scientific source differs")
    fixtures = {
        k: load_information(v) for k, v in strict(directory / "fixture_inputs.json").items()
    }
    rows = strict(directory / "fixtures.json")
    grid = strict(directory / "grid.json")
    if len(rows) != len(fixtures) or len(grid) != 48 or {r["case"] for r in rows} != set(fixtures):
        raise ValueError("Incomplete selected cases")
    negatives = 0
    for row in [*rows, *grid]:
        info = load_information(row["input"]) if "input" in row else fixtures[row["case"]]
        result = row["candidate"]
        negative = result.get("negative", {})
        if negative.get("status") == "proved_no_common_held_command":
            if not recheck_certificate(info, negative)["proved"]:
                raise ValueError("Invalid dual certificate")
            negatives += 1
        if result["status"] == "certified_common_prefix":
            positive = result["positive"]
            if (
                positive["information_sha256"] != info.identity()
                or positive["action"] != result["action"]
            ):
                raise ValueError("Positive input binding changed")
            if len(positive["hypotheses"]) != len(info.hypotheses) or any(
                h["status"] != "validated_containment" for h in positive["hypotheses"]
            ):
                raise ValueError("Missing positive enclosure evidence")
        if result.get("deadline_exceeded") and result.get("action") is not None:
            raise ValueError("Late answer treated as applied")
    scalar = strict(directory / "scalar.json")
    checks = 0
    if len(scalar["cases"]) != 512:
        raise ValueError("Scalar coverage differs")
    for row in scalar["cases"]:
        box = ScalarBox(*row["box"])
        args = dict(
            authority=row["authority"],
            effectiveness=tuple(row["effectiveness"]),
            disturbance=row["disturbance"],
        )
        if common_inputs([box], row["duration_s"], **args) != row["result"]:
            raise ValueError("Scalar formula drift")
        for c in row["checks"]:
            actual = action_is_safe([box], c["u"], row["duration_s"], **args)
            if actual != c["exact_extrema_safe"] or actual != c["interval_predicts_safe"]:
                raise ValueError("False scalar classification")
            checks += 1
    if checks != 8704 or checks != summary["scalar_checks"]:
        raise ValueError("Scalar check count")
    recovery = strict(directory / "recoveries.json")
    if len(recovery) != 10:
        raise ValueError("Missing individual recovery attempts")
    counts = Counter(r["candidate"]["status"] for r in rows)
    if (
        summary["named_positive"] != counts["certified_common_prefix"]
        or summary["named_negative"] != counts["proved_no_common_held_command"]
    ):
        raise ValueError("Named counts disagree")
    if summary["grid_statuses"] != dict(Counter(r["candidate"]["status"] for r in grid)):
        raise ValueError("Grid counts disagree")
    return {
        "passed": True,
        "files": len(manifest),
        "named_cases": len(rows),
        "grid_cases": len(grid),
        "scalar_exact_checks": checks,
        "rechecked_negative_certificates": negatives,
        "individual_recovery_attempts": len(recovery),
        "scope": "hashes, input binding and rational proof checks; positive records require original interval implementation assumptions",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), indent=2))
