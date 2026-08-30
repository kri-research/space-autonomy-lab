from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import binomtest

from kri_space_autonomy.experiment_002.analysis import exact_one_sided_upper

from .config import (
    CONFIRMATORY_STRATA,
    FAULTED_STRATA,
    HARM_CONTROL_STRATA,
    ConfirmatoryConfig,
)

BINARY_ENDPOINTS = (
    "analysis_hazard",
    "physical_hazard_observed",
    "collision",
    "sustained_success",
    "braking_unreachable",
)
RECOVERY_BINARY_ENDPOINTS = ("recovery_favorable_180",)
CONTINUOUS_ENDPOINTS = (
    "restricted_time_unrecovered_s_180",
    "minimum_braking_margin_m",
    "minimum_range_m",
    "handover_entries",
    "fallback_duty_cycle",
    "propellant_used_fraction",
    "goal_dwell_final60_fraction",
)
CONTRASTS = (("PD", "D"), ("PS", "D"), ("PD", "PS"))


def validate_episode_cells(
    rows: list[dict[str, Any]], study: ConfirmatoryConfig
) -> dict[str, Any]:
    cell_counts = Counter(
        (str(row.get("stratum_id")), str(row.get("root_seed_id")), str(row.get("arm")))
        for row in rows
    )
    duplicate_cells = [key for key, count in cell_counts.items() if count != 1]
    block_arms: dict[tuple[str, str], set[str]] = defaultdict(set)
    unexpected_rows: list[tuple[str, str, str]] = []
    for row in rows:
        stratum = str(row.get("stratum_id"))
        root = str(row.get("root_seed_id"))
        arm = str(row.get("arm"))
        if stratum not in CONFIRMATORY_STRATA or arm not in study.arms:
            unexpected_rows.append((stratum, root, arm))
            continue
        block_arms[(stratum, root)].add(arm)
    complete = {
        key for key, arms in block_arms.items() if arms == set(study.arms)
    }
    incomplete = [key for key, arms in block_arms.items() if arms != set(study.arms)]
    stratum_blocks = Counter(stratum for stratum, _ in block_arms)
    stratum_complete = Counter(stratum for stratum, _ in complete)
    incomplete_fraction_by_stratum = {
        stratum: 1.0 - stratum_complete[stratum] / study.seeds_per_stratum
        for stratum in CONFIRMATORY_STRATA
    }
    scheduled_missing_blocks = sum(
        study.seeds_per_stratum - stratum_blocks[stratum]
        for stratum in CONFIRMATORY_STRATA
    )
    incomplete_blocks = len(incomplete) + scheduled_missing_blocks
    overall_incomplete_fraction = incomplete_blocks / study.planned_blocks
    structural_valid = not duplicate_cells and not unexpected_rows and all(
        stratum_blocks[stratum] <= study.seeds_per_stratum
        for stratum in CONFIRMATORY_STRATA
    )
    completeness_passed = bool(
        overall_incomplete_fraction <= study.incomplete_block_limit
        and all(
            value <= study.incomplete_block_limit
            for value in incomplete_fraction_by_stratum.values()
        )
    )
    return {
        "structural_valid": structural_valid,
        "completeness_passed": completeness_passed,
        "exact_expected_cells": bool(
            len(rows) == study.planned_episodes
            and len(cell_counts) == study.planned_episodes
            and len(complete) == study.planned_blocks
        ),
        "episode_rows": len(rows),
        "unique_episode_cells": len(cell_counts),
        "observed_blocks": len(block_arms),
        "complete_four_arm_blocks": len(complete),
        "incomplete_or_missing_blocks": incomplete_blocks,
        "incomplete_fraction": overall_incomplete_fraction,
        "incomplete_fraction_by_stratum": incomplete_fraction_by_stratum,
        "duplicate_cells_preview": [list(key) for key in duplicate_cells[:20]],
        "unexpected_rows_preview": [list(key) for key in unexpected_rows[:20]],
    }


def _complete_root_ids(
    rows: list[dict[str, Any]], study: ConfirmatoryConfig
) -> dict[str, list[str]]:
    arms: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        key = (str(row["stratum_id"]), str(row["root_seed_id"]))
        arms[key].add(str(row["arm"]))
    return {
        stratum: sorted(
            root
            for (observed_stratum, root), observed_arms in arms.items()
            if observed_stratum == stratum and observed_arms == set(study.arms)
        )
        for stratum in CONFIRMATORY_STRATA
    }


