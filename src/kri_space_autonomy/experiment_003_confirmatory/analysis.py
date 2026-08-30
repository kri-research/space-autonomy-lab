from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import binomtest

from kri_space_autonomy.experiment_003.config import ESTIMATOR_STRATA

from .config import FAULTED_STRATA, ConfirmatoryConfig

ALLOWED_FAILURE_CLASSES = {
    "INVALID_ACTION",
    "NUMERICAL_FAILURE",
    "ESTIMATOR_DIVERGED",
}
PRIMARY_BOOTSTRAP_ENDPOINTS = (
    "analysis_hazard",
    "sustained_success",
    "physical_hazard_observed",
)


def validate_episode_cells(
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
) -> dict[str, Any]:
    scheduled = {
        (str(row.get("stratum_id")), str(row.get("root_seed_id"))) for row in seed_rows
    }
    scheduled_by_stratum = Counter(stratum for stratum, _ in scheduled)
    seed_contract_valid = bool(
        len(seed_rows) == study.planned_blocks
        and len(scheduled) == study.planned_blocks
        and all(
            scheduled_by_stratum[stratum] == study.roots_per_stratum
            for stratum in ESTIMATOR_STRATA
        )
    )
    cell_counts = Counter(
        (str(row.get("stratum_id")), str(row.get("root_seed_id")), str(row.get("arm")))
        for row in rows
    )
    duplicate_cells = [key for key, count in cell_counts.items() if count != 1]
    block_arms: dict[tuple[str, str], set[str]] = defaultdict(set)
    unexpected_rows: list[tuple[str, str, str]] = []
    invalid_failure_rows: list[tuple[str, str, str]] = []
    for row in rows:
        stratum = str(row.get("stratum_id"))
        root = str(row.get("root_seed_id"))
        arm = str(row.get("arm"))
        if (stratum, root) not in scheduled or arm not in study.arms:
            unexpected_rows.append((stratum, root, arm))
            continue
        block_arms[(stratum, root)].add(arm)
        failure = row.get("failure_class")
        if failure is not None and (
            failure not in ALLOWED_FAILURE_CLASSES
            or not bool(row.get("analysis_hazard"))
            or bool(row.get("sustained_success"))
            or row.get("recovery_state") != "FAILED"
        ):
            invalid_failure_rows.append((stratum, root, arm))
    complete = {
        key for key, observed_arms in block_arms.items() if observed_arms == set(study.arms)
    }
    complete_by_stratum = Counter(stratum for stratum, _ in complete)
    incomplete_fraction_by_stratum = {
        stratum: 1.0 - complete_by_stratum[stratum] / study.roots_per_stratum
        for stratum in ESTIMATOR_STRATA
    }
    incomplete_blocks = study.planned_blocks - len(complete)
    incomplete_fraction = incomplete_blocks / study.planned_blocks
    structural_valid = bool(
        seed_contract_valid
        and not duplicate_cells
        and not unexpected_rows
        and not invalid_failure_rows
    )
    completeness_passed = bool(
        incomplete_fraction <= study.incomplete_block_limit
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
        "seed_contract_valid": seed_contract_valid,
        "episode_rows": len(rows),
        "unique_episode_cells": len(cell_counts),
        "complete_four_arm_blocks": len(complete),
        "incomplete_or_missing_blocks": incomplete_blocks,
        "incomplete_fraction": incomplete_fraction,
        "incomplete_fraction_by_stratum": incomplete_fraction_by_stratum,
        "duplicate_cells_preview": [list(key) for key in duplicate_cells[:20]],
        "unexpected_rows_preview": [list(key) for key in unexpected_rows[:20]],
        "invalid_failure_rows_preview": [list(key) for key in invalid_failure_rows[:20]],
    }


