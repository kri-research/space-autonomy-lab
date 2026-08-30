from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import beta, norm

from .config import ARMS, ESTIMATOR_STRATA, Experiment003Config

BINARY_ENDPOINTS = (
    "analysis_hazard",
    "physical_hazard_observed",
    "collision",
    "sustained_success",
    "recovery_favorable_180",
)
ALLOWED_FAILURE_CLASSES = {
    "INVALID_ACTION",
    "NUMERICAL_FAILURE",
    "ESTIMATOR_DIVERGED",
}


def load_episode_rows(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def validate_cells(rows: list[dict[str, Any]], config: Experiment003Config) -> dict[str, Any]:
    counts: Counter[tuple[str, str, str]] = Counter()
    blocks: dict[tuple[str, str], set[str]] = defaultdict(set)
    unknown_failures: Counter[str] = Counter()
    for row in rows:
        key = (str(row.get("stratum_id")), str(row.get("root_seed_id")), str(row.get("arm")))
        counts[key] += 1
        blocks[key[:2]].add(key[2])
        failure = row.get("failure_class")
        if failure is not None and failure not in ALLOWED_FAILURE_CLASSES:
            unknown_failures[str(failure)] += 1
    duplicate_cells = sum(value - 1 for value in counts.values() if value > 1)
    complete_blocks = sum(arms == set(ARMS) for arms in blocks.values())
    incomplete = [
        {"stratum_id": key[0], "root_seed_id": key[1], "arms": sorted(arms)}
        for key, arms in blocks.items()
        if arms != set(ARMS)
    ]
    expected_keys = {
        (stratum, f"pilot003:{stratum}:{replicate:04d}", arm)
        for stratum in ESTIMATOR_STRATA
        for replicate in range(config.pilot_roots_per_stratum)
        for arm in ARMS
    }
    observed_keys = set(counts)
    missing = expected_keys - observed_keys
    extra = observed_keys - expected_keys
    passed = bool(
        len(rows) == config.pilot_episodes
        and not duplicate_cells
        and not missing
        and not extra
        and complete_blocks == config.pilot_blocks
        and not unknown_failures
    )
    return {
        "passed": passed,
        "rows": len(rows),
        "unique_cells": len(observed_keys),
        "expected_cells": config.pilot_episodes,
        "complete_blocks": complete_blocks,
        "expected_blocks": config.pilot_blocks,
        "duplicate_cells": duplicate_cells,
        "missing_cells": len(missing),
        "extra_cells": len(extra),
        "incomplete_blocks_preview": incomplete[:20],
        "unknown_failure_classes": dict(unknown_failures),
    }


def _selected(rows: list[dict[str, Any]]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {
        (str(row["stratum_id"]), str(row["root_seed_id"]), str(row["arm"])): row
        for row in rows
    }


def _arm_summaries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for stratum in ESTIMATOR_STRATA:
        result[stratum] = {}
        for arm in ARMS:
            selected = [
                row for row in rows if row["stratum_id"] == stratum and row["arm"] == arm
            ]
            binary = {
                endpoint: float(
                    np.mean(
                        [
                            float(bool(row[endpoint]))
                            for row in selected
                            if row.get(endpoint) is not None
                        ]
                    )
                )
                for endpoint in BINARY_ENDPOINTS
                if any(row.get(endpoint) is not None for row in selected)
            }
            result[stratum][arm] = {
                "episodes": len(selected),
                "risks": binary,
                "failure_classes": dict(
                    Counter(
                        str(row["failure_class"])
                        for row in selected
                        if row.get("failure_class") is not None
                    )
                ),
                "mean_fallback_duty_cycle": float(
                    np.mean([float(row["fallback_duty_cycle"]) for row in selected])
                ),
                "mean_primary_max_abs_range_error_m": float(
                    np.mean(
                        [float(row["primary_max_abs_range_error_m"]) for row in selected]
                    )
                ),
            }
    return result


def _paired_nuisance(
    rows: list[dict[str, Any]],
    endpoint: str,
    config: Experiment003Config,
) -> dict[str, Any]:
    selected = _selected(rows)
    result: dict[str, Any] = {}
    for stratum in ESTIMATOR_STRATA:
        differences: list[int] = []
        for replicate in range(config.pilot_roots_per_stratum):
            root = f"pilot003:{stratum}:{replicate:04d}"
            direct = selected[(stratum, root, "D")]
            protected = selected[(stratum, root, "PD")]
            differences.append(int(bool(protected[endpoint])) - int(bool(direct[endpoint])))
        negative = differences.count(-1)
        positive = differences.count(1)
        discordant = negative + positive
        total = len(differences)
        upper = (
            1.0
            if discordant == total
            else float(beta.ppf(0.95, discordant + 1, total - discordant))
        )
        result[stratum] = {
            "pairs": total,
            "PD_favorable_discordances": negative,
            "PD_adverse_discordances": positive,
            "discordance": discordant,
            "discordance_rate": discordant / total,
            "discordance_one_sided_95_upper": upper,
            "paired_risk_difference": float(np.mean(differences)),
        }
    return result


def _monte_carlo_lower(successes: int, simulations: int) -> float:
    if successes == 0:
        return 0.0
    return float(beta.ppf(0.025, successes, simulations - successes + 1))


def _simulated_test_pass(
    rng: np.random.Generator,
    roots_per_stratum: int,
    discordance_bounds: list[float],
    difference: float,
    margin: float,
    simulations: int,
    alternative: str,
) -> np.ndarray:
    estimates = np.zeros(simulations, dtype=np.float64)
    variance = np.zeros(simulations, dtype=np.float64)
    weight = 1.0 / len(discordance_bounds)
    for bound in discordance_bounds:
        q = max(abs(difference), min(1.0, bound))
        negative_probability = 0.5 * (q - difference)
        positive_probability = 0.5 * (q + difference)
        probabilities = [negative_probability, positive_probability, 1.0 - q]
        draws = rng.multinomial(roots_per_stratum, probabilities, size=simulations)
        mean = (draws[:, 1] - draws[:, 0]) / roots_per_stratum
        sum_squares = draws[:, 0] + draws[:, 1]
        sample_variance = (sum_squares - roots_per_stratum * mean**2) / max(
            1, roots_per_stratum - 1
        )
        estimates += weight * mean
        variance += weight**2 * sample_variance / roots_per_stratum
    standard_error = np.sqrt(np.maximum(0.0, variance))
    critical = float(norm.ppf(0.975))
    if alternative == "less":
        return estimates + critical * standard_error < margin
    if alternative == "greater":
        return estimates - critical * standard_error > margin
    raise ValueError("unknown planning alternative")


def resolve_future_sample_size(
    config: Experiment003Config,
    hazard_nuisance: dict[str, Any],
    success_nuisance: dict[str, Any],
) -> dict[str, Any]:
    hazard_bounds = [
        float(hazard_nuisance[stratum]["discordance_one_sided_95_upper"])
        for stratum in ESTIMATOR_STRATA
    ]
    success_bounds = [
        float(success_nuisance[stratum]["discordance_one_sided_95_upper"])
        for stratum in ESTIMATOR_STRATA
    ]
    rows = []
    selected: int | None = None
    simulations = config.power_simulation_replicates
    for candidate in config.future_candidate_roots_per_stratum:
        hazard_rng = np.random.Generator(
            np.random.PCG64DXSM(
                np.random.SeedSequence([config.power_simulation_seed, candidate, 1])
            )
        )
        success_rng = np.random.Generator(
            np.random.PCG64DXSM(
                np.random.SeedSequence([config.power_simulation_seed, candidate, 2])
            )
        )
        hazard_pass = _simulated_test_pass(
            hazard_rng,
            candidate,
            hazard_bounds,
            -config.h1_minimum_absolute_reduction,
            0.0,
            simulations,
            "less",
        )
        success_pass = _simulated_test_pass(
            success_rng,
            candidate,
            success_bounds,
            0.0,
            config.h2_noninferiority_margin,
            simulations,
            "greater",
        )
        h1_successes = int(np.sum(hazard_pass))
        h2_successes = int(np.sum(success_pass))
        h1_power = h1_successes / simulations
        h2_power = h2_successes / simulations
        h1_lower = _monte_carlo_lower(h1_successes, simulations)
        h2_lower = _monte_carlo_lower(h2_successes, simulations)
        passes = bool(
            h1_lower >= config.confirmatory_power_target
            and h2_lower >= config.confirmatory_power_target
        )
        rows.append(
            {
                "roots_per_stratum": candidate,
                "total_roots": candidate * len(ESTIMATOR_STRATA),
                "planned_episodes": candidate * len(ESTIMATOR_STRATA) * len(ARMS),
                "H1_marginal_power": h1_power,
                "H1_monte_carlo_95_lower": h1_lower,
                "H2_marginal_power": h2_power,
                "H2_monte_carlo_95_lower": h2_lower,
                "passes": passes,
            }
        )
        if passes and selected is None:
            selected = candidate
    return {
        "method": (
            "paired risk-difference normal-bound simulation using conservative per-stratum "
            "discordance upper bounds; fixed H1=-0.02 and H2=0 alternatives"
        ),
        "simulations": simulations,
        "seed": config.power_simulation_seed,
        "target_lower_bound": config.confirmatory_power_target,
        "candidate_results": rows,
        "selected_roots_per_stratum": selected,
        "observed_pilot_effect_used_as_alternative": False,
        "marginal_not_joint_power": True,
    }


def analyze_pilot(
    rows: list[dict[str, Any]],
    config: Experiment003Config,
    integrity: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    cells = validate_cells(rows, config)
    hazard_nuisance = (
        _paired_nuisance(rows, "analysis_hazard", config) if cells["passed"] else {}
    )
    success_nuisance = (
        _paired_nuisance(rows, "sustained_success", config) if cells["passed"] else {}
    )
    power = (
        resolve_future_sample_size(config, hazard_nuisance, success_nuisance)
        if cells["passed"]
        else {"selected_roots_per_stratum": None}
    )
    known_failures = all(
        row.get("failure_class") is None
        or row.get("failure_class") in ALLOWED_FAILURE_CLASSES
        for row in rows
    )
    progression = bool(
        cells["passed"]
        and integrity.get("passed")
        and known_failures
        and power.get("selected_roots_per_stratum") is not None
    )
    qc = {
        "schema_version": config.schema_version,
        "overall_passed": bool(cells["passed"] and integrity.get("passed") and known_failures),
        "cell_validation": cells,
        "integrity": integrity,
        "failure_classes_all_prespecified": known_failures,
    }
    analysis = {
        "schema_version": config.schema_version,
        "phase": "design_validation_pilot",
        "primary_hypotheses_tested": False,
        "primary_effect_direction_used_for_progression": False,
        "inferential_unit": "stratum by root-seed four-arm block",
        "stratum_weight": 1.0 / len(ESTIMATOR_STRATA),
        "arm_summaries": _arm_summaries(rows),
        "paired_nuisance": {
            "analysis_hazard": hazard_nuisance,
            "sustained_success": success_nuisance,
        },
        "future_sample_size_resolution": power,
        "progression": {
            "passed": progression,
            "decision": (
                "ready_to_freeze_separate_confirmatory_design"
                if progression
                else "do_not_progress"
            ),
        },
    }
    return analysis, qc


def write_report(analysis: dict[str, Any], path: str | Path) -> None:
    progression = analysis["progression"]
    selected = analysis["future_sample_size_resolution"].get("selected_roots_per_stratum")
    text = "\n".join(
        [
            "# Experiment 003 design-validation pilot",
            "",
            "> This pilot validates design and nuisance information. It does not test H1 or H2.",
            "",
            f"- Progression: **{progression['decision']}**",
            f"- Primary hypotheses tested: `{analysis['primary_hypotheses_tested']}`",
            f"- Selected future roots per stratum: `{selected}`",
            "- Observed effect direction was not a progression input.",
            "",
        ]
    )
    Path(path).write_text(text, encoding="utf-8")
