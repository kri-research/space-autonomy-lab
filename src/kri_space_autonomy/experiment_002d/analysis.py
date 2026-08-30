from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import norm

from kri_space_autonomy.experiment_002.analysis import exact_one_sided_upper

from .config import COMBINED_STRATUM, CombinedInformationConfig

CONFIRMATORY_GROUPS: tuple[tuple[str, str, str | None], ...] = (
    ("F0_nominal", "P0_nominal", None),
    ("F1_primary_range_bias", "P1_primary_navigation", "range_bias"),
    ("F2_primary_dropout", "P1_primary_navigation", "dropout"),
    ("F3_monitor_channel_fault", "P2_monitor_only", None),
    ("F4_shared_cause_navigation", "P3_shared_cause_navigation", None),
    ("F5_persistent_model_upset", "P4_model_upset", None),
    ("F6_actuator_degradation", "P5_actuator_degradation", None),
)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def _exact_one_sided_lower(events: int, n: int, alpha: float = 0.05) -> float:
    if events <= 0:
        return 0.0
    return 1.0 - exact_one_sided_upper(n - events, n, alpha)


def validate_information_cells(
    rows: list[dict[str, Any]],
    study: CombinedInformationConfig,
) -> dict[str, Any]:
    keys = [(row["root_seed_id"], row["arm"]) for row in rows]
    block_arms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        block_arms[str(row["root_seed_id"])].add(str(row["arm"]))
    incomplete = [root for root, arms in block_arms.items() if arms != set(study.arms)]
    unexpected = [
        row["root_seed_id"]
        for row in rows
        if row["stratum_id"] != COMBINED_STRATUM
        or row["fault_subtype"] != "primary_dropout_plus_actuator_degradation"
    ]
    valid = bool(
        len(rows) == study.planned_episodes
        and len(set(keys)) == study.planned_episodes
        and len(block_arms) == study.planned_blocks
        and not incomplete
        and not unexpected
    )
    return {
        "valid": valid,
        "episode_rows": len(rows),
        "unique_episode_cells": len(set(keys)),
        "blocks": len(block_arms),
        "complete_blocks": len(block_arms) - len(incomplete),
        "incomplete_blocks": len(incomplete),
        "incomplete_fraction": len(incomplete) / study.planned_blocks,
        "incomplete_limit": study.incomplete_block_limit,
        "unexpected_rows": len(unexpected),
    }


def _paired_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = {(str(row["root_seed_id"]), str(row["arm"])): row for row in rows}
    root_ids = sorted({root for root, _ in selected})
    direct = [selected[(root, "D")] for root in root_ids]
    protected = [selected[(root, "PD")] for root in root_ids]
    return direct, protected


