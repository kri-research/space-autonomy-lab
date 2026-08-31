from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from kri_space_autonomy.experiment_004.config import Experiment004Config, load_config
from kri_space_autonomy.experiment_004.control import (
    DeterministicHoldController,
    observation_from_snapshot,
)
from kri_space_autonomy.experiment_004.estimator import PlanarNavigationFilter
from kri_space_autonomy.experiment_004.evaluation import IndependentPlanarEvaluator
from kri_space_autonomy.experiment_004.geometry import HCWSegment, evaluate_segment
from kri_space_autonomy.experiment_004.measurements import (
    MeasurementFault,
    PlanarNavigationPacket,
)

from .config import PilotCase, PilotConfig, load_case_matrix, load_pilot_config
from .seeds import calibration_scenario, canonical_json, sha256_bytes

CALIBRATION_PATH = Path("experiments/004-pilot/calibration-evidence.json")


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


def _nominal_mechanics(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
) -> dict[str, Any]:
    scenario, _ = calibration_scenario(pilot, foundation, case, replicate)
    filter_ = PlanarNavigationFilter(foundation)
    controller = DeterministicHoldController(foundation)
    evaluator = IndependentPlanarEvaluator(foundation)
    state = np.asarray(scenario.initial_state, dtype=np.float64)
    first = _exact_packet(filter_, 0, 0.0, state)
    initial_disposition = filter_.ingest(first).disposition.value
    minimum_eigenvalue = float(np.linalg.eigvalsh(filter_.snapshot().covariance)[0])
    maximum_trace = float(np.trace(filter_.snapshot().covariance))
    digest = hashlib.sha256()
    for step in range(round(pilot.standard_horizon_s)):
        command = controller.decide(
            observation_from_snapshot(filter_.snapshot())
        ).acceleration_mps2
        segment = HCWSegment(
            state,
            command,
            foundation.mean_motion_rad_s,
            foundation.command_period_s,
            maximum_duration_s=foundation.event_interval_max_s,
        )
        evaluator.observe(segment)
        state = segment.state_at(foundation.command_period_s)
        next_time = float(step + 1)
        filter_.advance(command, next_time)
        disposition = filter_.ingest(
            _exact_packet(filter_, step + 1, next_time, state)
        ).disposition.value
        snapshot = filter_.snapshot()
        minimum_eigenvalue = min(
            minimum_eigenvalue,
            float(np.linalg.eigvalsh(snapshot.covariance)[0]),
        )
        maximum_trace = max(maximum_trace, float(np.trace(snapshot.covariance)))
        digest.update(np.asarray(state, dtype="<f8").tobytes())
        digest.update(np.asarray(command, dtype="<f8").tobytes())
        digest.update(disposition.encode())
    summary = evaluator.finalize()
    return {
        "root_seed_id": scenario.root_seed_id,
        "replicate": replicate,
        "initial_state": list(scenario.initial_state),
        "initial_disposition": initial_disposition,
        "hold_acquired": summary.mission.hold_acquired,
        "collision": summary.physical.collision,
        "keep_out_entry": summary.physical.unauthorized_keep_out_entry,
        "corridor_departure": summary.physical.corridor_departure,
        "minimum_separation_m": summary.physical.minimum_separation_m,
        "minimum_covariance_eigenvalue": minimum_eigenvalue,
        "maximum_covariance_trace": maximum_trace,
        "digest": digest.hexdigest(),
    }


def _forced_event_mechanics(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    case: PilotCase,
    replicate: int,
) -> dict[str, Any]:
    scenario, streams = calibration_scenario(pilot, foundation, case, replicate)
    state = np.asarray(scenario.initial_state, dtype=np.float64)
    evaluator = IndependentPlanarEvaluator(foundation)
    command = np.asarray(scenario.fixture_command_mps2, dtype=np.float64)
    substeps = round(
        foundation.command_period_s / foundation.process_acceleration_draw_period_s
    )
    for substep in range(substeps):
        realized = (
            command
            + streams.actuator_uncertainty_mps2[0]
            + streams.process_acceleration_mps2[substep]
        )
        segment = HCWSegment(
            state,
            realized,
            foundation.mean_motion_rad_s,
            foundation.process_acceleration_draw_period_s,
            maximum_duration_s=foundation.event_interval_max_s,
        )
        evaluator.observe(segment)
        state = segment.state_at(foundation.process_acceleration_draw_period_s)
    summary = evaluator.finalize()
    return {
        "root_seed_id": scenario.root_seed_id,
        "replicate": replicate,
        "collision": summary.physical.collision,
        "keep_out_entry": summary.physical.unauthorized_keep_out_entry,
        "corridor_departure": summary.physical.corridor_departure,
        "minimum_separation_m": summary.physical.minimum_separation_m,
        "maximum_corridor_excess_m": summary.physical.maximum_corridor_excess_m,
        "final_state": [float(value) for value in state],
    }


