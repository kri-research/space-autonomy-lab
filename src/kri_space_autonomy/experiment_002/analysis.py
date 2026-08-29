from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .config import ARMS, PILOT_STRATA, PilotConfig
from .seeds import sha256_bytes

BINARY_ENDPOINTS = (
    "analysis_hazard",
    "physical_hazard_observed",
    "collision",
    "sustained_success",
)
FAULTED_BINARY_ENDPOINTS = ("recovery_favorable_180",)
CONTINUOUS_ENDPOINTS = (
    "restricted_time_unrecovered_s_180",
    "minimum_range_m",
    "propellant_used_fraction",
    "fallback_duty_cycle",
    "goal_dwell_final60_fraction",
)
CONTRASTS = (("PD", "D"), ("PS", "D"), ("PD", "PS"))


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def validate_episode_cells(rows: list[dict[str, Any]], config: PilotConfig) -> dict[str, Any]:
    keys = [(row["stratum_id"], row["root_seed_id"], row["arm"]) for row in rows]
    counts = Counter(row["stratum_id"] for row in rows)
    block_arms: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        block_arms[(row["stratum_id"], row["root_seed_id"])].add(row["arm"])
    incomplete = [key for key, arms in block_arms.items() if arms != set(ARMS)]
    return {
        "valid": (
            len(rows) == config.planned_episodes
            and len(set(keys)) == config.planned_episodes
            and all(
                counts[stratum] == config.seeds_per_stratum * len(ARMS) for stratum in PILOT_STRATA
            )
            and not incomplete
        ),
        "episode_rows": len(rows),
        "unique_episode_cells": len(set(keys)),
        "stratum_episode_counts": dict(counts),
        "complete_blocks": len(block_arms) - len(incomplete),
        "incomplete_blocks": len(incomplete),
    }


def _paired_arrays(
    rows: list[dict[str, Any]], endpoint: str, arm_a: str, arm_b: str, stratum: str
) -> tuple[np.ndarray, np.ndarray]:
    selected = {
        (row["root_seed_id"], row["arm"]): row for row in rows if row["stratum_id"] == stratum
    }
    root_ids = sorted({root for root, _ in selected})
    a = np.array([selected[(root, arm_a)][endpoint] for root in root_ids], dtype=np.float64)
    b = np.array([selected[(root, arm_b)][endpoint] for root in root_ids], dtype=np.float64)
    return a, b


def _bootstrap_all(
    rows: list[dict[str, Any]], config: PilotConfig
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, float]]]:
    variable_keys = []
    for arm_a, arm_b in CONTRASTS:
        for endpoint in (*BINARY_ENDPOINTS, *FAULTED_BINARY_ENDPOINTS, *CONTINUOUS_ENDPOINTS):
            variable_keys.append(f"{arm_a}-{arm_b}:{endpoint}")
    bootstrap = {
        key: np.zeros(config.bootstrap_replicates, dtype=np.float64) for key in variable_keys
    }
    stratum_points: dict[str, dict[str, float]] = {key: {} for key in variable_keys}
    rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([config.bootstrap_seed])))
    chunk_size = 1000
    for stratum in PILOT_STRATA:
        differences: dict[str, np.ndarray] = {}
        for arm_a, arm_b in CONTRASTS:
            for endpoint in (*BINARY_ENDPOINTS, *FAULTED_BINARY_ENDPOINTS, *CONTINUOUS_ENDPOINTS):
                key = f"{arm_a}-{arm_b}:{endpoint}"
                if (
                    endpoint in FAULTED_BINARY_ENDPOINTS
                    or endpoint == "restricted_time_unrecovered_s_180"
                ):
                    if stratum == "P0_nominal":
                        continue
                a, b = _paired_arrays(rows, endpoint, arm_a, arm_b, stratum)
                differences[key] = a - b
                stratum_points[key][stratum] = float(np.nanmean(a - b))
        for start in range(0, config.bootstrap_replicates, chunk_size):
            stop = min(config.bootstrap_replicates, start + chunk_size)
            indices = rng.integers(
                0,
                config.seeds_per_stratum,
                size=(stop - start, config.seeds_per_stratum),
                dtype=np.int32,
            )
            for key, values in differences.items():
                bootstrap[key][start:stop] += np.nanmean(values[indices], axis=1) / (
                    5.0
                    if key.split(":", 1)[1]
                    in (*FAULTED_BINARY_ENDPOINTS, "restricted_time_unrecovered_s_180")
                    else 6.0
                )
    return bootstrap, stratum_points


