from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from .analysis import validate_episode_cells
from .config import PARTITION_CODES, PILOT_STRATA, PilotConfig
from .dynamics import TruthState, propagate_exact
from .evaluator import RecoveryCorridor
from .policy import FrozenPolicy
from .runner import run_block
from .seeds import validate_pilot_manifest


def _subset_replicates(config: PilotConfig, partition: str, count: int) -> dict[str, list[int]]:
    output = {}
    for stratum_index, stratum in enumerate(PILOT_STRATA, start=1):
        rng = np.random.Generator(
            np.random.PCG64DXSM(
                np.random.SeedSequence(
                    [config.master_seed, PARTITION_CODES[partition], stratum_index]
                )
            )
        )
        output[stratum] = sorted(
            int(value) for value in rng.choice(config.seeds_per_stratum, size=count, replace=False)
        )
    return output


def write_qc_subsets(config: PilotConfig, path: str | Path) -> dict[str, Any]:
    payload = {
        "schema_version": config.schema_version,
        "replay": _subset_replicates(config, "replay_subset", config.replay_blocks_per_stratum),
        "command_rate_sensitivity": _subset_replicates(
            config,
            "command_rate_subset",
            config.command_rate_blocks_per_stratum,
        ),
    }
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _rows_by_key(path: str | Path) -> dict[tuple[str, int, str], dict[str, Any]]:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    return {(row["stratum_id"], int(row["replicate"]), row["arm"]): row for row in rows}


def _values_equal(expected: Any, observed: Any, atol: float, rtol: float) -> bool:
    if isinstance(expected, dict) and isinstance(observed, dict):
        return expected.keys() == observed.keys() and all(
            _values_equal(expected[key], observed[key], atol, rtol) for key in expected
        )
    if isinstance(expected, float) or isinstance(observed, float):
        if expected is None or observed is None:
            return expected is observed
        return bool(math.isclose(float(expected), float(observed), abs_tol=atol, rel_tol=rtol))
    return expected == observed


def replay_check(
    episodes_path: str | Path,
    subset: dict[str, list[int]],
    config: PilotConfig,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    config_hash: str,
) -> dict[str, Any]:
    expected = _rows_by_key(episodes_path)
    compared = 0
    failures = []
    for stratum, replicates in subset.items():
        for replicate in replicates:
            rerun = run_block(config, stratum, replicate, policy, corridor, config_hash)
            for result in rerun:
                key = (stratum, replicate, result.arm)
                compared += 1
                if not _values_equal(
                    expected[key],
                    result.to_dict(),
                    config.float_absolute_tolerance,
                    config.float_relative_tolerance,
                ):
                    if len(failures) < 20:
                        failures.append(
                            {"stratum": stratum, "replicate": replicate, "arm": result.arm}
                        )
    return {"passed": not failures, "episodes_compared": compared, "failures_preview": failures}


def command_rate_sensitivity_check(
    episodes_path: str | Path,
    subset: dict[str, list[int]],
    config: PilotConfig,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    config_hash: str,
) -> dict[str, Any]:
    baseline = _rows_by_key(episodes_path)
    classification_failures = []
    separation_failures = []
    propellant_failures = []
    comparisons = 0
    max_separation_change = 0.0
    max_propellant_change = 0.0
    for stratum, replicates in subset.items():
        for replicate in replicates:
            for period in (0.5, 0.25):
                rerun = run_block(
                    config,
                    stratum,
                    replicate,
                    policy,
                    corridor,
                    config_hash,
                    command_period_s=period,
                )
                for result in rerun:
                    comparisons += 1
                    original = baseline[(stratum, replicate, result.arm)]
                    changed_class = any(
                        original[field] != result.to_dict()[field]
                        for field in (
                            "collision",
                            "physical_hazard_observed",
                            "sustained_success",
                        )
                    )
                    if changed_class and len(classification_failures) < 20:
                        classification_failures.append(
                            {
                                "stratum": stratum,
                                "replicate": replicate,
                                "arm": result.arm,
                                "period_s": period,
                            }
                        )
                    separation_change = abs(
                        float(original["minimum_range_m"]) - result.minimum_range_m
                    )
                    propellant_change = abs(
                        float(original["propellant_used_fraction"])
                        - result.propellant_used_fraction
                    )
                    max_separation_change = max(max_separation_change, separation_change)
                    max_propellant_change = max(max_propellant_change, propellant_change)
                    if separation_change >= 0.05 and len(separation_failures) < 20:
                        separation_failures.append(
                            {
                                "stratum": stratum,
                                "replicate": replicate,
                                "arm": result.arm,
                                "period_s": period,
                                "change_m": separation_change,
                            }
                        )
                    if propellant_change >= 0.01 and len(propellant_failures) < 20:
                        propellant_failures.append(
                            {
                                "stratum": stratum,
                                "replicate": replicate,
                                "arm": result.arm,
                                "period_s": period,
                                "absolute_fraction_change": propellant_change,
                            }
                        )
    passed = not classification_failures and not separation_failures and not propellant_failures
    return {
        "passed": passed,
        "comparisons": comparisons,
        "thresholds": {
            "classification_changes": 0,
            "minimum_range_absolute_change_m": "<0.05",
            "propellant_used_absolute_fraction_change": "<0.01",
        },
        "maximum_minimum_range_change_m": max_separation_change,
        "maximum_propellant_used_change_fraction": max_propellant_change,
        "classification_failures_preview": classification_failures,
        "separation_failures_preview": separation_failures,
        "propellant_failures_preview": propellant_failures,
    }


