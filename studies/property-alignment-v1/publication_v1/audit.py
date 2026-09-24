"""Read-only scientific artifact audit with explicit prior-commit identities."""

from pathlib import Path
import argparse
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent
REPO = STUDY.parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


SCIENTIFIC_SOURCE_COMMIT = "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8"


def verify_manifest(document=None, repository=REPO):
    """Version 2 binds working bytes/modes to Git, not just to a manifest."""
    from .git_binding import strict_json, verify_commit_content

    doc = (
        strict_json((ROOT / "evidence_manifest.json").read_bytes())
        if document is None
        else document
    )
    return verify_commit_content(doc, repository, expected_commit=SCIENTIFIC_SOURCE_COMMIT)


def outcomes():
    c = load(STUDY / "campaign_v2/recorded/analysis.json")
    t = load(STUDY / "transfer_cart_v1/recorded/summary.json")
    h = load(STUDY / "execution_validation_v1/recorded/summary.json")
    b = load(STUDY / "protective/recorded_analysis/results.json")
    a = load(STUDY / "causal/recorded_analysis/results.json")
    if (
        c["planned_denominator"] != 768
        or c["missing_selected"]
        or c["invalid_definite_certificates"]
    ):
        raise ValueError("Protected denominator or validity changed")
    statuses = c["candidate_statuses"]
    if sum(statuses.values()) != 768 or c["on_time_decisive_valid"] != 756:
        raise ValueError("Protected endpoint accounting")
    radius = math.sqrt(math.log(40) / (2 * 768))
    interval = c["balanced_coverage"]
    if (
        abs(interval["estimate"] - 756 / 768) > 1e-15
        or abs(interval["lower"] - (756 / 768 - radius)) > 1e-15
    ):
        raise ValueError("Frozen conditional-mean calculation changed")
    if interval["independent_hardware_sessions_observed"] or c["secondary_confirmatory_inference"]:
        raise ValueError("Unsupported inference")
    counts = t["methods"]["lag_aware_common_command"]["outcomes"]
    if sum(counts.values()) != t["cases"] or t["cases"] != 128:
        raise ValueError("Transfer accounting")
    predictive = t["methods"]["robust_predictive_prefix"]["outcomes"]["verified_prefix"]
    if predictive <= counts["verified_prefix"]:
        raise ValueError("Negative comparator result lost")
    pred = next(x for x in b["arms"] if x["arm"] == "predictive")
    barrier = next(x for x in b["arms"] if x["arm"] == "barrier")
    midpoint = [x for x in a["predicate_contrasts"] if x["case"] == "midpoint"]
    if len(midpoint) != 2 or not all(
        x["same_applied_commands"] and x["overrides_difference"] == 45 for x in midpoint
    ):
        raise ValueError("Controlled contrast changed")
    return {
        "campaign": {
            "denominator": 768,
            "statuses": statuses,
            "verified_diagnostics": 756,
            "conditional_mean_interval": [interval["lower"], interval["upper"]],
            "operational_safety_estimate": False,
        },
        "transfer": {
            "cases": 128,
            "criterion": counts,
            "predictive_prefixes": predictive,
            "pairwise_certified_joint_obstructions": t["all_pairs_certified_joint_obstructions"],
            "lag_mismatch": t["lag_mismatch_stress"]["methods"]["lag_aware_common_command"],
        },
        "development": {
            "predictive_contained": pred["contained"],
            "predictive_external_actions": pred["external_guard_decisions"],
            "barrier_continued_cases": barrier["admissible_cases"]
            - barrier["entirely_filter_protected"],
            "barrier_external_actions": barrier["external_guard_decisions"],
        },
        "host": {
            "measured_requests": h["measured_samples"],
            "warmups": h["warmup_samples"],
            "physical_trials": h["physical_trials"],
            "external_reviews": h["external_reviews"],
        },
        "inferential_populations_pooled": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = {
        "schema": "sal-publication-audit/2",
        "source": verify_manifest(),
        "outcomes": outcomes(),
        "protected_campaigns_executed": False,
        "scope": "Git-content/mode and derived-count checks; not physical or human validation",
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(text)
    print(text)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "passed": False,
                    "verification_version": "sal-git-content-binding/2",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        )
        raise SystemExit(2) from exc
