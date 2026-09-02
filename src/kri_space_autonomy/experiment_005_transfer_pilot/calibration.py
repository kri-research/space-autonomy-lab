from __future__ import annotations

import json
import math
import platform
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import minimize_scalar

from kri_space_autonomy.experiment_004.config import (
    Experiment004Config,
)
from kri_space_autonomy.experiment_004.config import (
    load_config as load_e004_config,
)
from kri_space_autonomy.experiment_004.estimator import PlanarNavigationFilter
from kri_space_autonomy.experiment_004.measurements import (
    MeasurementFault,
    PlanarNavigationPacket,
)
from kri_space_autonomy.experiment_005.config import (
    Experiment005Config,
)
from kri_space_autonomy.experiment_005.config import (
    load_config as load_e005_config,
)
from kri_space_autonomy.experiment_005.dynamics import (
    pair_from_relative,
    pair_to_relative,
    two_body_pair_derivative,
)
from kri_space_autonomy.experiment_005.geometry import (
    NonlinearTruthSegment,
    admissible_position_excess_m,
    evaluate_truth_segment,
)

from .config import (
    TransferCase,
    TransferPilotConfig,
    load_case_matrix,
    load_pilot_config,
)
from .runner import run_episode
from .seeds import calibration_scenario, canonical_json, sha256_bytes

CALIBRATION_DIRECTORY = Path("experiments/005-transfer-pilot")
CALIBRATION_EVIDENCE_PATH = CALIBRATION_DIRECTORY / "calibration-evidence.json"
CALIBRATION_PROVENANCE_PATH = CALIBRATION_DIRECTORY / "calibration-provenance.json"


def _case_map(cases: tuple[TransferCase, ...]) -> dict[str, TransferCase]:
    return {case.id: case for case in cases}


def _run_primary_episode(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
    replicate: int,
):
    scenario, streams = calibration_scenario(pilot, foundation, e004, case, replicate)
    run_order = scenario.configuration_run_order.index("primary_reference") + 1
    return run_episode(
        pilot,
        foundation,
        e004,
        case,
        scenario,
        streams,
        "primary_reference",
        run_order,
    )


def _nominal_transfer(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
) -> dict[str, Any]:
    rows = []
    for replicate in range(pilot.pilot_roots_per_case):
        episode = _run_primary_episode(pilot, foundation, e004, case, replicate)
        rows.append(
            {
                "root_seed_id": episode.root_seed_id,
                "replicate": episode.replicate,
                "hold_acquired": episode.hold_acquired,
                "maximum_contiguous_hold_dwell_s": (
                    episode.maximum_contiguous_hold_dwell_s
                ),
                "collision": episode.physical_collision,
                "keep_out_entry": episode.physical_keep_out_entry,
                "corridor_departure": episode.physical_corridor_departure,
                "minimum_separation_m": episode.minimum_separation_m,
                "minimum_covariance_eigenvalue": episode.minimum_covariance_eigenvalue,
                "maximum_covariance_trace": episode.maximum_covariance_trace,
                "nonlinear_truth_numerical_valid": (
                    episode.nonlinear_truth_numerical_valid
                ),
                "model_mismatch_observations": episode.model_mismatch_observations,
                "maximum_hcw_position_residual_m": (
                    episode.maximum_hcw_position_residual_m
                ),
                "maximum_hcw_velocity_residual_mps": (
                    episode.maximum_hcw_velocity_residual_mps
                ),
                "trace_digest": episode.trace_digest,
            }
        )
    passed = all(
        row["hold_acquired"]
        and row["nonlinear_truth_numerical_valid"]
        and row["minimum_covariance_eigenvalue"] >= -1e-12
        and row["maximum_covariance_trace"] < 1_000_000.0
        for row in rows
    )
    replay = _run_primary_episode(pilot, foundation, e004, case, 0)
    replay_passed = replay.trace_digest == rows[0]["trace_digest"]
    return {
        "passed": bool(passed and replay_passed),
        "configuration_used": "primary_reference only; no configuration contrast computed",
        "horizon_s": pilot.standard_horizon_s,
        "physical_events_reported_but_not_used_as_a_favorable_gate": True,
        "roots": rows,
        "deterministic_replay": {
            "passed": replay_passed,
            "root_seed_id": rows[0]["root_seed_id"],
            "first_digest": rows[0]["trace_digest"],
            "replay_digest": replay.trace_digest,
        },
    }


