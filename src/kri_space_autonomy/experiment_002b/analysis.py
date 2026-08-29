from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from scipy.stats import beta

from kri_space_autonomy.experiment_002.config import PILOT_STRATA
from kri_space_autonomy.experiment_002.seeds import canonical_json

from .config import AmendmentConfig


def _jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line
    ]


def one_sided_exact_upper(events: int, total: int, confidence: float) -> float:
    if not 0 <= events <= total or total <= 0:
        raise ValueError("invalid binomial counts")
    if events == total:
        return 1.0
    return float(beta.ppf(confidence, events + 1, total - events))


def _validate_operational(
    rows: list[dict[str, Any]], amendment: AmendmentConfig
) -> dict[str, Any]:
    expected = amendment.operational_seeds_per_stratum
    strata: dict[str, Any] = {}
    keys = set()
    errors: list[str] = []
    for row in rows:
        key = (row["root_seed_id"], row["command_period_s"], row["observation_period_s"])
        if key in keys:
            errors.append(f"duplicate:{key}")
        keys.add(key)
        if (
            row["command_period_s"] != amendment.operational_command_period_s
            or row["observation_period_s"] != amendment.operational_observation_period_s
        ):
            errors.append(f"timing:{row['episode_id']}")
    for stratum in PILOT_STRATA:
        selected = [row for row in rows if row["stratum_id"] == stratum]
        hazards = sum(bool(row["physical_hazard_observed"]) for row in selected)
        collisions = sum(bool(row["collision"]) for row in selected)
        depletions = sum(bool(row["propellant_depleted"]) for row in selected)
        failures = sum(row["failure_class"] is not None for row in selected)
        successes = sum(bool(row["sustained_success"]) for row in selected)
        upper = one_sided_exact_upper(
            hazards, len(selected), amendment.one_sided_confidence
        )
        reserve_failures = sum(
            float(row["final_propellant"]) + 1e-12 < 0.1 for row in selected
        )
        strata[stratum] = {
            "episodes": len(selected),
            "physical_hazards": hazards,
            "collisions": collisions,
            "propellant_depletions": depletions,
            "controller_or_numerical_failures": failures,
            "sustained_successes": successes,
            "sustained_success_rate": successes / len(selected) if selected else None,
            "minimum_final_propellant": min(
                (float(row["final_propellant"]) for row in selected), default=None
            ),
            "reserve_failures": reserve_failures,
            "physical_hazard_one_sided_exact_95_upper": upper,
            "passed": bool(
                len(selected) == expected
                and hazards == 0
                and collisions == 0
                and depletions == 0
                and failures == 0
                and reserve_failures == 0
                and upper < amendment.zero_event_upper_margin
            ),
        }
        if len(selected) != expected:
            errors.append(f"count:{stratum}")
    return {
        "passed": not errors and all(value["passed"] for value in strata.values()),
        "episode_rows": len(rows),
        "unique_cells": len(keys),
        "errors_preview": errors[:20],
        "confidence": amendment.one_sided_confidence,
        "upper_margin": amendment.zero_event_upper_margin,
        "zero_event_upper_at_frozen_n": amendment.zero_event_upper_bound,
        "strata": strata,
    }


