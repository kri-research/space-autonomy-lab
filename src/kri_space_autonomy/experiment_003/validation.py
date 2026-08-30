from __future__ import annotations

import hashlib
import inspect
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

from .config import Experiment003Config
from .estimator import FilterHealth, NavigationFilter, NavigationPacket, PacketDisposition
from .evaluation import offline_nees
from .model import (
    observability_diagnostics,
    piecewise_disturbance_covariance,
    propagate_mean,
)


def _packet(
    filter_: NavigationFilter,
    sequence: int,
    measured: float,
    received: float,
    state: np.ndarray,
) -> NavigationPacket:
    return NavigationPacket(
        sequence,
        measured,
        received,
        float(state[0]),
        float(state[1]),
        filter_.nominal_measurement_covariance,
    )


def _reference_error(study: Experiment003Config, production) -> dict[str, Any]:
    fixtures = (
        (np.array([100.0, -0.15, 0.0]), -0.04, 0.003),
        (np.array([6.5, -0.02, 0.03]), 0.05, -0.006),
        (np.array([20.0, 0.10, -0.05]), 0.0, 0.0),
    )
    errors: list[float] = []
    for initial, command, disturbance in fixtures:
        exact = propagate_mean(
            initial,
            command,
            production.command_period_s,
            production.actuator_time_constant_s,
            disturbance,
        )

        def rhs(_time, state, _command=command, _disturbance=disturbance):
            return np.array(
                [
                    state[1],
                    state[2] + _disturbance,
                    (_command - state[2]) / production.actuator_time_constant_s,
                ]
            )

        reference = solve_ivp(
            rhs,
            (0.0, production.command_period_s),
            initial,
            method="DOP853",
            rtol=1e-13,
            atol=1e-14,
        ).y[:, -1]
        errors.append(float(np.max(np.abs(exact - reference))))
    maximum = max(errors)
    return {
        "passed": maximum <= 2e-12,
        "fixtures": len(fixtures),
        "maximum_absolute_state_error": maximum,
        "acceptance_limit": 2e-12,
        "reference": "independent adaptive DOP853 integration",
    }


def _replay_digest(study: Experiment003Config, production) -> tuple[str, dict[str, float]]:
    filter_ = NavigationFilter(study, production)
    digest = hashlib.sha256()
    first = filter_.snapshot().mean
    filter_.ingest(_packet(filter_, 0, 0.0, 0.0, first))
    minimum_eigenvalue = float("inf")
    maximum_asymmetry = 0.0
    maximum_trace = 0.0
    for step in range(601):
        if step > 0:
            prior = filter_.advance(0.0, float(step))
            disposition = filter_.ingest(
                _packet(filter_, step, float(step), float(step), prior.mean)
            ).disposition
            if disposition is not PacketDisposition.ACCEPTED:
                raise RuntimeError("nominal numerical replay rejected an exact measurement")
        snapshot = filter_.snapshot()
        covariance = snapshot.covariance
        minimum_eigenvalue = min(
            minimum_eigenvalue,
            float(np.linalg.eigvalsh(covariance)[0]),
        )
        maximum_asymmetry = max(
            maximum_asymmetry,
            float(np.max(np.abs(covariance - covariance.T))),
        )
        maximum_trace = max(maximum_trace, float(np.trace(covariance)))
        digest.update(np.asarray(snapshot.mean, dtype="<f8").tobytes())
        digest.update(np.asarray(snapshot.covariance, dtype="<f8").tobytes())
        digest.update(snapshot.health.value.encode())
    return digest.hexdigest(), {
        "minimum_covariance_eigenvalue": minimum_eigenvalue,
        "maximum_covariance_asymmetry": maximum_asymmetry,
        "maximum_covariance_trace": maximum_trace,
    }


def _fixed_lag_equivalence(study: Experiment003Config, production) -> dict[str, Any]:
    command = -0.02
    state0 = np.array([100.0, -0.15, 0.0])
    state1 = propagate_mean(
        state0,
        command,
        production.command_period_s,
        production.actuator_time_constant_s,
    )
    direct = NavigationFilter(study, production)
    direct.ingest(_packet(direct, 0, 0.0, 0.0, state0))
    direct.advance(command, 1.0)
    direct.ingest(_packet(direct, 1, 1.0, 1.0, state1))
    delayed = NavigationFilter(study, production)
    delayed.advance(command, 1.0)
    delayed.ingest(_packet(delayed, 0, 0.0, 1.0, state0))
    delayed.ingest(_packet(delayed, 1, 1.0, 1.0, state1))
    mean_error = float(np.max(np.abs(direct.snapshot().mean - delayed.snapshot().mean)))
    covariance_error = float(
        np.max(np.abs(direct.snapshot().covariance - delayed.snapshot().covariance))
    )
    return {
        "passed": mean_error <= 1e-13 and covariance_error <= 1e-13,
        "maximum_mean_difference": mean_error,
        "maximum_covariance_difference": covariance_error,
        "acceptance_limit": 1e-13,
    }