def _model_mismatch_observability(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
) -> dict[str, Any]:
    episode = _run_primary_episode(pilot, foundation, e004, case, 0)
    passed = bool(
        episode.nonlinear_truth_numerical_valid
        and episode.model_mismatch_observations == round(pilot.model_mismatch_horizon_s)
        and np.isfinite(episode.maximum_hcw_position_residual_m)
        and np.isfinite(episode.maximum_hcw_velocity_residual_mps)
        and episode.maximum_hcw_position_residual_m > 0.0
        and episode.maximum_hcw_velocity_residual_mps > 0.0
        and episode.primary_fault_active_packets == 0
        and episode.monitor_fault_active_packets == 0
        and not episode.actuation_degradation_scheduled
        and not episode.disturbance_scheduled
    )
    return {
        "passed": passed,
        "root_seed_id": episode.root_seed_id,
        "horizon_s": pilot.model_mismatch_horizon_s,
        "observations": episode.model_mismatch_observations,
        "maximum_hcw_position_residual_m": episode.maximum_hcw_position_residual_m,
        "maximum_hcw_velocity_residual_mps": episode.maximum_hcw_velocity_residual_mps,
        "injected_sensor_fault": False,
        "mechanics_noise_enabled": False,
        "navigation_noise_enabled": False,
        "absolute_favorable_or_unfavorable_threshold": None,
        "interpretation": "descriptive observability diagnostic only",
    }


def _reference_minimum_separation(
    initial_pair: np.ndarray,
    command: np.ndarray,
    foundation: Experiment005Config,
    *,
    rtol: float,
) -> tuple[float, float, np.ndarray]:
    atol = np.array([1e-9] * 3 + [1e-12] * 3 + [1e-9] * 3 + [1e-12] * 3)
    solution = solve_ivp(
        lambda _time, state: two_body_pair_derivative(
            state, command, foundation.gravitational_parameter_m3_s2
        ),
        (0.0, 1.0),
        initial_pair,
        method="DOP853",
        rtol=rtol,
        atol=atol,
        max_step=0.02,
        dense_output=True,
    )
    if not solution.success or solution.sol is None:
        raise RuntimeError("DOP853 event-calibration reference failed")

    def separation(time_s: float) -> float:
        relative = pair_to_relative(np.asarray(solution.sol(time_s), dtype=np.float64))
        return float(np.linalg.norm(relative[:3]))

    result = minimize_scalar(
        separation,
        bounds=(0.0, 1.0),
        method="bounded",
        options={"xatol": 1e-14, "maxiter": 500},
    )
    endpoints = [(separation(0.0), 0.0), (separation(1.0), 1.0)]
    candidates = endpoints + ([(float(result.fun), float(result.x))] if result.success else [])
    minimum, time_s = min(candidates)
    return minimum, time_s, np.asarray(solution.y[:, -1], dtype=np.float64)