def _rk4_fixture(
    initial: TruthState,
    command: float,
    effectiveness: float,
    disturbance: float,
    duration: float,
    config: PilotConfig,
    steps: int,
) -> TruthState:
    dt = duration / steps
    vector = np.array(
        [
            initial.range_m,
            initial.relative_velocity_mps,
            initial.achieved_acceleration_mps2,
            initial.propellant,
        ],
        dtype=np.float64,
    )
    target = effectiveness * command

    def derivative(values: np.ndarray) -> np.ndarray:
        return np.array(
            [
                values[1],
                values[2] + disturbance,
                (target - values[2]) / config.actuator_time_constant_s,
                -config.propellant_cost_per_delta_v * abs(values[2]),
            ]
        )

    for _ in range(steps):
        k1 = derivative(vector)
        k2 = derivative(vector + 0.5 * dt * k1)
        k3 = derivative(vector + 0.5 * dt * k2)
        k4 = derivative(vector + dt * k3)
        vector += dt * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0
    return TruthState(
        initial.time_s + duration,
        float(vector[0]),
        float(vector[1]),
        float(vector[3]),
        float(vector[2]),
    )


def numerical_integration_check(config: PilotConfig) -> dict[str, Any]:
    fixtures = [
        (TruthState(0.0, 20.0, -0.2, 0.9, 0.01), 0.04, 1.0, -0.002),
        (TruthState(0.0, 80.0, -0.1, 0.95, -0.02), 0.05, 0.4, 0.003),
        (TruthState(0.0, 8.0, -0.04, 0.8, 0.03), 0.02, 0.7, -0.001),
    ]
    errors = []
    event_matches = []
    for initial, command, effectiveness, disturbance in fixtures:
        exact = propagate_exact(initial, command, effectiveness, disturbance, 1.0, config)
        rk4 = _rk4_fixture(initial, command, effectiveness, disturbance, 1.0, config, 4096)
        errors.append(
            max(
                abs(exact.state.range_m - rk4.range_m),
                abs(exact.state.relative_velocity_mps - rk4.relative_velocity_mps),
                abs(exact.state.achieved_acceleration_mps2 - rk4.achieved_acceleration_mps2),
                abs(exact.state.propellant - rk4.propellant),
            )
        )
        event_matches.append(
            (exact.collision_time_s is not None) == (rk4.range_m <= config.collision_range_m)
        )
    maximum_error = max(errors)
    return {
        "passed": maximum_error <= 1e-10 and all(event_matches),
        "method": "fixed open-loop commands; exact propagator versus float64 RK4/4096",
        "command_times_changed": False,
        "maximum_absolute_state_error": maximum_error,
        "tolerance": 1e-10,
        "event_classifications_match": all(event_matches),
    }


def build_qc_report(
    episodes_path: str | Path,
    pilot_manifest_path: str | Path,
    subsets_path: str | Path,
    validation_evidence_path: str | Path,
    config: PilotConfig,
    policy: FrozenPolicy,
    corridor: RecoveryCorridor,
    config_hash: str,
    output_path: str | Path,
) -> dict[str, Any]:
    rows = [
        json.loads(line) for line in Path(episodes_path).read_text(encoding="utf-8").splitlines()
    ]
    subsets = json.loads(Path(subsets_path).read_text(encoding="utf-8"))
    validation = json.loads(Path(validation_evidence_path).read_text(encoding="utf-8"))
    cells = validate_episode_cells(rows, config)
    seeds = validate_pilot_manifest(config, pilot_manifest_path)
    replay = replay_check(episodes_path, subsets["replay"], config, policy, corridor, config_hash)
    integration = numerical_integration_check(config)
    rate = command_rate_sensitivity_check(
        episodes_path,
        subsets["command_rate_sensitivity"],
        config,
        policy,
        corridor,
        config_hash,
    )
    checks = [
        {
            "id": "tests_lint_lock",
            "category": "validity",
            "passed": bool(validation["passed"]),
            "observed": validation,
            "threshold": "all frozen-install, test, lint, and source scans pass",
        },
        {
            "id": "episode_cells",
            "category": "validity",
            "passed": bool(cells["valid"]),
            "observed": cells,
            "threshold": "2,400 complete blocks and 9,600 unique episode cells",
        },
        {
            "id": "seed_manifest",
            "category": "validity",
            "passed": bool(seeds["valid"]),
            "observed": seeds,
            "threshold": "400/stratum; exact 200/200 mixed components; zero hash drift",
        },
        {
            "id": "same_platform_replay",
            "category": "validity",
            "passed": bool(replay["passed"]),
            "observed": replay,
            "threshold": "40 frozen blocks/stratum; exact discrete and tolerance-bounded floats",
        },
        {
            "id": "numerical_integration",
            "category": "validity",
            "passed": bool(integration["passed"]),
            "observed": integration,
            "threshold": "fixed-command exact/RK4 max state error <=1e-10",
        },
        {
            "id": "command_rate_sensitivity",
            "category": "validity",
            "passed": bool(rate["passed"]),
            "observed": rate,
            "threshold": "separate 1/0.5/0.25 s closed-loop sensitivity gate",
        },
    ]
    report = {
        "schema_version": config.schema_version,
        "overall_passed": all(check["passed"] for check in checks),
        "checks": checks,
        "deviations": [],
        "corridor": asdict(corridor),
    }
    Path(output_path).write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