def _diagnostic_equations(study: Experiment003Config, production) -> dict[str, Any]:
    filter_ = NavigationFilter(study, production)
    packet = _packet(filter_, 0, 0.0, 0.0, np.array([101.0, -0.14, 0.0]))
    prior = filter_.snapshot()
    innovation = packet.measurement - filter_.observation @ prior.mean
    innovation_covariance = (
        filter_.observation @ prior.covariance @ filter_.observation.T
        + packet.reported_covariance
    )
    expected_nis = float(innovation @ np.linalg.solve(innovation_covariance, innovation))
    observed = filter_.ingest(packet)
    truth = np.array([100.5, -0.145, 0.001])
    snapshot = filter_.snapshot()
    expected_nees = float(
        (truth - snapshot.mean)
        @ np.linalg.solve(snapshot.covariance, truth - snapshot.mean)
    )
    observed_nees = offline_nees(truth, snapshot)
    nis_error = abs(float(observed.nis) - expected_nis) if observed.nis is not None else np.inf
    nees_error = abs(float(observed_nees) - expected_nees) if observed_nees is not None else np.inf
    return {
        "passed": nis_error <= 1e-14 and nees_error <= 1e-12,
        "nis_absolute_error": nis_error,
        "nees_absolute_error": nees_error,
        "truth_use": "NEES computed only by the offline evaluator helper",
    }


def run_numerical_checks(study: Experiment003Config, production) -> dict[str, Any]:
    reference = _reference_error(study, production)
    observability = observability_diagnostics(
        production.command_period_s,
        production.actuator_time_constant_s,
    )
    process_covariance = piecewise_disturbance_covariance(
        production.command_period_s,
        production.exogenous_period_s,
        production.process_accel_sigma_mps2,
        study.actuator_model_process_sigma_mps2,
    )
    replay_one, covariance = _replay_digest(study, production)
    replay_two, _ = _replay_digest(study, production)
    fixed_lag = _fixed_lag_equivalence(study, production)
    diagnostics = _diagnostic_equations(study, production)
    divergence_filter = NavigationFilter(study, production)
    divergence = divergence_filter.advance(1e9, 1.0)
    divergence_passed = divergence.health is FilterHealth.DIVERGED

    import kri_space_autonomy.experiment_003.estimator as estimator_module
    import kri_space_autonomy.experiment_003.interfaces as interfaces_module

    online_source = inspect.getsource(estimator_module) + inspect.getsource(interfaces_module)
    prohibited = [
        token
        for token in ("TruthState", "IndependentEvaluator", "fault_onset_s", "fault_subtype")
        if token in online_source
    ]
    checks = {
        "exact_transition_reference": reference,
        "observability": {
            "passed": bool(
                observability.rank == 3
                and observability.smallest_singular_value > 1e-3
                and observability.condition_number < 1e5
            ),
            "rank": observability.rank,
            "smallest_scaled_singular_value": observability.smallest_singular_value,
            "scaled_condition_number": observability.condition_number,
            "acceptance": "rank 3; smallest singular value >1e-3; condition number <1e5",
        },
        "process_covariance": {
            "passed": bool(
                np.max(np.abs(process_covariance - process_covariance.T)) <= 1e-20
                and np.linalg.eigvalsh(process_covariance)[0] >= -1e-20
            ),
            "minimum_eigenvalue": float(np.linalg.eigvalsh(process_covariance)[0]),
        },
        "covariance_long_replay": {
            "passed": bool(
                covariance["minimum_covariance_eigenvalue"] > 1e-10
                and covariance["maximum_covariance_asymmetry"] <= 1e-15
                and covariance["maximum_covariance_trace"]
                < study.covariance_trace_limit
            ),
            **covariance,
            "steps": 601,
            "minimum_eigenvalue_acceptance": ">1e-10",
        },
        "deterministic_replay": {
            "passed": replay_one == replay_two,
            "replay_sha256": replay_one,
            "second_replay_sha256": replay_two,
        },
        "fixed_lag_update": fixed_lag,
        "diagnostic_equations": diagnostics,
        "divergence_handling": {
            "passed": divergence_passed,
            "observed_health": divergence.health.value,
            "observed_reason": divergence.reason.value,
        },
        "online_truth_interface_scan": {
            "passed": not prohibited,
            "prohibited_tokens_found": prohibited,
        },
    }
    return {
        "passed": all(bool(item["passed"]) for item in checks.values()),
        "checks": checks,
        "outcome_data_used": False,
        "outcome_seed_partition_used": False,
    }