def _paired_values(
    rows: list[dict[str, Any]],
    root_ids: list[str],
    stratum: str,
    arm_a: str,
    arm_b: str,
    endpoint: str,
) -> np.ndarray:
    selected = {
        (str(row["root_seed_id"]), str(row["arm"])): row
        for row in rows
        if row["stratum_id"] == stratum
    }
    values = []
    for root in root_ids:
        left = selected[(root, arm_a)].get(endpoint)
        right = selected[(root, arm_b)].get(endpoint)
        values.append(
            math.nan if left is None or right is None else float(left) - float(right)
        )
    return np.asarray(values, dtype=np.float64)


def _bootstrap_contrasts(
    rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    replicates: int | None = None,
    seed: int | None = None,
) -> tuple[dict[str, Any], dict[str, float]]:
    bootstrap_replicates = replicates or study.bootstrap_replicates
    bootstrap_seed = study.bootstrap_seed if seed is None else seed
    root_ids = _complete_root_ids(rows, study)
    endpoint_names = (*BINARY_ENDPOINTS, *RECOVERY_BINARY_ENDPOINTS, *CONTINUOUS_ENDPOINTS)
    distributions: dict[str, np.ndarray] = {}
    points: dict[str, dict[str, float]] = {}
    differences: dict[tuple[str, str], np.ndarray] = {}
    for arm_a, arm_b in CONTRASTS:
        contrast = f"{arm_a}-{arm_b}"
        for endpoint in endpoint_names:
            key = f"{contrast}:{endpoint}"
            distributions[key] = np.zeros(bootstrap_replicates, dtype=np.float64)
            points[key] = {}
            applicable = (
                FAULTED_STRATA
                if endpoint in (*RECOVERY_BINARY_ENDPOINTS, "restricted_time_unrecovered_s_180")
                else CONFIRMATORY_STRATA
            )
            for stratum in applicable:
                values = _paired_values(
                    rows,
                    root_ids[stratum],
                    stratum,
                    arm_a,
                    arm_b,
                    endpoint,
                )
                differences[(key, stratum)] = values
                points[key][stratum] = float(np.nanmean(values))
    rng = np.random.Generator(
        np.random.PCG64DXSM(np.random.SeedSequence([bootstrap_seed]))
    )
    stratum_harm_upper: dict[str, float] = {}
    for stratum in CONFIRMATORY_STRATA:
        n = len(root_ids[stratum])
        if n == 0:
            continue
        applicable_keys = [
            key
            for key in distributions
            if (key, stratum) in differences
        ]
        harm_distribution = np.zeros(bootstrap_replicates, dtype=np.float64)
        for start in range(0, bootstrap_replicates, 250):
            stop = min(bootstrap_replicates, start + 250)
            indices = rng.integers(0, n, size=(stop - start, n), dtype=np.int32)
            for key in applicable_keys:
                values = differences[(key, stratum)]
                sampled = values[indices]
                with np.errstate(invalid="ignore"):
                    means = np.nanmean(sampled, axis=1)
                weight = (
                    1.0 / len(FAULTED_STRATA)
                    if key.split(":", 1)[1]
                    in (*RECOVERY_BINARY_ENDPOINTS, "restricted_time_unrecovered_s_180")
                    else study.stratum_weight
                )
                distributions[key][start:stop] += means * weight
                if key == "PD-D:analysis_hazard":
                    harm_distribution[start:stop] = means
        if stratum in HARM_CONTROL_STRATA:
            stratum_harm_upper[stratum] = float(
                np.quantile(
                    harm_distribution,
                    1.0 - study.harm_control_per_stratum_alpha,
                )
            )
    output: dict[str, Any] = {}
    for key, values in distributions.items():
        point = sum(points[key].values()) / len(points[key])
        output[key] = {
            "estimate": point,
            "two_sided_95_interval": [
                float(np.nanquantile(values, 0.025)),
                float(np.nanquantile(values, 0.975)),
            ],
            "one_sided_97_5_lower": float(np.nanquantile(values, 0.025)),
            "one_sided_97_5_upper": float(np.nanquantile(values, 0.975)),
            "bootstrap_replicates": bootstrap_replicates,
            "bootstrap_seed": bootstrap_seed,
            "stratum_estimates": points[key],
        }
    return output, stratum_harm_upper


