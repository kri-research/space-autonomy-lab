from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from scipy.stats import binom, binomtest

from .config import ConfirmatoryConfig

REQUIRED_ROW_FIELDS = {
    "case_id",
    "root_seed_id",
    "configuration_id",
    "physical_collision",
    "physical_keep_out_entry",
    "physical_corridor_departure",
    "hold_acquired",
    "infrastructure_failure",
    "numerical_valid",
}


def exact_primary_sample_size(
    *, alpha: float, target_power: float, planning_net_reduction: float
) -> dict[str, Any]:
    """Smallest even N under worst-case all-discordant paired binary outcomes.

    At the no-effect boundary, beneficial and harmful discordances are equiprobable.
    The planning alternative is a net beneficial-discordance probability difference.
    All roots discordant maximizes paired-difference variance; smaller discordance
    fractions with the same net difference are no less favorable for this calculation.
    Even N is required so the two primary fault strata receive equal counts.
    """

    if not 0.0 < alpha < 0.5 or not 0.0 < target_power < 1.0:
        raise ValueError("alpha and target power must be probabilities")
    if not 0.0 < planning_net_reduction < 1.0:
        raise ValueError("planning net reduction must be in (0, 1)")
    alternative_beneficial_probability = 0.5 + planning_net_reduction / 2.0
    for roots in range(2, 100_002, 2):
        critical_beneficial = int(binom.isf(alpha, roots, 0.5)) + 1
        achieved_alpha = float(binom.sf(critical_beneficial - 1, roots, 0.5))
        achieved_power = float(
            binom.sf(
                critical_beneficial - 1,
                roots,
                alternative_beneficial_probability,
            )
        )
        if achieved_power >= target_power:
            return {
                "roots": roots,
                "critical_beneficial_discordances_if_all_discordant": critical_beneficial,
                "achieved_alpha": achieved_alpha,
                "achieved_power": achieved_power,
                "null_beneficial_probability": 0.5,
                "planning_beneficial_probability": alternative_beneficial_probability,
                "worst_case_discordance_fraction": 1.0,
            }
    raise RuntimeError("sample-size search exceeded its fixed bound")


def _physical_adverse(row: dict[str, Any]) -> bool:
    return bool(
        row["physical_collision"]
        or row["physical_keep_out_entry"]
        or row["physical_corridor_departure"]
    )


def _scheduled_keys(seed_rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(str(row["case_id"]), str(row["root_seed_id"])) for row in seed_rows}


def validate_fixed_cells(
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
) -> dict[str, Any]:
    scheduled = _scheduled_keys(seed_rows)
    expected = {
        (case_id, root_id, configuration)
        for case_id, root_id in scheduled
        for configuration in study.configurations
    }
    counts = Counter(
        (
            str(row.get("case_id")),
            str(row.get("root_seed_id")),
            str(row.get("configuration_id")),
        )
        for row in rows
    )
    observed = set(counts)
    malformed = sum(not REQUIRED_ROW_FIELDS <= set(row) for row in rows)
    infrastructure = sum(bool(row.get("infrastructure_failure")) for row in rows)
    numerical = sum(not bool(row.get("numerical_valid")) for row in rows)
    duplicates = sum(count - 1 for count in counts.values() if count > 1)
    missing = expected - observed
    extra = observed - expected
    expected_seed_counts = Counter(case_id for case_id, _ in scheduled)
    seed_count_valid = bool(
        len(seed_rows) == study.planned_blocks
        and len(scheduled) == study.planned_blocks
        and all(
            expected_seed_counts[stratum] == study.roots_by_stratum[stratum]
            for stratum in study.strata
        )
    )
    passed = bool(
        seed_count_valid
        and len(rows) == study.planned_episodes
        and not malformed
        and not infrastructure
        and not numerical
        and not duplicates
        and not missing
        and not extra
    )
    return {
        "passed": passed,
        "seed_count_valid": seed_count_valid,
        "scheduled_blocks": len(scheduled),
        "episode_rows": len(rows),
        "expected_episode_rows": study.planned_episodes,
        "malformed_rows": malformed,
        "infrastructure_failures": infrastructure,
        "numerical_failures": numerical,
        "duplicates": duplicates,
        "missing_cells": len(missing),
        "extra_cells": len(extra),
        "missing_preview": sorted(missing)[:20],
        "extra_preview": sorted(extra)[:20],
        "retry_replacement_or_imputation_used": False,
    }


