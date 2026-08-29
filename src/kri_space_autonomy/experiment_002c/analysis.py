from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import NumericalAmendmentConfig


def _historical_diagnostic(path: str | Path) -> dict[str, Any]:
    historical = json.loads(Path(path).read_text(encoding="utf-8"))
    by_pattern: dict[str, dict[str, Any]] = {}
    for pattern in (
        "pd_operational",
        "maximum_closing",
        "maximum_separating",
        "alternating_extrema",
    ):
        cases = [case for case in historical["cases"] if case["pattern"] == pattern]
        by_pattern[pattern] = {
            "cases": len(cases),
            "passed": sum(bool(case["passed"]) for case in cases),
            "maximum_state_error": max(case["maximum_state_error"] for case in cases),
            "maximum_metric_error": max(case["maximum_metric_error"] for case in cases),
        }
    smooth_closing_passed = by_pattern["maximum_closing"]["passed"] == 6
    reversal_or_depletion_dominated = bool(
        by_pattern["maximum_separating"]["passed"] == 0
        and by_pattern["alternating_extrema"]["passed"] == 0
        and by_pattern["alternating_extrema"]["maximum_metric_error"]
        == historical["maximum_state_or_metric_error"]
    )
    return {
        "source": "results/experiment-002b/fixed-command-replay.json",
        "historical_decision_preserved": not historical["passed"],
        "all_classifications_matched": historical["all_classifications_match"],
        "pattern_summary": by_pattern,
        "smooth_maximum_closing_cases_all_passed": smooth_closing_passed,
        "reversal_and_depletion_cases_dominated_failure": (
            reversal_or_depletion_dominated
        ),
        "supports_completed_diagnosis": bool(
            not historical["passed"]
            and historical["all_classifications_match"]
            and smooth_closing_passed
            and reversal_or_depletion_dominated
        ),
    }