def _arm_summaries(rows: list[dict[str, Any]], study: ConfirmatoryConfig) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for stratum in CONFIRMATORY_STRATA:
        output[stratum] = {}
        for arm in study.arms:
            selected = [
                row
                for row in rows
                if row["stratum_id"] == stratum and row["arm"] == arm
            ]
            summary: dict[str, Any] = {"n": len(selected)}
            for endpoint in BINARY_ENDPOINTS:
                events = sum(bool(row[endpoint]) for row in selected)
                item = {
                    "events": events,
                    "risk": events / len(selected) if selected else None,
                }
                if endpoint == "collision" and selected:
                    item["one_sided_exact_95_upper"] = exact_one_sided_upper(
                        events, len(selected)
                    )
                summary[endpoint] = item
            for endpoint in CONTINUOUS_ENDPOINTS:
                values = np.asarray(
                    [row[endpoint] for row in selected if row.get(endpoint) is not None],
                    dtype=np.float64,
                )
                summary[endpoint] = {
                    "n": len(values),
                    "mean": float(np.mean(values)) if len(values) else None,
                    "median": float(np.median(values)) if len(values) else None,
                    "p05": float(np.quantile(values, 0.05)) if len(values) else None,
                    "p95": float(np.quantile(values, 0.95)) if len(values) else None,
                }
            summary["recovery_states"] = dict(
                Counter(str(row["recovery_state"]) for row in selected)
            )
            summary["failure_classes"] = dict(
                Counter(
                    str(row["failure_class"])
                    for row in selected
                    if row.get("failure_class") is not None
                )
            )
            output[stratum][arm] = summary
    return output


def _weighted_arm_risk(
    summaries: dict[str, Any], arm: str, endpoint: str
) -> float:
    return sum(
        float(summaries[stratum][arm][endpoint]["risk"]) / len(CONFIRMATORY_STRATA)
        for stratum in CONFIRMATORY_STRATA
    )


def _discordant_counts(
    rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    endpoint: str,
    arm_a: str,
    arm_b: str,
    strata: tuple[str, ...],
) -> tuple[int, int]:
    root_ids = _complete_root_ids(rows, study)
    a1_b0 = 0
    a0_b1 = 0
    for stratum in strata:
        differences = _paired_values(
            rows, root_ids[stratum], stratum, arm_a, arm_b, endpoint
        )
        a1_b0 += int(np.sum(differences == 1.0))
        a0_b1 += int(np.sum(differences == -1.0))
    return a1_b0, a0_b1


def _one_sided_discordance_p(
    a1_b0: int,
    a0_b1: int,
    beneficial_direction: str,
) -> float:
    discordant = a1_b0 + a0_b1
    if discordant == 0:
        return 1.0
    alternative = "less" if beneficial_direction == "lower" else "greater"
    return float(binomtest(a1_b0, discordant, 0.5, alternative=alternative).pvalue)


def _sign_randomization_p(
    differences: np.ndarray,
    simulations: int,
    seed: int,
) -> float:
    values = differences[np.isfinite(differences)]
    if len(values) == 0:
        return 1.0
    observed = float(np.mean(values))
    if observed >= 0.0:
        return 1.0
    rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([seed])))
    extreme = 0
    for start in range(0, simulations, 1000):
        count = min(1000, simulations - start)
        signs = rng.integers(0, 2, size=(count, len(values)), dtype=np.int8)
        signs = signs * 2 - 1
        permuted = np.mean(signs * values, axis=1)
        extreme += int(np.sum(permuted <= observed))
    return (extreme + 1.0) / (simulations + 1.0)