def _event_geometry_calibration(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    case: TransferCase,
) -> dict[str, Any]:
    scenario, _ = calibration_scenario(pilot, foundation, e004, case, 0)
    chief = np.array(
        [
            foundation.reference_radius_m,
            0.0,
            0.0,
            0.0,
            math.sqrt(
                foundation.gravitational_parameter_m3_s2 / foundation.reference_radius_m
            ),
            0.0,
        ],
        dtype=np.float64,
    )
    initial_pair = pair_from_relative(
        chief, np.asarray(scenario.initial_relative_state, dtype=np.float64)
    )
    command = np.array([0.0, 0.0, 0.0])
    step_results: dict[str, dict[str, Any]] = {}
    minima: list[float] = []
    finals: list[np.ndarray] = []
    for step in (0.2, 0.1, 0.05):
        variant = replace(foundation, production_max_step_s=step)
        segment = NonlinearTruthSegment(initial_pair, command, variant, 1.0)
        result = evaluate_truth_segment(segment, variant, boundary_tolerance_m=1e-9)
        final = segment.state_at(1.0)
        minima.append(result.minimum_separation_m)
        finals.append(final)
        step_results[str(step)] = {
            "collision": result.collision,
            "keep_out_entry": result.keep_out_entry,
            "minimum_separation_m": result.minimum_separation_m,
            "minimum_separation_time_s": result.minimum_separation_time_s,
            "final_pair_sha256": sha256_bytes(np.asarray(final, dtype="<f8").tobytes()),
        }
    reference_loose = _reference_minimum_separation(
        initial_pair, command, foundation, rtol=1e-11
    )
    reference_tight = _reference_minimum_separation(
        initial_pair, command, foundation, rtol=1e-12
    )
    production_spread = max(minima) - min(minima)
    reference_spread = abs(reference_loose[0] - reference_tight[0])
    endpoint_spread = float(np.max(np.abs(reference_loose[2] - reference_tight[2])))
    empirical_enclosure = 10.0 * max(
        production_spread,
        reference_spread,
        endpoint_spread,
        np.finfo(float).eps,
    )
    minimum = reference_tight[0]
    classification_margin = min(
        abs(minimum - foundation.hard_body_radius_m),
        abs(minimum - foundation.keep_out_radius_m),
    )
    ambiguous = classification_margin <= empirical_enclosure
    patterns = [
        (value["collision"], value["keep_out_entry"])
        for value in step_results.values()
    ]
    crossing_stable = all(pattern == (False, True) for pattern in patterns)

    boundary = NonlinearTruthSegment(
        pair_from_relative(chief, np.array([0.0, -10.0, 0.0, 0.0, 0.0, 0.0])),
        command,
        foundation,
        0.01,
    )
    boundary_result = evaluate_truth_segment(
        boundary, foundation, boundary_tolerance_m=0.0
    )
    union_state = np.array([0.0, -30.0, 0.0, 0.0, 0.0, 0.0])
    union_closed = admissible_position_excess_m(union_state, foundation) <= 0.0
    departure_states = {
        "radial": np.array([8.0, -50.0, 0.0, 0.0, 0.0, 0.0]),
        "lower": np.array([0.0, -101.0, 0.0, 0.0, 0.0, 0.0]),
        "upper": np.array([0.0, -26.0, 0.0, 0.0, 0.0, 0.0]),
    }
    departures = {}
    for name, relative in departure_states.items():
        segment = NonlinearTruthSegment(
            pair_from_relative(chief, relative), command, foundation, 0.01
        )
        departures[name] = evaluate_truth_segment(segment, foundation).corridor_departure
    passed = bool(
        crossing_stable
        and not ambiguous
        and reference_tight[0] > foundation.hard_body_radius_m
        and reference_tight[0] < foundation.keep_out_radius_m
        and boundary_result.keep_out_entry
        and not boundary_result.collision
        and union_closed
        and all(departures.values())
    )
    return {
        "passed": passed,
        "root_seed_id": scenario.root_seed_id,
        "step_refinement": step_results,
        "DOP853_reference": {
            "loose_rtol": 1e-11,
            "tight_rtol": 1e-12,
            "loose_minimum_separation_m": reference_loose[0],
            "tight_minimum_separation_m": reference_tight[0],
            "tight_minimum_time_s": reference_tight[1],
            "minimum_spread_m": reference_spread,
            "endpoint_max_abs_spread": endpoint_spread,
        },
        "production_minimum_spread_m": production_spread,
        "empirical_numerical_enclosure_m": empirical_enclosure,
        "classification_margin_m": classification_margin,
        "numerically_ambiguous": ambiguous,
        "expected_pattern": {"collision": False, "keep_out_entry": True},
        "closed_keep_out_boundary": bool(
            boundary_result.keep_out_entry and not boundary_result.collision
        ),
        "closed_approach_hold_union_seam": bool(union_closed),
        "fail_closed_departures": departures,
        "certification_claimed": False,
        "interpretation": (
            "independent step/tolerance stability and large-margin classification; "
            "not a formal interval-arithmetic certificate"
        ),
    }


