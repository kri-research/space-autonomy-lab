"""Prewritten analysis for pilot and protected evaluation receipts."""

from collections import Counter
from pathlib import Path
import json

from .generator import STRATA
from .statistics import hoeffding_interval


def load_cases(directory):
    paths = sorted((Path(directory) / "cases").glob("*.json"))
    return [json.loads(path.read_text()) for path in paths]


def analyze_rows(rows, *, protected=False):
    eligible = [row for row in rows if row["primary"]["eligible"]]
    decisive = [row for row in eligible if row["primary"]["on_time_decisive_valid"]]
    invalid = [
        row
        for row in eligible
        if row["primary"]["decisive"] and not row["primary"]["valid_certificate"]
    ]
    statuses = Counter(row["candidate"]["status"] for row in eligible)
    pairwise_applicable = [row for row in eligible if row["pairwise_shortcut"]["applicable"]]
    pairwise_false_safe = [
        row
        for row in pairwise_applicable
        if row["pairwise_shortcut"]["declares_compatible"]
        and row["candidate"]["status"] == "proved_no_common_held_command"
    ]
    mean_declares = [row for row in eligible if row["mean_shortcut"]["declares_safe"]]
    mean_false = [row for row in mean_declares if row["mean_shortcut"]["false_safe_for_full_set"]]
    result = {
        "schema": "sal-evaluation-analysis/1",
        "protected": protected,
        "cases_loaded": len(rows),
        "eligible": len(eligible),
        "on_time_decisive_valid": len(decisive),
        "candidate_statuses": dict(statuses),
        "invalid_definite_certificates": len(invalid),
        "pairwise_applicable": len(pairwise_applicable),
        "pairwise_false_safe": len(pairwise_false_safe),
        "mean_shortcut_safe": len(mean_declares),
        "mean_shortcut_false_safe": len(mean_false),
        "per_stratum": {},
        "physical_validation": False,
    }
    if eligible:
        result["balanced_coverage"] = hoeffding_interval(len(decisive), len(eligible))
    for stratum in STRATA:
        group = [row for row in eligible if row["stratum"] == stratum]
        successes = sum(row["primary"]["on_time_decisive_valid"] for row in group)
        result["per_stratum"][stratum] = {
            "eligible": len(group),
            "on_time_decisive_valid": successes,
            "statuses": dict(Counter(row["candidate"]["status"] for row in group)),
            "max_candidate_wall_s": max(
                (row["candidate"].get("wall_s", 0.0) for row in group), default=0.0
            ),
        }
    native = {}
    for method in ("predictive", "barrier"):
        values = []
        for row in eligible:
            detail = row["native_baselines"].get("methods", {}).get(method)
            if detail is not None:
                values.append(bool(detail.get("protected")))
        native[method] = {
            "evaluated": len(values),
            "protected": sum(values),
            "interpretation": "secondary native-design comparator; stronger continuation obligations",
        }
    result["native_baselines"] = native
    return result


def analyze_directory(directory, output=None, protected=False):
    result = analyze_rows(load_cases(directory), protected=protected)
    if output is not None:
        Path(output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result