def _binomial_cdf(x: int, n: int, probability: float) -> float:
    return sum(
        math.comb(n, k) * probability**k * (1.0 - probability) ** (n - k) for k in range(x + 1)
    )


def exact_one_sided_upper(events: int, n: int, alpha: float = 0.05) -> float:
    if events >= n:
        return 1.0
    if events == 0:
        return 1.0 - alpha ** (1.0 / n)
    left, right = events / n, 1.0
    for _ in range(70):
        midpoint = 0.5 * (left + right)
        if _binomial_cdf(events, n, midpoint) > alpha:
            left = midpoint
        else:
            right = midpoint
    return 0.5 * (left + right)


def _arm_summaries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for stratum in PILOT_STRATA:
        output[stratum] = {}
        for arm in ARMS:
            selected = [row for row in rows if row["stratum_id"] == stratum and row["arm"] == arm]
            summary = {"n": len(selected)}
            for endpoint in BINARY_ENDPOINTS:
                events = sum(bool(row[endpoint]) for row in selected)
                summary[endpoint] = {
                    "events": events,
                    "risk": events / len(selected),
                }
                if endpoint == "collision":
                    summary[endpoint]["one_sided_95_upper"] = exact_one_sided_upper(
                        events, len(selected)
                    )
            for endpoint in CONTINUOUS_ENDPOINTS:
                values = np.array(
                    [row[endpoint] for row in selected if row[endpoint] is not None],
                    dtype=np.float64,
                )
                summary[endpoint] = {
                    "mean": float(np.mean(values)) if len(values) else None,
                    "median": float(np.median(values)) if len(values) else None,
                    "p05": float(np.quantile(values, 0.05)) if len(values) else None,
                    "p95": float(np.quantile(values, 0.95)) if len(values) else None,
                }
            summary["recovery_states"] = dict(Counter(row["recovery_state"] for row in selected))
            output[stratum][arm] = summary
    return output