def _holm_adjust(raw: dict[str, float], alpha: float) -> dict[str, Any]:
    ordered = sorted(raw, key=raw.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    m = len(ordered)
    for rank, name in enumerate(ordered):
        running = max(running, (m - rank) * raw[name])
        adjusted[name] = min(1.0, running)
    return {
        name: {
            "raw_p": raw[name],
            "holm_adjusted_p": adjusted[name],
            "rejected": adjusted[name] <= alpha,
        }
        for name in raw
    }


def _secondary_tests(
    rows: list[dict[str, Any]], study: ConfirmatoryConfig
) -> dict[str, Any]:
    h3_counts = _discordant_counts(
        rows, study, "analysis_hazard", "PS", "D", CONFIRMATORY_STRATA
    )
    h4_counts = _discordant_counts(
        rows, study, "analysis_hazard", "PD", "PS", CONFIRMATORY_STRATA
    )
    h5a_counts = _discordant_counts(
        rows, study, "recovery_favorable_180", "PD", "D", FAULTED_STRATA
    )
    root_ids = _complete_root_ids(rows, study)
    h5b_differences = np.concatenate(
        [
            _paired_values(
                rows,
                root_ids[stratum],
                stratum,
                "PD",
                "D",
                "restricted_time_unrecovered_s_180",
            )
            for stratum in FAULTED_STRATA
        ]
    )
    raw = {
        "H3_PS_minus_D_analysis_hazard": _one_sided_discordance_p(
            *h3_counts, beneficial_direction="lower"
        ),
        "H4_PD_minus_PS_analysis_hazard": _one_sided_discordance_p(
            *h4_counts, beneficial_direction="lower"
        ),
        "H5a_PD_minus_D_recovery_favorable": _one_sided_discordance_p(
            *h5a_counts, beneficial_direction="higher"
        ),
        "H5b_PD_minus_D_restricted_time": _sign_randomization_p(
            h5b_differences,
            study.secondary_randomization_replicates,
            study.secondary_randomization_seed,
        ),
    }
    return {
        "family": "four fixed one-sided tests with Holm adjustment",
        "family_alpha": study.secondary_holm_alpha,
        "tests": _holm_adjust(raw, study.secondary_holm_alpha),
        "discordant_counts": {
            "H3": {"a1_b0": h3_counts[0], "a0_b1": h3_counts[1]},
            "H4": {"a1_b0": h4_counts[0], "a0_b1": h4_counts[1]},
            "H5a": {"a1_b0": h5a_counts[0], "a0_b1": h5a_counts[1]},
        },
        "H5b_randomization": {
            "draws": study.secondary_randomization_replicates,
            "seed": study.secondary_randomization_seed,
        },
    }


def _primary_sensitivity_points(
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
) -> dict[str, Any]:
    selected = {
        (str(row["stratum_id"]), str(row["root_seed_id"]), str(row["arm"])): row
        for row in rows
    }
    worst_hazard = 0.0
    worst_success = 0.0
    available_hazard = 0.0
    available_success = 0.0
    available_counts: dict[str, int] = {}
    for stratum in CONFIRMATORY_STRATA:
        roots = [
            str(row["root_seed_id"])
            for row in seed_rows
            if row["stratum_id"] == stratum
        ]
        hazard_values = []
        success_values = []
        available_h = []
        available_s = []
        for root in roots:
            pd = selected.get((stratum, root, "PD"))
            direct = selected.get((stratum, root, "D"))
            pd_h = bool(pd["analysis_hazard"]) if pd is not None else True
            d_h = bool(direct["analysis_hazard"]) if direct is not None else False
            pd_s = bool(pd["sustained_success"]) if pd is not None else False
            d_s = bool(direct["sustained_success"]) if direct is not None else True
            hazard_values.append(float(pd_h) - float(d_h))
            success_values.append(float(pd_s) - float(d_s))
            if pd is not None and direct is not None:
                available_h.append(float(pd_h) - float(d_h))
                available_s.append(float(pd_s) - float(d_s))
        worst_hazard += float(np.mean(hazard_values)) * study.stratum_weight
        worst_success += float(np.mean(success_values)) * study.stratum_weight
        available_counts[stratum] = len(available_h)
        if available_h:
            available_hazard += float(np.mean(available_h)) * study.stratum_weight
            available_success += float(np.mean(available_s)) * study.stratum_weight
    return {
        "worst_case_missing_primary_cells": {
            "analysis_hazard_risk_difference": worst_hazard,
            "sustained_success_risk_difference": worst_success,
            "rule": "missing PD adverse; missing D favorable to D",
        },
        "all_available_D_PD_pairs": {
            "analysis_hazard_risk_difference": available_hazard,
            "sustained_success_risk_difference": available_success,
            "pairs_by_stratum": available_counts,
        },
    }


def analyze_confirmatory(
    study: ConfirmatoryConfig,
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    integrity: dict[str, Any],
    output_path: str | Path,
    qc_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cells = validate_episode_cells(rows, study)
    contrasts, harm_upper = _bootstrap_contrasts(rows, study)
    summaries = _arm_summaries(rows, study)
    hazard = contrasts["PD-D:analysis_hazard"]
    success = contrasts["PD-D:sustained_success"]
    physical = contrasts["PD-D:physical_hazard_observed"]
    h1_pass = hazard["two_sided_95_interval"][1] < 0.0
    h2_pass = bool(
        h1_pass
        and success["one_sided_97_5_lower"] > study.h2_noninferiority_margin
    )
    direct_hazard_risk = _weighted_arm_risk(summaries, "D", "analysis_hazard")
    protected_hazard_risk = _weighted_arm_risk(summaries, "PD", "analysis_hazard")
    relative_reduction = (
        (direct_hazard_risk - protected_hazard_risk) / direct_hazard_risk
        if direct_hazard_risk > 0.0
        else None
    )
    effect_thresholds_pass = bool(
        hazard["estimate"] <= -study.hazard_minimum_absolute_reduction
        and relative_reduction is not None
        and relative_reduction >= study.hazard_minimum_relative_reduction
    )
    harm_control_pass = bool(
        set(harm_upper) == set(HARM_CONTROL_STRATA)
        and all(value < study.harm_control_margin for value in harm_upper.values())
    )
    nominal_pd = summaries["F0_nominal"]["PD"]["fallback_duty_cycle"]
    fallback_pass = bool(
        nominal_pd["median"] is not None
        and nominal_pd["p95"] is not None
        and nominal_pd["median"] < 0.05
        and nominal_pd["p95"] < 0.15
    )
    validity_pass = bool(
        integrity.get("passed")
        and cells["structural_valid"]
        and cells["completeness_passed"]
    )
    favorable = bool(
        validity_pass
        and h1_pass
        and h2_pass
        and effect_thresholds_pass
        and harm_control_pass
        and fallback_pass
    )
    unfavorable = bool(
        validity_pass
        and (
            hazard["two_sided_95_interval"][0] > 0.0
            or (
                h1_pass
                and success["one_sided_97_5_upper"]
                < study.h2_noninferiority_margin
            )
        )
    )
    if not validity_pass:
        decision = "inconclusive_invalid"
    elif favorable:
        decision = "favorable"
    elif unfavorable:
        decision = "unfavorable"
    else:
        decision = "inconclusive"
    sensitivities = _primary_sensitivity_points(rows, seed_rows, study)
    sensitivities["physical_hazard_only"] = {
        "estimate": physical["estimate"],
        "two_sided_95_interval": physical["two_sided_95_interval"],
    }
    analysis = {
        "schema_version": study.schema_version,
        "study_phase": "confirmatory",
        "decision": decision,
        "estimand_registry": {
            "independent_unit": "stratum by root-seed four-arm block",
            "primary_contrast": "PD-D",
            "H1_endpoint": "adverse-coded analysis_hazard",
            "H2_endpoint": "sustained_success",
            "confirmatory_stratum_weight": study.stratum_weight,
            "recovery_weight": 1.0 / len(FAULTED_STRATA),
            "resampling": "stratified paired complete-block percentile bootstrap",
        },
        "counts": cells,
        "arm_summaries": summaries,
        "contrasts": contrasts,
        "primary_gatekeeping": {
            "H1": {
                "passed": h1_pass,
                "rule": "two-sided 95% upper bound below zero",
                **hazard,
            },
            "H2": {
                "status": "tested" if h1_pass else "not_tested_gate_closed",
                "passed": h2_pass if h1_pass else None,
                "margin": study.h2_noninferiority_margin,
                **success,
            },
        },
        "favorable_decision_gates": {
            "validity": validity_pass,
            "H1": h1_pass,
            "H2": h2_pass,
            "absolute_and_relative_effect": effect_thresholds_pass,
            "relative_hazard_reduction": relative_reduction,
            "four_stratum_harm_control": harm_control_pass,
            "harm_control_upper_bounds": harm_upper,
            "nominal_fallback": fallback_pass,
        },
        "secondary_family": _secondary_tests(rows, study),
        "predeclared_sensitivities": sensitivities,
        "integrity": integrity,
        "failure_classes": dict(
            Counter(
                str(row["failure_class"])
                for row in rows
                if row.get("failure_class") is not None
            )
        ),
    }
    qc = {
        "schema_version": study.schema_version,
        "overall_passed": validity_pass,
        "decision": decision,
        "checks": {
            "integrity": bool(integrity.get("passed")),
            "structural_cells": cells["structural_valid"],
            "completeness": cells["completeness_passed"],
        },
    }
    Path(output_path).write_text(
        json.dumps(analysis, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    Path(qc_path).write_text(
        json.dumps(qc, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return analysis, qc