def _fault_activation(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
) -> dict[str, Any]:
    records = []
    passed = True
    for case in cases:
        if case.fault == "none":
            continue
        for replicate in range(pilot.pilot_roots_per_case):
            scenario, _ = calibration_scenario(pilot, foundation, e004, case, replicate)
            sample_time = (
                None
                if scenario.fault_onset_s is None
                else float(np.ceil(scenario.fault_onset_s))
            )
            primary_active = False
            monitor_active = False
            if scenario.measurement_fault_kind != "none" and sample_time is not None:
                fault = MeasurementFault(
                    scenario.measurement_fault_kind,
                    scenario.measurement_fault_channel,
                    scenario.fault_onset_s,
                    scenario.fault_end_s,
                    scenario.additive_bias,
                    scenario.covariance_factor,
                )
                primary_active = fault.active(sample_time, "primary")
                monitor_active = fault.active(sample_time, "monitor")
                expected = {
                    "primary": (True, False),
                    "monitor": (False, True),
                    "shared": (True, True),
                }[scenario.measurement_fault_channel]
                passed = passed and (primary_active, monitor_active) == expected
            else:
                passed = passed and sample_time is not None
            records.append(
                {
                    "case_id": case.id,
                    "root_seed_id": scenario.root_seed_id,
                    "replicate": replicate,
                    "fault_kind": scenario.measurement_fault_kind,
                    "fault_channel": scenario.measurement_fault_channel,
                    "onset_s": scenario.fault_onset_s,
                    "end_s": scenario.fault_end_s,
                    "sample_time_s": sample_time,
                    "primary_active": primary_active,
                    "monitor_active": monitor_active,
                    "monitor_logic_fault": scenario.monitor_logic_fault,
                    "actuation_effectiveness": scenario.actuation_effectiveness,
                    "disturbance_bias_mps2": list(scenario.disturbance_bias_mps2),
                }
            )
    return {"passed": bool(passed), "records": records}


def _exact_packet(
    filter_: PlanarNavigationFilter,
    sequence: int,
    time_s: float,
    state: np.ndarray,
) -> PlanarNavigationPacket:
    return PlanarNavigationPacket(
        sequence,
        time_s,
        time_s,
        state,
        filter_.nominal_measurement_covariance,
    )


def _filter_fault_sanity(
    e004: Experiment004Config, bias: tuple[float, ...]
) -> dict[str, Any]:
    filter_ = PlanarNavigationFilter(e004)
    state = e004.initial_mean_array
    filter_.ingest(_exact_packet(filter_, 0, 0.0, state))
    for step in range(1, 11):
        filter_.advance(np.zeros(2), float(step))
        state = filter_.snapshot().mean
        filter_.ingest(_exact_packet(filter_, step, float(step), state))
    filter_.advance(np.zeros(2), 11.0)
    biased = PlanarNavigationPacket(
        11,
        11.0,
        11.0,
        filter_.snapshot().mean + np.asarray(bias),
        filter_.nominal_measurement_covariance,
    )
    bias_disposition = filter_.ingest(biased).disposition.value
    dropout = PlanarNavigationFilter(e004)
    dropout.ingest(_exact_packet(dropout, 0, 0.0, e004.initial_mean_array))
    for step in range(1, 5):
        dropout.advance(np.zeros(2), float(step))
    snapshot = dropout.snapshot()
    passed = bool(
        bias_disposition == "innovation_rejected"
        and snapshot.health.value == "degraded"
        and snapshot.prediction_only_age_s == 4.0
    )
    return {
        "passed": passed,
        "bias_disposition": bias_disposition,
        "dropout_health_after_four_seconds": snapshot.health.value,
        "dropout_prediction_only_age_s": snapshot.prediction_only_age_s,
    }