def _contrast_estimates(
    rows: list[dict[str, Any]],
    config: PilotConfig,
    bootstrap: dict[str, np.ndarray],
    stratum_points: dict[str, dict[str, float]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm_a, arm_b in CONTRASTS:
        contrast = f"{arm_a}-{arm_b}"
        output[contrast] = {}
        for endpoint in (*BINARY_ENDPOINTS, *FAULTED_BINARY_ENDPOINTS, *CONTINUOUS_ENDPOINTS):
            key = f"{contrast}:{endpoint}"
            values = bootstrap[key]
            applicable = (
                5
                if endpoint in (*FAULTED_BINARY_ENDPOINTS, "restricted_time_unrecovered_s_180")
                else 6
            )
            point = sum(stratum_points[key].values()) / applicable
            entry: dict[str, Any] = {
                "estimate": point,
                "ci95_percentile": [
                    float(np.nanquantile(values, 0.025)),
                    float(np.nanquantile(values, 0.975)),
                ],
                "bootstrap_replicates": config.bootstrap_replicates,
                "bootstrap_seed": config.bootstrap_seed,
                "interval_status": "estimation_only_pilot",
                "stratum_estimates": stratum_points[key],
            }
            if endpoint in BINARY_ENDPOINTS or endpoint in FAULTED_BINARY_ENDPOINTS:
                discordance = {}
                for stratum in stratum_points[key]:
                    a, b = _paired_arrays(rows, endpoint, arm_a, arm_b, stratum)
                    discordance[stratum] = {
                        "a1_b0": int(np.sum((a == 1) & (b == 0))),
                        "a0_b1": int(np.sum((a == 0) & (b == 1))),
                    }
                entry["discordant_pairs"] = discordance
                if sum(sum(item.values()) for item in discordance.values()) == 0:
                    entry["flag"] = "insufficient_discordance"
            output[contrast][endpoint] = entry
    return output


def _planning_power(
    rows: list[dict[str, Any]], config: PilotConfig, simulations: int = 20_000
) -> dict[str, Any]:
    rng = np.random.Generator(np.random.PCG64DXSM(np.random.SeedSequence([2002, 276])))
    nuisance = {}
    for stratum in PILOT_STRATA:
        pd_h, d_h = _paired_arrays(rows, "analysis_hazard", "PD", "D", stratum)
        pd_s, d_s = _paired_arrays(rows, "sustained_success", "PD", "D", stratum)
        nuisance[stratum] = {
            "hazard_discordance_upper95": exact_one_sided_upper(
                int(np.sum(pd_h != d_h)), len(pd_h)
            ),
            "success_discordance_upper95": exact_one_sided_upper(
                int(np.sum(pd_s != d_s)), len(pd_s)
            ),
            "direct_hazard_risk": float(np.mean(d_h)),
        }
    candidates = {}
    for n in (1000, 1500, 2000):
        h_estimate = np.zeros(simulations)
        h_variance = np.zeros(simulations)
        s_estimate = np.zeros(simulations)
        s_variance = np.zeros(simulations)
        for stratum in PILOT_STRATA:
            values = nuisance[stratum]
            hazard_delta = -max(0.02, 0.25 * values["direct_hazard_risk"])
            q_h = min(0.99, max(values["hazard_discordance_upper95"], abs(hazard_delta) + 0.001))
            p_h_positive = (q_h + hazard_delta) / 2.0
            p_h_negative = (q_h - hazard_delta) / 2.0
            h_counts = rng.multinomial(
                n,
                [max(0.0, p_h_positive), max(0.0, p_h_negative), 1.0 - q_h],
                size=simulations,
            )
            h_diff = (h_counts[:, 0] - h_counts[:, 1]) / n
            h_q = (h_counts[:, 0] + h_counts[:, 1]) / n
            h_estimate += h_diff / 6.0
            h_variance += np.maximum(0.0, h_q - h_diff**2) / n / 36.0

            q_s = min(0.99, max(values["success_discordance_upper95"], 0.001))
            s_counts = rng.multinomial(
                n,
                [q_s / 2.0, q_s / 2.0, 1.0 - q_s],
                size=simulations,
            )
            s_diff = (s_counts[:, 0] - s_counts[:, 1]) / n
            s_q = (s_counts[:, 0] + s_counts[:, 1]) / n
            s_estimate += s_diff / 6.0
            s_variance += np.maximum(0.0, s_q - s_diff**2) / n / 36.0
        h_pass = h_estimate + 1.96 * np.sqrt(h_variance) < 0.0
        s_pass = s_estimate - 1.96 * np.sqrt(s_variance) > -0.03
        joint = h_pass & s_pass
        candidates[str(n)] = {
            "h1_power": float(np.mean(h_pass)),
            "h2_power": float(np.mean(s_pass)),
            "joint_power_independent_endpoint_simulation": float(np.mean(joint)),
            "monte_carlo_se_joint": float(
                math.sqrt(np.mean(joint) * (1.0 - np.mean(joint)) / simulations)
            ),
        }
    return {
        "method": (
            "requirements-based paired multinomial simulation using 95% upper bounds on "
            "pilot discordance; hazard alternative is max(2 points, 25% of direct risk); "
            "success alternative is zero risk difference against -3 point margin"
        ),
        "simulations": simulations,
        "nuisance": nuisance,
        "candidate_confirmatory_seeds_per_stratum": candidates,
        "limitation": (
            "P7 combined-fault nuisance is absent from this six-stratum pilot; these values "
            "cannot by themselves justify the separate eight-stratum confirmatory design."
        ),
    }


def analyze_pilot(
    episodes_path: str | Path,
    config: PilotConfig,
    metadata: dict[str, Any],
    qc: dict[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    rows = _read_jsonl(episodes_path)
    cell_validation = validate_episode_cells(rows, config)
    bootstrap, stratum_points = _bootstrap_all(rows, config)
    power = _planning_power(rows, config)
    failed_validity = [
        check["id"]
        for check in qc["checks"]
        if check["category"] == "validity" and not check["passed"]
    ]
    information_pass = any(
        item["h1_power"] >= 0.95 and item["h2_power"] >= 0.95
        for item in power["candidate_confirmatory_seeds_per_stratum"].values()
    )
    # The absent combined-fault stratum is deliberately not guessed from pilot data.
    information_pass = False
    if failed_validity or not cell_validation["valid"]:
        progression = "do_not_proceed"
    elif not information_pass:
        progression = "redesign_required"
    else:
        progression = "proceed_to_confirmatory"
    analysis = {
        "metadata": {
            "schema_version": config.schema_version,
            "study_phase": "pilot_feasibility_design_validation",
            "controller_effect_interpretation": "estimation_only_not_confirmatory",
            "fixed_stratum_weights": {stratum: 1.0 / 6.0 for stratum in PILOT_STRATA},
            "mixed_component_weights": {
                stratum: {"range_bias": 1.0 / 12.0, "dropout": 1.0 / 12.0}
                for stratum in PILOT_STRATA[1:4]
            },
            **metadata,
        },
        "estimand_registry": {
            "unit": "root-seed four-arm block",
            "primary_contrast": "PD-D",
            "binary_effect": "paired risk difference A-B",
            "continuous_effect": "paired mean difference A-B",
            "resampling": "within-stratum paired block percentile bootstrap",
            "missing_failure_coding": (
                "controller/invalid/numerical failures adverse; physical and "
                "analysis hazard separate"
            ),
            "multiplicity": "pilot intervals estimation-only; no favorability decision",
        },
        "counts": cell_validation,
        "arm_summaries": _arm_summaries(rows),
        "contrast_estimates": _contrast_estimates(rows, config, bootstrap, stratum_points),
        "failure_classes": dict(
            Counter(row["failure_class"] for row in rows if row["failure_class"])
        ),
        "qc_checks": qc["checks"],
        "power_scenarios": power,
        "progression": {
            "decision": progression,
            "failed_validity_gate_ids": failed_validity,
            "information_gate_passed": information_pass,
            "reason": (
                "Pilot validity failures require correction before confirmation."
                if failed_validity
                else "Eight-stratum confirmatory power cannot be approved without a "
                "prespecified combined-fault nuisance model."
            ),
            "controller_favorability_used": False,
        },
        "deviations": qc.get("deviations", []),
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return analysis


def write_markdown_report(analysis: dict[str, Any], output_path: str | Path) -> None:
    summaries = analysis["arm_summaries"]
    contrast = analysis["contrast_estimates"]["PD-D"]
    lines = [
        "# Experiment 002 design-validation pilot",
        "",
        "> **Evidence boundary:** feasibility/design-validation evidence for the frozen synthetic ",
        "> six-stratum generator only. This is not confirmatory superiority or "
        "> flight-safety evidence.",
        "",
        "## Campaign",
        "",
        f"- Complete blocks: {analysis['counts']['complete_blocks']:,} / 2,400",
        f"- Episode records: {analysis['counts']['episode_rows']:,} / 9,600",
        "- Fixed weights: 1/6 per stratum; P1–P3 each contain exactly 200 bias and "
        "200 dropout blocks.",
        "- Bootstrap: 50,000 paired within-stratum block replicates.",
        "",
        "## Arm outcomes by stratum",
        "",
        "| Stratum | Arm | Hazard | Success | Collision | Median fallback duty |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for stratum in PILOT_STRATA:
        for arm in ARMS:
            item = summaries[stratum][arm]
            lines.append(
                f"| {stratum} | {arm} | {item['analysis_hazard']['risk']:.3f} | "
                f"{item['sustained_success']['risk']:.3f} | {item['collision']['risk']:.3f} | "
                f"{item['fallback_duty_cycle']['median']:.3f} |"
            )
    hazard = contrast["analysis_hazard"]
    success = contrast["sustained_success"]
    lines.extend(
        [
            "",
            "## Primary pilot estimates (PD − D)",
            "",
            f"- Analysis-hazard risk difference: **{hazard['estimate']:.4f}** "
            f"(estimation-only 95% bootstrap interval {hazard['ci95_percentile'][0]:.4f} to "
            f"{hazard['ci95_percentile'][1]:.4f}).",
            f"- Sustained-success risk difference: **{success['estimate']:.4f}** "
            f"(estimation-only 95% bootstrap interval {success['ci95_percentile'][0]:.4f} to "
            f"{success['ci95_percentile'][1]:.4f}).",
            "- PS−D and PD−PS mediation/channel estimates and all stratum-specific "
            "values are in `analysis.json`.",
            "",
            "## Validation and progression",
            "",
            f"- Progression classification: **{analysis['progression']['decision']}**.",
            f"- Reason: {analysis['progression']['reason']}",
            "- Pilot effect direction was not used as a progression gate.",
            "- The full eight-stratum, 32,000-episode confirmatory study was not run.",
            "",
        ]
    )
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def analysis_sha256(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())