def _complete_root_ids(
    rows: list[dict[str, Any]], study: ConfirmatoryConfig
) -> dict[str, list[str]]:
    arms: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        arms[(str(row["stratum_id"]), str(row["root_seed_id"]))].add(str(row["arm"]))
    return {
        stratum: sorted(
            root
            for (observed_stratum, root), observed_arms in arms.items()
            if observed_stratum == stratum and observed_arms == set(study.arms)
        )
        for stratum in ESTIMATOR_STRATA
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
        values.append(math.nan if left is None or right is None else float(left) - float(right))
    return np.asarray(values, dtype=np.float64)


def _bootstrap_primary(
    rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    *,
    replicates: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    bootstrap_replicates = study.bootstrap_replicates if replicates is None else replicates
    bootstrap_seed = study.bootstrap_seed if seed is None else seed
    if bootstrap_replicates <= 0:
        raise ValueError("bootstrap replicates must be positive")
    root_ids = _complete_root_ids(rows, study)
    differences = {
        (stratum, endpoint): _paired_values(
            rows,
            root_ids[stratum],
            stratum,
            "PD",
            "D",
            endpoint,
        )
        for stratum in ESTIMATOR_STRATA
        for endpoint in PRIMARY_BOOTSTRAP_ENDPOINTS
    }
    if any(len(root_ids[stratum]) == 0 for stratum in ESTIMATOR_STRATA):
        raise ValueError("every stratum requires at least one complete block")
    distributions = {
        endpoint: np.zeros(bootstrap_replicates, dtype=np.float64)
        for endpoint in PRIMARY_BOOTSTRAP_ENDPOINTS
    }
    points = {
        endpoint: {
            stratum: float(np.mean(differences[(stratum, endpoint)]))
            for stratum in ESTIMATOR_STRATA
        }
        for endpoint in PRIMARY_BOOTSTRAP_ENDPOINTS
    }
    rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([bootstrap_seed])))
    for stratum in ESTIMATOR_STRATA:
        n = len(root_ids[stratum])
        for start in range(0, bootstrap_replicates, 250):
            stop = min(bootstrap_replicates, start + 250)
            indices = rng.integers(0, n, size=(stop - start, n), dtype=np.int32)
            for endpoint in PRIMARY_BOOTSTRAP_ENDPOINTS:
                sampled = differences[(stratum, endpoint)][indices]
                distributions[endpoint][start:stop] += (
                    np.mean(sampled, axis=1) * study.stratum_weight
                )
    output: dict[str, Any] = {}
    for endpoint, values in distributions.items():
        output[endpoint] = {
            "estimate": sum(points[endpoint].values()) * study.stratum_weight,
            "two_sided_95_interval": [
                float(np.quantile(values, 0.025)),
                float(np.quantile(values, 0.975)),
            ],
            "one_sided_97_5_lower": float(np.quantile(values, 0.025)),
            "one_sided_97_5_upper": float(np.quantile(values, 0.975)),
            "bootstrap_replicates": bootstrap_replicates,
            "bootstrap_seed": bootstrap_seed,
            "stratum_estimates": points[endpoint],
        }
    return output


def _arm_summaries(rows: list[dict[str, Any]], study: ConfirmatoryConfig) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for stratum in ESTIMATOR_STRATA:
        output[stratum] = {}
        for arm in study.arms:
            selected = [
                row for row in rows if row["stratum_id"] == stratum and row["arm"] == arm
            ]
            output[stratum][arm] = {
                "n": len(selected),
                "analysis_hazard": {
                    "events": sum(bool(row["analysis_hazard"]) for row in selected),
                    "risk": (
                        float(np.mean([bool(row["analysis_hazard"]) for row in selected]))
                        if selected
                        else None
                    ),
                },
                "sustained_success": {
                    "events": sum(bool(row["sustained_success"]) for row in selected),
                    "risk": (
                        float(np.mean([bool(row["sustained_success"]) for row in selected]))
                        if selected
                        else None
                    ),
                },
                "failure_classes": dict(
                    Counter(
                        str(row["failure_class"])
                        for row in selected
                        if row.get("failure_class") is not None
                    )
                ),
            }
    return output


