"""Prespecified counts with conservative uncertainty and fixed denominators."""

from collections import Counter
from pathlib import Path
import math
from .generator import STRATA
from .statistics import conditional_mean_interval, PER_STRATUM
from .safety import strict_json, atomic_json, mean_evidence


def load_cases(directory):
    return [strict_json(path) for path in sorted((Path(directory) / "cases").glob("*.json"))]


def analyze_rows(rows, *, protected=False, expected_keys=None):
    rows = list(rows)
    keys = [(row["stratum"], row["index"]) for row in rows]
    if len(set(keys)) != len(keys) or len({row["case_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate case receipt")
    if any(key[0] not in STRATA for key in keys):
        raise ValueError("Unknown stratum")
    for row in rows:
        p = row["primary"]
        if any(
            type(p.get(k)) is not bool
            for k in (
                "eligible",
                "decisive",
                "on_time",
                "valid_certificate",
                "on_time_decisive_valid",
            )
        ):
            raise ValueError("Non-Boolean primary field")
        if p["on_time_decisive_valid"] != all(
            p[k] for k in ("eligible", "decisive", "on_time", "valid_certificate")
        ):
            raise ValueError("Inconsistent primary success flag")
    if protected and expected_keys is None:
        raise ValueError("Protected analysis requires the frozen selection denominator")
    if expected_keys is not None:
        expected_keys = list(expected_keys)
        if len(set(expected_keys)) != len(expected_keys) or not set(keys) <= set(expected_keys):
            raise ValueError("Selection membership differs")
        if any(sum(k[0] == s for k in expected_keys) != PER_STRATUM for s in STRATA):
            raise ValueError("Fixed stratum denominator changed")
        if any(not r["primary"]["eligible"] for r in rows):
            raise ValueError("Selected case silently became ineligible")
    eligible = [r for r in rows if r["primary"]["eligible"]]
    success = sum(r["primary"]["on_time_decisive_valid"] for r in eligible)
    invalid = sum(
        r["primary"]["decisive"] and not r["primary"]["valid_certificate"] for r in eligible
    )
    missing = [] if expected_keys is None else sorted(set(expected_keys) - set(keys))
    denominator = len(eligible) if expected_keys is None else len(expected_keys)
    pairwise = [r for r in eligible if r["pairwise_shortcut"]["applicable"]]
    false_pairs = sum(
        r["pairwise_shortcut"]["declares_compatible"]
        and r["candidate"]["status"] == "proved_no_common_held_command"
        and r["primary"]["valid_certificate"]
        for r in pairwise
    )
    mean = Counter(mean_evidence(r) for r in eligible)
    result = {
        "schema": "sal-evaluation-analysis/2",
        "protected": protected,
        "cases_loaded": len(rows),
        "eligible": len(eligible),
        "planned_denominator": denominator,
        "missing_selected": missing,
        "campaign_complete": not missing,
        "on_time_decisive_valid": success,
        "candidate_statuses": dict(Counter(r["candidate"]["status"] for r in eligible)),
        "invalid_definite_certificates": invalid,
        "validity_claim_gate_passed": invalid == 0 and not missing,
        "pairwise_applicable": len(pairwise),
        "pairwise_false_safe": false_pairs,
        "mean_shortcut_safe": sum(v for k, v in mean.items() if k != "no_admission"),
        "mean_shortcut_false_safe": mean["confirmed_false_safe"],
        "mean_shortcut_unresolved": mean["unresolved"],
        "legacy_mean_flags_not_treated_as_counterexamples": True,
        "per_stratum": {},
        "physical_validation": False,
        "secondary_confirmatory_inference": False,
    }
    if denominator:
        result["delivery_coverage_bounds"] = [
            success / denominator,
            (success + len(missing)) / denominator,
        ]
    for s in STRATA:
        group = [r for r in eligible if r["stratum"] == s]
        times = [r["candidate"].get("wall_s") for r in group]
        times = [x for x in times if x is not None and math.isfinite(x)]
        result["per_stratum"][s] = {
            "eligible": len(group),
            "on_time_decisive_valid": sum(r["primary"]["on_time_decisive_valid"] for r in group),
            "statuses": dict(Counter(r["candidate"]["status"] for r in group)),
            "max_candidate_wall_s": max(times, default=None),
        }
    sizes = [result["per_stratum"][s]["eligible"] for s in STRATA]
    if denominator and not missing and min(sizes) > 0 and len(set(sizes)) == 1:
        result["balanced_coverage"] = conditional_mean_interval(success, denominator)
        result["balanced_coverage"]["inferential_scope"] = (
            "protected fixed-order conditional-mean target"
            if protected
            else "pilot description only; not confirmatory"
        )
    elif denominator:
        result["observed_coverage"] = success / denominator
        result["balanced_interval_withheld"] = "incomplete or unequal stratum sizes"
    native = {}
    for method in ("predictive", "barrier"):
        details = [r["native_baselines"].get("methods", {}).get(method) for r in eligible]
        details = [x for x in details if x is not None]
        native[method] = {
            "evaluated": len(details),
            "protected": sum(bool(x.get("protected")) for x in details),
            "statuses": dict(Counter(x["status"] for x in details)),
            "interpretation": "native-design comparison with different information representation and continuation obligations; no superiority claim",
        }
    result["native_baselines"] = native
    return result


def analyze_directory(directory, output=None, protected=False):
    directory = Path(directory)
    expected = None
    if protected:
        selection = strict_json(directory / "selection.json")
        expected = [(s, i) for s in STRATA for i in selection["selected"][s]]
    result = analyze_rows(load_cases(directory), protected=protected, expected_keys=expected)
    if output is not None:
        atomic_json(output, result)
    return result