def _nuisance_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    direct, protected = _paired_rows(rows)
    n = len(direct)
    direct_hazard = sum(bool(row["analysis_hazard"]) for row in direct)
    protected_hazard = sum(bool(row["analysis_hazard"]) for row in protected)
    direct_success = sum(bool(row["sustained_success"]) for row in direct)
    protected_success = sum(bool(row["sustained_success"]) for row in protected)
    hazard_pd1_d0 = sum(
        bool(pd["analysis_hazard"]) and not bool(d["analysis_hazard"])
        for d, pd in zip(direct, protected, strict=True)
    )
    hazard_pd0_d1 = sum(
        not bool(pd["analysis_hazard"]) and bool(d["analysis_hazard"])
        for d, pd in zip(direct, protected, strict=True)
    )
    success_pd1_d0 = sum(
        bool(pd["sustained_success"]) and not bool(d["sustained_success"])
        for d, pd in zip(direct, protected, strict=True)
    )
    success_pd0_d1 = sum(
        not bool(pd["sustained_success"]) and bool(d["sustained_success"])
        for d, pd in zip(direct, protected, strict=True)
    )
    hazard_discordant = hazard_pd1_d0 + hazard_pd0_d1
    success_discordant = success_pd1_d0 + success_pd0_d1
    failure_cells = sum(
        row.get("failure_class") is not None for row in (*direct, *protected)
    )
    return {
        "paired_blocks": n,
        "direct_hazard_events": direct_hazard,
        "direct_hazard_risk": direct_hazard / n,
        "direct_hazard_lower95": _exact_one_sided_lower(direct_hazard, n),
        "direct_hazard_upper95": exact_one_sided_upper(direct_hazard, n),
        "protected_hazard_events": protected_hazard,
        "protected_hazard_risk": protected_hazard / n,
        "direct_success_events": direct_success,
        "direct_success_risk": direct_success / n,
        "protected_success_events": protected_success,
        "protected_success_risk": protected_success / n,
        "hazard_discordance": {
            "pd1_d0": hazard_pd1_d0,
            "pd0_d1": hazard_pd0_d1,
            "total": hazard_discordant,
            "risk": hazard_discordant / n,
            "one_sided_95_upper": exact_one_sided_upper(hazard_discordant, n),
        },
        "success_discordance": {
            "pd1_d0": success_pd1_d0,
            "pd0_d1": success_pd0_d1,
            "total": success_discordant,
            "risk": success_discordant / n,
            "one_sided_95_upper": exact_one_sided_upper(success_discordant, n),
        },
        "adverse_coded_failure_cells": failure_cells,
        "adverse_coded_failure_cell_risk": failure_cells / (2 * n),
        "adverse_coded_failure_cell_upper95": exact_one_sided_upper(
            failure_cells, 2 * n
        ),
    }


def historical_nuisance(path: str | Path) -> dict[str, Any]:
    rows = _read_jsonl(path)
    output: dict[str, Any] = {}
    for confirmatory_id, pilot_stratum, subtype in CONFIRMATORY_GROUPS:
        selected = [
            row
            for row in rows
            if row["stratum_id"] == pilot_stratum
            and (subtype is None or row["fault_subtype"] == subtype)
        ]
        output[confirmatory_id] = _nuisance_from_rows(selected)
    return output


def _wilson_interval(events: int, n: int, confidence: float = 0.95) -> list[float]:
    z = float(norm.ppf(0.5 + confidence / 2.0))
    estimate = events / n
    denominator = 1.0 + z * z / n
    center = (estimate + z * z / (2.0 * n)) / denominator
    half = (
        z
        * math.sqrt(estimate * (1.0 - estimate) / n + z * z / (4.0 * n * n))
        / denominator
    )
    return [max(0.0, center - half), min(1.0, center + half)]