def _event_tolerance_check(
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
) -> dict[str, Any]:
    patterns = {}
    expected = {
        "P01_forced_collision": (True, True, False),
        "P02_forced_keep_out_only": (False, True, False),
        "P03_forced_corridor_departure": (False, False, True),
    }
    for case in cases:
        if case.id not in expected:
            continue
        segment = HCWSegment(
            np.asarray(case.initial_state, dtype=np.float64),
            np.asarray(case.fixture_command_mps2, dtype=np.float64),
            foundation.mean_motion_rad_s,
            1.0,
            maximum_duration_s=foundation.event_interval_max_s,
        )
        observed = []
        for tolerance in (0.0, 1e-9, 1e-8):
            result = evaluate_segment(segment, foundation, boundary_tolerance_m=tolerance)
            observed.append(
                [result.collision, result.keep_out_entry, result.corridor_departure]
            )
        patterns[case.id] = observed
    return {
        "passed": all(
            all(tuple(value) == expected[case_id] for value in observed)
            for case_id, observed in patterns.items()
        ),
        "boundary_tolerances_m": [0.0, 1e-9, 1e-8],
        "patterns": patterns,
    }


def _fault_activation(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
) -> dict[str, Any]:
    records = []
    passed = True
    for case in cases:
        if case.fault == "none":
            continue
        for replicate in range(pilot.pilot_roots_per_case):
            scenario, _ = calibration_scenario(pilot, foundation, case, replicate)
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


def _filter_fault_sanity(
    foundation: Experiment004Config,
    bias: tuple[float, ...],
) -> dict[str, Any]:
    filter_ = PlanarNavigationFilter(foundation)
    state = foundation.initial_mean_array
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
        filter_.snapshot().mean + np.asarray(bias, dtype=np.float64),
        filter_.nominal_measurement_covariance,
    )
    bias_disposition = filter_.ingest(biased).disposition.value

    dropout = PlanarNavigationFilter(foundation)
    dropout.ingest(_exact_packet(dropout, 0, 0.0, foundation.initial_mean_array))
    for step in range(1, 5):
        dropout.advance(np.zeros(2), float(step))
    dropout_snapshot = dropout.snapshot()
    return {
        "passed": bool(
            bias_disposition == "innovation_rejected"
            and dropout_snapshot.health.value == "degraded"
            and dropout_snapshot.prediction_only_age_s == 4.0
        ),
        "navigation_bias": list(bias),
        "bias_disposition": bias_disposition,
        "dropout_health_after_four_seconds": dropout_snapshot.health.value,
        "dropout_prediction_only_age_s": dropout_snapshot.prediction_only_age_s,
    }


def _actuation_and_disturbance_sanity(
    pilot: PilotConfig,
    foundation: Experiment004Config,
) -> dict[str, Any]:
    controller = DeterministicHoldController(foundation)
    filter_ = PlanarNavigationFilter(foundation)
    filter_.ingest(_exact_packet(filter_, 0, 0.0, foundation.initial_mean_array))
    command = controller.decide(observation_from_snapshot(filter_.snapshot())).acceleration_mps2
    state = foundation.initial_mean_array
    full = HCWSegment(
        state,
        command,
        foundation.mean_motion_rad_s,
        1.0,
        maximum_duration_s=foundation.event_interval_max_s,
    ).state_at(1.0)
    degraded = HCWSegment(
        state,
        pilot.actuation_effectiveness * command,
        foundation.mean_motion_rad_s,
        1.0,
        maximum_duration_s=foundation.event_interval_max_s,
    ).state_at(1.0)
    disturbed = HCWSegment(
        state,
        command + np.asarray(pilot.disturbance_bias_mps2),
        foundation.mean_motion_rad_s,
        1.0,
        maximum_duration_s=foundation.event_interval_max_s,
    ).state_at(1.0)
    degraded_delta = float(np.linalg.norm(full - degraded))
    disturbance_delta = float(np.linalg.norm(full - disturbed))
    return {
        "passed": bool(degraded_delta > 0.0 and disturbance_delta > 0.0),
        "reference_command_mps2": command.tolist(),
        "actuation_effectiveness": pilot.actuation_effectiveness,
        "degraded_state_delta_norm": degraded_delta,
        "disturbance_bias_mps2": list(pilot.disturbance_bias_mps2),
        "disturbed_state_delta_norm": disturbance_delta,
    }