def _weighted_arm_risk(summaries: dict[str, Any], arm: str, endpoint: str) -> float:
    return sum(
        float(summaries[stratum][arm][endpoint]["risk"]) / len(ESTIMATOR_STRATA)
        for stratum in ESTIMATOR_STRATA
    )


def _discordant_counts(
    rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    endpoint: str,
    arm_a: str,
    arm_b: str,
    strata: tuple[str, ...],
) -> tuple[int, int]:
    roots = _complete_root_ids(rows, study)
    a1_b0 = 0
    a0_b1 = 0
    for stratum in strata:
        differences = _paired_values(
            rows,
            roots[stratum],
            stratum,
            arm_a,
            arm_b,
            endpoint,
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


def _sign_randomization_p(differences: np.ndarray, simulations: int, seed: int) -> float:
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
        signs = rng.integers(0, 2, size=(count, len(values)), dtype=np.int8) * 2 - 1
        extreme += int(np.sum(np.mean(signs * values, axis=1) <= observed))
    return (extreme + 1.0) / (simulations + 1.0)


def _holm_adjust(raw: dict[str, float], alpha: float) -> dict[str, Any]:
    ordered = sorted(raw, key=raw.get)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, name in enumerate(ordered):
        running = max(running, (len(ordered) - rank) * raw[name])
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
    rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    *,
    randomization_replicates: int | None = None,
    randomization_seed: int | None = None,
) -> dict[str, Any]:
    h3 = _discordant_counts(
        rows, study, "analysis_hazard", "PS", "D", ESTIMATOR_STRATA
    )
    h4 = _discordant_counts(
        rows, study, "analysis_hazard", "PD", "PS", ESTIMATOR_STRATA
    )
    h5a = _discordant_counts(
        rows, study, "recovery_favorable_180", "PD", "D", FAULTED_STRATA
    )
    roots = _complete_root_ids(rows, study)
    h5b_values = np.concatenate(
        [
            _paired_values(
                rows,
                roots[stratum],
                stratum,
                "PD",
                "D",
                "restricted_time_unrecovered_s_180",
            )
            for stratum in FAULTED_STRATA
        ]
    )
    simulations = (
        study.secondary_randomization_replicates
        if randomization_replicates is None
        else randomization_replicates
    )
    seed = (
        study.secondary_randomization_seed
        if randomization_seed is None
        else randomization_seed
    )
    raw = {
        "H3_PS_minus_D_analysis_hazard": _one_sided_discordance_p(
            *h3, beneficial_direction="lower"
        ),
        "H4_PD_minus_PS_analysis_hazard": _one_sided_discordance_p(
            *h4, beneficial_direction="lower"
        ),
        "H5a_PD_minus_D_recovery_favorable": _one_sided_discordance_p(
            *h5a, beneficial_direction="higher"
        ),
        "H5b_PD_minus_D_restricted_time": _sign_randomization_p(
            h5b_values,
            simulations,
            seed,
        ),
    }
    return {
        "family": "H3/H4/H5a/H5b fixed one-sided Holm family",
        "family_alpha": study.secondary_holm_alpha,
        "tests": _holm_adjust(raw, study.secondary_holm_alpha),
        "discordant_counts": {
            "H3": {"a1_b0": h3[0], "a0_b1": h3[1]},
            "H4": {"a1_b0": h4[0], "a0_b1": h4[1]},
            "H5a": {"a1_b0": h5a[0], "a0_b1": h5a[1]},
        },
        "H5b_randomization": {"draws": simulations, "seed": seed},
    }


