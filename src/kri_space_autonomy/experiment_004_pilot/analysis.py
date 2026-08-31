from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .config import CONFIGURATIONS, PilotCase, PilotConfig


def load_episode_rows(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
    ]


def validate_complete_cells(
    rows: list[dict[str, Any]],
    pilot: PilotConfig,
    cases: tuple[PilotCase, ...],
) -> dict[str, Any]:
    counts: Counter[tuple[str, str, str]] = Counter()
    block_configurations: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        key = (
            str(row.get("case_id")),
            str(row.get("root_seed_id")),
            str(row.get("configuration_id")),
        )
        counts[key] += 1
        block_configurations[key[:2]].add(key[2])
    expected = {
        (
            case.id,
            f"experiment004:43:{case.case_code:03d}:{replicate:04d}",
            configuration,
        )
        for case in cases
        for replicate in range(pilot.pilot_roots_per_case)
        for configuration in CONFIGURATIONS
    }
    observed = set(counts)
    duplicates = sum(value - 1 for value in counts.values() if value > 1)
    complete_blocks = sum(
        configurations == set(CONFIGURATIONS)
        for configurations in block_configurations.values()
    )
    missing = expected - observed
    extra = observed - expected
    return {
        "passed": bool(
            len(rows) == pilot.pilot_episodes
            and duplicates == 0
            and not missing
            and not extra
            and complete_blocks == pilot.pilot_blocks
        ),
        "rows": len(rows),
        "expected_rows": pilot.pilot_episodes,
        "complete_blocks": complete_blocks,
        "expected_blocks": pilot.pilot_blocks,
        "duplicates": duplicates,
        "missing": len(missing),
        "extra": len(extra),
        "missing_preview": sorted(missing)[:20],
        "extra_preview": sorted(extra)[:20],
    }


def _case_rows(rows: list[dict[str, Any]], case_id: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("case_id") == case_id]