def _planning_power(
    nuisance: dict[str, Any],
    study: CombinedInformationConfig,
    direct_risk_selector: Callable[[dict[str, Any]], float],
    scenario_index: int,
) -> dict[str, Any]:
    critical = float(norm.ppf(1.0 - study.h2_one_sided_alpha))
    output: dict[str, Any] = {}
    for n in study.candidate_confirmatory_seeds_per_stratum:
        rng = np.random.Generator(
            np.random.PCG64DXSM(
                np.random.SeedSequence([study.power_seed, scenario_index, n])
            )
        )
        simulations = study.power_simulations
        hazard_estimate = np.zeros(simulations, dtype=np.float64)
        hazard_variance = np.zeros(simulations, dtype=np.float64)
        success_estimate = np.zeros(simulations, dtype=np.float64)
        success_variance = np.zeros(simulations, dtype=np.float64)
        assumed_deltas: dict[str, float] = {}
        for stratum, values in nuisance.items():
            direct_risk = direct_risk_selector(values)
            hazard_delta = -max(
                study.hazard_minimum_absolute_reduction,
                study.hazard_minimum_relative_reduction * direct_risk,
            )
            assumed_deltas[stratum] = hazard_delta
            q_h = max(
                float(values["hazard_discordance"]["one_sided_95_upper"]),
                abs(hazard_delta),
            )
            if q_h > 1.0:
                raise ValueError("hazard discordance is outside the feasible range")
            h_counts = rng.multinomial(
                n,
                [(q_h + hazard_delta) / 2.0, (q_h - hazard_delta) / 2.0, 1.0 - q_h],
                size=simulations,
            )
            h_diff = (h_counts[:, 0] - h_counts[:, 1]) / n
            h_q = (h_counts[:, 0] + h_counts[:, 1]) / n
            hazard_estimate += h_diff / study.confirmatory_strata
            hazard_variance += (
                np.maximum(0.0, h_q - h_diff**2)
                / n
                / study.confirmatory_strata**2
            )

            q_s = float(values["success_discordance"]["one_sided_95_upper"])
            if not 0.0 <= q_s <= 1.0:
                raise ValueError("success discordance is outside the feasible range")
            s_counts = rng.multinomial(
                n,
                [q_s / 2.0, q_s / 2.0, 1.0 - q_s],
                size=simulations,
            )
            s_diff = (s_counts[:, 0] - s_counts[:, 1]) / n
            s_q = (s_counts[:, 0] + s_counts[:, 1]) / n
            success_estimate += s_diff / study.confirmatory_strata
            success_variance += (
                np.maximum(0.0, s_q - s_diff**2)
                / n
                / study.confirmatory_strata**2
            )
        h1_pass = hazard_estimate + critical * np.sqrt(hazard_variance) < 0.0
        h2_pass = (
            success_estimate - critical * np.sqrt(success_variance)
            > study.h2_noninferiority_margin
        )
        h1_events = int(np.sum(h1_pass))
        h2_events = int(np.sum(h2_pass))
        h1_power = h1_events / simulations
        h2_power = h2_events / simulations
        output[str(n)] = {
            "h1_marginal_power": h1_power,
            "h1_monte_carlo_95_interval": _wilson_interval(h1_events, simulations),
            "h2_marginal_power": h2_power,
            "h2_monte_carlo_95_interval": _wilson_interval(h2_events, simulations),
            "meets_target_by_monte_carlo_lower_bounds": bool(
                _wilson_interval(h1_events, simulations)[0] >= study.power_target
                and _wilson_interval(h2_events, simulations)[0] >= study.power_target
            ),
            "assumed_hazard_deltas_by_stratum": assumed_deltas,
        }
    return {
        "method": (
            "eight-stratum equal-weight paired multinomial simulation; separate one-sided "
            "95% discordance bounds; H1 requirements alternative and H2 zero-difference "
            "alternative; 1.96 critical value; marginal endpoint power only"
        ),
        "simulations": study.power_simulations,
        "critical_value": critical,
        "candidate_confirmatory_seeds_per_stratum": output,
    }


def prospective_worst_case_power(
    study: CombinedInformationConfig,
    historical_episodes_path: str | Path,
) -> dict[str, Any]:
    nuisance = historical_nuisance(historical_episodes_path)
    nuisance[COMBINED_STRATUM] = {
        "direct_hazard_risk": 0.0,
        "direct_hazard_lower95": 0.0,
        "hazard_discordance": {"one_sided_95_upper": 1.0},
        "success_discordance": {"one_sided_95_upper": 1.0},
        "prospective_placeholder": "least-favorable feasible discordance",
    }
    return _planning_power(
        nuisance,
        study,
        lambda values: float(values["direct_hazard_lower95"]),
        scenario_index=900,
    )


def replay_check(
    rows: list[dict[str, Any]],
    replay_replicates: list[int],
    rerun: Callable[[int], list[dict[str, Any]]],
) -> dict[str, Any]:
    expected = {(int(row["replicate"]), str(row["arm"])): row for row in rows}
    failures: list[dict[str, Any]] = []
    compared = 0
    for replicate in replay_replicates:
        for observed in rerun(replicate):
            key = (replicate, str(observed["arm"]))
            compared += 1
            if expected.get(key) != observed:
                failures.append({"replicate": replicate, "arm": observed["arm"]})
    return {
        "passed": not failures and compared == 2 * len(replay_replicates),
        "episodes_compared": compared,
        "failures_preview": failures[:20],
    }