def _actuation_and_disturbance_sanity(
    pilot: TransferPilotConfig, foundation: Experiment005Config
) -> dict[str, Any]:
    chief = np.array(
        [
            foundation.reference_radius_m,
            0.0,
            0.0,
            0.0,
            math.sqrt(
                foundation.gravitational_parameter_m3_s2 / foundation.reference_radius_m
            ),
            0.0,
        ]
    )
    initial = pair_from_relative(chief, foundation.initial_relative_state)
    command = np.array([0.005, 0.01, 0.0])
    duration = 0.25
    full = NonlinearTruthSegment(initial, command, foundation, duration).state_at(duration)
    degraded = NonlinearTruthSegment(
        initial, pilot.actuation_effectiveness * command, foundation, duration
    ).state_at(duration)
    disturbed_command = command + np.array([*pilot.disturbance_bias_mps2, 0.0])
    disturbed = NonlinearTruthSegment(
        initial, disturbed_command, foundation, duration
    ).state_at(duration)
    degraded_delta = float(np.linalg.norm(full - degraded))
    disturbance_delta = float(np.linalg.norm(full - disturbed))
    return {
        "passed": bool(degraded_delta > 0.0 and disturbance_delta > 0.0),
        "reference_command_mps2": command.tolist(),
        "actuation_effectiveness": pilot.actuation_effectiveness,
        "degraded_pair_state_delta_norm": degraded_delta,
        "disturbance_bias_mps2": list(pilot.disturbance_bias_mps2),
        "disturbed_pair_state_delta_norm": disturbance_delta,
    }


def _order_and_count_coverage(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
) -> dict[str, Any]:
    per_case = {}
    for case in cases:
        first_positions = []
        for replicate in range(pilot.pilot_roots_per_case):
            scenario, _ = calibration_scenario(pilot, foundation, e004, case, replicate)
            first_positions.append(scenario.configuration_run_order[0])
        counts = {
            configuration: first_positions.count(configuration)
            for configuration in pilot.configuration_ids
        }
        per_case[case.id] = counts
    mechanics_coverage = all(
        all(
            count >= pilot.minimum_order_appearances_per_position_per_case
            for count in counts.values()
        )
        for counts in per_case.values()
    )
    candidates = [
        {
            "roots_per_case": 1,
            "order_appearances_per_position": 0,
            "passes": False,
            "reason": "cannot place both diagnostic configurations in both order positions",
        },
        {
            "roots_per_case": 2,
            "order_appearances_per_position": 1,
            "passes": mechanics_coverage,
            "reason": "smallest count covering every case and both within-block order positions",
        },
    ]
    return {
        "passed": mechanics_coverage,
        "per_case_first_position_counts": per_case,
        "candidate_evaluations": candidates,
        "selected_roots_per_case": 2 if mechanics_coverage else None,
        "selected_blocks": 20 if mechanics_coverage else None,
        "selected_episodes": 40 if mechanics_coverage else None,
        "statistical_power_interpretation": False,
    }