def _forced_event_gates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    collision = _case_rows(rows, "P01_forced_collision")
    keep_out = _case_rows(rows, "P02_forced_keep_out_only")
    corridor = _case_rows(rows, "P03_forced_corridor_departure")
    checks = {
        "collision": bool(
            collision
            and all(
                row["physical_collision"] and row["physical_keep_out_entry"]
                for row in collision
            )
        ),
        "keep_out_only": bool(
            keep_out
            and all(
                not row["physical_collision"] and row["physical_keep_out_entry"]
                for row in keep_out
            )
        ),
        "corridor_only": bool(
            corridor
            and all(
                not row["physical_collision"]
                and not row["physical_keep_out_entry"]
                and row["physical_corridor_departure"]
                for row in corridor
            )
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def _nominal_gate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nominal = _case_rows(rows, "P00_nominal_feasibility")
    return {
        "passed": bool(
            nominal
            and all(
                row["hold_acquired"]
                and not row["physical_collision"]
                and not row["physical_keep_out_entry"]
                and not row["physical_corridor_departure"]
                and row["numerical_valid"]
                for row in nominal
            )
        ),
        "episodes": len(nominal),
    }


def _fault_activation_gates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {
        "primary_bias": all(
            row["primary_fault_active_packets"] > 0
            and row["monitor_fault_active_packets"] == 0
            and row["primary_estimator_fault"]
            and not row["monitor_estimator_fault"]
            and not row["shared_cause_fault"]
            for row in _case_rows(rows, "P04_primary_navigation_bias")
        ),
        "primary_dropout": all(
            row["primary_fault_active_packets"] > 0
            and row["primary_disposition_counts"].get("dropout", 0) > 0
            and row["monitor_fault_active_packets"] == 0
            for row in _case_rows(rows, "P05_primary_navigation_dropout")
        ),
        "monitor_bias": all(
            row["primary_fault_active_packets"] == 0
            and row["monitor_fault_active_packets"] > 0
            and not row["primary_estimator_fault"]
            and row["monitor_estimator_fault"]
            for row in _case_rows(rows, "P06_monitor_navigation_bias")
        ),
        "monitor_logic": all(
            (
                row["monitor_logic_active_commands"] > 0
                if row["configuration_id"] == "independent_monitor_gate"
                else row["monitor_logic_active_commands"] == 0
            )
            and row["monitor_logic_fault"]
            for row in _case_rows(rows, "P07_monitor_logic_false_trip")
        ),
        "shared": all(
            row["primary_fault_active_packets"] > 0
            and row["monitor_fault_active_packets"] > 0
            and row["shared_cause_fault"]
            and not row["primary_estimator_fault"]
            and not row["monitor_estimator_fault"]
            for row in _case_rows(rows, "P08_shared_navigation_bias")
        ),
        "actuation": all(
            row["actuation_degradation_scheduled"]
            and row["actuation_degradation_active_commands"] > 0
            and not row["disturbance_scheduled"]
            for row in _case_rows(rows, "P09_actuation_degradation")
        ),
        "disturbance": all(
            row["disturbance_scheduled"]
            and row["disturbance_active_substeps"] > 0
            and not row["actuation_degradation_scheduled"]
            for row in _case_rows(rows, "P10_disturbance_burst")
        ),
    }
    expected_nonempty = all(
        _case_rows(rows, case_id)
        for case_id in (
            "P04_primary_navigation_bias",
            "P05_primary_navigation_dropout",
            "P06_monitor_navigation_bias",
            "P07_monitor_logic_false_trip",
            "P08_shared_navigation_bias",
            "P09_actuation_degradation",
            "P10_disturbance_burst",
        )
    )
    return {"passed": bool(expected_nonempty and all(checks.values())), "checks": checks}


def _numerical_gate(rows: list[dict[str, Any]], pilot: PilotConfig) -> dict[str, Any]:
    valid = all(
        row.get("numerical_valid")
        and float(row.get("minimum_covariance_eigenvalue", -float("inf"))) >= -1e-12
        and float(row.get("maximum_covariance_trace", float("inf"))) < 1_000_000.0
        for row in rows
    )
    infrastructure_failures = sum(bool(row.get("infrastructure_failure")) for row in rows)
    rate = infrastructure_failures / len(rows) if rows else 1.0
    return {
        "passed": bool(
            rows
            and valid
            and rate <= pilot.maximum_infrastructure_failure_rate
            and infrastructure_failures == 0
        ),
        "numerical_and_covariance_valid": valid,
        "infrastructure_failures": infrastructure_failures,
        "infrastructure_failure_rate": rate,
        "maximum_allowed_rate": pilot.maximum_infrastructure_failure_rate,
        "complete_blocks_make_any_infrastructure_failure_fatal": True,
    }


def _descriptive_summary(
    rows: list[dict[str, Any]],
    cases: tuple[PilotCase, ...],
) -> dict[str, Any]:
    summary = {}
    for case in cases:
        summary[case.id] = {}
        for configuration in CONFIGURATIONS:
            selected = [
                row
                for row in rows
                if row.get("case_id") == case.id
                and row.get("configuration_id") == configuration
            ]
            summary[case.id][configuration] = {
                "episodes": len(selected),
                "event_counts": {
                    "collision": sum(bool(row["physical_collision"]) for row in selected),
                    "keep_out_entry": sum(
                        bool(row["physical_keep_out_entry"]) for row in selected
                    ),
                    "corridor_departure": sum(
                        bool(row["physical_corridor_departure"]) for row in selected
                    ),
                    "hold_acquired": sum(bool(row["hold_acquired"]) for row in selected),
                },
                "monitor_override_commands": sum(
                    int(row["monitor_override_commands"]) for row in selected
                ),
                "fault_activation_counts": {
                    "primary_packets": sum(
                        int(row["primary_fault_active_packets"]) for row in selected
                    ),
                    "monitor_packets": sum(
                        int(row["monitor_fault_active_packets"]) for row in selected
                    ),
                    "logic_commands": sum(
                        int(row["monitor_logic_active_commands"]) for row in selected
                    ),
                    "actuation_commands": sum(
                        int(row["actuation_degradation_active_commands"])
                        for row in selected
                    ),
                    "disturbance_substeps": sum(
                        int(row["disturbance_active_substeps"]) for row in selected
                    ),
                },
            }
    return summary


def analyze_pilot(
    rows: list[dict[str, Any]],
    pilot: PilotConfig,
    cases: tuple[PilotCase, ...],
    *,
    integrity: dict[str, Any],
    replay: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    cells = validate_complete_cells(rows, pilot, cases)
    forced = _forced_event_gates(rows)
    nominal = _nominal_gate(rows)
    faults = _fault_activation_gates(rows)
    numerical = _numerical_gate(rows, pilot)
    checks = {
        "complete_cells": cells,
        "forced_events": forced,
        "nominal_feasibility": nominal,
        "fault_activation_and_separation": faults,
        "numerical_covariance_infrastructure": numerical,
        "design_integrity": integrity,
        "deterministic_replay": replay,
    }
    passed = all(bool(check.get("passed")) for check in checks.values())
    qc = {
        "schema_version": pilot.schema_version,
        "phase": "noninferential_design_validation_pilot",
        "overall_passed": passed,
        "checks": checks,
    }
    analysis = {
        "schema_version": pilot.schema_version,
        "phase": "noninferential_design_validation_pilot",
        "analysis_mode": "descriptive_mechanistic_gate_only",
        "scientific_hypothesis_tested": False,
        "architecture_effect_estimated": False,
        "p_values_computed": False,
        "superiority_or_noninferiority_tested": False,
        "multiplicity_family_defined": False,
        "descriptive_mechanistic_summary": _descriptive_summary(rows, cases),
        "progression": {
            "passed": passed,
            "decision": (
                "pilot_design_gates_passed"
                if passed
                else "pilot_design_gates_failed_do_not_progress"
            ),
            "confirmatory_design_enabled": False,
        },
    }
    return analysis, qc