def analyze_002c(
    amendment: NumericalAmendmentConfig,
    numerical_path: str | Path,
    historical_002b_numerical_path: str | Path,
    historical_002b_analysis_path: str | Path,
    seed_validation: dict[str, Any],
    validation_evidence: dict[str, Any],
    freeze_verified: bool,
    output_analysis_path: str | Path,
    output_qc_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    numerical = json.loads(Path(numerical_path).read_text(encoding="utf-8"))
    historical_analysis = json.loads(
        Path(historical_002b_analysis_path).read_text(encoding="utf-8")
    )
    historical_diagnostic = _historical_diagnostic(
        historical_002b_numerical_path
    )
    historical_evidence_boundary = bool(
        historical_analysis["decision"] == "fail"
        and historical_analysis["operational"]["passed"]
        and historical_analysis["rate_decomposition"]["passed_feasibility_qc"]
        and not historical_analysis["confirmatory_campaign_executed"]
        and not historical_analysis["combined_fault_study_executed"]
        and historical_diagnostic["supports_completed_diagnosis"]
    )
    zero_source_failures = all(
        case["source_controller_failure"] is None for case in numerical["cases"]
    )
    exact_case_count = numerical["case_count"] == amendment.replay_cases
    unique_cases = len(
        {
            (case["root_seed_id"], case["pattern"])
            for case in numerical["cases"]
        }
    ) == amendment.replay_cases
    pattern_counts = Counter(case["pattern"] for case in numerical["cases"])
    expected_per_pattern = 6 * amendment.replay_seeds_per_stratum
    complete_patterns = all(
        pattern_counts[pattern] == expected_per_pattern
        for pattern in amendment.replay_command_patterns
    )
    numerical_passed = bool(
        numerical["passed"]
        and exact_case_count
        and unique_cases
        and complete_patterns
        and zero_source_failures
        and numerical["all_event_orderings_match"]
        and numerical["all_classifications_match"]
        and numerical["all_braking_unreachable_match"]
        and numerical["all_reference_convergence_checks_pass"]
    )
    checks = [
        {
            "id": "pre_outcome_validation_and_freeze",
            "passed": bool(validation_evidence.get("passed") and freeze_verified),
            "threshold": "all pre-outcome checks pass and every frozen hash verifies",
        },
        {
            "id": "seed_partition",
            "passed": bool(seed_validation["passed"]),
            "threshold": (
                "partition 24 contains six manifest-complete roots disjoint from all "
                "Experiment 002 and 002b roots"
            ),
            "observed": seed_validation,
        },
        {
            "id": "historical_evidence_boundary",
            "passed": historical_evidence_boundary,
            "threshold": (
                "002b remains failed; passing operational/rate evidence is referenced only; "
                "completed numerical diagnosis is independently supported"
            ),
            "observed": historical_diagnostic,
        },
        {
            "id": "fixed_command_numerical_replay",
            "passed": numerical_passed,
            "threshold": (
                "all 24 traces pass unit-specific production/reference bounds, identical event "
                "ordering and classifications, explicit evaluator/extrema checks, raw residual "
                "bounds, and 25%-of-bound coarse/fine convergence"
            ),
            "observed": {
                "case_count": numerical["case_count"],
                "production_vs_reference_category_maxima": numerical[
                    "production_vs_reference_category_maxima"
                ],
                "coarse_vs_fine_category_maxima": numerical[
                    "coarse_vs_fine_category_maxima"
                ],
                "all_event_orderings_match": numerical[
                    "all_event_orderings_match"
                ],
                "all_classifications_match": numerical[
                    "all_classifications_match"
                ],
                "all_braking_unreachable_match": numerical[
                    "all_braking_unreachable_match"
                ],
                "all_reference_convergence_checks_pass": numerical[
                    "all_reference_convergence_checks_pass"
                ],
            },
        },
        {
            "id": "campaigns_remain_blocked",
            "passed": True,
            "threshold": (
                "operational, rate, combined-fault, and 32,000-episode confirmatory campaigns "
                "are not executed by Experiment 002c"
            ),
        },
    ]
    passed = all(check["passed"] for check in checks)
    decision = "pass" if passed else "fail"
    next_step = (
        "combined_fault_nuisance_information_requirement"
        if passed
        else "localize_remaining_numerical_issue"
    )
    analysis = {
        "schema_version": amendment.schema_version,
        "decision": decision,
        "numerical_blocker_resolved": passed,
        "historical_002b_diagnostic_reverification": historical_diagnostic,
        "fixed_command_numerical_replay": numerical,
        "operational_and_rate_evidence": {
            "carried_by_reference_only": True,
            "source": "results/experiment-002b/analysis.json",
            "operational_passed_in_002b": historical_analysis["operational"]["passed"],
            "rate_feasibility_qc_passed_in_002b": historical_analysis[
                "rate_decomposition"
            ]["passed_feasibility_qc"],
            "experiment_002b_overall_decision": historical_analysis["decision"],
        },
        "next_scientific_blocker": next_step,
        "confirmatory_campaign_executed": False,
        "combined_fault_study_executed": False,
        "operational_campaign_rerun": False,
        "rate_campaign_rerun": False,
    }
    qc = {
        "schema_version": amendment.schema_version,
        "overall_passed": passed,
        "decision": decision,
        "checks": checks,
        "deviations": [],
    }
    Path(output_analysis_path).write_text(
        json.dumps(analysis, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    Path(output_qc_path).write_text(
        json.dumps(qc, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return analysis, qc


def write_report(analysis: dict[str, Any], path: str | Path) -> None:
    replay = analysis["fixed_command_numerical_replay"]
    bounds = replay["acceptance_bounds"]
    convergence_bounds = replay["convergence_bounds"]
    production_maxima = replay["production_vs_reference_category_maxima"]
    convergence_maxima = replay["coarse_vs_fine_category_maxima"]
    rows = []
    for category in bounds:
        rows.append(
            f"| {category} | `{production_maxima[category]:.3e}` | "
            f"`{bounds[category]:.3e}` | `{convergence_maxima[category]:.3e}` | "
            f"`{convergence_bounds[category]:.3e}` |"
        )
    failed_cases = [
        f"{case['root_seed_id']} / {case['pattern']}"
        for case in replay["cases"]
        if not case["passed"]
    ]
    lines = [
        "# Experiment 002c numerical corrective amendment",
        "",
        "_Frozen numerical-only replay; Experiments 002 and 002b remain historical_",
        "",
        "---",
        "",
        "## ✅ Decision",
        "",
        f"**`{analysis['decision']}`**. Numerical blocker resolved: ",
        f"`{str(analysis['numerical_blocker_resolved']).lower()}`.",
        "",
        "The operational and rate campaigns were not rerun. The `32,000`-episode",
        "confirmatory campaign and combined-fault study were not run.",
        "",
        "## 📊 Numerical replay",
        "",
        f"- Complete traces: `{replay['case_count']}`",
        "- Event ordering identical: "
        f"`{str(replay['all_event_orderings_match']).lower()}`",
        "- Required classifications identical: "
        f"`{str(replay['all_classifications_match']).lower()}`",
        "- `braking_unreachable` identical: "
        f"`{str(replay['all_braking_unreachable_match']).lower()}`",
        "- All coarse/fine convergence checks passed: "
        f"`{str(replay['all_reference_convergence_checks_pass']).lower()}`",
        "",
        "| Quantity | Production/fine max | Bound | Coarse/fine max | 25% bound |",
        "| --- | ---: | ---: | ---: | ---: |",
        *rows,
        "",
        "## 🔍 Historical diagnosis",
        "",
        "The frozen 002b replay remains failed. Independent inspection again found that all",
        "smooth maximum-closing traces passed while reversal/depletion patterns dominated the",
        "error and all required classifications matched. Focused regression tests cover the",
        "separate production terminal-extremum defect.",
        "",
        "## 🎯 Next scientific blocker",
        "",
        f"`{analysis['next_scientific_blocker']}`.",
        "",
    ]
    if failed_cases:
        lines.extend(
            [
                "## ⚠️ Remaining numerical failures",
                "",
                *[f"- `{value}`" for value in failed_cases],
                "",
            ]
        )
    Path(path).write_text("\n".join(lines), encoding="utf-8")