def _primary_sensitivity_points(
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    study: ConfirmatoryConfig,
    physical: dict[str, Any],
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
    for stratum in ESTIMATOR_STRATA:
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
            protected = selected.get((stratum, root, "PD"))
            direct = selected.get((stratum, root, "D"))
            protected_hazard = bool(protected["analysis_hazard"]) if protected else True
            direct_hazard = bool(direct["analysis_hazard"]) if direct else False
            protected_success = bool(protected["sustained_success"]) if protected else False
            direct_success = bool(direct["sustained_success"]) if direct else True
            hazard_values.append(float(protected_hazard) - float(direct_hazard))
            success_values.append(float(protected_success) - float(direct_success))
            if protected is not None and direct is not None:
                available_h.append(float(protected_hazard) - float(direct_hazard))
                available_s.append(float(protected_success) - float(direct_success))
        worst_hazard += float(np.mean(hazard_values)) * study.stratum_weight
        worst_success += float(np.mean(success_values)) * study.stratum_weight
        available_counts[stratum] = len(available_h)
        if available_h:
            available_hazard += float(np.mean(available_h)) * study.stratum_weight
            available_success += float(np.mean(available_s)) * study.stratum_weight
    result = {
        "worst_case_missing_primary_cells": {
            "analysis_hazard_risk_difference": worst_hazard,
            "sustained_success_risk_difference": worst_success,
            "rule": "missing PD adverse; missing D favorable to D",
        },
        "physical_hazard_only": {
            "estimate": physical["estimate"],
            "two_sided_95_interval": physical["two_sided_95_interval"],
        },
        "all_available_D_PD_pairs": {
            "analysis_hazard_risk_difference": available_hazard,
            "sustained_success_risk_difference": available_success,
            "pairs_by_stratum": available_counts,
        },
    }
    if tuple(result) != study.primary_sensitivities:
        raise RuntimeError("primary sensitivity registry drifted")
    return result


def analyze_confirmatory(
    study: ConfirmatoryConfig,
    rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
    integrity: dict[str, Any],
    output_path: str | Path,
    qc_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cells = validate_episode_cells(rows, seed_rows, study)
    contrasts = _bootstrap_primary(rows, study)
    summaries = _arm_summaries(rows, study)
    hazard = contrasts["analysis_hazard"]
    success = contrasts["sustained_success"]
    physical = contrasts["physical_hazard_observed"]
    h1_pass = hazard["two_sided_95_interval"][1] < 0.0
    h2_pass = bool(
        h1_pass and success["one_sided_97_5_lower"] > study.h2_noninferiority_margin
    )
    direct_risk = _weighted_arm_risk(summaries, "D", "analysis_hazard")
    protected_risk = _weighted_arm_risk(summaries, "PD", "analysis_hazard")
    relative_reduction = (
        (direct_risk - protected_risk) / direct_risk if direct_risk > 0.0 else None
    )
    effect_thresholds_pass = bool(
        hazard["estimate"] <= -study.h1_minimum_absolute_reduction
        and relative_reduction is not None
        and relative_reduction >= study.h1_minimum_relative_reduction
    )
    validity_pass = bool(
        integrity.get("passed")
        and cells["structural_valid"]
        and cells["completeness_passed"]
    )
    favorable = bool(
        validity_pass and h1_pass and h2_pass and effect_thresholds_pass
    )
    decision = (
        "inconclusive_invalid"
        if not validity_pass
        else "favorable"
        if favorable
        else "inconclusive"
    )
    analysis = {
        "schema_version": study.schema_version,
        "study_phase": "confirmatory",
        "decision": decision,
        "estimand_registry": {
            "independent_unit": "stratum by root-seed complete four-arm block",
            "primary_contrast": "PD-D",
            "H1_endpoint": "adverse-coded analysis_hazard",
            "H2_endpoint": "sustained_success",
            "stratum_weight": study.stratum_weight,
            "resampling": "stratified paired complete-block percentile bootstrap",
        },
        "counts": cells,
        "arm_summaries": summaries,
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
        "favorable_classification": {
            "validity": validity_pass,
            "H1": h1_pass,
            "H2": h2_pass,
            "absolute_and_relative_effect": effect_thresholds_pass,
            "relative_hazard_reduction": relative_reduction,
        },
        "secondary_family": _secondary_tests(rows, study),
        "primary_sensitivities": _primary_sensitivity_points(
            rows,
            seed_rows,
            study,
            physical,
        ),
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