def _paired_rows(
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    strata: tuple[str, ...],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    selected = {
        (
            str(row["case_id"]),
            str(row["root_seed_id"]),
            str(row["configuration_id"]),
        ): row
        for row in rows
    }
    pairs = []
    for seed in seed_rows:
        case_id = str(seed["case_id"])
        if case_id not in strata:
            continue
        root_id = str(seed["root_seed_id"])
        reference = selected[(case_id, root_id, "primary_reference")]
        monitored = selected[(case_id, root_id, "independent_monitor_gate")]
        pairs.append((reference, monitored))
    return pairs


def _primary_gate(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    study: ConfirmatoryConfig,
) -> dict[str, Any]:
    beneficial = 0
    harmful = 0
    for reference, monitored in pairs:
        reference_adverse = _physical_adverse(reference)
        monitored_adverse = _physical_adverse(monitored)
        beneficial += int(reference_adverse and not monitored_adverse)
        harmful += int(monitored_adverse and not reference_adverse)
    discordant = beneficial + harmful
    p_value = (
        float(binomtest(beneficial, discordant, 0.5, alternative="greater").pvalue)
        if discordant
        else 1.0
    )
    risk_difference = (harmful - beneficial) / len(pairs)
    passed = bool(
        p_value <= study.primary_one_sided_alpha
        and risk_difference <= -study.primary_minimum_reportable_net_reduction
    )
    return {
        "passed": passed,
        "hypothesis": (
            "H0: gate physical-adverse risk minus reference physical-adverse risk >= 0; "
            "H1: the paired difference is < 0"
        ),
        "endpoint": (
            "collision OR unauthorized keep-out entry OR corridor departure, from the "
            "independent physical truth evaluator"
        ),
        "reference_adverse_gate_safe": beneficial,
        "gate_adverse_reference_safe": harmful,
        "discordant_pairs": discordant,
        "paired_roots": len(pairs),
        "gate_minus_reference_risk_difference": risk_difference,
        "minimum_reportable_net_reduction": (
            study.primary_minimum_reportable_net_reduction
        ),
        "one_sided_exact_p": p_value,
        "alpha": study.primary_one_sided_alpha,
        "test": "exact one-sided paired discordance (McNemar/sign) test",
    }


def _mission_gate(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    study: ConfirmatoryConfig,
    *, primary_passed: bool,
) -> dict[str, Any]:
    harms = sum(
        bool(reference["hold_acquired"] and not monitored["hold_acquired"])
        for reference, monitored in pairs
    )
    p_value = float(
        binomtest(
            harms,
            len(pairs),
            study.mission_harm_margin,
            alternative="less",
        ).pvalue
    )
    passed = bool(primary_passed and p_value <= study.primary_one_sided_alpha)
    return {
        "status": "tested" if primary_passed else "not_tested_primary_gate_closed",
        "passed": passed if primary_passed else None,
        "hypothesis": (
            f"H0: P(reference acquires hold and gate does not) >= "
            f"{study.mission_harm_margin:.2f}; H1: probability is below that margin"
        ),
        "endpoint": "gate-induced loss of frozen hold acquisition",
        "harmful_pairs": harms,
        "paired_roots": len(pairs),
        "harm_rate": harms / len(pairs),
        "margin": study.mission_harm_margin,
        "one_sided_exact_p": p_value if primary_passed else None,
        "alpha": study.primary_one_sided_alpha,
        "test": "exact one-sided binomial risk-limit test",
    }


def _mechanism_summary(
    rows: list[dict[str, Any]], study: ConfirmatoryConfig
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for stratum in study.strata:
        summary[stratum] = {}
        for configuration in study.configurations:
            selected = [
                row
                for row in rows
                if row["case_id"] == stratum
                and row["configuration_id"] == configuration
            ]
            summary[stratum][configuration] = {
                "episodes": len(selected),
                "physical_adverse": sum(_physical_adverse(row) for row in selected),
                "collision": sum(bool(row["physical_collision"]) for row in selected),
                "keep_out_entry": sum(
                    bool(row["physical_keep_out_entry"]) for row in selected
                ),
                "corridor_departure": sum(
                    bool(row["physical_corridor_departure"]) for row in selected
                ),
                "hold_acquired": sum(bool(row["hold_acquired"]) for row in selected),
                "technical_flags": {
                    name: sum(bool(row.get(name)) for row in selected)
                    for name in (
                        "primary_estimator_fault",
                        "monitor_estimator_fault",
                        "monitor_logic_fault",
                        "shared_cause_fault",
                        "actuation_degradation_scheduled",
                        "disturbance_scheduled",
                        "infrastructure_failure",
                    )
                },
            }
    return summary


def analyze_confirmatory_rows(
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
) -> dict[str, Any]:
    cells = validate_fixed_cells(rows, seed_rows, study)
    if not cells["passed"]:
        return {
            "schema_version": study.schema_version,
            "decision": "inconclusive_invalid",
            "validity": cells,
            "primary_gatekeeping": None,
            "secondary_inferential_family": None,
            "no_retry_replacement_extension_or_imputation": True,
        }
    pairs = _paired_rows(rows, seed_rows, study, study.primary_strata)
    primary = _primary_gate(pairs, study)
    mission = _mission_gate(pairs, study, primary_passed=primary["passed"])
    favorable = bool(primary["passed"] and mission["passed"])
    return {
        "schema_version": study.schema_version,
        "decision": "favorable" if favorable else "inconclusive",
        "validity": cells,
        "estimand": {
            "independent_unit": "complete case-by-root paired two-configuration block",
            "target_population": (
                "equal-weight mixture of frozen primary-navigation bias and dropout "
                "challenge strata"
            ),
            "primary": (
                "gate-minus-reference risk difference for independent-evaluator physical "
                "adverse endpoint"
            ),
            "mission": (
                "probability that reference acquires hold while monitor-gated arm does not"
            ),
        },
        "primary_gatekeeping": {"H1_physical_safety": primary, "H2_mission": mission},
        "secondary_inferential_family": None,
        "mechanism_specific_descriptive_summary": _mechanism_summary(rows, study),
        "no_retry_replacement_extension_or_imputation": True,
        "claim_boundary": (
            "deterministic planar HCW assurance only; no AI-policy, operational prevalence, "
            "flight-safety, 6-DoF, or HIL claim"
        ),
    }


def write_analysis(
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    output_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    if output.exists():
        raise RuntimeError("refusing pre-existing confirmatory analysis output")
    result = analyze_confirmatory_rows(rows, seed_rows, study)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return result