def run_calibration(
    pilot: TransferPilotConfig,
    foundation: Experiment005Config,
    e004: Experiment004Config,
    cases: tuple[TransferCase, ...],
    *,
    attempt_number: int,
) -> dict[str, Any]:
    case_map = _case_map(cases)
    nominal = _nominal_transfer(
        pilot, foundation, e004, case_map["T00_nominal_transfer"]
    )
    mismatch = _model_mismatch_observability(
        pilot,
        foundation,
        e004,
        case_map["T01_truth_model_mismatch_stress"],
    )
    geometry = _event_geometry_calibration(
        pilot,
        foundation,
        e004,
        case_map["T02_truth_keep_out_crossing_fixture"],
    )
    faults = _fault_activation(pilot, foundation, e004, cases)
    filters = _filter_fault_sanity(e004, pilot.navigation_bias)
    actuation = _actuation_and_disturbance_sanity(pilot, foundation)
    coverage = _order_and_count_coverage(pilot, foundation, e004, cases)
    checks = {
        "nominal_transfer_feasibility": nominal,
        "model_mismatch_observability": mismatch,
        "truth_event_geometry_stability": geometry,
        "fault_domain_activation": faults,
        "filter_fault_plumbing": filters,
        "actuation_disturbance_path": actuation,
        "outcome_blind_order_and_count_coverage": coverage,
    }
    passed = all(check["passed"] for check in checks.values())
    return {
        "schema_version": pilot.schema_version,
        "phase": "prospective_partition_51_mechanics_calibration",
        "attempt_number": attempt_number,
        "status": "CALIBRATION_PASS" if passed else "CALIBRATION_FAIL",
        "passed": passed,
        "partition_code": 51,
        "checks": checks,
        "permitted_information_used": [
            "nonlinear nominal feasibility and horizon practicality",
            "finite estimator covariance",
            "descriptive nonlinear-truth versus HCW residual observability",
            "truth-event classification under step and reference refinement",
            "closed event-boundary and admissible-union behavior",
            "navigation, monitor-logic, shared-cause, actuation, and disturbance activation",
            "deterministic mechanics replay",
            "within-block order and design-validation coverage",
        ],
        "prohibited_information_used": [],
        "architecture_configuration_difference_computed": False,
        "architecture_benefit_or_hazard_discordance_computed": False,
        "scientific_hypothesis_selected": False,
        "controller_or_policy_selected_or_fitted": False,
        "experiment_004_outcomes_used": False,
        "pilot_outcomes_generated": False,
        "partition_52_materialized": False,
        "partition_52_executed": False,
        "partition_53_touched": False,
        "sample_count_selection": {
            "basis": "design-validation coverage and one appearance in each order position",
            "selected_roots_per_case": coverage["selected_roots_per_case"],
            "selected_blocks": coverage["selected_blocks"],
            "selected_episodes": coverage["selected_episodes"],
            "statistical_power_interpretation": False,
        },
    }


