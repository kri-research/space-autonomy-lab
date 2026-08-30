from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .config import Experiment003Config
from .estimator import FilterHealth, NavigationSnapshot

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class OfflineEstimatorSample:
    time_s: float
    range_error_m: float
    velocity_error_mps: float
    acceleration_error_mps2: float
    nees: float | None
    runtime_health: FilterHealth


def offline_nees(true_state: FloatArray, estimate: NavigationSnapshot) -> float | None:
    """Truth-based consistency diagnostic for the offline evaluator only."""

    truth = np.asarray(true_state, dtype=np.float64)
    if truth.shape != (3,) or not np.all(np.isfinite(truth)):
        raise ValueError("offline truth state must be a finite three-vector")
    if estimate.health is FilterHealth.DIVERGED:
        return None
    error = truth - estimate.mean
    try:
        value = float(error @ np.linalg.solve(estimate.covariance, error))
    except np.linalg.LinAlgError:
        return None
    return value if np.isfinite(value) else None


def offline_sample(true_state: FloatArray, estimate: NavigationSnapshot) -> OfflineEstimatorSample:
    truth = np.asarray(true_state, dtype=np.float64)
    if truth.shape != (3,) or not np.all(np.isfinite(truth)):
        raise ValueError("offline truth state must be a finite three-vector")
    error = estimate.mean - truth
    return OfflineEstimatorSample(
        estimate.time_s,
        float(error[0]),
        float(error[1]),
        float(error[2]),
        offline_nees(truth, estimate),
        estimate.health,
    )


def classify_estimator_recovery(
    samples: list[OfflineEstimatorSample],
    *,
    fault_onset_s: float | None,
    fault_end_s: float | None,
    failed: bool,
    sustained_success: bool,
    protected_arm: bool,
    fallback_latched: bool,
    config: Experiment003Config,
) -> dict[str, Any]:
    """Apply the frozen Experiment 003 estimator-recovery precedence."""

    if fault_onset_s is None:
        return {
            "recovery_state": "NOT_APPLICABLE",
            "estimator_first_affected_s": None,
            "qualifying_recovery_start_s": None,
            "recovery_favorable_180": None,
            "restricted_time_unrecovered_s_180": None,
        }

    def inside(sample: OfflineEstimatorSample) -> bool:
        return (
            sample.runtime_health is FilterHealth.VALID
            and abs(sample.range_error_m) <= config.recovery_max_abs_range_error_m
            and abs(sample.velocity_error_mps)
            <= config.recovery_max_abs_velocity_error_mps
            and sample.nees is not None
            and sample.nees <= config.offline_nees_recovery_threshold
        )

    post_fault = [sample for sample in samples if sample.time_s >= fault_onset_s]
    first_affected = next((sample.time_s for sample in post_fault if not inside(sample)), None)
    qualifying: float | None = None
    if failed:
        state = "FAILED"
    elif first_affected is None:
        state = "UNAFFECTED"
    else:
        restoration = fault_end_s if fault_end_s is not None else float("inf")
        dwell_start: float | None = None
        for sample in post_fault:
            if sample.time_s < max(first_affected, restoration):
                continue
            if inside(sample):
                if dwell_start is None:
                    dwell_start = sample.time_s
                if sample.time_s - dwell_start >= config.recovery_dwell_s - 1e-12:
                    qualifying = dwell_start
                    break
            else:
                dwell_start = None
        timely = (
            qualifying is not None
            and qualifying - first_affected <= config.recovery_deadline_s
            and sustained_success
        )
        if timely:
            state = "RECOVERED"
        elif protected_arm and fallback_latched and sustained_success:
            state = "GRACEFUL_DEGRADED"
        else:
            state = "NOT_RECOVERED"
    favorable = state in {"UNAFFECTED", "RECOVERED"}
    if state == "UNAFFECTED":
        restricted = 0.0
    elif state == "RECOVERED" and first_affected is not None and qualifying is not None:
        restricted = min(config.recovery_deadline_s, qualifying - first_affected)
    else:
        restricted = config.recovery_deadline_s
    return {
        "recovery_state": state,
        "estimator_first_affected_s": first_affected,
        "qualifying_recovery_start_s": qualifying,
        "recovery_favorable_180": favorable,
        "restricted_time_unrecovered_s_180": restricted,
    }