def run_calibration(
    pilot: PilotConfig,
    foundation: Experiment004Config,
    cases: tuple[PilotCase, ...],
) -> dict[str, Any]:
    case_map = {case.id: case for case in cases}
    nominal = [
        _nominal_mechanics(
            pilot,
            foundation,
            case_map["P00_nominal_feasibility"],
            replicate,
        )
        for replicate in range(pilot.pilot_roots_per_case)
    ]
    nominal_replay = _nominal_mechanics(
        pilot,
        foundation,
        case_map["P00_nominal_feasibility"],
        0,
    )
    forced = {
        case_id: [
            _forced_event_mechanics(pilot, foundation, case_map[case_id], replicate)
            for replicate in range(pilot.pilot_roots_per_case)
        ]
        for case_id in (
            "P01_forced_collision",
            "P02_forced_keep_out_only",
            "P03_forced_corridor_departure",
        )
    }
    forced_pass = bool(
        all(row["collision"] and row["keep_out_entry"] for row in forced["P01_forced_collision"])
        and all(
            not row["collision"] and row["keep_out_entry"]
            for row in forced["P02_forced_keep_out_only"]
        )
        and all(
            not row["collision"]
            and not row["keep_out_entry"]
            and row["corridor_departure"]
            for row in forced["P03_forced_corridor_departure"]
        )
    )
    nominal_pass = all(
        row["initial_disposition"] == "accepted"
        and row["hold_acquired"]
        and not row["collision"]
        and not row["keep_out_entry"]
        and not row["corridor_departure"]
        and row["minimum_covariance_eigenvalue"] >= -1e-12
        and row["maximum_covariance_trace"] < foundation.covariance_trace_limit
        for row in nominal
    )
    replay_pass = nominal[0]["digest"] == nominal_replay["digest"]
    tolerance = _event_tolerance_check(foundation, cases)
    faults = _fault_activation(pilot, foundation, cases)
    filter_sanity = _filter_fault_sanity(foundation, pilot.navigation_bias)
    actuation = _actuation_and_disturbance_sanity(pilot, foundation)
    mechanics_pass = bool(
        nominal_pass
        and forced_pass
        and replay_pass
        and tolerance["passed"]
        and faults["passed"]
        and filter_sanity["passed"]
        and actuation["passed"]
    )
    candidates = [
        {
            "roots_per_case": 2,
            "mechanics_available": mechanics_pass,
            "configuration_order_appearances_per_position": 1,
            "passes": False,
            "reason": "fails frozen minimum of two appearances per order position",
        },
        {
            "roots_per_case": 4,
            "mechanics_available": mechanics_pass,
            "configuration_order_appearances_per_position": 2,
            "passes": mechanics_pass,
            "reason": "smallest count satisfying mechanics and balanced repeated order coverage",
        },
    ]
    selected = 4 if mechanics_pass else None
    result = {
        "schema_version": pilot.schema_version,
        "phase": "prospective_partition_41_mechanics_calibration",
        "status": "CALIBRATION_PASS" if mechanics_pass else "CALIBRATION_FAIL",
        "passed": mechanics_pass,
        "partition_code": pilot.calibration_partition_code,
        "permitted_information_used": [
            "bounded initial-state reachability",
            "exact forced-event reachability under bounded nuisance draws",
            "boundary-tolerance classification stability",
            "navigation fault activation and packet disposition",
            "prediction-only health transition",
            "actuation-effectiveness and disturbance path activation",
            "covariance finiteness and positive-semidefinite tolerance",
            "deterministic mechanics replay identity",
            "balanced within-block order coverage",
        ],
        "prohibited_information_used": [],
        "architecture_configuration_difference_computed": False,
        "hazard_discordance_computed": False,
        "scientific_hypothesis_selected": False,
        "controller_or_policy_selected_or_fitted": False,
        "pilot_outcomes_generated": False,
        "confirmatory_information_generated": False,
        "nominal_feasibility": {"passed": nominal_pass, "roots": nominal},
        "forced_event_reachability": {"passed": forced_pass, "cases": forced},
        "event_tolerance": tolerance,
        "fault_activation": faults,
        "filter_fault_sanity": filter_sanity,
        "actuation_and_disturbance_sanity": actuation,
        "deterministic_replay": {
            "passed": replay_pass,
            "root_seed_id": nominal[0]["root_seed_id"],
            "first_digest": nominal[0]["digest"],
            "replay_digest": nominal_replay["digest"],
        },
        "sample_count_selection": {
            "rule": (
                "select the first candidate in [2,4,6,8] that passes all partition-41 "
                "mechanics and places each diagnostic configuration in each order position "
                "at least twice; stop at the first passing candidate"
            ),
            "candidate_evaluations": candidates,
            "selected_roots_per_case": selected,
            "selected_blocks": None if selected is None else selected * len(cases),
            "selected_episodes": (
                None if selected is None else selected * len(cases) * len(pilot.configuration_ids)
            ),
            "confirmatory_power_interpretation": False,
        },
    }
    return result