def _write_json_no_clobber(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def calibrate(root: str | Path = ".") -> dict[str, Any]:
    project = Path(root)
    if (project / CALIBRATION_EVIDENCE_PATH).exists():
        raise RuntimeError("refusing to overwrite completed partition-51 calibration evidence")
    forbidden = (
        project / "experiments/005-transfer-pilot/seeds",
        project / "results/experiment-005-transfer-pilot",
        project / "experiments/005-confirmatory",
        project / "results/experiment-005-confirmatory",
    )
    if any(path.exists() for path in forbidden):
        raise RuntimeError("calibration requires partitions 52 and 53 to remain absent")
    existing = sorted((project / CALIBRATION_DIRECTORY).glob("calibration-attempt-*.json"))
    attempt_number = len(existing) + 1
    attempt_path = (
        project
        / CALIBRATION_DIRECTORY
        / f"calibration-attempt-{attempt_number:03d}.json"
    )
    pilot = load_pilot_config(project / CALIBRATION_DIRECTORY / "config.json", root=project)
    foundation = load_e005_config(project / "experiments/005/config.json", root=project)
    e004 = load_e004_config(project / "experiments/004/config.json")
    cases = load_case_matrix(project / CALIBRATION_DIRECTORY / "case-matrix.json")
    try:
        result = run_calibration(
            pilot,
            foundation,
            e004,
            cases,
            attempt_number=attempt_number,
        )
    except BaseException as exc:
        message = f"{type(exc).__name__}:{exc}"
        failure = {
            "schema_version": pilot.schema_version,
            "phase": "prospective_partition_51_mechanics_calibration",
            "attempt_number": attempt_number,
            "status": "CALIBRATION_EXCEPTION_TERMINAL",
            "passed": False,
            "partition_code": 51,
            "execution_began": True,
            "exception_class": type(exc).__name__,
            "exception_message_sha256": sha256_bytes(message.encode()),
            "platform": platform.system(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "retry_or_replacement_allowed": False,
            "partition_52_materialized": False,
            "partition_53_touched": False,
        }
        failure["calibration_id"] = sha256_bytes(canonical_json(failure))
        _write_json_no_clobber(attempt_path, failure)
        raise
    result["calibration_id"] = sha256_bytes(canonical_json(result))
    _write_json_no_clobber(attempt_path, result)
    if result["passed"]:
        _write_json_no_clobber(project / CALIBRATION_EVIDENCE_PATH, result)
    provenance = {
        "schema_version": pilot.schema_version,
        "partition_code": 51,
        "attempts": [
            {
                "artifact": path.relative_to(project).as_posix(),
                "sha256": sha256_bytes(path.read_bytes()),
                "status": json.loads(path.read_text())["status"],
                "preserved": True,
            }
            for path in sorted(
                (project / CALIBRATION_DIRECTORY).glob("calibration-attempt-*.json")
            )
        ],
        "final_evidence": (
            CALIBRATION_EVIDENCE_PATH.as_posix() if result["passed"] else None
        ),
        "failed_attempts_deleted_or_retried": False,
        "architecture_comparisons_used": False,
        "partition_52_materialized": False,
        "partition_53_touched": False,
    }
    provenance_path = project / CALIBRATION_PROVENANCE_PATH
    if provenance_path.exists():
        archived = (
            provenance_path.parent
            / f"calibration-provenance-attempt-{attempt_number - 1:03d}.json"
        )
        provenance_path.rename(archived)
    _write_json_no_clobber(provenance_path, provenance)
    return result


def verify_calibration(
    root: str | Path = ".", *, recompute: bool = True
) -> dict[str, Any]:
    project = Path(root)
    path = project / CALIBRATION_EVIDENCE_PATH
    errors: list[str] = []
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
        calibration_id = evidence.pop("calibration_id")
        if calibration_id != sha256_bytes(canonical_json(evidence)):
            errors.append("calibration_self_hash")
    except (OSError, KeyError, json.JSONDecodeError):
        return {"passed": False, "errors_preview": ["calibration_evidence_load"]}
    if recompute:
        pilot = load_pilot_config(
            project / CALIBRATION_DIRECTORY / "config.json", root=project
        )
        foundation = load_e005_config(
            project / "experiments/005/config.json", root=project
        )
        e004 = load_e004_config(project / "experiments/004/config.json")
        cases = load_case_matrix(project / CALIBRATION_DIRECTORY / "case-matrix.json")
        observed = run_calibration(
            pilot,
            foundation,
            e004,
            cases,
            attempt_number=int(evidence["attempt_number"]),
        )
        if observed != evidence:
            errors.append("calibration_recompute_mismatch")
    provenance_path = project / CALIBRATION_PROVENANCE_PATH
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        attempts = provenance["attempts"]
        attempts_ok = bool(
            attempts
            and all(
                (project / item["artifact"]).is_file()
                and sha256_bytes((project / item["artifact"]).read_bytes())
                == item["sha256"]
                and item["preserved"] is True
                for item in attempts
            )
        )
    except (OSError, KeyError, json.JSONDecodeError):
        attempts_ok = False
    if not attempts_ok:
        errors.append("calibration_attempt_provenance")
    if not evidence.get("passed") or evidence.get("partition_code") != 51:
        errors.append("calibration_not_passed_or_wrong_partition")
    if evidence.get("architecture_configuration_difference_computed") is not False:
        errors.append("comparative_calibration_field")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "calibration_id": calibration_id,
        "evidence_sha256": sha256_bytes(path.read_bytes()),
        "provenance_sha256": (
            sha256_bytes(provenance_path.read_bytes()) if provenance_path.is_file() else None
        ),
        "attempts_preserved": len(attempts) if attempts_ok else 0,
        "selected_roots_per_case": evidence.get("sample_count_selection", {}).get(
            "selected_roots_per_case"
        ),
        "pilot_outcomes_generated": evidence.get("pilot_outcomes_generated"),
        "architecture_configuration_difference_computed": evidence.get(
            "architecture_configuration_difference_computed"
        ),
        "partition_52_materialized": evidence.get("partition_52_materialized"),
        "partition_53_touched": evidence.get("partition_53_touched"),
    }