def _validate_trace_events(
    rate_rows: list[dict[str, Any]], events_path: str | Path
) -> dict[str, Any]:
    expected = {row["episode_id"]: row for row in rate_rows}
    counts: Counter[str] = Counter()
    digests = {episode_id: hashlib.sha256() for episode_id in expected}
    errors: list[str] = []
    event_count = 0
    with gzip.open(events_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            episode_id = event["episode_id"]
            event_count += 1
            if episode_id not in expected:
                if len(errors) < 20:
                    errors.append(f"unknown_episode:{episode_id}")
                continue
            counts[episode_id] += 1
            digests[episode_id].update(canonical_json(event) + b"\n")
            decision_time = float(event["decision_time_s"])
            command_period = float(event["command_period_s"])
            observation_period = float(event["observation_period_s"])
            if abs(decision_time / command_period - round(decision_time / command_period)) > 1e-9:
                if len(errors) < 20:
                    errors.append(f"command_timing:{episode_id}")
            for channel in ("primary", "monitor"):
                sample_time = float(event[f"{channel}_sample_time_s"])
                age = float(event[f"{channel}_packet_age_s"])
                if (
                    abs(sample_time / observation_period - round(sample_time / observation_period))
                    > 1e-9
                    or age < -1e-12
                    or age >= observation_period + 1e-12
                    or abs((decision_time - sample_time) - age) > 1e-10
                ):
                    if len(errors) < 20:
                        errors.append(f"observation_timing:{episode_id}:{channel}")
    for episode_id, row in expected.items():
        if counts[episode_id] != int(row["command_decisions"]):
            errors.append(f"event_count:{episode_id}")
        if digests[episode_id].hexdigest() != row["command_trace_sha256"]:
            errors.append(f"event_digest:{episode_id}")
    return {
        "passed": not errors,
        "episodes": len(expected),
        "command_events": event_count,
        "errors_preview": errors[:20],
        "all_episode_trace_digests_match": not any(
            error.startswith("event_digest:") for error in errors
        ),
    }


def _latency(row: dict[str, Any], field: str) -> float | None:
    onset = row["fault_onset_s"]
    value = row[field]
    if onset is None or value is None:
        return None
    return float(value) - float(onset)


def _rate_decomposition(
    rows: list[dict[str, Any]], amendment: AmendmentConfig
) -> dict[str, Any]:
    expected_per_cell = amendment.rate_blocks
    by_timing: dict[str, Any] = {}
    baseline = {
        row["root_seed_id"]: row
        for row in rows
        if row["command_period_s"] == 1.0 and row["observation_period_s"] == 1.0
    }
    errors: list[str] = []
    if len(baseline) != expected_per_cell:
        errors.append("baseline_count")
    for command_period in amendment.diagnostic_command_periods_s:
        for observation_period in amendment.diagnostic_observation_periods_s:
            selected = [
                row
                for row in rows
                if row["command_period_s"] == command_period
                and row["observation_period_s"] == observation_period
            ]
            key = f"command_{command_period:g}s__observation_{observation_period:g}s"
            if len(selected) != expected_per_cell:
                errors.append(f"count:{key}")
            hazards = sum(bool(row["physical_hazard_observed"]) for row in selected)
            collisions = sum(bool(row["collision"]) for row in selected)
            successes = sum(bool(row["sustained_success"]) for row in selected)
            depletions = sum(bool(row["propellant_depleted"]) for row in selected)
            failures = sum(row["failure_class"] is not None for row in selected)
            reserve_failures = sum(
                float(row["final_propellant"]) + 1e-12 < 0.1 for row in selected
            )
            gate_counts: Counter[str] = Counter()
            for row in selected:
                gate_counts.update(row["gate_reason_counts"])
            paired = [
                (row, baseline[row["root_seed_id"]])
                for row in selected
                if row["root_seed_id"] in baseline
            ]
            hazard_change = (
                sum(
                    int(row["physical_hazard_observed"])
                    - int(base["physical_hazard_observed"])
                    for row, base in paired
                )
                / len(paired)
                if paired
                else None
            )
            success_change = (
                sum(
                    int(row["sustained_success"]) - int(base["sustained_success"])
                    for row, base in paired
                )
                / len(paired)
                if paired
                else None
            )
            range_changes = [
                float(row["minimum_range_m"]) - float(base["minimum_range_m"])
                for row, base in paired
            ]
            propellant_changes = [
                float(row["propellant_used_fraction"])
                - float(base["propellant_used_fraction"])
                for row, base in paired
            ]
            sample_latencies = [
                value
                for row in selected
                for value in [
                    _latency(row, "first_primary_sample_on_or_after_fault_s"),
                    _latency(row, "first_monitor_sample_on_or_after_fault_s"),
                ]
                if value is not None
            ]
            command_latencies = [
                value
                for row in selected
                if (
                    value := _latency(row, "first_command_on_or_after_fault_s")
                )
                is not None
            ]
            override_latencies = [
                value
                for row in selected
                if (
                    value := _latency(row, "first_override_on_or_after_fault_s")
                )
                is not None
            ]
            by_timing[key] = {
                "command_period_s": command_period,
                "observation_period_s": observation_period,
                "episodes": len(selected),
                "physical_hazards": hazards,
                "collisions": collisions,
                "sustained_successes": successes,
                "propellant_depletions": depletions,
                "controller_or_numerical_failures": failures,
                "reserve_failures": reserve_failures,
                "minimum_final_propellant": min(
                    (float(row["final_propellant"]) for row in selected), default=None
                ),
                "gate_reason_counts": dict(sorted(gate_counts.items())),
                "paired_vs_1s_1s": {
                    "pairs": len(paired),
                    "physical_hazard_risk_difference": hazard_change,
                    "sustained_success_risk_difference": success_change,
                    "mean_minimum_range_change_m": (
                        sum(range_changes) / len(range_changes) if range_changes else None
                    ),
                    "maximum_absolute_minimum_range_change_m": max(
                        (abs(value) for value in range_changes), default=None
                    ),
                    "mean_propellant_use_change_fraction": (
                        sum(propellant_changes) / len(propellant_changes)
                        if propellant_changes
                        else None
                    ),
                    "maximum_absolute_propellant_use_change_fraction": max(
                        (abs(value) for value in propellant_changes), default=None
                    ),
                },
                "fault_response_timing_s": {
                    "median_sensor_sample_latency": (
                        median(sample_latencies) if sample_latencies else None
                    ),
                    "maximum_sensor_sample_latency": (
                        max(sample_latencies) if sample_latencies else None
                    ),
                    "median_command_latency": (
                        median(command_latencies) if command_latencies else None
                    ),
                    "maximum_command_latency": (
                        max(command_latencies) if command_latencies else None
                    ),
                    "median_override_latency_when_observed": (
                        median(override_latencies) if override_latencies else None
                    ),
                    "override_responses_observed": len(override_latencies),
                },
            }
    failures = sum(row["failure_class"] is not None for row in rows)
    depletions = sum(bool(row["propellant_depleted"]) for row in rows)
    reserve_failures = sum(float(row["final_propellant"]) + 1e-12 < 0.1 for row in rows)
    return {
        "passed_feasibility_qc": bool(
            not errors and failures == 0 and depletions == 0 and reserve_failures == 0
        ),
        "support_claim": False,
        "interpretation": (
            "descriptive mechanism-identification grid only; no closed-loop trajectory "
            "identity or multi-rate noninferiority claim"
        ),
        "episode_rows": len(rows),
        "expected_episode_rows": amendment.rate_episodes,
        "controller_or_numerical_failures": failures,
        "propellant_depletions": depletions,
        "reserve_failures": reserve_failures,
        "errors_preview": errors[:20],
        "timing_cells": by_timing,
    }


def analyze_002b(
    amendment: AmendmentConfig,
    operational_path: str | Path,
    rate_path: str | Path,
    rate_events_path: str | Path,
    numerical_path: str | Path,
    seed_validation: dict[str, Any],
    validation_evidence: dict[str, Any],
    freeze_verified: bool,
    output_analysis_path: str | Path,
    output_qc_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    operational_rows = _jsonl(operational_path)
    rate_rows = _jsonl(rate_path)
    numerical = json.loads(Path(numerical_path).read_text(encoding="utf-8"))
    operational = _validate_operational(operational_rows, amendment)
    trace = _validate_trace_events(rate_rows, rate_events_path)
    rate = _rate_decomposition(rate_rows, amendment)
    zero_failures = (
        sum(row["failure_class"] is not None for row in operational_rows + rate_rows) == 0
        and all(case["source_controller_failure"] is None for case in numerical["cases"])
    )
    reserve = (
        all(float(row["final_propellant"]) + 1e-12 >= 0.1 for row in operational_rows)
        and all(float(row["final_propellant"]) + 1e-12 >= 0.1 for row in rate_rows)
        and not any(bool(row["propellant_depleted"]) for row in operational_rows + rate_rows)
    )
    checks = [
        {
            "id": "pre_outcome_validation_and_freeze",
            "passed": bool(validation_evidence.get("passed") and freeze_verified),
            "threshold": "all pre-outcome checks pass and frozen hashes verify",
        },
        {
            "id": "seed_partition",
            "passed": bool(seed_validation["passed"]),
            "threshold": "all 002b seeds are manifest-complete and disjoint from Experiment 002",
            "observed": seed_validation,
        },
        {
            "id": "zero_controller_numerical_failures",
            "passed": zero_failures,
            "threshold": "zero controller, invalid-action, or numerical failures",
        },
        {
            "id": "fixed_command_numerical_replay",
            "passed": bool(numerical["passed"]),
            "threshold": (
                "full fixed-command max state/metric error <=1e-10 and identical collision, "
                "physical-hazard, depletion, and sustained-success classes"
            ),
            "observed": {
                "cases": numerical["case_count"],
                "maximum_state_or_metric_error": numerical[
                    "maximum_state_or_metric_error"
                ],
                "all_classifications_match": numerical["all_classifications_match"],
            },
        },
        {
            "id": "operational_1s_safety",
            "passed": bool(operational["passed"]),
            "threshold": (
                "150 disjoint seeds/stratum, zero physical hazards/collisions, and one-sided "
                "exact 95% upper bound <0.02 in every stratum"
            ),
            "observed": operational,
        },
        {
            "id": "propellant_reserve",
            "passed": reserve,
            "threshold": "no depletion and final propellant >=0.10 in every 002b episode",
        },
        {
            "id": "rate_decomposition_evidence",
            "passed": bool(rate["passed_feasibility_qc"] and trace["passed"]),
            "threshold": (
                "complete 3x3 timing grid, intact command/sensor trace evidence, zero failures, "
                "and reserve retained; no multi-rate support claim"
            ),
            "observed": {
                "rate": rate,
                "trace_integrity": trace,
            },
        },
        {
            "id": "confirmatory_campaign_blocked",
            "passed": True,
            "threshold": "full 32,000-episode campaign and combined-fault study are not executed",
        },
    ]
    passed = all(check["passed"] for check in checks)
    decision = "pass" if passed else "fail"
    next_step = (
        "combined_fault_nuisance_information_study"
        if passed
        else "investigate_experiment_002b_failure"
    )
    analysis = {
        "schema_version": amendment.schema_version,
        "decision": decision,
        "operational_configuration": {
            "command_period_s": 1.0,
            "observation_period_s": 1.0,
            "qualified": passed,
        },
        "multi_rate_support_claim": False,
        "operational": operational,
        "rate_decomposition": rate,
        "trace_integrity": trace,
        "fixed_command_numerical_replay": numerical,
        "next_step": next_step,
        "confirmatory_campaign_executed": False,
        "combined_fault_study_executed": False,
    }
    qc = {
        "schema_version": amendment.schema_version,
        "overall_passed": passed,
        "decision": decision,
        "checks": checks,
        "deviations": [],
    }
    Path(output_analysis_path).write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    Path(output_qc_path).write_text(
        json.dumps(qc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return analysis, qc


def write_report(analysis: dict[str, Any], path: str | Path) -> None:
    operational = analysis["operational"]
    numerical = analysis["fixed_command_numerical_replay"]
    rate = analysis["rate_decomposition"]
    rows = []
    for stratum, values in operational["strata"].items():
        row_template = (
            "| {stratum} | {episodes} | {hazards} | {successes} | "
            "{reserve:.6f} | {upper:.5f} |"
        )
        rows.append(
            row_template.format(
                stratum=stratum,
                episodes=values["episodes"],
                hazards=values["physical_hazards"],
                successes=values["sustained_successes"],
                reserve=values["minimum_final_propellant"],
                upper=values["physical_hazard_one_sided_exact_95_upper"],
            )
        )
    rate_rows = []
    for values in rate["timing_cells"].values():
        paired = values["paired_vs_1s_1s"]
        row_template = (
            "| {command:g} | {observation:g} | {hazards} | {successes} | "
            "{hazard_delta:+.4f} | {success_delta:+.4f} | {fuel:+.5f} |"
        )
        rate_rows.append(
            row_template.format(
                command=values["command_period_s"],
                observation=values["observation_period_s"],
                hazards=values["physical_hazards"],
                successes=values["sustained_successes"],
                hazard_delta=paired["physical_hazard_risk_difference"],
                success_delta=paired["sustained_success_risk_difference"],
                fuel=paired["mean_propellant_use_change_fraction"],
            )
        )
    lines = [
        "# Experiment 002b corrective validation amendment",
        "",
        "_Frozen corrective study; Experiment 002 historical artifacts remain unchanged_",
        "",
        "> **Evidence boundary:** This amendment validates the sampled-data methodology",
        "> and frozen PD controller at the existing 1.0 s command/observation setting in",
        "> the six-stratum synthetic generator. It is not flight-safety evidence, a",
        "> multi-rate qualification, or a confirmatory architecture claim.",
        "",
        "## Decision",
        "",
        f"**`{analysis['decision']}`**. The full 32,000-episode confirmatory campaign was",
        "not run. The combined-fault nuisance/information study was not run.",
        "",
        "## Operational 1.0 s validation",
        "",
        "| Stratum | Episodes | Hazards | Successes | Minimum final propellant | 95% upper |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        *rows,
        "",
        "The frozen sample was 150 disjoint seeds per stratum. With zero events, the",
        "per-stratum one-sided exact 95% upper bound is",
        f"`{operational['zero_event_upper_at_frozen_n']:.5f}`, below the prospective",
        "`0.02` margin. Success is descriptive and need not remain identical across",
        "different sampled-data systems.",
        "",
        "## Full fixed-command numerical replay",
        "",
        f"- Complete traces: {numerical['case_count']}",
        "- Maximum state or metric error: "
        f"`{numerical['maximum_state_or_metric_error']:.3e}`",
        "- Required classifications identical: "
        f"`{str(numerical['all_classifications_match']).lower()}`",
        "- Gate tolerance: `1e-10`",
        "",
        "## Rate decomposition",
        "",
        "| Command (s) | Observation (s) | Hazards | Successes | Hazard change | "
        "Success change | Mean fuel change |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        *rate_rows,
        "",
        "The 3×3 grid independently varies command hold/update timing and sensor sampling",
        "timing. It is a 12-seed-per-stratum mechanism-identification feasibility design.",
        "Machine-readable evidence retains commands, gate reasons, packet identities, and",
        "fault-response timing. Trajectory, range/fuel, and success identity are not gates",
        "across closed-loop timing configurations. No support is claimed for 0.5 s or",
        "0.25 s command periods.",
        "",
        "## Next step",
        "",
        f"`{analysis['next_step']}`. The confirmatory campaign remains blocked until its",
        "separate combined-fault nuisance/information requirement is prospectively resolved.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