def calibrate(root: str | Path = ".") -> dict[str, Any]:
    project_root = Path(root)
    path = project_root / CALIBRATION_PATH
    if path.exists():
        raise RuntimeError("refusing to overwrite partition-41 calibration evidence")
    for forbidden in (
        project_root / "experiments/004-pilot/seeds",
        project_root / "results/experiment-004-pilot",
        project_root / "experiments/004-confirmatory",
        project_root / "results/experiment-004-confirmatory",
    ):
        if forbidden.exists():
            raise RuntimeError("calibration requires pilot and confirmatory outputs to be absent")
    pilot = load_pilot_config(project_root / "experiments/004-pilot/config.json")
    foundation = load_config(project_root / "experiments/004/config.json")
    cases = load_case_matrix(project_root / "experiments/004-pilot/case-matrix.json")
    result = run_calibration(pilot, foundation, cases)
    unsigned = dict(result)
    unsigned["calibration_id"] = sha256_bytes(canonical_json(result))
    path.write_text(
        json.dumps(unsigned, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return unsigned


def verify_calibration(root: str | Path = ".", *, recompute: bool = True) -> dict[str, Any]:
    project_root = Path(root)
    path = project_root / CALIBRATION_PATH
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
        calibration_id = evidence.pop("calibration_id")
        self_hash_ok = sha256_bytes(canonical_json(evidence)) == calibration_id
    except (OSError, KeyError, json.JSONDecodeError):
        return {"passed": False, "errors_preview": ["calibration_evidence_load"]}
    errors = [] if self_hash_ok else ["calibration_self_hash"]
    if recompute:
        pilot = load_pilot_config(project_root / "experiments/004-pilot/config.json")
        foundation = load_config(project_root / "experiments/004/config.json")
        cases = load_case_matrix(project_root / "experiments/004-pilot/case-matrix.json")
        observed = run_calibration(pilot, foundation, cases)
        if observed != evidence:
            errors.append("calibration_recompute_mismatch")
    if not evidence.get("passed") or evidence.get("partition_code") != 41:
        errors.append("calibration_not_passed_or_wrong_partition")
    return {
        "passed": not errors,
        "errors_preview": errors[:20],
        "calibration_id": calibration_id,
        "evidence_sha256": sha256_bytes(path.read_bytes()),
        "selected_roots_per_case": evidence.get("sample_count_selection", {}).get(
            "selected_roots_per_case"
        ),
        "pilot_outcomes_generated": evidence.get("pilot_outcomes_generated"),
        "architecture_configuration_difference_computed": evidence.get(
            "architecture_configuration_difference_computed"
        ),
    }