def analyze_002d(
    study: CombinedInformationConfig,
    information_path: str | Path,
    historical_episodes_path: str | Path,
    validation: dict[str, Any],
    seed_validation: dict[str, Any],
    historical_integrity: dict[str, Any],
    freeze_verified: bool,
    replay: dict[str, Any],
    output_path: str | Path,
    qc_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = _read_jsonl(information_path)
    cells = validate_information_cells(rows, study)
    historical = historical_nuisance(historical_episodes_path)
    combined = _nuisance_from_rows(rows)
    nuisance = {**historical, COMBINED_STRATUM: combined}
    historical_compatible = _planning_power(
        nuisance,
        study,
        lambda values: float(values["direct_hazard_risk"]),
        scenario_index=1,
    )
    conservative = _planning_power(
        nuisance,
        study,
        lambda values: float(values["direct_hazard_lower95"]),
        scenario_index=2,
    )
    candidates = []
    for n in study.candidate_confirmatory_seeds_per_stratum:
        key = str(n)
        if (
            historical_compatible["candidate_confirmatory_seeds_per_stratum"][key][
                "meets_target_by_monte_carlo_lower_bounds"
            ]
            and conservative["candidate_confirmatory_seeds_per_stratum"][key][
                "meets_target_by_monte_carlo_lower_bounds"
            ]
        ):
            candidates.append(n)
    recommended_n = min(candidates) if candidates else None
    checks = [
        {
            "id": "pre_outcome_validation",
            "passed": bool(validation.get("passed")),
            "threshold": "all pre-outcome tests, lint, lock, source, and scan checks pass",
        },
        {
            "id": "historical_integrity",
            "passed": bool(historical_integrity.get("passed")),
            "threshold": "Experiments 002, 002b, and 002c remain unchanged and verified",
        },
        {
            "id": "freeze_verified",
            "passed": freeze_verified,
            "threshold": "all frozen inputs verify before and after execution",
        },
        {
            "id": "seed_manifest",
            "passed": bool(seed_validation.get("passed")),
            "threshold": "299 disjoint F7 roots in partition 25; partition 16 untouched",
        },
        {
            "id": "paired_cells",
            "passed": bool(
                cells["valid"]
                and cells["incomplete_fraction"] <= study.incomplete_block_limit
            ),
            "threshold": "299 complete D/PD blocks; incomplete fraction <=1%",
            "observed": cells,
        },
        {
            "id": "same_platform_replay",
            "passed": bool(replay.get("passed")),
            "threshold": "20 frozen roots reproduce both episode rows exactly",
            "observed": replay,
        },
        {
            "id": "bounded_scope",
            "passed": bool(
                len(rows) == 598
                and {row["arm"] for row in rows} == {"D", "PD"}
                and {row["stratum_id"] for row in rows} == {COMBINED_STRATUM}
            ),
            "threshold": "only the F7 information study ran; no confirmatory campaign",
        },
        {
            "id": "h1_h2_information",
            "passed": recommended_n is not None,
            "threshold": (
                "smallest 1,000-2,000 candidate has H1 and H2 marginal power lower "
                "Monte Carlo bounds >=95% in both planning scenarios"
            ),
        },
    ]
    qc_passed = all(check["passed"] for check in checks)
    resolved = bool(qc_passed and recommended_n is not None)
    decision = "resolved_freeze_confirmatory_design" if resolved else "blocked"
    next_action = (
        "freeze_separate_eight_stratum_confirmatory_preregistration_without_materializing_"
        "or_opening_reserved_seeds"
        if resolved
        else "retain_confirmatory_block_and_resolve_failed_002d_gate"
    )
    analysis = {
        "schema_version": study.schema_version,
        "study_phase": "bounded_combined_fault_information",
        "decision": decision,
        "information_requirement_resolved": resolved,
        "combined_fault_stratum": COMBINED_STRATUM,
        "confirmatory_stratum_weights": {key: 1.0 / 8.0 for key in nuisance},
        "information_counts": cells,
        "nuisance": nuisance,
        "power": {
            "historical_compatible_point_direct_risk": historical_compatible,
            "conservative_direct_risk_lower95": conservative,
            "recommended_confirmatory_seeds_per_stratum": recommended_n,
            "recommended_confirmatory_episodes": (
                8 * recommended_n * 4 if recommended_n is not None else None
            ),
            "endpoint_power_interpretation": "marginal, not joint",
            "nuisance_bound_interpretation": (
                "separate one-sided 95% bounds; no simultaneous-coverage claim"
            ),
        },
        "failure_classes": dict(
            Counter(row["failure_class"] for row in rows if row["failure_class"])
        ),
        "qc_check_ids": [check["id"] for check in checks],
        "confirmatory_campaign_executed": False,
        "reserved_confirmatory_partition_materialized": False,
        "next_action": next_action,
    }
    qc = {
        "schema_version": study.schema_version,
        "overall_passed": qc_passed,
        "decision": decision,
        "checks": checks,
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


def write_report(analysis: dict[str, Any], path: str | Path) -> None:
    combined = analysis["nuisance"][COMBINED_STRATUM]
    conservative = analysis["power"]["conservative_direct_risk_lower95"][
        "candidate_confirmatory_seeds_per_stratum"
    ]
    lines = [
        "# Experiment 002d combined-fault information study",
        "",
        "> **Evidence boundary:** bounded nuisance and paired-information evidence for the frozen",
        "> synthetic F7 generator only. This is not confirmatory superiority or flight-safety",
        "> evidence.",
        "",
        "## Decision",
        "",
        f"**`{analysis['decision']}`**.",
        "",
        (
            "- Complete paired root-seed blocks: "
            f"`{analysis['information_counts']['complete_blocks']}`"
        ),
        f"- Episode rows: `{analysis['information_counts']['episode_rows']}` (D and PD only)",
        "- Confirmatory campaign executed: `false`",
        "- Reserved confirmatory partition materialized: `false`",
        "",
        "## F7 nuisance estimates",
        "",
        f"- D analysis-hazard risk: `{combined['direct_hazard_risk']:.6f}` "
        f"({combined['direct_hazard_events']}/{combined['paired_blocks']})",
        f"- Hazard discordance: `{combined['hazard_discordance']['risk']:.6f}`; "
        f"one-sided 95% upper `{combined['hazard_discordance']['one_sided_95_upper']:.6f}`",
        f"- Sustained-success discordance: `{combined['success_discordance']['risk']:.6f}`; "
        f"one-sided 95% upper `{combined['success_discordance']['one_sided_95_upper']:.6f}`",
        f"- Adverse-coded failure cells: `{combined['adverse_coded_failure_cells']}`",
        "",
        "## Eight-stratum marginal power",
        "",
        "| Seeds/stratum | H1 power | H1 MC 95% lower | H2 power | H2 MC 95% lower | Pass |",
        "| ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for key, item in conservative.items():
        lines.append(
            f"| {key} | {item['h1_marginal_power']:.5f} | "
            f"{item['h1_monte_carlo_95_interval'][0]:.5f} | "
            f"{item['h2_marginal_power']:.5f} | "
            f"{item['h2_monte_carlo_95_interval'][0]:.5f} | "
            f"{'yes' if item['meets_target_by_monte_carlo_lower_bounds'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "Endpoint powers are marginal, not a claim about joint H1/H2 rejection probability.",
            "Nuisance bounds are separate one-sided 95% bounds; no simultaneous-coverage claim is",
            "made. Controller effects observed here are descriptive and are not progression gates.",
            "",
            "## Exact next action",
            "",
            f"`{analysis['next_action']}`.",
            "",
        ]
    )
    Path(path).write_text("\n".join(lines), encoding="utf-8")
